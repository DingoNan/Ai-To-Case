"""Chroma 向量库模块

包含 DashScope Embedding、文本分块、Chroma CRUD 等功能。
"""
import os
import re
from typing import Dict, Any, List
from .config import CHROMA_DB_PATH, DASHSCOPE_EMBEDDING_MODEL
from .helpers import get_current_datetime
from .document import parse_markdown_with_images, parse_pdf_to_text, parse_word_to_text


def get_dashscope_embedding(texts: List[str]) -> List[List[float]]:
    """
    使用通义千问 text-embedding-v3 模型获取文本向量

    Args:
        texts: 文本列表

    Returns:
        List[List[float]]: 向量列表
    """
    import dashscope
    from dashscope import TextEmbedding

    # 从环境变量获取API Key
    api_key = os.getenv("ALIYUN_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise Exception("缺少 ALIYUN_API_KEY 或 DASHSCOPE_API_KEY 环境变量")

    dashscope.api_key = api_key

    embeddings = []

    # 逐条处理，避免批量大小限制问题
    for i, text in enumerate(texts):
        print(f"正在向量化第 {i+1}/{len(texts)} 个文本块...")
        response = TextEmbedding.call(
            model=DASHSCOPE_EMBEDDING_MODEL,
            input=text
        )

        if response.status_code != 200:
            raise Exception(f"Embedding API调用失败: {response.message}")

        # 单条返回的结构
        embedding = response.output['embeddings'][0]['embedding']
        embeddings.append(embedding)

    return embeddings


def split_text_into_chunks(text: str, chunk_size: int = 500, chunk_overlap: int = 50) -> List[str]:
    """
    将文本切割成块

    Args:
        text: 原始文本
        chunk_size: 每块的最大字符数
        chunk_overlap: 块之间的重叠字符数

    Returns:
        List[str]: 文本块列表
    """
    if not text or not text.strip():
        return []

    # 按段落分割
    paragraphs = re.split(r'\n\s*\n', text)

    chunks = []
    current_chunk = ""

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        # 如果当前段落本身就超过chunk_size，需要进一步切割
        if len(para) > chunk_size:
            # 先保存当前chunk
            if current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = ""

            # 按句子切割长段落
            sentences = re.split(r'([。！？；\n])', para)
            temp_chunk = ""

            for i in range(0, len(sentences), 2):
                sentence = sentences[i]
                if i + 1 < len(sentences):
                    sentence += sentences[i + 1]  # 加上标点

                if len(temp_chunk) + len(sentence) <= chunk_size:
                    temp_chunk += sentence
                else:
                    if temp_chunk:
                        chunks.append(temp_chunk.strip())
                    # 保留重叠部分
                    if chunk_overlap > 0 and len(temp_chunk) > chunk_overlap:
                        temp_chunk = temp_chunk[-chunk_overlap:] + sentence
                    else:
                        temp_chunk = sentence

            if temp_chunk:
                current_chunk = temp_chunk
        else:
            # 正常段落处理
            if len(current_chunk) + len(para) + 1 <= chunk_size:
                current_chunk += "\n" + para if current_chunk else para
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                # 保留重叠部分
                if chunk_overlap > 0 and len(current_chunk) > chunk_overlap:
                    current_chunk = current_chunk[-chunk_overlap:] + "\n" + para
                else:
                    current_chunk = para

    # 添加最后一个chunk
    if current_chunk:
        chunks.append(current_chunk.strip())

    return chunks


async def init_chroma_vector_db(file_bytes: bytes, filename: str, base_path: str = None) -> tuple:
    """
    使用 Chroma + 通义千问Embedding 初始化向量数据库
    支持 txt, md, pdf, docx 格式
    自动使用阿里云 OCR 识别文档中的图片
    MD 文件中的图片引用会被解析并还原到原位置

    Args:
        file_bytes: 文件字节内容
        filename: 文件名
        base_path: 文件所在的基础路径（用于解析 MD 文件中的相对路径图片）

    Returns:
        tuple: (success, collection_name/error_message, message)
    """
    try:
        import chromadb

        # 确保目录存在
        os.makedirs(CHROMA_DB_PATH, exist_ok=True)

        # 根据文件类型解析内容
        file_ext = filename.lower().split('.')[-1]

        if file_ext == 'txt':
            text = file_bytes.decode('utf-8')
        elif file_ext == 'md':
            text = file_bytes.decode('utf-8')
            text = await parse_markdown_with_images(text, base_path=base_path, vision_provider="aliyun")
            print(f"[MD向量化] 文件 {filename} 图片解析完成")
        elif file_ext == 'pdf':
            text = await parse_pdf_to_text(file_bytes, enable_ocr=True)
        elif file_ext in ('docx', 'doc'):
            text = await parse_word_to_text(file_bytes, enable_ocr=True)
        else:
            return False, None, f"不支持的文件格式: {file_ext}"

        if not text.strip():
            return False, None, "文档内容为空"

        # 切割文本
        chunks = split_text_into_chunks(text, chunk_size=500, chunk_overlap=50)

        if not chunks:
            return False, None, "文档切割后无有效内容"

        print(f"文档 {filename} 切割成 {len(chunks)} 个文本块")

        # 获取文本向量
        embeddings = get_dashscope_embedding(chunks)

        # 创建Chroma客户端 (持久化存储)
        client = chromadb.PersistentClient(path=CHROMA_DB_PATH)

        # 生成唯一的collection名称 (基于文件名和时间戳)
        timestamp = get_current_datetime()
        safe_filename = re.sub(r'[^a-zA-Z0-9]', '_', filename.rsplit('.', 1)[0])[:30]
        collection_name = f"doc_{safe_filename}_{timestamp}"

        # 创建或获取collection
        collection = client.get_or_create_collection(
            name=collection_name,
            metadata={
                "filename": filename,
                "created_at": timestamp,
                "original_document": text
            }
        )

        # 添加文档到collection
        ids = [f"chunk_{i}" for i in range(len(chunks))]
        metadatas = [{"chunk_index": i, "filename": filename} for i in range(len(chunks))]

        collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=chunks,
            metadatas=metadatas
        )

        return True, collection_name, f"向量数据库初始化完成！文件 {filename} 已成功存储到 Chroma，共 {len(chunks)} 个文本块。"

    except Exception as e:
        import traceback
        traceback.print_exc()
        return False, None, f"Chroma向量数据库初始化失败: {str(e)}"


def query_chroma_vector_db(collection_name: str, query_text: str, top_k: int = 5, recall_all: bool = False) -> Dict[str, Any]:
    """
    从 Chroma 向量数据库中检索相关内容

    Args:
        collection_name: collection名称
        query_text: 查询文本（全量召回时可以为空）
        top_k: 返回的最相似结果数量
        recall_all: 是否全量召回（返回集合中所有文档）

    Returns:
        Dict: 包含检索结果的字典
    """
    try:
        import chromadb

        client = chromadb.PersistentClient(path=CHROMA_DB_PATH)

        try:
            collection = client.get_collection(name=collection_name)
        except Exception:
            return {"success": False, "error": f"未找到collection: {collection_name}"}

        # 全量召回
        if recall_all:
            all_data = collection.get(include=["documents", "metadatas"])
            documents = all_data.get("documents", [])
            metadatas = all_data.get("metadatas", [])

            if not documents:
                return {"success": False, "error": "集合中没有文档内容"}

            doc_with_meta = list(zip(documents, metadatas))
            doc_with_meta.sort(key=lambda x: x[1].get("chunk_index", 0) if x[1] else 0)

            sorted_docs = [doc for doc, _ in doc_with_meta]
            full_content = "\n\n".join(sorted_docs)

            return {
                "success": True,
                "context": full_content,
                "chunks": [{"rank": i+1, "content": doc, "distance": None, "metadata": meta}
                          for i, (doc, meta) in enumerate(doc_with_meta)],
                "total_chunks": len(documents),
                "is_original": True
            }
        else:
            query_embedding = get_dashscope_embedding([query_text])[0]
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                include=["documents", "metadatas", "distances"]
            )

        documents = results.get('documents', [[]])[0]
        distances = results.get('distances', [[]])[0]
        metadatas = results.get('metadatas', [[]])[0]

        retrieved_chunks = []
        for i, (doc, dist, meta) in enumerate(zip(documents, distances, metadatas)):
            retrieved_chunks.append({
                "rank": i + 1,
                "content": doc,
                "distance": dist,
                "metadata": meta
            })

        context = "\n\n---\n\n".join([chunk["content"] for chunk in retrieved_chunks])

        return {
            "success": True,
            "context": context,
            "chunks": retrieved_chunks,
            "total_chunks": len(retrieved_chunks)
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"success": False, "error": f"Chroma向量检索失败: {str(e)}"}


def list_chroma_collections() -> List[Dict[str, Any]]:
    """
    列出所有可用的Chroma collections

    Returns:
        List[Dict]: collection列表
    """
    try:
        import chromadb

        client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
        collections = client.list_collections()

        result = []
        for col in collections:
            result.append({
                "name": col.name,
                "metadata": col.metadata,
                "count": col.count()
            })

        return result

    except Exception as e:
        print(f"列出collections失败: {str(e)}")
        return []


def check_document_exists(filename: str) -> tuple:
    """
    检查文档是否已经向量化存储

    Args:
        filename: 文件名

    Returns:
        tuple: (exists: bool, collection_name: str or None)
    """
    try:
        collections = list_chroma_collections()
        for col in collections:
            if col.get("metadata", {}).get("filename") == filename:
                return True, col.get("name")
        return False, None
    except Exception:
        return False, None


def delete_chroma_collection(collection_name: str) -> bool:
    """
    删除指定的Chroma collection

    Args:
        collection_name: collection名称

    Returns:
        bool: 是否删除成功
    """
    try:
        import chromadb

        client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
        client.delete_collection(name=collection_name)
        return True

    except Exception as e:
        print(f"删除collection失败: {str(e)}")
        return False
