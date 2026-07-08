"""知识库管理模块

包含知识库创建、管理、召回、智能生成等功能。
"""
import os
import re
import json
import hashlib
import asyncio
import time
from datetime import datetime
from typing import Dict, Any, List, Optional
from copy import deepcopy
from urllib.parse import urlparse, unquote, parse_qs

import aiohttp
from bs4 import BeautifulSoup

from llms import call_llm_api
from .config import CHROMA_DB_PATH, KNOWLEDGE_BASE_PATH
from .helpers import get_current_datetime
from .text import _fix_json_control_chars
from .chroma import split_text_into_chunks, get_dashscope_embedding, query_chroma_vector_db
from .llm_helper import refine_requirements_markdown_async


# ============ 元数据Schema定义 ============

METADATA_SCHEMA = {
    "doc_type": "page_full | page_incremental | module_fused | business_flow",
    "page_key": "页面唯一标识",
    "page_name": "页面中文名称",
    "module": "所属模块",
    "business_domain": "业务域",
    "is_incremental": "Boolean: 是否为增量内容",
    "has_blue_text": "Boolean: 是否包含蓝色字体",
    "related_pages": "关联的页面keys列表",
    "prerequisite_pages": "前置页面",
    "subsequent_pages": "后续页面",
    "content_length": "内容长度",
    "created_at": "创建时间",
}


# ============ 数据模型 ============

class PageData:
    """页面数据模型"""
    def __init__(self, page_key: str, page_name: str, page_url: str, full_content: str = "",
                 incremental_content: str = "", module: str = "", raw_html: str = ""):
        self.page_key = page_key
        self.page_name = page_name
        self.page_url = page_url
        self.module = module
        self.full_content = full_content
        self.incremental_content = incremental_content
        self.has_incremental = bool(incremental_content.strip())
        self.related_pages = []
        self.prerequisite_pages = []
        self.subsequent_pages = []
        self.raw_html = raw_html

    def to_dict(self) -> dict:
        return {
            "page_key": self.page_key,
            "page_name": self.page_name,
            "page_url": self.page_url,
            "module": self.module,
            "full_content": self.full_content,
            "incremental_content": self.incremental_content,
            "has_incremental": self.has_incremental,
            "related_pages": self.related_pages,
            "prerequisite_pages": self.prerequisite_pages,
            "subsequent_pages": self.subsequent_pages,
            "raw_html": self.raw_html
        }


class MetadataFilter:
    """元数据过滤器工具类（符合ChromaDB where语法）"""

    @staticmethod
    def page_key(page_key: str) -> dict:
        return {"page_key": {"$eq": page_key}}

    @staticmethod
    def page_incremental(page_key: str) -> dict:
        return {
            "$and": [
                {"page_key": {"$eq": page_key}},
                {"is_incremental": {"$eq": True}}
            ]
        }

    @staticmethod
    def page_full(page_key: str) -> dict:
        return {
            "$and": [
                {"page_key": {"$eq": page_key}},
                {"doc_type": {"$eq": "page_full"}}
            ]
        }

    @staticmethod
    def module(module_name: str) -> dict:
        return {
            "$and": [
                {"doc_type": {"$eq": "module_fused"}},
                {"module": {"$eq": module_name}}
            ]
        }

    @staticmethod
    def incremental_only() -> dict:
        return {"is_incremental": {"$eq": True}}

    @staticmethod
    def doc_type(doc_type: str) -> dict:
        return {"doc_type": {"$eq": doc_type}}

    @staticmethod
    def combine(*filters) -> dict:
        conditions = []
        for f in filters:
            if isinstance(f, dict):
                conditions.append(f)
        if len(conditions) == 1:
            return conditions[0]
        elif len(conditions) > 1:
            return {"$and": conditions}
        return {}


# ============ 蓝色字体识别 ============

def extract_blue_text_from_html(html_content: str) -> tuple:
    """
    从HTML中提取蓝色字体（增量）和非蓝色字体（全量）

    Returns:
        (full_content, incremental_content)
    """
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
    except ImportError:
        print("[蓝色字体识别] BeautifulSoup未安装，使用简单正则表达式")
        return extract_blue_text_simple(html_content)

    try:
        blue_texts = []
        normal_texts = []

        for element in soup.find_all(['span', 'div', 'p', 'td', 'li', 'font', 'a']):
            style = element.get('style', '').lower().replace(' ', '')
            class_attr = element.get('class', [])
            color_attr = element.get('color', '').lower() if element.name == 'font' else ''

            is_blue = (
                'color:blue' in style or
                'color:#0000ff' in style or
                'color:#00f' in style or
                'rgb(0,0,255)' in style or
                'color:rgb(0,0,255)' in style or
                any('blue' in str(c).lower() for c in class_attr) or
                color_attr == 'blue' or
                color_attr == '#0000ff' or
                color_attr == '#00f'
            )

            if is_blue:
                text = element.get_text(strip=True)
                if text and len(text) > 1:
                    blue_texts.append(text)
            else:
                element_copy = deepcopy(element)
                for blue_elem in element_copy.find_all(style=lambda s: s and 'blue' in s.lower()):
                    blue_elem.decompose()
                for blue_elem in element_copy.find_all(class_=lambda c: c and any('blue' in str(cl).lower() for cl in c)):
                    blue_elem.decompose()
                text = element_copy.get_text(strip=True)
                if text and len(text) > 1:
                    normal_texts.append(text)

        full_content = "\n".join(normal_texts)
        incremental_content = "\n".join(blue_texts)
        print(f"[蓝色字体识别] 全量内容: {len(full_content)} 字符, 增量内容: {len(incremental_content)} 字符")
        return full_content, incremental_content

    except Exception as e:
        print(f"[蓝色字体识别] BeautifulSoup解析失败: {e}，使用简单正则表达式")
        return extract_blue_text_simple(html_content)


def extract_blue_text_simple(html_content: str) -> tuple:
    """简单版蓝色字体识别（使用正则表达式）"""
    blue_pattern = re.compile(
        r'<[^>]*(?:style\s*=\s*["\'][^"\']*?\bcolor\s*:\s*(?:blue|#0{0,2}00ff|#00f|rgb\(\s*0\s*,\s*0\s*,\s*255\s*\))[^"\']*?["\']|color\s*=\s*["\']?(?:blue|#0{0,2}00ff|#00f)["\']?)[^>]*>(.*?)</[^>]+>',
        re.IGNORECASE | re.DOTALL
    )
    blue_matches = blue_pattern.findall(html_content)
    incremental_content = "\n".join([m.strip() for m in blue_matches if m.strip()])
    full_content = blue_pattern.sub('', html_content)
    full_content = re.sub(r'<[^>]+>', '\n', full_content)
    full_content = re.sub(r'\n+', '\n', full_content).strip()
    return full_content, incremental_content


# ============ 格式化为Markdown ============

def format_page_to_markdown(page_data: PageData) -> dict:
    """将页面内容格式化为Markdown"""
    full_markdown = f"# {page_data.page_name}\n\n"
    full_markdown += page_data.full_content

    incremental_markdown = ""
    if page_data.incremental_content:
        incremental_markdown = f"# {page_data.page_name} - 本次新增\n\n"
        incremental_markdown += page_data.incremental_content

    return {
        "page_key": page_data.page_key,
        "full_markdown": full_markdown,
        "incremental_markdown": incremental_markdown
    }


# ============ 原有知识库管理功能（保留兼容） ============

os.makedirs(KNOWLEDGE_BASE_PATH, exist_ok=True)


async def create_knowledge_base(
    name: str,
    axure_url: str,
    vision_provider: str = "doubao",
    username: str = None,
    password: str = None,
    use_ai_refine: bool = False,
    max_concurrent: int = 5
) -> Dict[str, Any]:
    """
    创建知识库（快速版）：直接 HTTP 获取 Axure 内容 -> 并发处理 -> 向量化存储

    Args:
        name: 知识库名称
        axure_url: Axure 原型首页链接
        vision_provider: 视觉模型提供商（此版本不使用）
        username: 登录用户名（此版本不使用）
        password: 登录密码（此版本不使用）
        use_ai_refine: 是否使用AI整理内容（默认关闭以加快速度）
        max_concurrent: 最大并发数

    Returns:
        Dict: 创建结果
    """
    import chromadb

    try:
        print(f"[知识库] 开始创建知识库: {name}")
        start_time = asyncio.get_event_loop().time()

        parsed = urlparse(axure_url)
        base_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

        pages_to_process = []
        all_documents = []

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }

        async with aiohttp.ClientSession(headers=headers) as session:
            # 1. 直接获取 sitemap.js 解析站点地图
            print("[知识库] 获取站点地图...")
            sitemap_js_url = base_url.replace('start.html', 'data/sitemap.js')

            try:
                async with session.get(sitemap_js_url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status == 200:
                        js_content = await resp.text()
                        match = re.search(r'\$axure\.loadSitemap\s*\(\s*(\{[\s\S]*\})\s*\)', js_content)
                        if match:
                            sitemap_json = match.group(1)
                            sitemap_json = re.sub(r'(\w+)\s*:', r'"\1":', sitemap_json)
                            sitemap_json = sitemap_json.replace("'", '"')
                            try:
                                sitemap_data = json.loads(sitemap_json)
                                def extract_pages(nodes):
                                    result = []
                                    for node in nodes:
                                        page_name = node.get('pageName') or node.get('name') or node.get('id', '')
                                        if page_name:
                                            result.append({
                                                'name': page_name,
                                                'url': f"{base_url}?p={page_name}",
                                                'page_id': page_name
                                            })
                                        if node.get('children'):
                                            result.extend(extract_pages(node['children']))
                                    return result
                                root_nodes = sitemap_data.get('rootNodes', sitemap_data.get('children', []))
                                pages_to_process = extract_pages(root_nodes)
                                print(f"[知识库] 从 sitemap.js 获取到 {len(pages_to_process)} 个页面")
                            except json.JSONDecodeError as e:
                                print(f"[知识库] sitemap JSON 解析失败: {e}")
                    else:
                        print(f"[知识库] sitemap.js 请求失败: {resp.status}")
            except Exception as e:
                print(f"[知识库] 获取站点地图失败: {e}")

            if not pages_to_process:
                current_page_name = unquote(parsed.query.split('p=')[-1]) if 'p=' in axure_url else "首页"
                pages_to_process.append({
                    'name': current_page_name,
                    'url': axure_url,
                    'page_id': current_page_name
                })
                print(f"[知识库] 使用当前页面: {current_page_name}")

            # 2. 并发获取每个页面的内容
            print(f"[知识库] 开始并发获取 {len(pages_to_process)} 个页面内容...")
            semaphore = asyncio.Semaphore(max_concurrent)

            async def fetch_page_content(page_info):
                async with semaphore:
                    try:
                        page_name = page_info['name']
                        base_path = parsed.path.rsplit('/', 1)[0] if '/' in parsed.path else parsed.path
                        page_html_url = f"{parsed.scheme}://{parsed.netloc}{base_path}/{page_name}.html"
                        async with session.get(page_html_url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                            if resp.status != 200:
                                print(f"[知识库] ✗ {page_name}: HTTP {resp.status}")
                                return None
                            html_content = await resp.text()
                        soup = BeautifulSoup(html_content, 'html.parser')
                        for tag in soup(['script', 'style', 'noscript', 'link', 'meta']):
                            tag.decompose()
                        texts = []
                        tables_data = []
                        for table in soup.find_all('table'):
                            rows = []
                            for tr in table.find_all('tr'):
                                cells = [td.get_text(strip=True) for td in tr.find_all(['td', 'th'])]
                                if cells and any(c for c in cells):
                                    rows.append(cells)
                            if rows:
                                tables_data.append(rows)
                        seen_texts = set()
                        for element in soup.find_all(['div', 'span', 'p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'label', 'a']):
                            text = element.get_text(strip=True)
                            if text and len(text) > 1 and text not in seen_texts:
                                text_lower = text.lower()
                                if not any(kw in text_lower for kw in ['axure', 'prototype', 'preview', 'inspect', 'console']):
                                    seen_texts.add(text)
                                    texts.append(text)

                        md_parts = [f"# {page_name}\n"]
                        for idx, table_rows in enumerate(tables_data):
                            if len(table_rows) >= 1:
                                max_cols = max(len(row) for row in table_rows)
                                header = table_rows[0]
                                header_padded = header + [''] * (max_cols - len(header))
                                md_parts.append("| " + " | ".join(header_padded) + " |")
                                md_parts.append("| " + " | ".join(['---'] * max_cols) + " |")
                                for row in table_rows[1:]:
                                    row_padded = row + [''] * (max_cols - len(row))
                                    row_cleaned = [cell.replace('\n', ' ').replace('|', '\uff5c') for cell in row_padded]
                                    md_parts.append("| " + " | ".join(row_cleaned) + " |")
                                md_parts.append("")
                        for text in texts[:200]:
                            md_parts.append(f"- {text}")

                        markdown_content = "\n".join(md_parts)
                        if markdown_content and len(markdown_content) > 50:
                            print(f"[知识库] ✓ {page_name}: {len(markdown_content)} 字符")
                            return {
                                'page_name': page_name,
                                'page_url': page_info['url'],
                                'page_id': page_info['page_id'],
                                'combined_content': markdown_content
                            }
                        else:
                            print(f"[知识库] ✗ {page_name}: 内容过少")
                            return None
                    except Exception as e:
                        print(f"[知识库] ✗ {page_info['name']}: {e}")
                        return None

            tasks = [fetch_page_content(page) for page in pages_to_process]
            results = await asyncio.gather(*tasks)
            all_documents = [doc for doc in results if doc is not None]
            print(f"[知识库] 成功获取 {len(all_documents)}/{len(pages_to_process)} 个页面")

        if not all_documents:
            return {
                "success": False,
                "error": "没有成功获取任何页面内容"
            }

        # 3. 可选的AI整理
        if use_ai_refine:
            print("[知识库] 开始AI整理内容...")
            for i, doc in enumerate(all_documents):
                try:
                    print(f"[知识库] AI整理 {i+1}/{len(all_documents)}: {doc['page_name']}")
                    refined = await refine_requirements_markdown_async(doc['combined_content'], provider="deepseek")
                    if refined and len(refined) > 100:
                        doc['combined_content'] = refined
                except Exception as e:
                    print(f"[知识库] AI整理失败: {e}")

        # 4. 分块处理
        print("[知识库] 开始分块...")
        all_chunks = []
        for doc in all_documents:
            content = doc['combined_content']
            if len(content) > 7000:
                chunks = split_text_into_chunks(content, chunk_size=6000, chunk_overlap=200)
                for i, chunk in enumerate(chunks):
                    all_chunks.append({
                        'page_name': doc['page_name'],
                        'page_url': doc['page_url'],
                        'page_id': doc['page_id'],
                        'chunk_index': i,
                        'total_chunks': len(chunks),
                        'content': chunk
                    })
            else:
                all_chunks.append({
                    'page_name': doc['page_name'],
                    'page_url': doc['page_url'],
                    'page_id': doc['page_id'],
                    'chunk_index': 0,
                    'total_chunks': 1,
                    'content': content
                })

        print(f"[知识库] 分块完成，共 {len(all_chunks)} 个文本块")

        # 5. 向量化
        print("[知识库] 开始向量化...")
        texts_to_embed = [chunk['content'] for chunk in all_chunks]
        embeddings = get_dashscope_embedding(texts_to_embed)

        # 6. 存储到 Chroma
        client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
        timestamp = get_current_datetime()
        name_hash = hashlib.md5(name.encode('utf-8')).hexdigest()[:8]
        collection_name = f"kb_{name_hash}_{timestamp}"

        collection = client.get_or_create_collection(
            name=collection_name,
            metadata={
                "kb_name": name,
                "display_name": name,
                "axure_url": axure_url,
                "created_at": timestamp,
                "type": "knowledge_base",
                "page_count": len(all_documents)
            }
        )

        ids = [f"chunk_{i}" for i in range(len(all_chunks))]
        metadatas = [{
            "page_name": chunk['page_name'],
            "page_url": chunk['page_url'],
            "page_id": chunk['page_id'],
            "chunk_index": chunk['chunk_index'],
            "total_chunks": chunk['total_chunks']
        } for chunk in all_chunks]
        documents = [chunk['content'] for chunk in all_chunks]

        collection.add(ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas)

        end_time = asyncio.get_event_loop().time()
        elapsed = end_time - start_time
        print(f"[知识库] 创建完成! 耗时: {elapsed:.1f}秒")

        return {
            "success": True,
            "collection_name": collection_name,
            "kb_name": name,
            "page_count": len(all_documents),
            "total_pages": len(all_documents),
            "total_chunks": len(all_chunks),
            "elapsed_seconds": round(elapsed, 1),
            "pages": [{"name": doc['page_name'], "url": doc['page_url']} for doc in all_documents],
            "message": f"知识库 '{name}' 创建成功，共处理 {len(all_documents)} 个页面，生成 {len(all_chunks)} 个文本块，耗时 {elapsed:.1f} 秒"
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": f"创建知识库失败: {str(e)}"
        }


def list_knowledge_bases() -> List[Dict[str, Any]]:
    """列出所有知识库"""
    try:
        import chromadb

        client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
        collections = client.list_collections()

        knowledge_bases = []
        for col in collections:
            metadata = col.metadata or {}
            if metadata.get("type") == "knowledge_base":
                knowledge_bases.append({
                    "collection_name": col.name,
                    "kb_name": metadata.get("kb_name", col.name),
                    "axure_url": metadata.get("axure_url", ""),
                    "created_at": metadata.get("created_at", ""),
                    "page_count": metadata.get("page_count", col.count()),
                    "doc_count": col.count()
                })

        return knowledge_bases
    except Exception as e:
        print(f"[知识库] 列出知识库失败: {e}")
        return []


def delete_knowledge_base(collection_name: str) -> bool:
    """删除知识库"""
    try:
        import chromadb

        client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
        client.delete_collection(name=collection_name)
        return True
    except Exception as e:
        print(f"[知识库] 删除知识库失败: {e}")
        return False


async def recall_from_knowledge_base(
    collection_name: str,
    query_text: str,
    top_k: int = 5
) -> Dict[str, Any]:
    """从知识库召回相关内容"""
    try:
        result = query_chroma_vector_db(
            collection_name=collection_name,
            query_text=query_text,
            top_k=top_k
        )
        return result
    except Exception as e:
        return {
            "success": False,
            "error": f"召回失败: {str(e)}"
        }


async def generate_test_points(
    context: str,
    requirement: str,
    provider: str = "azure"
) -> Dict[str, Any]:
    """根据召回内容生成测试点"""
    prompt = f"""你是一名资深测试工程师。请根据以下需求信息，提取关键的测试点。

## 用户需求
{requirement}

## 相关功能文档
{context}

## 输出要求
请列出所有需要测试的测试点，每个测试点应包含：
1. 测试点名称（简洁明了）
2. 测试目的（验证什么功能/场景）
3. 测试类型（功能测试/边界测试/异常测试/性能测试等）

请直接输出 JSON 格式：
{{
  "test_points": [
    {{
      "name": "测试点名称",
      "purpose": "测试目的",
      "type": "测试类型"
    }}
  ]
}}
"""

    try:
        response = await call_llm_api(prompt, provider=provider)
        content = response.get("choices", [{}])[0].get("message", {}).get("content", "")

        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            test_points = json.loads(json_match.group())
            return {
                "success": True,
                "test_points": test_points.get("test_points", []),
                "raw_content": content
            }
        else:
            return {
                "success": True,
                "test_points": [],
                "raw_content": content
            }
    except Exception as e:
        return {
            "success": False,
            "error": f"生成测试点失败: {str(e)}"
        }


async def generate_test_cases_from_points(
    test_points: List[Dict],
    context: str,
    test_module: str,
    provider: str = "azure"
) -> Dict[str, Any]:
    """根据测试点生成详细测试用例"""
    points_text = "\n".join([
        f"{i+1}. {p['name']} - {p['purpose']} ({p['type']})"
        for i, p in enumerate(test_points)
    ])

    prompt = f"""你是一名资深测试工程师。请根据以下测试点，生成详细的测试用例。

## 模块名称
{test_module}

## 测试点列表
{points_text}

## 相关功能文档
{context}

## 输出要求
为每个测试点生成 1-2 个测试用例，每个测试用例包含：
- case_id: 用例ID（格式 TC-001, TC-002...）
- test_module: 模块名称
- title: 用例标题
- precondition: 前置条件
- steps: 测试步骤（每步一行，用换行符分隔）
- expected_result: 预期结果（每项一行，用换行符分隔）
- priority: 优先级（高/中/低）

请直接输出 JSON 格式：
{{
  "test_cases": [
    {{
      "case_id": "TC-001",
      "test_module": "{test_module}",
      "title": "用例标题",
      "precondition": "前置条件",
      "steps": "1. 步骤1\\n2. 步骤2",
      "expected_result": "1. 预期1\\n2. 预期2",
      "priority": "高"
    }}
  ]
}}
"""

    try:
        response = await call_llm_api(prompt, provider=provider)
        content = response.get("choices", [{}])[0].get("message", {}).get("content", "")

        fixed_content = _fix_json_control_chars(content)

        json_match = re.search(r'\{[\s\S]*\}', fixed_content)
        if json_match:
            test_cases = json.loads(json_match.group())
            return {
                "success": True,
                "test_cases": test_cases,
                "raw_content": content
            }
        else:
            return {
                "success": True,
                "test_cases": {"test_cases": []},
                "raw_content": content
            }
    except Exception as e:
        return {
            "success": False,
            "error": f"生成测试用例失败: {str(e)}"
        }


# ============ Phase 5: 智能召回系统 ============

def add_title_suffix_to_documents(documents: list, suffix: str) -> list:
    """
    给文档列表中的第一个标题添加后缀

    Args:
        documents: 文档列表
        suffix: 要添加的后缀（如 " - 当前页面全量"）

    Returns:
        修改后的文档列表
    """
    if not documents or not documents[0]:
        return documents

    result = []
    for doc in documents:
        if doc:
            lines = doc.split('\n')
            modified = False
            for i, line in enumerate(lines):
                stripped = line.strip()
                if stripped.startswith('#') and not modified:
                    lines[i] = line.rstrip() + ' ' + suffix
                    modified = True
                    break
            result.append('\n'.join(lines))
        else:
            result.append(doc)

    return result


def assemble_incremental_with_context(
    incremental: dict,
    page_full: dict,
    context: dict,
    query: str
) -> str:
    """
    组装增量 + 全量页面 + 模块的完整prompt

    Args:
        incremental: 增量召回结果（蓝色内容）
        page_full: 页面全量召回结果
        context: 模块融合召回结果
        query: 用户查询

    Returns:
        组装后的完整内容
    """
    parts = []

    if context and context.get('documents'):
        parts.append(f"""#  模块功能背景（整体业务逻辑）

请首先理解以下模块的整体业务逻辑和基础规则：


{context['documents'][0]}\n


""")
        print(f"[组装-DEBUG] 添加模块背景: {len(context['documents'][0])} 字符")
    else:
        print(f"[组装-DEBUG] 跳过模块背景: context={context}, documents={context.get('documents') if context else None}")

    if page_full and page_full.get('documents'):
        page_name = page_full.get('metadatas', [{}])[0].get('page_name', '当前页面')
        parts.append(f"""

以下是该页面的完整功能说明：


{page_full['documents'][0]}\n


""")
        print(f"[组装-DEBUG] 添加页面全量: {len(page_full['documents'][0])} 字符")
    else:
        print(f"[组装-DEBUG] 跳过页面全量: page_full={page_full}, documents={page_full.get('documents') if page_full else None}")

    if incremental.get('documents'):
        parts.append(f"""

以下是需要重点测试的本次新增或变更的功能点：


{incremental['documents'][0]}\n


""")
        print(f"[组装-DEBUG] 添加增量需求: {len(incremental['documents'][0])} 字符")
    else:
        print(f"[组装-DEBUG] 跳过增量需求: documents={incremental.get('documents')}")

    result = "\n".join(parts)
    print(f"[组装-DEBUG] 最终组装: {len(parts)} 个部分, 总长度 {len(result)} 字符")
    return result


async def structure_recall_content_with_ai(combined_content: str, query: str, provider: str = "deepseek") -> dict:
    """
    使用AI对召回的内容进行结构化处理

    Args:
        combined_content: 组装后的内容（已格式化的 Markdown）
        query: 用户查询
        provider: LLM提供商

    Returns:
        结构化后的结果 {{
            "structured": "AI结构化后的内容",
            "raw": "原始 Markdown 内容"
        }}
    """
    if not combined_content:
        return {{"structured": "", "raw": ""}}

    raw_content = combined_content

    try:
        print(f"[AI结构化] 开始处理内容, 总长度={len(raw_content)}")
        structured_content = await refine_requirements_markdown_async(raw_content, provider=provider)
        print(f"[AI结构化] 完成, structured 长度={len(structured_content)}")
        return {{"structured": structured_content, "raw": raw_content}}
    except Exception as e:
        print(f"[AI结构化] 结构化失败: {e}")
        import traceback
        traceback.print_exc()
        return {"structured": raw_content, "raw": raw_content}


def format_recall_results(query_results: dict) -> dict:
    """
    格式化召回结果

    Args:
        query_results: ChromaDB查询结果

    Returns:
        格式化后的结果
    """
    if not query_results or not query_results.get('ids') or not query_results['ids'][0]:
        return {"documents": [], "metadatas": []}

    return {
        "documents": query_results.get('documents', [[]])[0],
        "metadatas": query_results.get('metadatas', [[]])[0],
        "distances": query_results.get('distances', [[]])[0]
    }


async def smart_recall_from_knowledge_base(
    collection_name: str,
    query: str,
    page_key: Optional[str] = None,
    recall_strategy: str = "incremental_with_context",
    top_k: int = 5,
    use_ai_structure: bool = False,
    ai_provider: str = "deepseek"
) -> dict:
    """
    智能召回：根据查询内容自动选择最佳召回策略

    Args:
        collection_name: collection名称
        query: 查询文本
        page_key: 页面key（可选）
        recall_strategy: 召回策略 (auto | incremental_with_context | page_level | module_level)
        top_k: 召回数量
        use_ai_structure: 是否使用AI结构化召回内容
        ai_provider: AI服务提供商

    Returns:
        召回结果，包含原始内容和AI结构化内容（如果启用）
    """
    try:
        import chromadb

        client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
        collection = client.get_collection(collection_name)

        print(f"[智能召回] 召回策略: {recall_strategy}, 查询: {query[:50]}...")

        # 使用 DashScope embedding 对查询文本进行向量化
        query_embedding = get_dashscope_embedding([query])[0]
        print(f"[智能召回] Query embedding 维度: {len(query_embedding)}")

        results = {"strategy": recall_strategy}

        if recall_strategy == "incremental_with_context":
            # 策略1: 蓝色 + 全量 + 模块三合一

            # 1.1 召回增量内容（蓝色）
            where_filter = MetadataFilter.incremental_only()
            if page_key:
                where_filter = MetadataFilter.page_incremental(page_key)

            incremental_results = collection.query(
                query_embeddings=[query_embedding],
                where=where_filter,
                n_results=top_k
            )
            incremental_formatted = format_recall_results(incremental_results)

            # 1.2 从增量结果中提取 page_key，并召回页面全量内容
            page_full_formatted = None
            actual_page_key = page_key

            if incremental_formatted.get('metadatas') and not actual_page_key:
                page_metadata = incremental_formatted['metadatas'][0]
                actual_page_key = page_metadata.get('page_key', '')
                print(f"[智能召回-DEBUG] 从增量metadata提取page_key: '{actual_page_key}'")

            if actual_page_key:
                print(f"[智能召回-DEBUG] 准备查询页面全量: page_key='{actual_page_key}'")
                page_full_results = collection.query(
                    query_embeddings=[query_embedding],
                    where=MetadataFilter.page_full(actual_page_key),
                    n_results=top_k
                )
                page_full_formatted = format_recall_results(page_full_results)

                if page_full_formatted.get('documents'):
                    sample = page_full_formatted['documents'][0][:500]
                    print(f"[智能召回-DEBUG] 页面全量内容样本:\n{sample}")
            else:
                print(f"[智能召回-DEBUG] 未获取到page_key，跳过页面全量查询")

            # 1.3 获取模块上下文
            print(f"[智能召回-DEBUG] 开始获取模块上下文...")

            if incremental_formatted.get('metadatas'):
                page_metadata = incremental_formatted['metadatas'][0]
                module_name = page_metadata.get('module', '')

                context_formatted = None
                if module_name:
                    print(f"[智能召回-DEBUG] 准备查询模块: '{module_name}'")
                    module_embedding = get_dashscope_embedding([module_name])[0]
                    context_results = collection.query(
                        query_embeddings=[module_embedding],
                        where=MetadataFilter.module(module_name),
                        n_results=1
                    )
                    context_formatted = format_recall_results(context_results)
                    if context_formatted.get('documents'):
                        context_formatted['documents'] = add_title_suffix_to_documents(
                            context_formatted['documents'], "- 关联需求"
                        )

                # 组装结果
                results['incremental'] = incremental_formatted
                results['page_full'] = page_full_formatted
                results['context'] = context_formatted

                results['combined'] = assemble_incremental_with_context(
                    incremental=incremental_formatted,
                    page_full=page_full_formatted,
                    context=context_formatted,
                    query=query
                )

                results['total_chunks'] = len(incremental_formatted.get('documents', []))
            else:
                # 没有增量，降级为普通召回
                print(f"[智能召回] 未找到增量内容，降级为 page_level")
                return await smart_recall_from_knowledge_base(
                    collection_name=collection_name,
                    query=query,
                    page_key=page_key,
                    recall_strategy="page_level",
                    top_k=top_k
                )

        # AI结构化处理（如果启用）
        if use_ai_structure:
            content_to_structure = None

            if results.get('combined'):
                content_to_structure = results['combined']
                print(f"[智能召回] 使用 combined 内容进行AI结构化...")
            elif results.get('data') and results['data'].get('documents'):
                documents = results['data']['documents']
                content_to_structure = "\n\n---\n\n".join(documents)
                print(f"[智能召回] 使用 data 内容进行AI结构化...")

            if content_to_structure:
                print(f"[智能召回] 正在进行AI结构化处理...")
                structured = await structure_recall_content_with_ai(content_to_structure, query, ai_provider)
                results['structured'] = structured['structured']
                results['raw'] = structured['raw']
                print(f"[智能召回] AI结构化完成")

        return results

    except Exception as e:
        print(f"[智能召回] 召回失败: {e}")
        import traceback
        traceback.print_exc()
        return {
            "strategy": recall_strategy,
            "error": str(e)
        }
