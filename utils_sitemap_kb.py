# -*- coding: utf-8 -*-
"""
基于站点地图(Sitemap)的Axure知识库管理
完整流程：sitemap.js解析 → 并发获取页面 → 向量化 → 存储 → 智能召回
"""

import os
import json
import re
import hashlib
import asyncio
import time
from datetime import datetime
from typing import Dict, Any, List, Optional
from urllib.parse import urlparse, unquote, parse_qs, quote

import aiohttp
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

# 导入基础工具
from utils import (
    PageData, MetadataFilter,
    extract_blue_text_from_html,
    format_page_to_markdown,
    CHROMA_DB_PATH,
    call_llm_api,
    KNOWLEDGE_BASE_PATH,
    get_dashscope_embedding
)

# 全局 playwright 实例（整个程序生命周期只创建一次）
_playwright_instance = None
_browser_pool = {}
_max_browsers = 3
_browser_idle_timeout = 300
_lock = asyncio.Lock()

# 上下文池：为每个任务提供独立的 BrowserContext
_context_pool = {}
_context_lock = asyncio.Lock()


async def get_browser():
    """获取或创建浏览器实例（支持复用和空闲超时）"""
    global _playwright_instance, _browser_pool

    if _playwright_instance is None:
        _playwright_instance = await async_playwright().start()

    async with _lock:
        current_time = time.time()
        # 清理空闲超时的浏览器
        for browser_id in list(_browser_pool.keys()):
            browser, last_used = _browser_pool[browser_id]
            if current_time - last_used > _browser_idle_timeout:
                try:
                    await browser.close()
                except:
                    pass
                del _browser_pool[browser_id]

        # 如果有可用浏览器，返回最近使用的
        if _browser_pool:
            most_recent_id = max(_browser_pool.keys(), key=lambda k: _browser_pool[k][1])
            browser, _ = _browser_pool[most_recent_id]
            _browser_pool[most_recent_id] = (browser, time.time())
            return browser

        # 创建新浏览器并加入池
        browser = await _playwright_instance.chromium.launch(headless=True)
        browser_id = f"browser_{int(time.time() * 1000)}"
        _browser_pool[browser_id] = (browser, time.time())

        return browser


async def get_isolated_context():
    """
    获取独立的浏览器上下文（BrowserContext）
    每个上下文完全隔离，避免并发任务之间的状态干扰
    """
    browser = await get_browser()

    async with _context_lock:
        current_time = time.time()

        # 清理空闲超时的上下文
        for ctx_id in list(_context_pool.keys()):
            ctx, last_used = _context_pool[ctx_id]
            if current_time - last_used > 60:  # 上下文超时时间更短（60秒）
                try:
                    await ctx.close()
                except:
                    pass
                del _context_pool[ctx_id]

        # 如果有可用上下文，返回最近使用的
        if _context_pool:
            most_recent_id = max(_context_pool.keys(), key=lambda k: _context_pool[k][1])
            context, _ = _context_pool[most_recent_id]
            _context_pool[most_recent_id] = (context, time.time())
            return context

        # 创建新上下文并加入池
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )
        ctx_id = f"context_{int(time.time() * 1000)}"
        _context_pool[ctx_id] = (context, time.time())

        return context


# ==================== Phase 1: 站点地图解析 ====================

async def parse_sitemap_js(axure_url: str, username: str = "", password: str = "", timeout: int = 30) -> List[Dict[str, str]]:
    """
    使用浏览器方式解析Axure的站点地图，获取所有页面列表

    Args:
        axure_url: Axure URL (如: http://example.com/start.html?p=xxx)
        username: 登录用户名（可选）
        password: 登录密码（可选）
        timeout: 请求超时时间(秒)

    Returns:
        页面列表，每个元素包含: {name, url, page_id}
    """
    print(f"[站点地图] 开始解析（浏览器方式）: {axure_url}")
    if username:
        print(f"[站点地图] 使用认证: {username}")

    context = None
    page = None

    try:
        # 使用独立的上下文
        context = await get_isolated_context()
        page = await context.new_page()

        # 访问页面
        await page.goto(axure_url, wait_until='networkidle', timeout=timeout * 1000)

        # 检查是否需要登录
        if '认证' in await page.title():
            print(f"[站点地图] 检测到需要认证，正在登录...")
            try:
                # 尝试第一种定位方式
                await page.locator('input[placeholder="请输入您的用户名"]').fill(username)
                await page.locator('input[placeholder="请输入您的密码"]').fill(password)
            except Exception:
                # 第一种方式失败，尝试备用定位方式
                await page.get_by_role('textbox', name='用户名').fill(username)
                await page.get_by_role('textbox', name='密码').fill(password)

            await page.get_by_role('button', name='登录').click()
            await page.wait_for_load_state('networkidle')
            await asyncio.sleep(2)
            print(f"[站点地图] 登录成功")

        # 获取页面内容
        content = await page.content()
        soup = BeautifulSoup(content, 'html.parser')

        # 提取 sitemap
        sitemap_tree = soup.find('ul', class_='sitemapTree')
        if not sitemap_tree:
            print(f"[站点地图] 未找到站点地图元素")
            return []

        # 递归解析树
        def parse_node(li_element, level=0):
            node = {
                'name': '',
                'url': '',
                'page_id': '',
                'level': level,
                'children': []
            }

            link_container = li_element.find('div', class_='sitemapPageLinkContainer')
            if link_container:
                page_link = link_container.find('a', class_='sitemapPageLink')
                if page_link:
                    nodeurl = page_link.get('nodeurl', '')
                    page_name = page_link.find('span', class_='sitemapPageName')
                    if page_name:
                        node['name'] = page_name.get_text(strip=True)

                    # 构建完整的 URL: start.html?p=页面名称
                    if nodeurl:
                        # 去掉 .html 后缀
                        page_name_clean = nodeurl.replace('.html', '')
                        node['page_id'] = page_name_clean
                        # URL 编码页面名称
                        page_name_encoded = quote(page_name_clean)
                        # 构建完整 URL
                        parsed_url = urlparse(axure_url)
                        base_url = f"{parsed_url.scheme}://{parsed_url.netloc}/{parsed_url.path.split('/')[1]}/"
                        node['url'] = f"{base_url}start.html?p={page_name_encoded}"
                else:
                    page_name = link_container.find('span', class_='sitemapPageName')
                    if page_name:
                        node['name'] = page_name.get_text(strip=True)

            child_ul = li_element.find('ul')
            if child_ul:
                for child_li in child_ul.find_all('li', recursive=False):
                    child_node = parse_node(child_li, level + 1)
                    if child_node['name']:
                        node['children'].append(child_node)

            return node

        # 构建页面列表（扁平化）
        pages = []

        def flatten_tree(nodes):
            for node in nodes:
                if node['url']:  # 有URL的是页面
                    pages.append({
                        'name': node['name'],
                        'url': node['url'],
                        'page_id': node['page_id']
                    })
                if node['children']:
                    flatten_tree(node['children'])

        # 解析根节点
        root_lis = sitemap_tree.find_all('li', class_='sitemapNode', recursive=False)
        for li in root_lis:
            node = parse_node(li)
            if node['children']:
                flatten_tree(node['children'])
            elif node['url']:
                pages.append({
                    'name': node['name'],
                    'url': node['url'],
                    'page_id': node['page_id']
                })

        print(f"[站点地图] 成功解析 {len(pages)} 个页面")
        print(f"[站点地图] {'='*70}")
        for i, page in enumerate(pages):
            print(f"[站点地图] {i+1:3d}. {page['name']}")
            print(f"[站点地图]     URL: {page['url']}")
        print(f"[站点地图] {'='*70}")

        return pages

    except Exception as e:
        print(f"[站点地图] 解析失败: {e}")
        import traceback
        traceback.print_exc()
        return []

    finally:
        if page:
            try:
                await page.close()
            except:
                pass
        if context:
            try:
                await context.close()
            except:
                pass


# ==================== Phase 2: 并发获取页面内容 ====================

async def fetch_page_content_http(
    page_info: Dict[str, str],
    base_url: str,
    semaphore: asyncio.Semaphore,
    username: str = "",
    password: str = "",
    retry_count: int = 0,
    max_retries: int = 2
) -> Optional[Dict[str, Any]]:
    """
    使用浏览器方式获取Axure页面内容

    Args:
        page_info: 页面信息 {name, url, page_id}
        base_url: 基础URL
        semaphore: 并发控制信号量
        username: 登录用户名（可选）
        password: 登录密码（可选）
        retry_count: 当前重试次数
        max_retries: 最大重试次数

    Returns:
        页面数据字典
    """
    async with semaphore:
        context = None
        page_obj = None

        try:
            page_name = page_info['name']
            page_url = page_info['url']

            # 调试：打印正在获取的页面URL
            print(f"[页面获取] 正在获取: {page_url}")

            # 使用独立的浏览器上下文（关键修复：避免并发上下文混乱）
            context = await get_isolated_context()
            page_obj = await context.new_page()

            # 访问页面
            await page_obj.goto(page_url, wait_until='networkidle', timeout=30000)

            # 额外等待，确保Axure动态内容加载完成
            # Linux 上可能需要更长的等待时间
            await asyncio.sleep(3)

            # 等待 iframe 加载完成 - 改进版：等待特定条件而非固定时间
            max_wait_cycles = 5
            iframe_loaded = False
            for cycle in range(max_wait_cycles):
                try:
                    # 等待至少一个 iframe 加载完成
                    await page_obj.wait_for_selector('iframe', timeout=10000)

                    # 检查 iframe 是否真正加载（不是 about:blank）
                    frames = page_obj.frames
                    for frame in frames:
                        if frame.url and 'about:blank' not in frame.url and frame != page_obj.main_frame:
                            iframe_loaded = True
                            break

                    if iframe_loaded:
                        print(f"[页面获取] 检测到 iframe 已加载，额外等待确保样式渲染...")
                        # 等待样式完全渲染（重要！）
                        await asyncio.sleep(3)
                        break
                    else:
                        print(f"[页面获取] 循环 {cycle + 1}: iframe 存在但未加载内容，等待3秒...")
                        await asyncio.sleep(3)
                except:
                    print(f"[页面获取] 循环 {cycle + 1}: 未检测到 iframe，等待3秒...")
                    await asyncio.sleep(3)

            # 检查是否需要登录
            if '认证' in await page_obj.title():
                print(f"[页面获取] 检测到需要认证，正在登录...")
                try:
                    await page_obj.locator('input[placeholder="请输入您的用户名"]').fill(username)
                    await page_obj.locator('input[placeholder="请输入您的密码"]').fill(password)
                except Exception:
                    await page_obj.get_by_role('textbox', name='用户名').fill(username)
                    await page_obj.get_by_role('textbox', name='密码').fill(password)

                await page_obj.get_by_role('button', name='登录').click()
                await page_obj.wait_for_load_state('networkidle')
                await asyncio.sleep(2)  # 登录后额外等待

            # 获取iframe内容
            print(f"[页面获取] 开始获取主内容区域...")

            frames = page_obj.frames
            print(f"[页面获取] 共发现 {len(frames)} 个frames")

            # 改进的 iframe 选择逻辑：优先选择包含实际内容的 frame
            candidate_frames = []

            for i, frame in enumerate(frames):
                try:
                    frame_url = frame.url or ''
                    frame_name = frame.name or ''

                    # 跳过主frame
                    if frame == page_obj.main_frame:
                        print(f"[页面获取] Frame {i}: 跳过主frame")
                        continue

                    # 跳过 about:blank 的 frame
                    if 'about:blank' in frame_url:
                        print(f"[页面获取] Frame {i}: 跳过 about:blank frame")
                        continue

                    # 跳过sitemap/导航相关的frame
                    frame_url_lower = frame_url.lower()
                    frame_name_lower = frame_name.lower()
                    if any(keyword in frame_url_lower or keyword in frame_name_lower
                           for keyword in ['sitemap', 'toc', 'nav', 'menu', 'tree', 'left', 'console']):
                        print(f"[页面获取] Frame {i}: 跳过导航frame (name={frame_name})")
                        continue

                    # 获取frame内容
                    content = await frame.content()
                    content_len = len(content)

                    print(f"[页面获取] Frame {i}: name={frame_name}, url={frame_url[:60]}, 长度={content_len}")

                    # 只考虑内容长度合理的 frame (大于1000字符)
                    if content_len > 1000:
                        # 计算得分：考虑内容长度和是否包含 Axure 特征
                        score = content_len
                        # 如果包含 id 属性，加分（Axure 特征）
                        if 'id=' in content or 'axure' in content.lower():
                            score += 10000

                        candidate_frames.append({
                            'frame': frame,
                            'content': content,
                            'score': score,
                            'name': frame_name,
                            'url': frame_url
                        })
                        print(f"[页面获取]   候选frame: 得分={score}")

                except Exception as e:
                    print(f"[页面获取] Frame {i} 处理失败: {e}")
                    continue

            # 选择得分最高的 frame
            if candidate_frames:
                # 按得分排序
                candidate_frames.sort(key=lambda x: x['score'], reverse=True)
                best = candidate_frames[0]
                html_content = best['content']
                target_frame = best['frame']
                print(f"[页面获取] 使用最佳frame: {best['name']}, 内容长度: {len(html_content)}")
            else:
                # 如果没有找到合适的iframe，尝试直接用JavaScript获取页面内容
                print(f"[页面获取] 未找到合适的iframe，尝试直接获取页面内容")
                html_content = await page_obj.content()
                target_frame = page_obj

            print(f"[页面获取] 最终HTML内容长度: {len(html_content)}")

            # 如果HTML内容仍然很少，直接用JavaScript提取文本
            if len(html_content) < 1000:
                print(f"[页面获取] HTML内容过少，使用JavaScript直接提取文本...")
                try:
                    direct_text = await target_frame.evaluate("""
                    () => {
                        // 获取所有可见文本
                        const body = document.body;
                        if (!body) return '';

                        // 移除script和style标签
                        const clone = body.cloneNode(true);
                        const scripts = clone.querySelectorAll('script, style, noscript');
                        scripts.forEach(el => el.remove());

                        return clone.innerText || clone.textContent || '';
                    }
                    """)

                    print(f"[页面获取] JavaScript提取的文本长度: {len(direct_text)}")

                    # 如果直接文本提取成功，构建简单的内容
                    if len(direct_text) > 100:
                        lines = [line.strip() for line in direct_text.split('\n') if line.strip()]
                        # 去重
                        seen = set()
                        unique_lines = []
                        for line in lines:
                            if line not in seen and len(line) > 1:
                                seen.add(line)
                                unique_lines.append(line)

                        full_content = f"# {page_name}\n\n## 页面内容\n\n" + "\n".join(f"- {line}" for line in unique_lines[:500])

                        print(f"[页面获取] ✓ {page_name}: {len(full_content)} 字符 (直接提取)")
                        return {
                            'page_name': page_name,
                            'page_key': page_name,
                            'page_url': page_info['url'],
                            'page_id': page_info['page_id'],
                            'full_content': full_content,
                            'incremental_content': '',
                            'has_incremental': False,
                            'blue_texts': [],
                            'tables_count': 0
                        }
                except Exception as js_err:
                    print(f"[页面获取] JavaScript提取失败: {js_err}")

            # 正常处理：使用BeautifulSoup解析
            from bs4 import BeautifulSoup

            # ============= 使用JavaScript获取computed color =============
            blue_texts_from_js = set()

            # 关键改进：等待样式完全加载后再检测颜色
            print(f"[页面获取] 等待样式完全加载...")
            try:
                # 等待 document.readyState 为 complete
                await target_frame.wait_for_load_state('domcontentloaded')
                # 额外等待确保样式加载
                await asyncio.sleep(2)
                print(f"[页面获取] 样式加载完成，开始颜色检测...")

                color_info = await target_frame.evaluate("""
                () => {
                    const results = [];
                    const elements = document.querySelectorAll('div, span, p, h1, h2, h3, h4, h5, h6, li, a, td, th, label');
                    for (const el of elements) {
                        const text = el.innerText ? el.innerText.trim() : '';
                        if (text && text.length > 1 && text.length < 500) {
                            const style = window.getComputedStyle(el);
                            const color = style.color;
                            results.push({
                                text: text.substring(0, 200),
                                color: color
                            });
                        }
                    }
                    return results;
                }
                """)

                print(f"[页面获取-DEBUG] JS返回了 {len(color_info) if color_info else 0} 条颜色信息")

                if color_info:
                    for info in color_info:
                        color = info.get('color', '')
                        text = info.get('text', '').strip()
                        if not text or not color:
                            continue

                        # 调试：打印前几条颜色信息
                        if len(blue_texts_from_js) < 3:
                            print(f"[页面获取-DEBUG] 颜色: {color}, 文本: {text[:50]}")

                        is_colored = False
                        # 支持多种颜色格式
                        if 'rgb' in color.lower():
                            try:
                                # 处理 rgb(r, g, b) 和 rgba(r, g, b, a)
                                color_clean = color.lower()
                                parts = color_clean.replace('rgb(', '').replace('rgba(', '').replace(')', '').split(',')
                                r, g, b = int(parts[0].strip()), int(parts[1].strip()), int(parts[2].strip())
                                # 蓝色: B高(>150), R低(<150)
                                if b > 150 and r < 150:
                                    is_colored = True
                                # 红色: R高(>200), G和B低(<100)
                                elif r > 200 and g < 100 and b < 100:
                                    is_colored = True
                            except Exception as color_err:
                                print(f"[页面获取-DEBUG] 解析颜色失败: {color}, 错误: {color_err}")
                                pass
                        # 检查十六进制颜色
                        elif color.startswith('#'):
                            try:
                                hex_color = color[1:]
                                if len(hex_color) == 3:
                                    # 缩写格式 #fff
                                    r = int(hex_color[0]*2, 16)
                                    g = int(hex_color[1]*2, 16)
                                    b = int(hex_color[2]*2, 16)
                                elif len(hex_color) == 6:
                                    # 标准格式 #ffffff
                                    r = int(hex_color[0:2], 16)
                                    g = int(hex_color[2:4], 16)
                                    b = int(hex_color[4:6], 16)
                                else:
                                    continue
                                # 蓝色判断
                                if b > 150 and r < 150:
                                    is_colored = True
                                # 红色判断
                                elif r > 200 and g < 100 and b < 100:
                                    is_colored = True
                            except:
                                pass

                        if is_colored:
                            blue_texts_from_js.add(text)
                            for line in text.split('\n'):
                                line = line.strip()
                                if line and len(line) > 1:
                                    blue_texts_from_js.add(line)

                print(f"[页面获取] JS识别到 {len(blue_texts_from_js)} 条蓝色/红色文本")
                if len(blue_texts_from_js) > 0:
                    print(f"[页面获取-DEBUG] 前3条: {list(blue_texts_from_js)[:3]}")
            except Exception as js_err:
                print(f"[页面获取] JS获取computed color失败: {js_err}")
                import traceback
                traceback.print_exc()

            # 使用BeautifulSoup解析
            soup = BeautifulSoup(html_content, 'html.parser')

            # 移除不需要的标签
            for tag in soup(['script', 'style', 'noscript', 'link', 'meta']):
                tag.decompose()

            # 提取蓝色文字（增量需求）
            blue_texts = []

            # inline style检测函数
            def check_color_in_style(style_str):
                normalized = style_str.lower().replace(' ', '')
                color_patterns = [
                    'color:blue', 'color:#0000ff', 'color:#00f',
                    'color:rgb(0,0,255)', 'color:#0066cc', 'color:#0066ff',
                    'color:#3366ff', 'color:#1e90ff', 'color:#4169e1',
                    'color:#0000cd', 'color:#000080', 'color:#0080ff',
                    'color:#4a90e2', 'color:#5b9bd5', 'color:#2196f3',
                    'color:dodgerblue', 'color:royalblue',
                    'color:red', 'color:#ff0000', 'color:#f00',
                    'color:rgb(255,0,0)', 'color:#dc143c', 'color:#ff4500',
                ]
                return any(p in normalized for p in color_patterns)

            def check_element_color(element):
                style = element.get('style', '')
                if style and check_color_in_style(style):
                    return True
                parent = element.parent
                for _ in range(5):
                    if parent is None or parent.name is None:
                        break
                    parent_style = parent.get('style', '')
                    if parent_style and check_color_in_style(parent_style):
                        return True
                    parent = parent.parent
                return False

            # 收集所有增量文本
            seen_blue = set()
            for element in soup.find_all(['div', 'span', 'p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'a', 'td', 'th', 'label']):
                text = element.get_text(strip=True)
                if not text or len(text) < 2 or text in seen_blue:
                    continue
                # inline style检测
                is_increment = check_element_color(element)
                # JS computed color检测
                if not is_increment and text.strip() in blue_texts_from_js:
                    is_increment = True
                if not is_increment:
                    for blue_text in blue_texts_from_js:
                        if text.strip() in blue_text:
                            is_increment = True
                            break
                if is_increment:
                    seen_blue.add(text)
                    blue_texts.append(text)

            # 提取表格数据
            tables_data = []
            for table in soup.find_all('table'):
                rows = []
                for tr in table.find_all('tr'):
                    cells = [td.get_text(strip=True) for td in tr.find_all(['td', 'th'])]
                    if cells and any(c for c in cells):
                        rows.append(cells)
                if rows:
                    tables_data.append(rows)

            # 提取所有文本元素 - 改进版本，保留更多内容
            texts = []
            seen_texts = set()

            # 递归获取所有文本
            def extract_all_texts(element):
                if hasattr(element, 'name') and element.name in ['script', 'style', 'noscript', 'link', 'meta']:
                    return

                # 检查是否有子元素 - BeautifulSoup的children是迭代器
                try:
                    children = list(element.children) if hasattr(element, 'children') else []
                    if len(children) > 0:
                        for child in children:
                            extract_all_texts(child)
                except:
                    pass

                # 提取当前元素的文本
                if hasattr(element, 'get_text'):
                    text = element.get_text(strip=True)
                    if text and len(text) > 1 and len(text) < 1000 and text not in seen_texts:
                        text_lower = text.lower()
                        skip_keywords = ['axure', 'prototype', 'preview', 'inspect', 'console']
                        if not any(kw in text_lower for kw in skip_keywords):
                            seen_texts.add(text)
                            texts.append(text)

            extract_all_texts(soup)

            print(f"[页面获取] 提取到 {len(texts)} 个文本片段")

            # 构建Markdown内容
            md_parts=[f'<span style="color: blue;"># {page_name} --- 全量需求</span>\n']
            # 添加表格
            if tables_data:
                md_parts.append("## 数据表格\n")
                for table_rows in tables_data:
                    if len(table_rows) >= 1:
                        max_cols = max(len(row) for row in table_rows)
                        header = table_rows[0]
                        header_padded = header + [''] * (max_cols - len(header))
                        md_parts.append("| " + " | ".join(header_padded) + " |")
                        md_parts.append("| " + " | ".join(['---'] * max_cols) + " |")
                        for row in table_rows[1:]:
                            row_padded = row + [''] * (max_cols - len(row))
                            row_cleaned = [cell.replace('\n', ' ').replace('|', '｜') for cell in row_padded]
                            md_parts.append("| " + " | ".join(row_cleaned) + " |")
                        md_parts.append("")

            # 添加文本内容
            for text in texts[:500]:  # 增加到500个
                md_parts.append(f"- {text}")

            full_content = "\n".join(md_parts)

            # 构建增量内容
            incremental_content = ""
            if blue_texts:
                incremental_parts = [f'<span style="color: blue;"># {page_name} --- 增量需求</span>\n']
                for blue_text in blue_texts:
                    incremental_parts.append(f"- {blue_text}")
                incremental_content = "\n".join(incremental_parts)

            print(f"[页面获取] 构建完成: full_content={len(full_content)}, blue_texts={len(blue_texts)}, tables={len(tables_data)}")

            if full_content and len(full_content) > 50:
                print(f"[页面获取] ✓ {page_name}: {len(full_content)} 字符" + (f" (含{len(blue_texts)}条增量)" if blue_texts else ""))

                # 内容稳定性验证：检查是否应该有增量但没有检测到
                # 如果检测到的蓝色文本少于预期（如页面有"新增"相关关键词但蓝色文本很少），则重试
                should_have_incremental = any(kw in full_content.lower() for kw in ['新增', '增量', '本次', '蓝色', '变更'])
                actual_incremental = len(blue_texts) > 0

                if should_have_incremental and not actual_incremental and retry_count < max_retries:
                    print(f"[页面获取] ⚠ {page_name}: 检测到增量关键词但未识别到蓝色文本，可能样式未加载完成，进行重试 ({retry_count + 1}/{max_retries})...")
                    await page_obj.close()
                    await context.close()
                    await asyncio.sleep(2)
                    return await fetch_page_content_http(page_info, base_url, semaphore, username, password, retry_count + 1, max_retries)

                return {
                    'page_name': page_name,
                    'page_key': page_name,
                    'page_url': page_info['url'],
                    'page_id': page_info['page_id'],
                    'full_content': full_content,
                    'incremental_content': incremental_content,
                    'has_incremental': bool(blue_texts),
                    'blue_texts': blue_texts,
                    'tables_count': len(tables_data)
                }
            else:
                # 内容过少，重试
                if retry_count < max_retries:
                    print(f"[页面获取] ⚠ {page_name}: 内容过少 (长度={len(full_content) if full_content else 0})，进行重试 ({retry_count + 1}/{max_retries})...")
                    await page_obj.close()
                    await context.close()
                    await asyncio.sleep(2)
                    return await fetch_page_content_http(page_info, base_url, semaphore, username, password, retry_count + 1, max_retries)
                else:
                    print(f"[页面获取] ✗ {page_name}: 内容过少，已达最大重试次数")
                    return None

        except asyncio.TimeoutError:
            print(f"[页面获取] ✗ {page_info['name']}: 超时")
            return None
        except Exception as e:
            print(f"[页面获取] ✗ {page_info['name']}: {e}")
            import traceback
            traceback.print_exc()
            return None
        finally:
            if page_obj:
                try:
                    await page_obj.close()
                except:
                    pass
            if context:
                try:
                    await context.close()
                except:
                    pass


async def fetch_all_pages_from_sitemap(
    axure_url: str,
    username: str = "",
    password: str = "",
    max_concurrent: int = 1  # 串行执行，避免并发导致的增量检测不稳定
) -> List[PageData]:
    """
    从sitemap获取所有页面的完整内容（使用浏览器方式）

    Args:
        axure_url: Axure URL
        username: 登录用户名（可选）
        password: 登录密码（可选）
        max_concurrent: 最大并发数

    Returns:
        PageData列表
    """
    print(f"\n[{'='*50}]")
    print(f"[sitemap知识库] 开始获取所有页面")
    print(f"[{'='*50}]")

    # Step 1: 解析sitemap
    pages_list = await parse_sitemap_js(axure_url, username=username, password=password)
    if not pages_list:
        print("[sitemap知识库] 未获取到页面列表")
        return []

    # Step 2: 并发获取所有页面
    print(f"\n[sitemap知识库] 开始并发获取 {len(pages_list)} 个页面内容...")

    parsed = urlparse(axure_url)
    base_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

    semaphore = asyncio.Semaphore(max_concurrent)

    # 使用浏览器方式获取每个页面
    tasks = [
        fetch_page_content_http(page, base_url, semaphore, username=username, password=password)
        for page in pages_list
    ]
    results = await asyncio.gather(*tasks)

    # 过滤失败结果并转换为PageData
    pages_data = []
    for result in results:
        if result:
            pages_data.append(PageData(
                page_key=result['page_key'],
                page_name=result['page_name'],
                page_url=result['page_url'],
                full_content=result['full_content'],
                incremental_content=result['incremental_content']
            ))

    print(f"\n[sitemap知识库] 成功获取 {len(pages_data)}/{len(pages_list)} 个页面")

    # 统计
    incremental_count = sum(1 for p in pages_data if p.has_incremental)
    print(f"[sitemap知识库] 其中 {incremental_count} 个页面包含增量内容")

    return pages_data


# ==================== Phase 3: AI分析页面关联 ====================

PAGE_ANALYSIS_PROMPT = """你是一个需求分析专家，请分析以下Axure原型页面的关联关系。

## 页面列表
{pages_info}

## 任务
1. **模块划分**：将页面按功能模块分组
2. **业务流程**：识别页面间的业务流程关系（如：登录 -> 转账 -> 确认）
3. **依赖关系**：识别页面间的依赖关系（如：转账依赖登录）

## 输出格式（JSON）
```json
{{
    "modules": {{
        "用户模块": ["登录", "注册"],
        "支付模块": ["转账", "收款", "支付设置"]
    }},
    "business_flows": [
        ["登录", "转账", "付款确认"],
        ["登录", "收款管理"]
    ],
    "page_relations": {{
        "转账": {{
            "prerequisites": ["登录"],
            "subsequent": ["付款确认"],
            "related": ["收款管理"]
        }}
    }}
}}
```

请严格按照上述JSON格式输出，不要包含其他内容，不要使用markdown代码块。直接输出JSON。"""


async def analyze_page_relationships_with_ai(pages: List[PageData], provider: str = "deepseek") -> dict:
    """
    使用AI分析页面关联关系

    Args:
        pages: PageData列表
        provider: 大模型提供商

    Returns:
        {
            "modules": {"模块名": ["页面key列表"]},
            "business_flows": [["页面1", "页面2", ...]],
            "page_relations": {"页面key": {...}},
            "page_modules": {"页面key": "模块名"}
        }
    """
    print(f"\n[AI分析] 开始分析 {len(pages)} 个页面的关联关系")

    # 构建页面信息摘要
    pages_info = []
    for page in pages[:20]:  # 限制数量避免token过多
        info = f"""
- 页面名称: {page.page_name}
  页面Key: {page.page_key}
  内容摘要: {page.full_content[:200]}...
"""
        if page.incremental_content:
            info += f"  增量内容: {page.incremental_content[:100]}..."
        pages_info.append(info)

    prompt = PAGE_ANALYSIS_PROMPT.format(pages_info="\n".join(pages_info))

    try:
        # 调用大模型
        response = await call_llm_api(prompt, provider=provider)
        content = response.get("choices", [{}])[0].get("message", {}).get("content", "")

        # 提取JSON结果
        content = content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        # 解析JSON
        result = json.loads(content)

        # 构建 page_modules 映射
        page_modules = {}
        for module, page_keys in result.get('modules', {}).items():
            for page_key in page_keys:
                page_modules[page_key] = module

        result['page_modules'] = page_modules

        print(f"[AI分析] 分析完成，识别出 {len(result.get('modules', {}))} 个模块")
        print(f"[AI分析] 模块: {list(result.get('modules', {}).keys())}")

        return result

    except Exception as e:
        print(f"[AI分析] 分析失败: {e}")
        # 返回默认分析结果
        return {
            "modules": {"默认模块": [p.page_key for p in pages]},
            "business_flows": [],
            "page_relations": {},
            "page_modules": {p.page_key: "默认模块" for p in pages}
        }


# ==================== Phase 4: 三层向量化存储 ====================

def build_three_tier_vectors(pages: List[PageData], analysis: dict = None) -> List[dict]:
    """
    构建三层向量存储结构

    层级1: 单页全量向量 (page_full)
    层级2: 单页增量向量 (page_incremental)
    层级3: 模块融合向量 (module_fused)

    Args:
        pages: PageData列表
        analysis: AI分析结果

    Returns:
        向量列表，每个向量包含 content 和 metadata
    """
    vectors = []
    created_at = datetime.now().isoformat()

    print(f"\n[向量构建] 开始构建三层向量结构...")

    # 层级1: 单页全量向量
    print(f"[向量构建] 层级1: 单页全量向量 ({len(pages)} 个)")
    for page in pages:
        if page.full_content and len(page.full_content) > 50:
            vectors.append({
                "content": page.full_content,
                "metadata": {
                    "doc_type": "page_full",
                    "page_key": page.page_key,
                    "page_name": page.page_name,
                    "module": page.module,
                    "is_incremental": False,
                    "has_blue_text": page.has_incremental,
                    "content_length": len(page.full_content),
                    "created_at": created_at
                }
            })

    # 层级2: 单页增量向量
    incremental_pages = [p for p in pages if p.incremental_content and len(p.incremental_content) > 20]
    print(f"[向量构建] 层级2: 单页增量向量 ({len(incremental_pages)} 个)")
    for page in incremental_pages:
        vectors.append({
            "content": page.incremental_content,
            "metadata": {
                "doc_type": "page_incremental",
                "page_key": page.page_key,
                "page_name": page.page_name,
                "module": page.module,
                "is_incremental": True,
                "related_full_type": "page_full",
                "content_length": len(page.incremental_content),
                "created_at": created_at
            }
        })

    # 层级3: 模块融合向量
    if analysis and analysis.get('modules'):
        print(f"[向量构建] 层级3: 模块融合向量 ({len(analysis['modules'])} 个)")
        for module_name, page_keys in analysis['modules'].items():
            module_pages = [p for p in pages if p.page_key in page_keys]

            if module_pages:
                fused_content = fuse_module_content(module_pages, module_name)

                vectors.append({
                    "content": fused_content,
                    "metadata": {
                        "doc_type": "module_fused",
                        "module": module_name,
                        "included_pages": json.dumps(page_keys, ensure_ascii=False),  # 转换为JSON字符串
                        "page_count": len(page_keys),
                        "content_length": len(fused_content),
                        "created_at": created_at
                    }
                })

    print(f"[向量构建] 总计构建 {len(vectors)} 个向量")

    return vectors


def fuse_module_content(pages: List[PageData], module_name: str) -> str:
    """
    融合同一模块的所有页面内容（全量内容已包含增量）

    Args:
        pages: 页面列表
        module_name: 模块名称

    Returns:
        融合后的Markdown内容
    """
    content_parts = [f'<span style="color: blue;"># {module_name} - 模块关联需求</span>\n']
    for page in pages:
        if page.full_content:
            content_parts.append(page.full_content)

    return "\n".join(content_parts)


async def store_vectors_to_chroma(
    collection_name: str,
    vectors: List[dict],
    kb_name: str = "",
    metadata_type: str = "sitemap_kb"
) -> bool:
    """
    将向量存储到ChromaDB

    Args:
        collection_name: collection名称
        vectors: 向量列表
        kb_name: 知识库名称（可选，用于保存原始中文名称）
        metadata_type: metadata类型（默认 "sitemap_kb"）

    Returns:
        是否成功
    """
    try:
        import chromadb

        print(f"\n[向量存储] 开始存储向量到 collection: {collection_name}")

        # 创建collection
        client = chromadb.PersistentClient(path=CHROMA_DB_PATH)

        # 删除已存在的collection
        try:
            client.delete_collection(name=collection_name)
        except:
            pass

        # 构建 metadata
        collection_metadata = {
            "type": metadata_type,
            "created_at": datetime.now().isoformat()
        }
        if kb_name:
            collection_metadata["kb_name"] = kb_name

        # 创建新collection
        collection = client.create_collection(
            name=collection_name,
            metadata=collection_metadata
        )

        # 分批向量化并存储
        batch_size = 10
        total_added = 0

        for i in range(0, len(vectors), batch_size):
            batch = vectors[i:i + batch_size]

            # 检查并分块过长的文本
            texts_to_embed = []
            metadatas_to_add = []
            ids_to_add = []

            for j, v in enumerate(batch):
                content = v["content"]
                metadata = v["metadata"]

                # DashScope Embedding 限制：最大8192字符
                max_length = 8000  # 留一些余量

                if len(content) <= max_length:
                    # 文本长度正常，直接添加
                    texts_to_embed.append(content)
                    metadatas_to_add.append(metadata)
                    ids_to_add.append(f"{collection_name}_{i}_{j}")
                else:
                    # 文本过长，需要分块
                    print(f"[向量存储] 警告: 文本过长 ({len(content)} 字符)，进行分块处理")

                    # 分块处理
                    chunk_size = max_length
                    chunks = [content[k:k+chunk_size] for k in range(0, len(content), chunk_size)]

                    for idx, chunk in enumerate(chunks):
                        texts_to_embed.append(chunk)
                        # 复制metadata并添加分块信息
                        chunk_metadata = metadata.copy()
                        chunk_metadata['chunk_index'] = idx
                        chunk_metadata['total_chunks'] = len(chunks)
                        chunk_metadata['is_chunk'] = True
                        metadatas_to_add.append(chunk_metadata)
                        ids_to_add.append(f"{collection_name}_{i}_{j}_chunk{idx}")

            print(f"[向量存储] 向量化批次 {i//batch_size + 1}/{(len(vectors)-1)//batch_size + 1}，本批次 {len(texts_to_embed)} 个文本块")

            # 向量化
            embeddings = get_dashscope_embedding(texts_to_embed)

            # 存储到ChromaDB
            collection.add(
                documents=texts_to_embed,
                embeddings=embeddings,
                metadatas=metadatas_to_add,
                ids=ids_to_add
            )

            total_added += len(texts_to_embed)

        print(f"[向量存储] 存储完成，共 {len(vectors)} 个向量")
        return True

    except Exception as e:
        print(f"[向量存储] 存储失败: {e}")
        import traceback
        traceback.print_exc()
        return False


# ==================== Phase 5: 智能召回系统 ====================

def format_recall_results(query_results: dict) -> dict:
    """格式化召回结果"""
    if not query_results or not query_results.get('ids') or not query_results['ids'][0]:
        return {"documents": [], "metadatas": []}

    return {
        "documents": query_results.get('documents', [[]])[0],
        "metadatas": query_results.get('metadatas', [[]])[0],
        "distances": query_results.get('distances', [[]])[0]
    }


def assemble_incremental_with_context(incremental: dict, context: dict, query: str) -> str:
    """
    组装增量 + 上下文的完整prompt

    Args:
        incremental: 增量召回结果
        context: 上下文召回结果
        query: 用户查询

    Returns:
        组装后的完整内容
    """
    parts = []

    # 添加全量上下文
    if context.get('documents'):
        parts.append(f"""## 功能背景（模块全量需求）

请首先理解以下业务逻辑和基础规则，这些是理解增量需求的基础：

{context['documents'][0]}

""")

    # 添加增量需求
    if incremental.get('documents'):
        parts.append(f"""## 本次增量需求（新增/变更）

以下是需要测试的本次新增或变更的功能点：

{incremental['documents'][0]}

""")

    # 添加提示
    parts.append(f"""## **__重要提示__**

在生成测试用例时，请：

1. **理解背景**：基于「功能背景」理解完整的业务逻辑、数据流转、约束条件
2. **关注增量**：重点测试「本次增量需求」中的新增/变更功能
3. **结合生成**：将增量和全量结合，生成完整的测试用例
   - 测试增量功能本身
   - 测试增量功能与现有功能的集成
   - 测试增量功能受到的全量约束（如限额、验证等）

用户需求：{query}
""")

    return "\n".join(parts)


async def smart_recall_from_knowledge_base(
    collection_name: str,
    query: str,
    page_key: Optional[str] = None,
    recall_strategy: str = "auto",
    top_k: int = 5
) -> dict:
    """
    智能召回：根据查询内容自动选择最佳召回策略

    Args:
        collection_name: collection名称
        query: 查询文本
        page_key: 页面key（可选）
        recall_strategy: 召回策略 (auto | incremental_with_context | page_level | module_level)
        top_k: 召回数量

    Returns:
        召回结果
    """
    try:
        import chromadb

        client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
        collection = client.get_collection(collection_name)

        print(f"[智能召回] 召回策略: {recall_strategy}, 查询: {query[:50]}...")

        # 🔥 关键：使用 DashScope embedding 对查询文本进行向量化
        query_embedding = get_dashscope_embedding([query])[0]
        print(f"[智能召回] Query embedding 维度: {len(query_embedding)}")

        # 自动策略判断
        if recall_strategy == "auto":
            if any(kw in query for kw in ["新增", "增量", "本次", "蓝色", "变更", "增加"]):
                recall_strategy = "incremental_with_context"
            elif any(kw in query for kw in ["模块", "整体", "全部", "完整"]):
                recall_strategy = "module_level"
            else:
                recall_strategy = "page_level"

            print(f"[智能召回] 自动判断策略: {recall_strategy}")

        results = {"strategy": recall_strategy}

        if recall_strategy == "incremental_with_context":
            # 策略1: 增量 + 全量上下文

            # 1.1 召回增量内容
            where_filter = {"is_incremental": {"$eq": True}}
            if page_key:
                where_filter = {
                    "$and": [
                        {"is_incremental": {"$eq": True}},
                        {"page_key": {"$eq": page_key}}
                    ]
                }

            incremental_results = collection.query(
                query_embeddings=[query_embedding],
                where=where_filter,
                n_results=top_k
            )

            incremental_formatted = format_recall_results(incremental_results)

            # 1.2 获取模块上下文
            if incremental_formatted.get('metadatas'):
                page_metadata = incremental_formatted['metadatas'][0]
                module_name = page_metadata.get('module', '')

                if module_name:
                    # 对模块名也进行向量化
                    module_embedding = get_dashscope_embedding([module_name])[0]
                    context_results = collection.query(
                        query_embeddings=[module_embedding],
                        where={
                            "$and": [
                                {"doc_type": {"$eq": "module_fused"}},
                                {"module": {"$eq": module_name}}
                            ]
                        },
                        n_results=1
                    )

                    context_formatted = format_recall_results(context_results)

                    results['incremental'] = incremental_formatted
                    results['context'] = context_formatted
                    results['combined'] = assemble_incremental_with_context(
                        incremental=incremental_formatted,
                        context=context_formatted,
                        query=query
                    )
                    results['total_chunks'] = len(incremental_formatted.get('documents', []))
                else:
                    results['data'] = incremental_formatted
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

        elif recall_strategy == "page_level":
            # 策略2: 单页级别召回

            where_filter = {"doc_type": {"$eq": "page_full"}}
            if page_key:
                where_filter = {
                    "$and": [
                        {"doc_type": {"$eq": "page_full"}},
                        {"page_key": {"$eq": page_key}}
                    ]
                }

            page_results = collection.query(
                query_embeddings=[query_embedding],
                where=where_filter,
                n_results=top_k
            )

            results['data'] = format_recall_results(page_results)
            results['total_chunks'] = len(results['data'].get('documents', []))

        elif recall_strategy == "module_level":
            # 策略3: 模块级别召回

            module_results = collection.query(
                query_embeddings=[query_embedding],
                where={"doc_type": {"$eq": "module_fused"}},
                n_results=min(top_k, 3)
            )

            results['data'] = format_recall_results(module_results)
            results['total_chunks'] = len(results['data'].get('documents', []))

        return results

    except Exception as e:
        print(f"[智能召回] 召回失败: {e}")
        import traceback
        traceback.print_exc()
        return {
            "strategy": recall_strategy,
            "error": str(e)
        }



def list_sitemap_knowledge_bases() -> List[Dict[str, Any]]:
    """列出所有基于sitemap的知识库"""
    try:
        import chromadb

        client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
        collections = client.list_collections()

        knowledge_bases = []
        for col in collections:
            metadata = col.metadata or {}
            if metadata.get("type") == "sitemap_kb":
                kb_name = metadata.get("kb_name", col.name)
                # 从collection名称中提取kb_name
                if col.name.startswith("sitemap_kb_"):
                    parts = col.name.split("_")
                    if len(parts) >= 3:
                        kb_name = "_".join(parts[2:-1])

                knowledge_bases.append({
                    "collection_name": col.name,
                    "kb_name": kb_name,
                    "doc_count": col.count(),
                    "created_at": metadata.get("created_at", ""),
                    "is_sitemap": True
                })

        return knowledge_bases

    except Exception as e:
        print(f"[知识库] 列出知识库失败: {e}")
        return []


def delete_sitemap_knowledge_base(collection_name: str) -> bool:
    """删除知识库"""
    try:
        import chromadb

        client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
        client.delete_collection(name=collection_name)
        print(f"[知识库] 已删除知识库: {collection_name}")
        return True

    except Exception as e:
        print(f"[知识库] 删除知识库失败: {e}")
        return False
