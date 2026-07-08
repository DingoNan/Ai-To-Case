"""LlamaIndex 向量库模块"""
from .config import VECTOR_DB_PATH, EMBEDDING_MODEL
from .document import parse_pdf_to_text, parse_word_to_text


def init_vector_db(file_bytes: bytes, filename: str):
    """
    初始化向量数据库，支持 txt, md, pdf, docx 格式

    Args:
        file_bytes: 文件字节内容
        filename: 文件名

    Returns:
        tuple: (success, persist_dir/error_message, message)
    """
    try:
        from llama_index.core import VectorStoreIndex, Document, Settings
        from llama_index.core.node_parser import SentenceSplitter
        from llama_index.embeddings.huggingface import HuggingFaceEmbedding

        # 根据文件类型解析内容
        file_ext = filename.lower().split('.')[-1]

        if file_ext in ('txt', 'md'):
            text = file_bytes.decode('utf-8')
        elif file_ext == 'pdf':
            text = parse_pdf_to_text(file_bytes)
        elif file_ext in ('docx', 'doc'):
            text = parse_word_to_text(file_bytes)
        else:
            return False, None, f"不支持的文件格式: {file_ext}"

        if not text.strip():
            return False, None, "文档内容为空"

        # 设置全局模型配置
        Settings.embed_model = HuggingFaceEmbedding(model_name=EMBEDDING_MODEL)
        Settings.llm = None  # 明确禁用LLM

        # 创建文档
        documents = [Document(text=text, id=filename)]

        # 使用 SentenceSplitter 进行分片（更通用）
        text_splitter = SentenceSplitter(
            chunk_size=512,
            chunk_overlap=50
        )

        # 对文档进行分片
        nodes = text_splitter.get_nodes_from_documents(documents)

        # 创建向量索引
        index = VectorStoreIndex(nodes)

        # 持久化存储
        persist_dir = f"{VECTOR_DB_PATH}/{filename}"
        index.storage_context.persist(persist_dir=persist_dir)

        return True, persist_dir, f"向量数据库初始化完成！文件 {filename} 已成功存储，共 {len(nodes)} 个文本块。"

    except Exception as e:
        return False, None, f"向量数据库初始化失败: {str(e)}"


def query_vector_db_and_call_api(persist_dir, prompt):
    from llama_index.core import StorageContext, load_index_from_storage, Settings
    from llama_index.embeddings.huggingface import HuggingFaceEmbedding

    Settings.embed_model = HuggingFaceEmbedding(model_name=EMBEDDING_MODEL)
    Settings.llm = None

    storage_context = StorageContext.from_defaults(persist_dir=persist_dir)
    index = load_index_from_storage(storage_context)

    query_engine = index.as_query_engine(
        similarity_top_k=3,
        llm=None
    )

    retrieved_docs = query_engine.query(prompt)
    context = retrieved_docs.response
    return context
