"""utils 包 - 重新导出所有公共符号，保持向后兼容"""
from typing import List, Dict, Any

# 配置常量
from .config import (
    VECTOR_DB_PATH,
    CHROMA_DB_PATH,
    EMBEDDING_MODEL,
    DASHSCOPE_EMBEDDING_MODEL,
    OCR_TIMEOUT,
    OCR_MAX_RETRIES,
    KNOWLEDGE_BASE_PATH,
)

# 辅助函数
from .helpers import get_current_datetime

# 文本工具
from .text import (
    _fix_json_control_chars,
    build_system_message,
)

# 流式生成
from .streaming import generate_test_cases_stream

# OCR 识别
from .ocr import (
    ocr_image_async,
    _structure_ocr_result,
)

# 文档解析
from .document import (
    parse_markdown_with_images,
    parse_pdf_to_text,
    parse_word_to_text,
)

# 向量数据库（旧版 LlamaIndex）
from .vector import (
    init_vector_db,
    query_vector_db_and_call_api,
)

# Chroma 向量库
from .chroma import (
    init_chroma_vector_db,
    query_chroma_vector_db,
    list_chroma_collections,
    delete_chroma_collection,
    check_document_exists,
    get_dashscope_embedding,
    split_text_into_chunks,
)

# LLM 辅助函数
from .llm_helper import (
    refine_requirements_markdown,
    refine_requirements_markdown_async,
)

# 流程图
from .flowchart import (
    detect_and_extract_flowchart,
    convert_flowchart_to_mermaid_async,
)

# Axure 原型解析
from .axure import (
    parse_axure_zip_to_text,
    parse_axure_html_to_text,
    format_axure_text_to_markdown,
    format_incremental_text_to_markdown,
    fetch_axure_from_url,
    fetch_axure_from_url_async,
    fetch_axure_from_url_async_recursive,
)

# 知识库管理
from .knowledge_base import (
    PageData,
    MetadataFilter,
    extract_blue_text_from_html,
    extract_blue_text_simple,
    format_page_to_markdown,
    create_knowledge_base,
    list_knowledge_bases,
    delete_knowledge_base,
    recall_from_knowledge_base,
    generate_test_points,
    generate_test_cases_from_points,
    add_title_suffix_to_documents,
    assemble_incremental_with_context,
    structure_recall_content_with_ai,
    format_recall_results,
    smart_recall_from_knowledge_base,
)

# 外部依赖重新导出（被 utils_sitemap_kb.py 等文件使用）
from llms import call_llm_api
