# -*- coding: utf-8 -*-
"""
增强版知识库管理功能 - Phase 2-5
包含：
- Phase 2: 增强版Axure解析
- Phase 3: 分层向量化存储
- Phase 4: 大模型关联分析
- Phase 5: 智能召回系统
"""

import os
import json
import asyncio
import time
import hashlib
from datetime import datetime
from typing import Dict, Any, List, Optional
from urllib.parse import urlparse, unquote, parse_qs

import aiohttp
from bs4 import BeautifulSoup

# 导入基础工具
from utils import (
    PageData,
    CHROMA_DB_PATH,
)

# 从 utils_sitemap_kb 导入共享函数
from utils_sitemap_kb import (
    analyze_page_relationships_with_ai,
    build_three_tier_vectors,
    store_vectors_to_chroma
)


async def parse_axure_all_pages_enhanced(
    axure_url: str,
    username: str = "",
    password: str = "",
    max_concurrent: int = 1  # 串行执行，避免并发导致的增量检测不稳定
) -> List[PageData]:
    """
    增强版Axure解析：获取所有页面并分离全量/增量

    使用sitemap.js解析获取所有页面列表

    Args:
        axure_url: Axure URL
        username: 登录用户名（可选）
        password: 登录密码（可选）
        max_concurrent: 最大并发数

    Returns:
        PageData列表
    """
    print(f"[增强解析] 开始解析Axure: {axure_url}")
    print(f"[增强解析] 使用sitemap.js解析方式")

    # 直接使用sitemap知识库的解析函数
    from utils_sitemap_kb import fetch_all_pages_from_sitemap

    pages_data = await fetch_all_pages_from_sitemap(
        axure_url=axure_url,
        username=username,
        password=password,
        max_concurrent=max_concurrent
    )

    print(f"[增强解析] 解析完成，共 {len(pages_data)} 个页面")

    return pages_data






async def create_enhanced_knowledge_base(
    name: str,
    axure_url: str,
    username: str = "",
    password: str = "",
    use_ai_analysis: bool = True,
    max_concurrent: int = 5
) -> Dict[str, Any]:
    """
    创建增强版知识库

    Args:
        name: 知识库名称
        axure_url: Axure URL
        username: 登录用户名
        password: 登录密码
        use_ai_analysis: 是否使用AI分析页面关联
        max_concurrent: 最大并发数

    Returns:
        创建结果

    Note:
        创建知识库时不进行AI结构化（避免太慢），AI结构化在召回时进行
    """
    start_time = time.time()

    try:
        print(f"[增强知识库] 开始创建知识库: {name}")
        print(f"[增强知识库] AI分析: {use_ai_analysis}")

        # Step 1: 解析所有页面
        print(f"[增强知识库] Step 1: 解析Axure页面")
        pages = await parse_axure_all_pages_enhanced(
            axure_url=axure_url,
            username=username,
            password=password,
            max_concurrent=max_concurrent
        )

        if not pages:
            return {
                "success": False,
                "error": "未获取到任何页面内容"
            }

        # Step 2: AI分析页面关联关系
        analysis = None
        if use_ai_analysis:
            print(f"[增强知识库] Step 2: AI分析页面关联")
            analysis = await analyze_page_relationships_with_ai(pages)

            # 更新页面的module信息
            for page in pages:
                page.module = analysis.get('page_modules', {}).get(page.page_key, "")

        # Step 3: 构建三层向量（不做AI结构化，召回时再处理）
        print(f"[增强知识库] Step 3: 构建分层向量")
        vectors = build_three_tier_vectors(pages, analysis)

        # Step 4: 存储到ChromaDB
        print(f"[增强知识库] Step 4: 存储向量到ChromaDB")
        # 使用 MD5 hash 避免中文导致的 collection 名称无效
        name_hash = hashlib.md5(name.encode('utf-8')).hexdigest()[:8]
        collection_name = f"enhanced_kb_{name_hash}_{int(time.time())}"

        success = await store_vectors_to_chroma(
            collection_name,
            vectors,
            kb_name=name,
            metadata_type="enhanced_knowledge_base"
        )

        if not success:
            return {
                "success": False,
                "error": "向量存储失败"
            }

        elapsed_time = time.time() - start_time

        # 统计信息
        incremental_count = sum(1 for p in pages if p.has_incremental)
        module_count = len(analysis.get('modules', {})) if analysis else 0

        result = {
            "success": True,
            "collection_name": collection_name,
            "kb_name": name,
            "total_pages": len(pages),
            "incremental_pages": incremental_count,
            "total_vectors": len(vectors),
            "modules": list(analysis.get('modules', {}).keys()) if analysis else [],
            "module_count": module_count,
            "elapsed_seconds": round(elapsed_time, 1),
            "message": f"知识库 '{name}' 创建成功，处理 {len(pages)} 个页面（{incremental_count} 个含增量），生成 {len(vectors)} 个向量，耗时 {elapsed_time:.1f} 秒"
        }

        print(f"[增强知识库] 创建完成: {result['message']}")
        return result

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": f"创建知识库失败: {str(e)}"
        }


# ============ Phase 5: 智能召回系统 ============
# format_recall_results 从 utils_sitemap_kb 导入（如果需要）


def assemble_incremental_with_context(
    incremental: dict,
    page_full: dict,
    context: dict,
    query: str
) -> str:
    """
    组装增量 + 页面全量 + 模块上下文的完整prompt

    Args:
        incremental: 增量召回结果
        page_full: 页面全量需求召回结果
        context: 模块上下文召回结果
        query: 用户查询

    Returns:
        组装后的完整内容
    """
    parts = []

    # 1. 添加页面全量需求（保留原始标题格式）
    if page_full.get('documents'):
        parts.append(f"""{page_full['documents'][0]}

""")

    # 2. 添加增量需求（保留原始标题格式）
    if incremental.get('documents'):
        parts.append(f"""{incremental['documents'][0]}

""")

    # 3. 添加模块上下文（保留原始标题格式）
    if context.get('documents'):
        parts.append(f"""{context['documents'][0]}

""")

    # 4. 添加提示
    parts.append(f"""## **__重要提示__**

在生成测试用例时，请：

1. **理解页面全量**：基于页面全量需求理解该页面完整的业务逻辑、数据流转、约束条件
2. **关注增量**：重点测试本次增量需求中的新增/变更功能
3. **参考模块上下文**：基于模块完整需求理解跨页面的业务流程和依赖关系
4. **结合生成**：将增量、页面全量和模块上下文结合，生成完整的测试用例
   - 测试增量功能本身
   - 测试增量功能与页面现有功能的集成
   - 测试增量功能与模块内其他页面的关联影响
   - 测试增量功能受到的全量约束（如限额、验证等）

用户需求：{query}
""")

    return "\n".join(parts)


def list_enhanced_knowledge_bases() -> List[Dict[str, Any]]:
    """
    列出所有增强版知识库

    Returns:
        知识库列表
    """
    try:
        import chromadb

        client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
        collections = client.list_collections()

        knowledge_bases = []
        for col in collections:
            metadata = col.metadata or {}
            # 只返回增强版知识库
            if metadata.get("type") == "enhanced_knowledge_base":
                # 优先使用 metadata 中的 kb_name（保存的原始中文名称）
                kb_name = metadata.get("kb_name", col.name)
                # 如果 metadata 中没有 kb_name，尝试从 collection 名称解析
                if not metadata.get("kb_name") and col.name.startswith("enhanced_kb_"):
                    parts = col.name.split("_")
                    if len(parts) >= 3:
                        kb_name = "_".join(parts[2:-1])  # 去掉前缀和时间戳

                knowledge_bases.append({
                    "collection_name": col.name,
                    "kb_name": kb_name,
                    "doc_count": col.count(),
                    "created_at": metadata.get("created_at", ""),
                    "is_enhanced": True
                })

        return knowledge_bases

    except Exception as e:
        print(f"[知识库] 列出知识库失败: {e}")
        return []


# ============ 删除知识库 ============

def delete_enhanced_knowledge_base(collection_name: str) -> bool:
    """
    删除知识库

    Args:
        collection_name: collection名称

    Returns:
        是否成功
    """
    try:
        import chromadb

        client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
        client.delete_collection(name=collection_name)
        print(f"[知识库] 已删除知识库: {collection_name}")
        return True

    except Exception as e:
        print(f"[知识库] 删除知识库失败: {e}")
        return False
