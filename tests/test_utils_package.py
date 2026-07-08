# -*- coding: utf-8 -*-
"""utils 包单元测试 - 验证拆分后的每个子模块"""
import sys
import os

# 确保项目根目录在 Python 路径中
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

print("=" * 60)
print("utils 包单元测试")
print("=" * 60)

# 1. 测试所有模块导入
print("\n1. 测试所有子模块导入...")
from utils.config import VECTOR_DB_PATH, CHROMA_DB_PATH, EMBEDDING_MODEL, DASHSCOPE_EMBEDDING_MODEL, OCR_TIMEOUT, OCR_MAX_RETRIES, KNOWLEDGE_BASE_PATH
print("   [OK] config")
from utils.helpers import get_current_datetime; print(f"   [OK] helpers -> {get_current_datetime()}")
from utils.text import _fix_json_control_chars, build_system_message; print("   [OK] text")
from utils.streaming import generate_test_cases_stream; print("   [OK] streaming")
from utils.ocr import ocr_image_async, _structure_ocr_result; print("   [OK] ocr")
from utils.document import parse_markdown_with_images, parse_pdf_to_text, parse_word_to_text; print("   [OK] document")
from utils.vector import init_vector_db, query_vector_db_and_call_api; print("   [OK] vector")
from utils.chroma import (init_chroma_vector_db, query_chroma_vector_db, list_chroma_collections, delete_chroma_collection, check_document_exists, get_dashscope_embedding, split_text_into_chunks); print("   [OK] chroma")
from utils.llm_helper import refine_requirements_markdown, refine_requirements_markdown_async; print("   [OK] llm_helper")
from utils.flowchart import detect_and_extract_flowchart, convert_flowchart_to_mermaid_async; print("   [OK] flowchart")
from utils.axure import (parse_axure_zip_to_text, parse_axure_html_to_text, format_axure_text_to_markdown, format_incremental_text_to_markdown, fetch_axure_from_url, fetch_axure_from_url_async, fetch_axure_from_url_async_recursive); print("   [OK] axure")
from utils.knowledge_base import (PageData, MetadataFilter, extract_blue_text_from_html, extract_blue_text_simple, format_page_to_markdown, create_knowledge_base, list_knowledge_bases, delete_knowledge_base, recall_from_knowledge_base, generate_test_points, generate_test_cases_from_points, add_title_suffix_to_documents, assemble_incremental_with_context, structure_recall_content_with_ai, format_recall_results, smart_recall_from_knowledge_base); print("   [OK] knowledge_base")
from llms import call_llm_api; print("   [OK] llms (re-export)")

# 2. 测试PageData数据模型
print("\n2. 测试数据模型...")
pd = PageData("key1", "Page1", "http://example.com")
assert pd.page_key == "key1"
assert pd.page_name == "Page1"
d = pd.to_dict()
assert d["page_key"] == "key1"
assert d["has_incremental"] == False
print("   [OK] PageData 创建与序列化")

# 3. 测试 MetadataFilter
print("\n3. 测试 MetadataFilter...")
f1 = MetadataFilter.page_key("test")
assert f1 == {"page_key": {"$eq": "test"}}
f2 = MetadataFilter.incremental_only()
assert f2 == {"is_incremental": {"$eq": True}}
f3 = MetadataFilter.combine(f1, f2)
assert "$and" in f3
print("   [OK] MetadataFilter 过滤条件生成")

# 4. 测试 config 常量
print("\n4. 测试配置常量...")
assert CHROMA_DB_PATH == "./DB/chroma_db"
assert OCR_TIMEOUT == 60
assert OCR_MAX_RETRIES == 2
print(f"   [OK] CHROMA_DB_PATH={CHROMA_DB_PATH}")
print(f"   [OK] KNOWLEDGE_BASE_PATH={KNOWLEDGE_BASE_PATH}")

# 5. 测试 text 模块
print("\n5. 测试文本工具...")
fixed = _fix_json_control_chars('{"a": "hello world"}')
assert fixed == '{"a": "hello world"}'
sys_msg = build_system_message("test content", "功能测试", "ModuleX", 5, "")
assert "test content" in sys_msg
assert "ModuleX" in sys_msg
print("   [OK] _fix_json_control_chars")
print("   [OK] build_system_message")

# 6. 测试 split_text_into_chunks
print("\n6. 测试文本分块...")
chunks = split_text_into_chunks("hello world this is a test chunk")
print(f"   [OK] split_text_into_chunks ({len(chunks)} chunks)")

# 7. 测试 add_title_suffix_to_documents
print("\n7. 测试文档工具...")
docs = add_title_suffix_to_documents(["# Title\ncontent"], " - suffix")
assert "suffix" in docs[0]
print("   [OK] add_title_suffix_to_documents")

# 8. 测试外部导入兼容性
print("\n8. 测试向后兼容性...")
from utils import (
    generate_test_cases_stream, build_system_message,
    get_current_datetime, init_vector_db, ocr_image_async,
    PageData as PD2, MetadataFilter as MF2,
    CHROMA_DB_PATH as C2, call_llm_api as CLA2
)
assert PD2 is PageData
assert MF2 is MetadataFilter
assert C2 == CHROMA_DB_PATH
print("   [OK] 所有符号从 utils 顶级包正确导入")

print()
print("=" * 60)
print("所有单元测试通过!")
print("=" * 60)
