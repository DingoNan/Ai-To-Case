# -*- coding: utf-8 -*-
"""
FastAPI主程序 - AI测试用例生成系统
"""
import os
import json
import asyncio
import tempfile
from io import BytesIO
from datetime import datetime
from typing import Optional, List

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from llms import call_llm_api, call_llm_api_stream
from utils import (
    generate_test_cases_stream, build_system_message,
    get_current_datetime, init_vector_db, ocr_image_async,
    query_vector_db_and_call_api, parse_axure_zip_to_text, parse_axure_html_to_text,
    format_axure_text_to_markdown, format_incremental_text_to_markdown,
    refine_requirements_markdown, refine_requirements_markdown_async,
    # 新增 Chroma 向量化功能
    init_chroma_vector_db, query_chroma_vector_db, list_chroma_collections,
    delete_chroma_collection, check_document_exists,
    # 新增 Axure 在线链接获取功能
    fetch_axure_from_url, fetch_axure_from_url_async,
    # 新增 递归解析功能
    fetch_axure_from_url_async_recursive,
    # 新增知识库管理功能
    create_knowledge_base, list_knowledge_bases, delete_knowledge_base, recall_from_knowledge_base,
    # 基础数据类型
    PageData, MetadataFilter
)
# 增强版知识库管理功能
from utils_enhanced_kb import (
    create_enhanced_knowledge_base,
    list_enhanced_knowledge_bases,
    delete_enhanced_knowledge_base
)
# 智能召回功能（从 utils 导入，因为使用了 MetadataFilter 等基础类型）
from utils import smart_recall_from_knowledge_base
from md_to_xmind_utils import md_to_xmind, test_cases_to_xmind_text, test_cases_to_xmind
# 新增 基于Sitemap的知识库管理功能
from utils_sitemap_kb import (
    list_sitemap_knowledge_bases,
    delete_sitemap_knowledge_base,
    smart_recall_from_knowledge_base as sitemap_smart_recall
)
# 新增 Token 统计功能
from token_stats import token_stats_manager

# 创建FastAPI应用
app = FastAPI(
    title="AI测试用例生成系统",
    description="基于AI的测试用例自动生成工具",
    version="2.0.0"
)

# 添加 CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 静态文件和模板
app.mount("/static", StaticFiles(directory="static"), name="static")

# 初始化 Jinja2 模板引擎(禁用缓存避免 dict 哈希问题)
from jinja2 import ChoiceLoader, FileSystemLoader
from starlette.templating import Jinja2Templates

jinja_env = {
    "loader": ChoiceLoader([FileSystemLoader("templates")]),
    "auto_reload": True,
}
templates = Jinja2Templates(directory="templates")

# 读取提示词配置
with open('prompts.json', 'r', encoding='utf-8') as file:
    prompts = json.load(file)

prompt_query = prompts.get('prompt_field', '')
prompt_again = prompts.get('promptAgain', '')
prompt_default = prompts.get('prompt_default', '')

# 全局存储（生产环境应使用Redis等）
vector_db_store = {}
test_cases_store = {}


# ==================== 辅助函数 ====================

def get_client_ip(request: Request) -> str:
    """获取客户端真实 IP 地址"""
    # 优先从 X-Forwarded-For 获取（经过代理的情况）
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # 取第一个 IP（原始客户端 IP）
        return forwarded_for.split(",")[0].strip()
    
    # 从 X-Real-IP 获取
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    
    # 从连接地址获取
    if request.client:
        return request.client.host
    
    return "unknown"


# ==================== 数据模型 ====================

class GenerateRequest(BaseModel):
    requirement_text: str
    context_text: str = ""  # 上下文（全量内容，用于增量模式）
    test_module: str = "模块"
    menu1: str = ""
    menu2: str = ""
    test_case_count: int = 10
    prompt: str = ""
    provider: str = "azure"
    source_type: str = "manual-input"  # 来源类型：upload-doc, upload-axure, upload-image, manual-input, knowledge-base


class RefineRequest(BaseModel):
    content: str
    provider: str = "azure"


class VectorQueryRequest(BaseModel):
    persist_dir: str
    question: str
    provider: str = "azure"


class ChromaQueryRequest(BaseModel):
    """Chroma向量检索请求"""
    collection_name: str
    query_text: str
    top_k: int = 5
    use_ai_refine: bool = False  # 是否使用大模型整理结果
    provider: str = "azure"


class CreateKnowledgeBaseRequest(BaseModel):
    """创建知识库请求"""
    name: str
    axure_url: str
    vision_provider: str = "doubao"
    username: str = ""
    password: str = ""
    use_ai_refine: bool = False
    max_concurrent: int = 5


class RecallFromKnowledgeBaseRequest(BaseModel):
    """从知识库召回请求"""
    collection_name: str
    query_text: str
    top_k: int = 5


class GenerateTestCasesFromKBRequest(BaseModel):
    """从知识库生成测试用例请求"""
    collection_name: str
    requirement: str
    test_module: str = "模块"
    top_k: int = 5
    provider: str = "azure"


class CreateEnhancedKBRequest(BaseModel):
    """创建知识库请求"""
    name: str
    axure_url: str


class SmartRecallRequest(BaseModel):
    """智能召回请求"""
    collection_name: str
    query: str
    page_key: Optional[str] = None
    recall_strategy: str = "incremental_with_context"  # auto | incremental_with_context | page_level | module_level
    top_k: int = 5
    use_ai_structure: bool = False  # 是否使用AI结构化召回内容
    ai_provider: str = "deepseek"  # AI服务提供商


class GenerateTestCasesSmartRequest(BaseModel):
    """智能生成测试用例请求"""
    collection_name: str
    query: str
    test_module: str = "模块"
    page_key: Optional[str] = None
    recall_strategy: str = "auto"
    top_k: int = 5
    provider: str = "azure"
    use_ai_structure: bool = False  # 是否使用AI结构化召回内容


class CreateSitemapKBRequest(BaseModel):
    """创建基于Sitemap的知识库请求"""
    name: str
    axure_url: str
    username: str = ""
    password: str = ""
    use_ai_analysis: bool = True
    max_concurrent: int = 5


class SitemapSmartRecallRequest(BaseModel):
    """Sitemap知识库智能召回请求"""
    collection_name: str
    query: str
    page_key: Optional[str] = None
    recall_strategy: str = "auto"  # auto | incremental_with_context | page_level | module_level
    top_k: int = 5


class GenerateTestCasesFromSitemapRequest(BaseModel):
    """从Sitemap知识库智能生成测试用例请求"""
    collection_name: str
    query: str
    test_module: str = "模块"
    page_key: Optional[str] = None
    recall_strategy: str = "auto"
    top_k: int = 5
    provider: str = "azure"


class ExportRequest(BaseModel):
    test_cases: dict
    menu1: str = ""
    menu2: str = ""


# ==================== 页面路由 ====================

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """主页"""
    import aiofiles
    try:
        async with aiofiles.open("templates/index.html", mode='r', encoding='utf-8') as f:
            content = await f.read()
        return HTMLResponse(content=content)
    except Exception as e:
        return HTMLResponse(content=f"<h1>Error loading page</h1><p>{str(e)}</p>", status_code=500)


@app.get("/stats", response_class=HTMLResponse)
async def stats_page(request: Request):
    """Token 统计页面"""
    import aiofiles
    try:
        async with aiofiles.open("templates/stats.html", mode='r', encoding='utf-8') as f:
            content = await f.read()
        return HTMLResponse(content=content)
    except Exception as e:
        return HTMLResponse(content=f"<h1>Error loading page</h1><p>{str(e)}</p>", status_code=500)


# ==================== API路由 ====================

@app.get("/api/prompts")
async def get_prompts():
    """获取提示词模板"""
    return {
        "prompt_default": prompt_default,
        "prompt_query": prompt_query,
        "prompt_again": prompt_again
    }


class FileWrapper:
    """包装FastAPI UploadFile为类似Streamlit的文件对象"""
    def __init__(self, upload_file: UploadFile, content: bytes):
        self.name = upload_file.filename
        self._content = content
        self._pos = 0

    def read(self, size=-1):
        if size == -1:
            data = self._content[self._pos:]
            self._pos = len(self._content)
        else:
            data = self._content[self._pos:self._pos + size]
            self._pos += len(data)
        return data

    def seek(self, pos):
        self._pos = pos


@app.post("/api/upload/document")
async def upload_document(file: UploadFile = File(...)):
    """
    上传需求文档并向量化
    支持 txt, md, pdf, docx 格式
    """
    filename = file.filename.lower()
    if not filename.endswith(('.txt', '.md', '.pdf', '.docx', '.doc')):
        raise HTTPException(status_code=400, detail="仅支持 txt, md, pdf, docx 格式文件")

    try:
        # 读取文件内容
        file_bytes = await file.read()

        # 调用向量化函数
        success, persist_dir, message = init_vector_db(file_bytes, file.filename)
        if success:
            # 存储向量库路径
            session_id = get_current_datetime()
            vector_db_store[session_id] = persist_dir
            return {
                "success": True,
                "session_id": session_id,
                "persist_dir": persist_dir,
                "message": message
            }
        else:
            raise HTTPException(status_code=500, detail=message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文档处理失败: {str(e)}")


@app.post("/api/upload/axure")
async def upload_axure(
    file: UploadFile = File(...),
    use_md: bool = Form(True),
    use_ai_refine: bool = Form(False),
    provider: str = Form("azure")
):
    """
    上传Axure原型包
    支持 ZIP, HTML 格式
    """
    filename = file.filename.lower()
    if not filename.endswith(('.zip', '.html', '.htm')):
        raise HTTPException(status_code=400, detail="仅支持 zip, html, htm 格式文件")

    try:
        file_bytes = await file.read()

        # 解析Axure文件
        if filename.endswith('.zip'):
            axure_data = parse_axure_zip_to_text(file_bytes)
        else:
            axure_data = parse_axure_html_to_text(file_bytes)

        full_content = axure_data.get('full_content', '')
        incremental_content = axure_data.get('incremental_content', '')

        # Markdown格式化
        if use_md:
            if full_content:
                full_content = format_axure_text_to_markdown(full_content)
            if incremental_content:
                incremental_content = format_incremental_text_to_markdown(incremental_content)

        # AI优化整理（并行处理全量和增量内容）
        if use_ai_refine:
            # 使用 asyncio.gather 并行处理
            tasks = []
            has_full = bool(full_content)
            has_incremental = bool(incremental_content)

            if has_full:
                tasks.append(refine_requirements_markdown_async(full_content, provider=provider))
            if has_incremental:
                tasks.append(refine_requirements_markdown_async(incremental_content, provider=provider))

            if tasks:
                results = await asyncio.gather(*tasks)

                # 按顺序取回结果
                idx = 0
                if has_full:
                    full_content = results[idx]
                    idx += 1
                if has_incremental:
                    incremental_content = results[idx]

        return {
            "success": True,
            "full_content": full_content,
            "incremental_content": incremental_content
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Axure解析失败: {str(e)}")


class AxureUrlRequest(BaseModel):
    """Axure在线链接请求"""
    url: str
    username: str = ""  # 域账号用户名（可选）
    password: str = ""  # 域账号密码（可选）
    use_md: bool = True
    use_ai_refine: bool = True
    provider: str = "azure"
    enable_recursive: bool = False  # 是否启用递归解析蓝色链接
    max_depth: int = 3  # 递归最大深度


@app.post("/api/fetch/axure-url")
async def fetch_axure_url(request: AxureUrlRequest):
    """
    通过无头浏览器获取Axure在线原型内容
    """
    if not request.url:
        raise HTTPException(status_code=400, detail="请提供Axure链接")

    # 验证URL格式
    from urllib.parse import urlparse
    parsed = urlparse(request.url)
    if not parsed.scheme or not parsed.netloc:
        raise HTTPException(status_code=400, detail="请提供有效的URL地址")

    try:
        # 获取Axure在线内容 - 使用异步版本
        # 从环境变量获取认证信息
        username = os.getenv("AXURE_USERNAME")
        password = os.getenv("AXURE_PASSWORD")

        # 根据是否启用递归选择不同的解析函数
        if request.enable_recursive:
            print(f"[DEBUG] 启用递归解析, max_depth={request.max_depth}")
            axure_data = await fetch_axure_from_url_async_recursive(
                url=request.url,
                username=username,
                password=password,
                wait_time=5,
                max_depth=request.max_depth,
                enable_recursive=True
            )
        else:
            axure_data = await fetch_axure_from_url_async(
                url=request.url,
                username=username,
                password=password,
                wait_time=5,
                provider=request.provider  # 用于流程图 Mermaid 转换
            )

        full_content = axure_data.get('full_content', '')
        incremental_content = axure_data.get('incremental_content', '')
        mermaid_code = axure_data.get('mermaid_code', '')  # 获取 Mermaid 代码

        # Markdown格式化
        if request.use_md:
            if full_content:
                full_content = format_axure_text_to_markdown(full_content)
            if incremental_content:
                incremental_content = format_incremental_text_to_markdown(incremental_content)

        # AI优化整理（并行处理全量和增量内容）
        if request.use_ai_refine:
            print(f"[DEBUG] AI结构化已启用, provider={request.provider}")

            # 使用 asyncio.gather 并行处理
            tasks = []
            has_full = bool(full_content)
            has_incremental = bool(incremental_content)

            if has_full:
                print(f"[DEBUG] 添加全量内容AI结构化任务, 长度={len(full_content)}")
                tasks.append(refine_requirements_markdown_async(full_content, provider=request.provider))
            if has_incremental:
                print(f"[DEBUG] 添加增量内容AI结构化任务, 长度={len(incremental_content)}")
                tasks.append(refine_requirements_markdown_async(incremental_content, provider=request.provider))

            if tasks:
                print(f"[DEBUG] 开始并行执行 {len(tasks)} 个AI结构化任务...")
                results = await asyncio.gather(*tasks)
                print(f"[DEBUG] 并行任务完成")

                # 按顺序取回结果
                idx = 0
                if has_full:
                    full_content = results[idx]
                    idx += 1
                if has_incremental:
                    incremental_content = results[idx]
        else:
            print(f"[DEBUG] AI结构化未启用")

        # 在所有格式化处理完成后，添加流程图 Mermaid 代码
        if mermaid_code:
            flowchart_section = f"\n\n## 流程图\n\n```mermaid\n{mermaid_code}\n```\n"
            full_content = full_content + flowchart_section
            print(f"[DEBUG] 已添加流程图 Mermaid 代码到全量内容")

        return {
              "success": True,
            "full_content": full_content,
            "incremental_content": incremental_content,
            "mermaid_code": mermaid_code,  # 返回 Mermaid 代码供前端渲染
            "message": f"成功获取Axure在线内容: {len(full_content)} 字符"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取Axure在线内容失败: {str(e)}")


@app.post("/api/upload/images")
async def upload_images(
    files: List[UploadFile] = File(...),
    provider: str = Form("doubao"),
    prompt: str = Form("")
):
    """
    上传图片进行OCR识别
    支持多张图片，使用阿里云或豆包视觉模型
    provider: "doubao" (默认) | "aliyun"
    prompt: 自定义识别提示词
    """
    try:
        all_bytes = []
        for f in files:
            content = await f.read()
            all_bytes.append(content)

        # 调用视觉模型OCR（异步版本）
        result = await ocr_image_async(uploaded_files=all_bytes, vision_provider=provider, custom_prompt=prompt if prompt else None)

        return {
            "success": True,
            "text": result,
            "image_count": len(files)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"图片识别失败: {str(e)}")


@app.post("/api/vector/query")
async def vector_query(request: VectorQueryRequest):
    """向量检索并调用大模型"""
    try:
        # 检索向量库
        context = query_vector_db_and_call_api(request.persist_dir, request.question)

        # 调用大模型过滤结果
        temp_text = f'''请帮我从以下内容过滤出### {request.question}相关的内容即可\n{context}'''
        response = await call_llm_api(temp_text, provider=request.provider)
        content = response.get("choices", [{}])[0].get("message", {}).get("content", "")

        return {
            "success": True,
            "raw_context": context,
            "filtered_content": content
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"向量检索失败: {str(e)}")


# ==================== Chroma 向量数据库 API ====================

# 文档解析辅助函数（用于上传并解析模式）
async def parse_document_with_images(file_bytes: bytes, filename: str) -> str:
    """
    解析文档内容（包括图片OCR），不进行向量化
    支持 txt, md, pdf, docx 格式
    """
    from utils import parse_markdown_with_images, parse_pdf_to_text, parse_word_to_text

    file_ext = filename.lower().split('.')[-1]

    if file_ext == 'txt':
        # TXT 文件直接解码，无图片处理
        text = file_bytes.decode('utf-8')
    elif file_ext == 'md':
        # MD 文件先解码，然后解析其中的图片引用
        text = file_bytes.decode('utf-8')
        # 解析 MD 中的图片并还原到原位置
        text = await parse_markdown_with_images(text, base_path=None, vision_provider="aliyun")
        print(f"[MD解析] 文件 {filename} 图片解析完成")
    elif file_ext == 'pdf':
        text = await parse_pdf_to_text(file_bytes, enable_ocr=True)
    elif file_ext in ('docx', 'doc'):
        text = await parse_word_to_text(file_bytes, enable_ocr=True)
    else:
        raise ValueError(f"不支持的文件格式: {file_ext}")

    return text

@app.post("/api/chroma/upload")
async def upload_document_chroma(file: UploadFile = File(...), parse_only: bool = Form(False)):
    """
    上传文档并使用 Chroma + 通义千问Embedding 向量化
    支持 txt, md, pdf, docx 格式
    如果 parse_only=True，则仅解析文档不进行向量化
    如果文档已存在则直接返回已有的 collection
    """
    filename = file.filename.lower()
    if not filename.endswith(('.txt', '.md', '.pdf', '.docx', '.doc')):
        raise HTTPException(status_code=400, detail="仅支持 txt, md, pdf, docx 格式文件")

    try:
        # 读取文件内容
        file_bytes = await file.read()

        # 如果是仅解析模式
        if parse_only:
            # 解析文档内容（包括图片OCR）
            parsed_content = await parse_document_with_images(file_bytes, file.filename)

            # 进行 Markdown 格式化
            formatted_content = format_axure_text_to_markdown(parsed_content)
            print(f"[上传并解析] 已对解析内容进行 Markdown 格式化，长度: {len(formatted_content)}")

            # 调用大模型进行整理
            prompt = f"""请整理以下需求文档内容，提取并结构化所有需求信息。

文档内容：
{formatted_content}

请按以下格式整理输出：
你是一名文档整理专家。请将以下从原型提取的文字整理为清晰的Markdown格式，要求：

1. **保持原型的原始结构和层级关系**，不要改变内容的组织方式，去掉菜单功能描述，只保留页面主要功能描述和介绍

2. **表格处理（重要）**：
   - 如果内容包含表格数据，必须转换为标准 Markdown 表格格式
   - 标准格式示例：
     ```
     | 列1 | 列2 | 列3 |
     |-----|-----|-----|
     | 数据1 | 数据2 | 数据3 |
     ```
   - 确保每行的列数一致，表头和分隔符完整
   - 识别"字段|类型|说明"等结构并格式化为表格

3. **流程图处理（重要）**：
   - 如果内容描述了流程、步骤、状态转换，请用 Mermaid 流程图格式输出
   - 格式示例：
   ```mermaid
   flowchart TD
       A[开始] --> B[条件判断]
       B -->|是| C[操作1]
       B -->|否| D[操作2]
       C --> E[结束]
       D --> E
   ```

4. **格式规范**：
   - 使用 # ## ### 等标记层级
   - 使用 **加粗** 标记关键字段、按钮、状态
   - 使用 `代码标记` 标记字段名、变量名、API路径
   - 列表使用 - 或 1. 2. 3. 标记
   - 保持段落清晰，避免大段文字堆积

5. **内容优化**：
   - 识别并提取核心需求点
   - 保持逻辑清晰，层次分明
   - 去除冗余信息，保留关键内容
   - 确保信息的完整性和准确性
   - 本文档可能包含多段不同来源的内容，请保留所有文字，不要因主题相关性而过滤任何段落。
"""

            refined_result = await call_llm_api(prompt)

            # 从 LLM 返回的字典中提取文本内容
            refined_content = None
            if isinstance(refined_result, dict):
                if "error" in refined_result:
                    print(f"[上传并解析] AI整理失败: {refined_result.get('error')}")
                    refined_content = None
                elif "choices" in refined_result and len(refined_result["choices"]) > 0:
                    refined_content = refined_result["choices"][0].get("message", {}).get("content", "")
                elif "content" in refined_result:
                    refined_content = refined_result["content"]
                else:
                    refined_content = str(refined_result)
            elif isinstance(refined_result, str):
                refined_content = refined_result

            print(f"[上传并解析] AI整理完成，长度: {len(refined_content) if refined_content else 0}")

            return {
                "success": True,
                "parsed_content": formatted_content,
                "refined_content": refined_content,
                "message": f"文档 {file.filename} 解析完成",
                "parse_only": True
            }

        # 检查文档是否已经向量化
        exists, existing_collection = check_document_exists(file.filename)
        if exists:
            return {
                "success": True,
                "collection_name": existing_collection,
                "message": f"文档 {file.filename} 已经向量化，无需重复上传。",
                "already_exists": True
            }

        # 调用 Chroma 向量化函数（异步）
        success, collection_name, message = await init_chroma_vector_db(file_bytes, file.filename)
        if success:
            return {
                "success": True,
                "collection_name": collection_name,
                "message": message,
                "already_exists": False
            }
        else:
            raise HTTPException(status_code=500, detail=message)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文档处理失败: {str(e)}")


@app.post("/api/chroma/query")
async def query_chroma(request: ChromaQueryRequest, http_request: Request):
    """
    从 Chroma 向量数据库检索相关内容
    use_ai_refine=True 时会使用大模型整理结果
    """
    client_ip = get_client_ip(http_request)
    try:
        # 执行向量检索（不使用全量召回）
        result = query_chroma_vector_db(
            collection_name=request.collection_name,
            query_text=request.query_text,
            top_k=request.top_k,
            recall_all=False
        )

        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "检索失败"))

        context = result.get("context", "")
        refined_content = None

        # 先进行 Markdown 格式化（无论是否使用 AI 整理）
        if context:
            context = format_axure_text_to_markdown(context)
            print(f"[召回格式化] 已对召回内容进行 Markdown 格式化，长度: {len(context)}")

        # 如果需要大模型整理
        if request.use_ai_refine and context:
            # 使用统一的提示词整理召回内容
            prompt = f"""请根据以下检索到的文档内容，整理出与用户问题“{request.query_text}"相关的需求信息。

检索到的内容：
{context}

请按以下格式整理输出：
你是一名文档整理专家。请将以下从原型提取的文字整理为清晰的Markdown格式，要求：

1. **保持原型的原始结构和层级关系**，不要改变内容的组织方式，不要删除原来里面的内容

2. **表格处理（重要）**：
   - 如果内容包含表格数据，必须转换为标准 Markdown 表格格式
   - 标准格式示例：
     ```
     | 列1 | 列2 | 列3 |
     |-----|-----|-----|
     | 数据1 | 数据2 | 数据3 |
     ```
   - 确保每行的列数一致，表头和分隔符完整
   - 识别“字段|类型|说明”等结构并格式化为表格

3. **流程图处理（重要）**：
   - 如果内容描述了流程、步骤、状态转换，请用 Mermaid 流程图格式输出
   - 格式示例：
     ```mermaid
     flowchart TD
         A[开始] --> B{{判断条件}}
         B -->|是| C[执行操作1]
         B -->|否| D[执行操作2]
         C --> E[结束]
         D --> E
     ```
   - 状态流转用 `stateDiagram-v2`
   - 时序图用 `sequenceDiagram`

4. 使用合适的Markdown标记：
   - 标题用 # ## ###
   - 列表用 - 或 1. 2. 3.
   - 重要内容可以用 **加粗**
   - 代码或技术术语用 `反引号`

5. 清理格式问题：
   - 去除多余的空行和空格
   - 修复破碎的句子
   - 合并重复的内容
   - 本文档可能包含多段不同来源的内容，请保留所有文字，不要因主题相关性而过滤任何段落。

6. **不要添加原文没有的内容**，不要臆造字段或功能

7. **不要改变原型的结构**，保持按页面/模块组织的方式

8. 你只需要返回待整理的内容即可，不要返回其他内容，同时请切记不要删除掉我原来文本里面的内容，你只需按照格式格式化就行，不要过滤掉我原来里面内容

"""
            response = await call_llm_api(prompt, provider=request.provider)
            refined_content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
            
            # 记录 Token 统计
            token_usage = response.get("_token_usage", {})
            try:
                token_stats_manager.record_usage(
                    ip=client_ip,
                    endpoint="/api/chroma/query",
                    provider=request.provider,
                    prompt_tokens=token_usage.get("prompt_tokens", 0),
                    completion_tokens=token_usage.get("completion_tokens", 0),
                    total_tokens=token_usage.get("total_tokens", 0),
                    model=token_usage.get("model", ""),
                    status="success"
                )
            except Exception as e:
                print(f"[TokenStats] 记录统计失败: {e}")

        return {
            "success": True,
            "context": context,
            "refined_content": refined_content,
            "chunks": result.get("chunks", []),
            "total_chunks": result.get("total_chunks", 0)
        }
    except HTTPException:
        raise
    except Exception as e:
        # 记录错误
        try:
            token_stats_manager.record_usage(
                ip=client_ip,
                endpoint="/api/chroma/query",
                provider=request.provider,
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
                model="",
                status="error",
                error_message=str(e)
            )
        except:
            pass
        raise HTTPException(status_code=500, detail=f"向量检索失败: {str(e)}")


@app.get("/api/chroma/collections")
async def get_chroma_collections():
    """
    获取所有已存储的文档集合列表
    """
    try:
        collections = list_chroma_collections()
        return {
            "success": True,
            "collections": collections,
            "total": len(collections)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取集合列表失败: {str(e)}")


@app.delete("/api/chroma/collection/{collection_name}")
async def delete_collection(collection_name: str):
    """
    删除指定的文档集合
    """
    try:
        success = delete_chroma_collection(collection_name)
        if success:
            return {
                "success": True,
                "message": f"集合 {collection_name} 已删除"
            }
        else:
            raise HTTPException(status_code=500, detail="删除集合失败")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除集合失败: {str(e)}")


# ==================== 知识库管理 API ====================

@app.get("/api/kb/list")
async def get_knowledge_bases():
    """
    获取所有已创建的知识库列表
    """
    try:
        knowledge_bases = list_knowledge_bases()
        return {
            "success": True,
            "knowledge_bases": knowledge_bases,
            "total": len(knowledge_bases)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取知识库列表失败: {str(e)}")


@app.post("/api/kb/create")
async def create_kb(request: CreateKnowledgeBaseRequest):
    """
    创建新的知识库
    从Axure原型链接自动获取内容并向量化为知识库
    """
    try:
        result = await create_knowledge_base(
            name=request.name,
            axure_url=request.axure_url,
            vision_provider=request.vision_provider,
            username=request.username,
            password=request.password,
            use_ai_refine=request.use_ai_refine,
            max_concurrent=request.max_concurrent
        )

        if result.get("success"):
            return result
        else:
            raise HTTPException(status_code=500, detail=result.get("error", "创建知识库失败"))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建知识库失败: {str(e)}")


@app.delete("/api/kb/{collection_name}")
async def delete_kb(collection_name: str):
    """
    删除指定的知识库
    """
    try:
        success = delete_knowledge_base(collection_name)
        if success:
            return {
                "success": True,
                "message": f"知识库 {collection_name} 已删除"
            }
        else:
            raise HTTPException(status_code=500, detail="删除知识库失败")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除知识库失败: {str(e)}")


@app.post("/api/kb/recall")
async def recall_from_kb(request: RecallFromKnowledgeBaseRequest):
    """
    从知识库中召回相关内容
    """
    try:
        result = await recall_from_knowledge_base(
            collection_name=request.collection_name,
            query_text=request.query_text,
            top_k=request.top_k
        )

        if result.get("success"):
            return result
        else:
            raise HTTPException(status_code=500, detail=result.get("error", "召回失败"))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"召回失败: {str(e)}")


@app.post("/api/kb/generate-test-cases")
async def generate_test_cases_from_kb(request: GenerateTestCasesFromKBRequest):
    """
    从知识库召回内容并生成测试用例
    这是完整流程：召回 -> 提取测试点 -> 生成测试用例
    """
    try:
        # 1. 从知识库召回相关内容
        recall_result = await recall_from_knowledge_base(
            collection_name=request.collection_name,
            query_text=request.requirement,
            top_k=request.top_k
        )

        if not recall_result.get("success"):
            raise HTTPException(status_code=500, detail=recall_result.get("error", "召回失败"))

        context = recall_result.get("context", "")

        # 2. 构建系统提示词
        prompt = prompt_default  # 使用默认提示词
        system_message = build_system_message(
            requirement_text=context,
            test_level="系统测试",
            test_module=request.test_module,
            test_case_count=-1,  # AI自动判断用例数量
            prompt=prompt
        )

        # 3. 生成测试用例（完整流程）
        test_cases_data = None
        test_points = []

        # 使用流式生成函数，但我们需要完整结果
        async for result in generate_test_cases_stream(
            requirement_text=context,
            test_module=request.test_module,
            test_level="系统测试",
            test_case_count=-1,
            system_message=system_message,
            provider=request.provider,
            prompt=prompt
        ):
            if result["type"] == "complete":
                test_cases_data = result["test_cases"]
            elif result["type"] == "error":
                raise HTTPException(status_code=500, detail=result["content"])

        return {
            "success": True,
            "context": context,
            "total_chunks": recall_result.get("total_chunks", 0),
            "test_points": test_points,
            "test_cases": test_cases_data
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"生成测试用例失败: {str(e)}")


@app.post("/api/refine")
async def refine_content(request: RefineRequest, http_request: Request):
    """AI优化需求文档为结构化Markdown"""
    client_ip = get_client_ip(http_request)
    try:
        result = await refine_requirements_markdown_async(request.content, provider=request.provider)
        
        # 记录统计（refine 函数不返回 token，暂时记录为 0）
        try:
            token_stats_manager.record_usage(
                ip=client_ip,
                endpoint="/api/refine",
                provider=request.provider,
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
                model="",
                status="success"
            )
        except Exception as e:
            print(f"[TokenStats] 记录统计失败: {e}")
        
        return {
            "success": True,
            "content": result
        }
    except Exception as e:
        # 记录错误
        try:
            token_stats_manager.record_usage(
                ip=client_ip,
                endpoint="/api/refine",
                provider=request.provider,
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
                model="",
                status="error",
                error_message=str(e)
            )
        except:
            pass
        raise HTTPException(status_code=500, detail=f"AI优化失败: {str(e)}")


# ==================== 增强版知识库管理 API ====================

@app.get("/api/kb/enhanced/list")
async def get_enhanced_knowledge_bases():
    """
    获取所有增强版知识库列表
    """
    try:
        knowledge_bases = list_enhanced_knowledge_bases()
        return {
            "success": True,
            "knowledge_bases": knowledge_bases,
            "total": len(knowledge_bases)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取知识库列表失败: {str(e)}")


@app.post("/api/kb/enhanced/create")
async def create_enhanced_kb(request: CreateEnhancedKBRequest):
    """
    创建知识库
    - 分层向量存储（单页 + 增量 + 模块）
    - AI分析页面关联关系
    - 蓝色字体识别
    - Markdown格式化（表格→Markdown表格）
    """
    # 从环境变量获取认证信息和默认参数
    FIXED_USERNAME = os.getenv("AXURE_USERNAME")
    FIXED_PASSWORD = os.getenv("AXURE_PASSWORD")

    try:
        result = await create_enhanced_knowledge_base(
            name=request.name,
            axure_url=request.axure_url,
            username=FIXED_USERNAME,
            password=FIXED_PASSWORD,
            use_ai_analysis=True,  # 固定开启AI分析
            max_concurrent=1  # 串行执行，避免并发导致的增量检测不稳定
        )

        if result.get("success"):
            return result
        else:
            raise HTTPException(status_code=500, detail=result.get("error", "创建知识库失败"))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建知识库失败: {str(e)}")


@app.delete("/api/kb/enhanced/{collection_name}")
async def delete_enhanced_kb(collection_name: str):
    """
    删除增强版知识库
    """
    try:
        success = delete_enhanced_knowledge_base(collection_name)
        if success:
            return {
                "success": True,
                "message": f"知识库 {collection_name} 已删除"
            }
        else:
            raise HTTPException(status_code=500, detail="删除知识库失败")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除知识库失败: {str(e)}")


@app.post("/api/kb/enhanced/smart-recall")
async def smart_recall(request: SmartRecallRequest):
    """
    智能召回：自动选择最佳召回策略
    - 增量 + 全量上下文
    - 元数据过滤
    - 自动判断召回策略
    - AI结构化（可选）
    """
    try:
        result = await smart_recall_from_knowledge_base(
            collection_name=request.collection_name,
            query=request.query,
            page_key=request.page_key,
            recall_strategy=request.recall_strategy,
            top_k=request.top_k,
            use_ai_structure=request.use_ai_structure,
            ai_provider=request.ai_provider
        )

        if "error" in result:
            raise HTTPException(status_code=500, detail=result["error"])

        return {
            "success": True,
            **result
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"智能召回失败: {str(e)}")


@app.post("/api/kb/enhanced/generate-test-cases")
async def generate_test_cases_enhanced(request: GenerateTestCasesSmartRequest):
    """
    使用智能召回生成测试用例
    1. 智能召回（增量 + 全量上下文）
    2. AI结构化（可选）
    3. 自动组装完整prompt
    4. 生成测试用例
    """
    try:
        # 1. 智能召回
        recall_result = await smart_recall_from_knowledge_base(
            collection_name=request.collection_name,
            query=request.query,
            page_key=request.page_key,
            recall_strategy=request.recall_strategy,
            top_k=request.top_k,
            use_ai_structure=request.use_ai_structure,
            ai_provider=request.provider
        )

        if "error" in recall_result:
            raise HTTPException(status_code=500, detail=recall_result["error"])

        # 2. 获取组装好的内容（优先使用structured，其次combined，最后data）
        if request.use_ai_structure and "structured" in recall_result:
            # 使用AI结构化后的内容
            content = recall_result["structured"]
        elif "combined" in recall_result and recall_result["combined"]:
            content = recall_result["combined"]
        elif "data" in recall_result and recall_result["data"].get("documents"):
            # 如果有多个文档，合并它们
            documents = recall_result["data"]["documents"]
            content = "\n\n".join(documents)
        else:
            raise HTTPException(status_code=404, detail="未召回到相关内容")

        # 3. 生成测试用例
        system_message = build_system_message(
            requirement_text=content,
            test_level="系统测试",
            test_module=request.test_module,
            test_case_count=-1,
            prompt=prompt_default
        )

        test_cases = None
        async for result in generate_test_cases_stream(
            requirement_text=content,
            test_module=request.test_module,
            test_level="系统测试",
            test_case_count=-1,
            system_message=system_message,
            provider=request.provider,
            prompt=prompt_default
        ):
            if result['type'] == 'complete':
                test_cases = result['test_cases']
            elif result['type'] == 'error':
                raise HTTPException(status_code=500, detail=result['content'])

        response = {
            "success": True,
            "recall_strategy": recall_result.get('strategy'),
            "recall_chunks": recall_result.get('total_chunks', 0),
            "test_cases": test_cases
        }

        # 如果使用了AI结构化，返回结构化后的内容
        if request.use_ai_structure:
            response["structured"] = recall_result.get("structured", "")
            response["raw"] = recall_result.get("raw", "")
            response["summary"] = recall_result.get("summary", "")

        return response
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"生成测试用例失败: {str(e)}")


@app.post("/api/testcase/generate/stream")
async def generate_testcase_stream(request: GenerateRequest, http_request: Request):
    """
    流式生成测试用例（SSE）
    """
    if not request.requirement_text:
        raise HTTPException(status_code=400, detail="请提供需求信息")
    if not request.test_module:
        raise HTTPException(status_code=400, detail="请提供模块名称")

    prompt = request.prompt or prompt_default
    source_type = request.source_type
    client_ip = get_client_ip(http_request)

    # 根据来源类型生成不同的提示词
    requirement_with_context = request.requirement_text

    if source_type == "upload-axure":
        # Axure 原型场景
        if request.context_text:
            requirement_with_context = f"""## 功能背景（全量需求）

{request.context_text}\n

## 本次需要测试的增量需求

{request.requirement_text}\n\n

## **__请注意:以上为本次全量需求以及增量需求，请您首先理解「功能背景」中的业务逻辑、上下文背景，然后根据当前「增量需求」中的需求去生成测试用例__** """
        else:
            requirement_with_context = request.requirement_text

    elif source_type == "knowledge-base":
        # 知识库召回场景：combined 内容已包含模块+页面+增量，添加说明提示词
        requirement_with_context = f"""{request.requirement_text}

---

**说明**：以上内容来自知识库召回，已包含：
- 📦 **关联需求上下文信息**
- 📄 **当前页面全量**
- 🔵 **本次增量需求**（新增/变更）

## **__请结合上述完整信息结合关联需求上下文信息、当前页面全量理解业逻辑后后生成本次增量需求需求部分的测试用例。__** """

    elif source_type == "upload-doc" or source_type == "upload-image" or source_type == "manual-input" :
        # 文档上传场景
        requirement_with_context = f"""{request.requirement_text}\n\n"""

    # 构建系统提示词
    system_message = build_system_message(
        requirement_text=requirement_with_context,
        test_level="系统测试",
        test_module=request.test_module,
        test_case_count=request.test_case_count,
        prompt=prompt
    )

    async def event_generator():
        """SSE事件生成器"""
        total_tokens = 0
        prompt_tokens = 0
        completion_tokens = 0
        model_name = ""
        status = "success"
        error_message = ""
        
        try:
            # 先发送系统提示词
            yield f"data: {json.dumps({'type': 'system_message', 'content': system_message}, ensure_ascii=False)}\n\n"

            async for result in generate_test_cases_stream(
                requirement_text=requirement_with_context,
                test_module=request.test_module,
                test_level="系统测试",
                test_case_count=request.test_case_count,
                system_message=system_message,
                provider=request.provider,
                prompt=prompt
            ):
                if result["type"] == "chunk":
                    yield f"data: {json.dumps({'type': 'chunk', 'content': result['content']}, ensure_ascii=False)}\n\n"
                elif result["type"] == "complete":
                    yield f"data: {json.dumps({'type': 'complete', 'test_cases': result['test_cases']}, ensure_ascii=False)}\n\n"
                    # 提取 Token 信息（如果有）
                    if "_token_usage" in result:
                        token_usage = result["_token_usage"]
                        prompt_tokens = token_usage.get("prompt_tokens", 0)
                        completion_tokens = token_usage.get("completion_tokens", 0)
                        total_tokens = token_usage.get("total_tokens", 0)
                        model_name = token_usage.get("model", "")
                elif result["type"] == "error":
                    yield f"data: {json.dumps({'type': 'error', 'content': result['content']}, ensure_ascii=False)}\n\n"
                    status = "error"
                    error_message = result.get('content', '')

            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)}, ensure_ascii=False)}\n\n"
            status = "error"
            error_message = str(e)
        finally:
            # 记录统计数据
            try:
                token_stats_manager.record_usage(
                    ip=client_ip,
                    endpoint="/api/testcase/generate/stream",
                    provider=request.provider,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                    model=model_name,
                    status=status,
                    error_message=error_message
                )
            except Exception as e:
                print(f"[TokenStats] 记录统计失败: {e}")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@app.post("/api/export/csv")
async def export_csv(request: ExportRequest):
    """导出CSV格式"""
    import pandas as pd

    try:
        rows = []
        for case in request.test_cases.get("test_cases", []):
            row = {
                "用例ID": case.get("case_id", ""),
                "模块": case.get("test_module", ""),
            }
            if request.menu1:
                row["菜单1"] = request.menu1
            if request.menu2:
                row["菜单2"] = request.menu2
            row.update({
                "标题": case.get("title", ""),
                "测试步骤": case.get("steps", ""),
                "预期结果": case.get("expected_result", "")
            })
            rows.append(row)

        df = pd.DataFrame(rows)
        csv_buffer = BytesIO()
        df.to_csv(csv_buffer, index=False, encoding='utf-8-sig')
        csv_buffer.seek(0)

        filename = f"test_cases_{get_current_datetime()}.csv"
        return StreamingResponse(
            csv_buffer,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导出CSV失败: {str(e)}")


@app.post("/api/export/markdown")
async def export_markdown(request: ExportRequest):
    """导出Markdown格式"""
    try:
        md_text = "# 测试用例\n\n"

        for case in request.test_cases.get("test_cases", []):
            md_text += f"## {case.get('test_module', '')}\n\n"
            if request.menu1:
                md_text += f"### {request.menu1}\n\n"
                if request.menu2:
                    md_text += f"#### {request.menu2}\n\n"
                    md_text += f"##### {case.get('title', '')}\n\n"
                    md_text += "###### 测试步骤:\n\n"
                    md_text += f"{case.get('steps', '')}\n\n"
                    md_text += "###### 预期结果:\n\n"
                    md_text += f"{case.get('expected_result', '')}\n\n\n"
                else:
                    md_text += f"#### {case.get('title', '')}\n\n"
                    md_text += "##### 测试步骤:\n\n"
                    md_text += f"{case.get('steps', '')}\n\n"
                    md_text += "##### 预期结果:\n\n"
                    md_text += f"{case.get('expected_result', '')}\n\n\n"
            else:
                md_text += f"### {case.get('title', '')}\n\n"
                md_text += "#### 测试步骤:\n\n"
                md_text += f"{case.get('steps', '')}\n\n"
                md_text += "#### 预期结果:\n\n"
                md_text += f"{case.get('expected_result', '')}\n\n\n"

        md_buffer = BytesIO(md_text.encode('utf-8'))
        filename = f"test_cases_{get_current_datetime()}.md"

        return StreamingResponse(
            md_buffer,
            media_type="text/markdown",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导出Markdown失败: {str(e)}")


@app.post("/api/export/xmind")
async def export_xmind(request: ExportRequest):
    """导出XMind格式（直接从测试用例数据生成，保留换行符）"""
    try:
        # 生成临时xmind文件
        with tempfile.NamedTemporaryFile(suffix='.xmind', delete=False) as xmind_file:
            xmind_path = xmind_file.name

        # 使用新函数直接生成 XMind，保留换行符
        test_cases_to_xmind(
            test_cases_data=request.test_cases,
            xmind_path=xmind_path,
            root_title="测试用例",
            menu1=request.menu1 or "",
            menu2=request.menu2 or ""
        )

        # 读取文件
        with open(xmind_path, 'rb') as f:
            xmind_bytes = f.read()

        # 删除临时文件
        os.unlink(xmind_path)

        filename = f"test_cases_{get_current_datetime()}.xmind"
        return StreamingResponse(
            BytesIO(xmind_bytes),
            media_type="application/vnd.xmind.workbook",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导出XMind失败: {str(e)}")


@app.post("/api/export/xmind-text")
async def export_xmind_text(request: ExportRequest):
    """获取XMind粘贴格式文本"""
    try:
        xmind_text = test_cases_to_xmind_text(
            request.test_cases,
            menu1=request.menu1,
            menu2=request.menu2
        )
        return {
            "success": True,
            "text": xmind_text
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"生成XMind文本失败: {str(e)}")


# ==================== 基于Sitemap的知识库 API ====================

@app.get("/api/kb/sitemap/list")
async def list_sitemap_kb():
    """列出所有基于Sitemap的知识库"""
    try:
        kbs = list_sitemap_knowledge_bases()
        return {
            "success": True,
            "knowledge_bases": kbs,
            "total": len(kbs)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"列出知识库失败: {str(e)}")


@app.delete("/api/kb/sitemap/{collection_name}")
async def delete_sitemap_kb(collection_name: str):
    """删除基于Sitemap的知识库"""
    try:
        success = delete_sitemap_knowledge_base(collection_name)
        if success:
            return {"success": True, "message": f"知识库 {collection_name} 已删除"}
        else:
            raise HTTPException(status_code=500, detail="删除知识库失败")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除知识库失败: {str(e)}")


@app.post("/api/kb/sitemap/smart-recall")
async def sitemap_smart_recall_api(request: SitemapSmartRecallRequest):
    """
    Sitemap知识库智能召回：自动选择最佳召回策略
    - 增量 + 全量上下文
    - 元数据过滤
    - 自动判断召回策略
    """
    try:
        result = await sitemap_smart_recall(
            collection_name=request.collection_name,
            query=request.query,
            page_key=request.page_key,
            recall_strategy=request.recall_strategy,
            top_k=request.top_k
        )

        if "error" in result:
            raise HTTPException(status_code=500, detail=result["error"])

        return {
            "success": True,
            **result
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"智能召回失败: {str(e)}")


@app.post("/api/kb/sitemap/generate-test-cases")
async def generate_test_cases_sitemap(request: GenerateTestCasesFromSitemapRequest):
    """
    使用Sitemap知识库智能召回生成测试用例
    1. 智能召回（增量 + 全量上下文）
    2. 自动组装完整prompt
    3. 生成测试用例
    """
    try:
        # 1. 智能召回
        recall_result = await sitemap_smart_recall(
            collection_name=request.collection_name,
            query=request.query,
            page_key=request.page_key,
            recall_strategy=request.recall_strategy,
            top_k=request.top_k
        )

        if "error" in recall_result:
            raise HTTPException(status_code=500, detail=recall_result["error"])

        # 2. 获取组装好的内容（优先使用combined，其次使用data）
        if "combined" in recall_result and recall_result["combined"]:
            content = recall_result["combined"]
        elif "data" in recall_result and recall_result["data"].get("documents"):
            # 如果有多个文档，合并它们
            documents = recall_result["data"]["documents"]
            content = "\n\n".join(documents)
        else:
            raise HTTPException(status_code=404, detail="未召回到相关内容")

        # 3. 生成测试用例
        system_message = build_system_message(
            requirement_text=content,
            test_level="系统测试",
            test_module=request.test_module,
            test_case_count=-1,
            prompt=prompt_default
        )

        test_cases = None
        async for result in generate_test_cases_stream(
            requirement_text=content,
            test_module=request.test_module,
            test_level="系统测试",
            test_case_count=-1,
            system_message=system_message,
            provider=request.provider,
            prompt=prompt_default
        ):
            if result['type'] == 'complete':
                test_cases = result['test_cases']
            elif result['type'] == 'error':
                raise HTTPException(status_code=500, detail=result['content'])

        return {
            "success": True,
            "recall_strategy": recall_result.get('strategy'),
            "recall_chunks": recall_result.get('total_chunks', 0),
            "context_used": 'context' in recall_result,
            "test_cases": test_cases
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"生成测试用例失败: {str(e)}")


# ==================== Token 统计 API ====================

class StatsQueryRequest(BaseModel):
    """统计查询请求"""
    days: int = 30
    ip: Optional[str] = None


class StatsClearRequest(BaseModel):
    """清理统计请求"""
    days: int = 90


@app.get("/api/stats/summary")
async def get_token_stats_summary(days: int = 30):
    """
    获取 Token 消耗总体统计
    
    Args:
        days: 最近多少天的数据
    """
    try:
        stats = token_stats_manager.get_all_stats(days=days)
        return {
            "success": True,
            **stats
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取统计信息失败: {str(e)}")


@app.get("/api/stats/ip-list")
async def get_ip_list(days: int = 30):
    """
    获取所有 IP 列表及其统计信息
    
    Args:
        days: 最近多少天的数据
    """
    try:
        ip_stats = token_stats_manager.get_stats_by_ip(days=days)
        
        # 转换为列表格式并按总 token 排序
        ip_list = []
        for ip, stats in ip_stats.items():
            ip_list.append({
                "ip": ip,
                **stats,
                "providers": dict(stats["providers"]),
                "endpoints": dict(stats["endpoints"])
            })
        
        # 按总 token 数降序排列
        ip_list.sort(key=lambda x: x["total_tokens"], reverse=True)
        
        return {
            "success": True,
            "ip_list": ip_list,
            "total_ips": len(ip_list)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取 IP 列表失败: {str(e)}")


@app.get("/api/stats/ip/{ip}")
async def get_ip_stats(ip: str, days: int = 30):
    """
    获取指定 IP 的详细统计信息
    
    Args:
        ip: IP 地址
        days: 最近多少天的数据
    """
    try:
        ip_stats = token_stats_manager.get_stats_by_ip(ip=ip, days=days)
        
        if ip not in ip_stats:
            return {
                "success": True,
                "ip": ip,
                "message": "该 IP 无使用记录",
                "stats": None
            }
        
        stats = ip_stats[ip]
        return {
            "success": True,
            "ip": ip,
            "stats": {
                **stats,
                "providers": dict(stats["providers"]),
                "endpoints": dict(stats["endpoints"])
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取 IP 统计失败: {str(e)}")


@app.get("/api/stats/recent")
async def get_recent_records(limit: int = 100, days: int = 7):
    """
    获取最近的调用记录
    
    Args:
        limit: 返回记录数量限制
        days: 最近多少天的数据
    """
    try:
        records = token_stats_manager.get_recent_records(limit=limit, days=days)
        return {
            "success": True,
            "records": records,
            "total": len(records)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取记录失败: {str(e)}")


@app.post("/api/stats/clear")
async def clear_old_stats(request: StatsClearRequest):
    """
    清理旧统计数据
    
    Args:
        days: 保留最近多少天的数据
    """
    try:
        removed_count = token_stats_manager.clear_old_records(days=request.days)
        return {
            "success": True,
            "message": f"成功清理 {removed_count} 条旧记录",
            "removed_count": removed_count
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"清理统计失败: {str(e)}")


# ==================== 启动配置 ====================

if __name__ == "__main__":
    import uvicorn
    from uvicorn.config import LOGGING_CONFIG
    
    # 配置 uvicorn 超时参数
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8001,
        timeout_keep_alive=300,  # 保持连接超时 5 分钟
        access_log=False,
        log_level="info"
    )
