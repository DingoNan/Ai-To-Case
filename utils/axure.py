"""Axure 原型解析模块

包含 Axure ZIP/HTML 文本提取、蓝色字体识别、在线获取等功能。
"""
import re
import json
import zipfile
import asyncio
from io import BytesIO
from typing import Dict, Any, List
from urllib.parse import urlparse, unquote, parse_qs

from .flowchart import detect_and_extract_flowchart, convert_flowchart_to_mermaid_async


# ==================== HTML 文本清理 ====================

def _clean_html_text(raw_html: str) -> str:
    try:
        # Remove script/style
        raw_html = re.sub(r"<script[\s\S]*?</script>", " ", raw_html, flags=re.IGNORECASE)
        raw_html = re.sub(r"<style[\s\S]*?</style>", " ", raw_html, flags=re.IGNORECASE)
        # Strip tags
        text = re.sub(r"<[^>]+>", " ", raw_html)
        # Unescape common entities
        text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        # Collapse whitespace
        text = re.sub(r"\s+", " ", text)
        return text.strip()
    except Exception:
        return raw_html


# ==================== 蓝色字体提取 ====================

def _extract_blue_text_from_html(raw_html: str) -> str:
    """
    从HTML中提取增量需求的文本内容（包括蓝色和红色字体）
    识别多种颜色表示方式：蓝色、红色等用于标识增量需求
    """
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(raw_html, 'html.parser')

        # 扩展增量需求相关的CSS颜色值（包括蓝色和红色）
        increment_colors = [
            # 蓝色系
            'blue', '#0000ff', '#00f', '#0000FF', '#0000ff',
            'rgb(0,0,255)', 'rgb(0, 0, 255)', 'rgb(0,0,255)', 'rgb(0, 0, 255)',
            '#0066cc', '#0066CC', '#3366ff', '#3366FF', '#1e90ff', '#1E90FF',
            '#4169e1', '#4169E1', '#0000CD', '#0000cd', '#191970', '#191970',
            '#000080', '#000080', '#0080FF', '#0080ff', '#0080ff', '#0080FF',
            '#4A90E2', '#4a90e2', '#5B9BD5', '#5b9bd5',
            'rgb(0,102,204)', 'rgb(0,102,255)', 'rgb(51,102,255)', 'rgb(30,144,255)',
            'rgb(65,105,225)', 'rgb(0,0,205)', 'rgb(25,25,112)', 'rgb(0,0,128)',
            'rgb(0,128,255)', 'rgb(74,144,226)', 'rgb(91,155,213)',
            'rgba(0,0,255,', 'rgba(0,102,204,', 'rgba(51,102,255,',
            'dodgerblue', 'royalblue', 'mediumblue', 'darkblue', 'midnightblue',
            'steelblue', 'cornflowerblue', 'lightblue', 'skyblue', 'deepskyblue',
            # 红色系（用于标识增量需求）
            'red', '#ff0000', '#f00', '#FF0000', '#ff0000',
            'rgb(255,0,0)', 'rgb(255, 0, 0)', 'rgb(255,0,0)', 'rgb(255, 0, 0)',
            '#dc143c', '#DC143C', '#b22222', '#B22222', '#8b0000', '#8B0000',
            '#ff4500', '#FF4500', '#ff6347', '#FF6347', '#ff7f50', '#FF7F50',
            'rgb(220,20,60)', 'rgb(178,34,34)', 'rgb(139,0,0)', 'rgb(255,69,0)',
            'rgb(255,99,71)', 'rgb(255,127,80)',
            'rgba(255,0,0,', 'rgba(220,20,60,', 'rgba(178,34,34,',
            'crimson', 'darkred', 'firebrick', 'indianred', 'lightcoral',
            'salmon', 'tomato', 'orangered', 'darkorange'
        ]

        increment_texts = []

        for element in soup.find_all(True):
            # 检查style属性
            if element.get('style'):
                style = element.get('style').lower()
                for color in increment_colors:
                    if color.lower() in style:
                        text = element.get_text(strip=True)
                        if text and len(text) > 1:
                            increment_texts.append(text)
                        break

            # 检查class属性
            if element.get('class'):
                classes = ' '.join(element.get('class')).lower()
                increment_keywords = ['blue', 'red', 'increment', 'new', 'add', 'modify', 'update',
                                      'change', 'enhance', 'improve', 'feature', 'highlight', 'important']
                if any(keyword in classes for keyword in increment_keywords):
                    text = element.get_text(strip=True)
                    if text and len(text) > 1:
                        increment_texts.append(text)

            # 检查data属性
            for attr_name, attr_value in element.attrs.items():
                if isinstance(attr_value, str) and 'color' in attr_name.lower():
                    attr_value_lower = attr_value.lower()
                    for color in increment_colors:
                        if color.lower() in attr_value_lower:
                            text = element.get_text(strip=True)
                            if text and len(text) > 1:
                                increment_texts.append(text)
                            break

        # 使用CSS类提取方法作为补充
        css_increment_texts = _extract_blue_text_from_css_classes(raw_html)
        if css_increment_texts:
            for text in css_increment_texts.split('\n'):
                if text.strip() and text.strip() not in increment_texts:
                    increment_texts.append(text.strip())

        # 使用正则表达式作为补充
        regex_increment_texts = _extract_blue_text_with_regex(raw_html)
        if regex_increment_texts:
            for text in regex_increment_texts.split('\n'):
                if text.strip() and text.strip() not in increment_texts:
                    increment_texts.append(text.strip())

        # 去重并合并
        unique_texts = []
        seen = set()
        for text in increment_texts:
            if text not in seen:
                seen.add(text)
                unique_texts.append(text)

        return '\n'.join(unique_texts)

    except ImportError:
        return _extract_blue_text_with_regex(raw_html)
    except Exception:
        return ""


def _extract_blue_text_from_css_classes(raw_html: str) -> str:
    """从HTML中提取通过CSS类定义的蓝色文本"""
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(raw_html, 'html.parser')
        blue_texts = []

        for element in soup.find_all(True):
            element_id = element.get('id', '')
            element_class = ' '.join(element.get('class', []))
            text = element.get_text(strip=True)
            if text and len(text) > 1:
                blue_element_ids = [
                    'u2838', 'u2839', 'u2840', 'u2841', 'u2871', 'u2872', 'u2873', 'u2874', 'u2875', 'u2876',
                    'u2877', 'u2878', 'u2879', 'u2880', 'u2881', 'u2882', 'u2883', 'u2884', 'u2885', 'u2898',
                    'u2902', 'u2903', 'u2904', 'u2905', 'u2906', 'u2907', 'u2908', 'u2909'
                ]
                if element_id and any(pattern in element_id for pattern in blue_element_ids):
                    blue_texts.append(text)
                if any(keyword in element_class.lower() for keyword in
                       ['blue', 'highlight', 'new', 'add', 'modify', 'increment']):
                    blue_texts.append(text)

        unique_texts = []
        seen = set()
        for text in blue_texts:
            if text not in seen:
                seen.add(text)
                unique_texts.append(text)
        return '\n'.join(unique_texts)

    except ImportError:
        return _extract_blue_text_from_css_classes_regex(raw_html)
    except Exception:
        return ""


def _extract_blue_text_from_css_classes_regex(raw_html: str) -> str:
    """使用正则表达式提取CSS类定义的蓝色文本的备选方案"""
    try:
        blue_texts = []
        blue_element_ids = [
            'u2838', 'u2839', 'u2840', 'u2841', 'u2871', 'u2872', 'u2873', 'u2874', 'u2875', 'u2876',
            'u2877', 'u2878', 'u2879', 'u2880', 'u2881', 'u2882', 'u2883', 'u2884', 'u2885', 'u2898',
            'u2902', 'u2903', 'u2904', 'u2905', 'u2906', 'u2907', 'u2908', 'u2909'
        ]
        id_patterns = []
        for element_id in blue_element_ids:
            id_patterns.append(rf'<[^>]*id="{element_id}"[^>]*>.*?<[^>]*>([^<]+)</[^>]*>.*?</[^>]*>')
            id_patterns.append(rf'<[^>]*id="{element_id}"[^>]*>([^<]*)</[^>]*>')
        for pattern in id_patterns:
            matches = re.findall(pattern, raw_html, re.IGNORECASE | re.DOTALL)
            blue_texts.extend(matches)
        class_patterns = [
            r'<[^>]*class="[^"]*blue[^"]*"[^>]*>([^<]+)</[^>]*>',
            r'<[^>]*class="[^"]*highlight[^"]*"[^>]*>([^<]+)</[^>]*>',
            r'<[^>]*class="[^"]*new[^"]*"[^>]*>([^<]+)</[^>]*>',
            r'<[^>]*class="[^"]*increment[^"]*"[^>]*>([^<]+)</[^>]*>',
        ]
        for pattern in class_patterns:
            matches = re.findall(pattern, raw_html, re.IGNORECASE)
            blue_texts.extend(matches)
        unique_texts = []
        seen = set()
        for text in blue_texts:
            cleaned_text = text.strip()
            if cleaned_text and cleaned_text not in seen:
                seen.add(cleaned_text)
                unique_texts.append(cleaned_text)
        return '\n'.join(unique_texts)
    except Exception:
        return ""


def _extract_blue_text_with_regex(raw_html: str) -> str:
    """使用正则表达式提取增量需求文本的备选方案（包括蓝色和红色）"""
    try:
        increment_patterns = [
            r'<[^>]*style="[^"]*color\s*:\s*(?:blue|#0000ff|#00f|#0000FF)[^"]*"[^>]*>([^<]+)</[^>]*>',
            r'<[^>]*style="[^"]*color\s*:\s*rgb\s*\(\s*0\s*,\s*0\s*,\s*255\s*\)[^"]*"[^>]*>([^<]+)</[^>]*>',
            r'<[^>]*style="[^"]*color\s*:\s*rgb\s*\(\s*0\s*,\s*102\s*,\s*204\s*\)[^"]*"[^>]*>([^<]+)</[^>]*>',
            r'<[^>]*style="[^"]*color\s*:\s*rgb\s*\(\s*51\s*,\s*102\s*,\s*255\s*\)[^"]*"[^>]*>([^<]+)</[^>]*>',
            r'<[^>]*style="[^"]*color\s*:\s*rgb\s*\(\s*30\s*,\s*144\s*,\s*255\s*\)[^"]*"[^>]*>([^<]+)</[^>]*>',
            r'<[^>]*style="[^"]*color\s*:\s*rgb\s*\(\s*65\s*,\s*105\s*,\s*225\s*\)[^"]*"[^>]*>([^<]+)</[^>]*>',
            r'<[^>]*style="[^"]*color\s*:\s*#0066cc[^"]*"[^>]*>([^<]+)</[^>]*>',
            r'<[^>]*style="[^"]*color\s*:\s*#0066FF[^"]*"[^>]*>([^<]+)</[^>]*>',
            r'<[^>]*style="[^"]*color\s*:\s*#3366ff[^"]*"[^>]*>([^<]+)</[^>]*>',
            r'<[^>]*style="[^"]*color\s*:\s*#1e90ff[^"]*"[^>]*>([^<]+)</[^>]*>',
            r'<[^>]*style="[^"]*color\s*:\s*#4169e1[^"]*"[^>]*>([^<]+)</[^>]*>',
            r'<[^>]*style="[^"]*color\s*:\s*#0000CD[^"]*"[^>]*>([^<]+)</[^>]*>',
            r'<[^>]*style="[^"]*color\s*:\s*#000080[^"]*"[^>]*>([^<]+)</[^>]*>',
            r'<[^>]*style="[^"]*color\s*:\s*#0080FF[^"]*"[^>]*>([^<]+)</[^>]*>',
            r'<[^>]*style="[^"]*color\s*:\s*#4A90E2[^"]*"[^>]*>([^<]+)</[^>]*>',
            r'<[^>]*style="[^"]*color\s*:\s*#5B9BD5[^"]*"[^>]*>([^<]+)</[^>]*>',
            r'<[^>]*style="[^"]*color\s*:\s*rgba\s*\(\s*0\s*,\s*0\s*,\s*255\s*,[^)]*\)[^"]*"[^>]*>([^<]+)</[^>]*>',
            r'<[^>]*style="[^"]*color\s*:\s*rgba\s*\(\s*0\s*,\s*102\s*,\s*204\s*,[^)]*\)[^"]*"[^>]*>([^<]+)</[^>]*>',
            r'<[^>]*style="[^"]*color\s*:\s*(?:dodgerblue|royalblue|mediumblue|darkblue|midnightblue|steelblue|cornflowerblue|lightblue|skyblue|deepskyblue)[^"]*"[^>]*>([^<]+)</[^>]*>',
            r'<[^>]*style="[^"]*color\s*:\s*(?:red|#ff0000|#f00|#FF0000)[^"]*"[^>]*>([^<]+)</[^>]*>',
            r'<[^>]*style="[^"]*color\s*:\s*rgb\s*\(\s*255\s*,\s*0\s*,\s*0\s*\)[^"]*"[^>]*>([^<]+)</[^>]*>',
            r'<[^>]*style="[^"]*color\s*:\s*rgb\s*\(\s*220\s*,\s*20\s*,\s*60\s*\)[^"]*"[^>]*>([^<]+)</[^>]*>',
            r'<[^>]*style="[^"]*color\s*:\s*rgb\s*\(\s*178\s*,\s*34\s*,\s*34\s*\)[^"]*"[^>]*>([^<]+)</[^>]*>',
            r'<[^>]*style="[^"]*color\s*:\s*rgb\s*\(\s*139\s*,\s*0\s*,\s*0\s*\)[^"]*"[^>]*>([^<]+)</[^>]*>',
            r'<[^>]*style="[^"]*color\s*:\s*#dc143c[^"]*"[^>]*>([^<]+)</[^>]*>',
            r'<[^>]*style="[^"]*color\s*:\s*#DC143C[^"]*"[^>]*>([^<]+)</[^>]*>',
            r'<[^>]*style="[^"]*color\s*:\s*#b22222[^"]*"[^>]*>([^<]+)</[^>]*>',
            r'<[^>]*style="[^"]*color\s*:\s*#B22222[^"]*"[^>]*>([^<]+)</[^>]*>',
            r'<[^>]*style="[^"]*color\s*:\s*#8b0000[^"]*"[^>]*>([^<]+)</[^>]*>',
            r'<[^>]*style="[^"]*color\s*:\s*#8B0000[^"]*"[^>]*>([^<]+)</[^>]*>',
            r'<[^>]*style="[^"]*color\s*:\s*#ff4500[^"]*"[^>]*>([^<]+)</[^>]*>',
            r'<[^>]*style="[^"]*color\s*:\s*#FF4500[^"]*"[^>]*>([^<]+)</[^>]*>',
            r'<[^>]*style="[^"]*color\s*:\s*#ff6347[^"]*"[^>]*>([^<]+)</[^>]*>',
            r'<[^>]*style="[^"]*color\s*:\s*#FF6347[^"]*"[^>]*>([^<]+)</[^>]*>',
            r'<[^>]*style="[^"]*color\s*:\s*#ff7f50[^"]*"[^>]*>([^<]+)</[^>]*>',
            r'<[^>]*style="[^"]*color\s*:\s*#FF7F50[^"]*"[^>]*>([^<]+)</[^>]*>',
            r'<[^>]*style="[^"]*color\s*:\s*rgba\s*\(\s*255\s*,\s*0\s*,\s*0\s*,[^)]*\)[^"]*"[^>]*>([^<]+)</[^>]*>',
            r'<[^>]*style="[^"]*color\s*:\s*rgba\s*\(\s*220\s*,\s*20\s*,\s*60\s*,[^)]*\)[^"]*"[^>]*>([^<]+)</[^>]*>',
            r'<[^>]*style="[^"]*color\s*:\s*rgba\s*\(\s*178\s*,\s*34\s*,\s*34\s*,[^)]*\)[^"]*"[^>]*>([^<]+)</[^>]*>',
            r'<[^>]*style="[^"]*color\s*:\s*(?:crimson|darkred|firebrick|indianred|lightcoral|salmon|tomato|orangered|darkorange)[^"]*"[^>]*>([^<]+)</[^>]*>',
            r"<[^>]*style='[^']*color\s*:\s*(?:blue|red|#0000ff|#ff0000|#0000FF|#FF0000|#0066cc|#0066FF|#3366ff|#1e90ff|#4169e1|#dc143c|#DC143C)[^']*'[^>]*>([^<]+)</[^>]*>",
            r'<[^>]*style=[^>]*color\s*:\s*(?:blue|red|#0000ff|#ff0000|#0000FF|#FF0000|#0066cc|#0066FF|#3366ff|#1e90ff|#4169e1|#dc143c|#DC143C)[^>]*>([^<]+)</[^>]*>',
        ]
        increment_texts = []
        for pattern in increment_patterns:
            matches = re.findall(pattern, raw_html, re.IGNORECASE)
            increment_texts.extend(matches)
        unique_texts = []
        seen = set()
        for text in increment_texts:
            cleaned_text = text.strip()
            if cleaned_text and cleaned_text not in seen:
                seen.add(cleaned_text)
                unique_texts.append(cleaned_text)
        return '\n'.join(unique_texts)
    except Exception:
        return ""


def _extract_axure_js_strings(js_text: str) -> List[str]:
    extracted: List[str] = []
    try:
        patterns = [
            r"\bname\s*:\s*\"([^\"]+)\"",
            r"\blabel\s*:\s*\"([^\"]+)\"",
            r"\btype\s*:\s*\"([^\"]+)\"",
            r"\bnotes\s*:\s*\{[\s\S]*?\btext\s*:\s*\"([\s\S]*?)\"[\s\S]*?\}",
            r"\btext\s*:\s*\{[\s\S]*?\bexpr\b[\s\S]*?\}|\btext\s*:\s*\"([\s\S]*?)\"",
            r"\btip\s*:\s*\"([\s\S]*?)\"",
        ]
        for pat in patterns:
            for m in re.finditer(pat, js_text):
                for g in m.groups():
                    if g:
                        cleaned = re.sub(r"\\n|\\r", " ", g)
                        cleaned = re.sub(r"\s+", " ", cleaned).strip()
                        if cleaned:
                            extracted.append(cleaned)
    except Exception:
        pass
    return extracted


def _collect_blue_selectors_from_css(css_text: str) -> Dict[str, set]:
    """从CSS文本中收集设置为蓝色(color)的选择器"""
    blue_color_patterns = [
        r"blue\b", r"#0000ff\b", r"#00f\b", r"rgb\s*\(\s*0\s*,\s*0\s*,\s*255\s*\)",
        r"#0066cc\b", r"#3366ff\b", r"#1e90ff\b", r"#4169e1\b"
    ]
    color_regex = r"(?:" + "|".join(blue_color_patterns) + r")"
    blue_ids: set = set()
    blue_classes: set = set()
    try:
        for m in re.finditer(r"#([\w-]+)\s*\{[^}]*?color\s*:\s*" + color_regex + r"[^}]*\}", css_text, re.IGNORECASE):
            blue_ids.add(m.group(1))
        for m in re.finditer(r"#([\\w-]+)\s+[^\{]*\{[^}]*?color\s*:\s*" + color_regex + r"[^}]*\}", css_text, re.IGNORECASE):
            blue_ids.add(m.group(1))
        for m in re.finditer(r"\.([\w-]+)\s*\{[^}]*?color\s*:\s*" + color_regex + r"[^}]*\}", css_text, re.IGNORECASE):
            blue_classes.add(m.group(1))
    except Exception:
        pass
    return {"ids": blue_ids, "classes": blue_classes}


def _extract_text_by_selectors(html: str, blue_ids: set, blue_classes: set) -> List[str]:
    """使用已知蓝色id与class集合，从HTML中提取对应元素的文本"""
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')
        results: List[str] = []
        for bid in blue_ids:
            el = soup.find(id=bid)
            if el:
                txt = el.get_text(strip=True)
                if txt:
                    results.append(txt)
        if blue_classes:
            class_selector = ",".join([f".{c}" for c in blue_classes])
            for el in soup.select(class_selector):
                txt = el.get_text(strip=True)
                if txt:
                    results.append(txt)
        return results
    except Exception:
        return []


# ==================== Axure ZIP/HTML 解析 ====================

def parse_axure_zip_to_text(file_bytes: bytes) -> Dict[str, str]:
    """解析 Axure HTML 导出 ZIP 包，返回全量内容和增量内容"""
    full_texts: List[str] = []
    incremental_texts: List[str] = []

    try:
        css_blue_ids: set = set()
        css_blue_classes: set = set()
        with zipfile.ZipFile(BytesIO(file_bytes)) as zf:
            # 第一遍：聚合CSS蓝色选择器
            for info in zf.infolist():
                name_lower = info.filename.lower()
                if name_lower.endswith(".css") and not name_lower.startswith("__macosx/"):
                    with zf.open(info, "r") as fp:
                        raw = fp.read()
                        try:
                            css_text = raw.decode("utf-8", errors="ignore")
                        except Exception:
                            css_text = raw.decode(errors="ignore")
                        selectors = _collect_blue_selectors_from_css(css_text)
                        css_blue_ids.update(selectors.get("ids", set()))
                        css_blue_classes.update(selectors.get("classes", set()))

            # 第二遍：解析HTML/JS
            for info in zf.infolist():
                name_lower = info.filename.lower()
                if name_lower.endswith((".html", ".htm")) and not name_lower.startswith("__macosx/"):
                    with zf.open(info, "r") as fp:
                        raw = fp.read()
                        try:
                            html = raw.decode("utf-8", errors="ignore")
                        except Exception:
                            html = raw.decode(errors="ignore")
                        full_text = _clean_html_text(html)
                        if full_text:
                            full_texts.append(full_text)
                        blue_text = _extract_blue_text_from_html(html)
                        if css_blue_ids or css_blue_classes:
                            more = _extract_text_by_selectors(html, css_blue_ids, css_blue_classes)
                            if more:
                                blue_text = (blue_text + "\n" + "\n".join(more)).strip() if blue_text else "\n".join(more)
                        if blue_text:
                            incremental_texts.append(blue_text)
                elif name_lower.endswith(".js") and ("data" in name_lower or "pages" in name_lower or "document" in name_lower):
                    with zf.open(info, "r") as fp:
                        raw = fp.read()
                        try:
                            js_text = raw.decode("utf-8", errors="ignore")
                        except Exception:
                            js_text = raw.decode(errors="ignore")
                        full_texts.extend(_extract_axure_js_strings(js_text))

    except zipfile.BadZipFile:
        raise Exception("Axure包不是有效的ZIP文件")
    except Exception as e:
        raise Exception(f"解析Axure ZIP失败: {str(e)}")

    full_merged = "\n".join([t for t in full_texts if t])
    full_parts = []
    seen_full = set()
    for line in full_merged.split("\n"):
        key = line.strip()
        if key and key not in seen_full:
            seen_full.add(key)
            full_parts.append(key)

    incremental_merged = "\n".join([t for t in incremental_texts if t])
    incremental_parts = []
    seen_incremental = set()
    for line in incremental_merged.split("\n"):
        key = line.strip()
        if key and key not in seen_incremental:
            seen_incremental.add(key)
            incremental_parts.append(key)

    return {
        'full_content': "\n".join(full_parts),
        'incremental_content': "\n".join(incremental_parts)
    }


def parse_axure_html_to_text(file_bytes: bytes) -> Dict[str, str]:
    """解析单个 Axure HTML 文件"""
    try:
        html = file_bytes.decode("utf-8", errors="ignore")
        full_content = _clean_html_text(html)
        incremental_content = _extract_blue_text_from_html(html)
        return {
            'full_content': full_content,
            'incremental_content': incremental_content
        }
    except Exception as e:
        raise Exception(f"解析Axure HTML失败: {str(e)}")


# ==================== Markdown 格式化 ====================

def format_axure_text_to_markdown(axure_text: str) -> str:
    """将提取的 Axure 文本转换为 Markdown 结构"""
    if not axure_text:
        return ""
    lines = [l.strip() for l in axure_text.split("\n") if l and l.strip()]
    md_lines: List[str] = ["# 原型需求提取\n"]
    last_was_heading = False
    for line in lines:
        if (len(line) <= 40 and
                re.search(r"[：:]|(页面|功能|模块|流程|用例|说明|规则|字段)$", line) or
                (line.istitle() and not re.search(r"\s", line) and len(line) <= 20)):
            if not last_was_heading:
                md_lines.append("")
            md_lines.append(f"## {line}")
            last_was_heading = True
        else:
            bullet = line
            kv = re.split(r"[：:]", line, maxsplit=1)
            if len(kv) == 2 and len(kv[0]) <= 20:
                bullet = f"**{kv[0].strip()}**: {kv[1].strip()}"
            md_lines.append(f"- {bullet}")
            last_was_heading = False
    return "\n".join(md_lines).strip()


def format_incremental_text_to_markdown(incremental_text: str) -> str:
    """将增量（蓝色字体）内容转换为 Markdown 结构"""
    if not incremental_text:
        return ""
    lines = [l.strip() for l in incremental_text.split("\n") if l and l.strip()]
    if not lines:
        return ""
    md_lines: List[str] = ["# 增量需求提取\n"]
    md_lines.append("> 以下内容为原型中的蓝色字体部分，通常表示新增或修改的需求\n\n")
    for line in lines:
        if (len(line) <= 50 and
                (re.search(r"[：:]|(新增|修改|更新|优化|改进|功能|模块|页面|流程)$", line) or
                 line.istitle() and len(line) <= 30)):
            md_lines.append(f"## {line}")
        else:
            md_lines.append(f"- {line}")
    return "\n".join(md_lines).strip()


# ==================== Axure 在线链接获取功能 ====================


def fetch_axure_from_url(url: str, username: str = None, password: str = None,
                          wait_time: int = 5) -> Dict[str, str]:
    """
    使用无头浏览器获取Axure在线原型内容（同步版本）
    更好地解析 Axure 页面结构，提取表格和结构化内容

    Args:
        url: Axure在线原型链接
        username: 域账号用户名（可选）
        password: 域账号密码（可选）
        wait_time: 页面加载等待时间（秒）

    Returns:
        Dict with keys: 'full_content', 'incremental_content'
    """
    try:
        from playwright.sync_api import sync_playwright
        from playwright_stealth import Stealth
        from bs4 import BeautifulSoup
        from urllib.parse import urlparse, unquote
        import time

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            page = context.new_page()

            stealth = Stealth()
            stealth.apply_stealth_sync(page)

            print(f"正在访问Axure链接: {url}")
            page.goto(url, wait_until='networkidle', timeout=60000)
            time.sleep(wait_time)

            if username and password:
                page_title = page.title()
                if '认证' in page_title or 'login' in page_title.lower():
                    print("检测到登录页面，正在登录...")
                    try:
                        login_methods = [
                            ('input[placeholder="请输入您的用户名"]', 'input[placeholder="请输入您的密码"]'),
                            ('input[name="username"]', 'input[name="password"]'),
                            ('input[type="text"]', 'input[type="password"]'),
                        ]
                        for user_sel, pwd_sel in login_methods:
                            try:
                                if page.locator(user_sel).count() > 0:
                                    page.locator(user_sel).fill(username)
                                    page.locator(pwd_sel).fill(password)
                                    break
                            except Exception:
                                continue
                        login_btns = ['button:has-text("登录")', 'input[type="submit"]', 'button[type="submit"]']
                        for btn_sel in login_btns:
                            try:
                                if page.locator(btn_sel).count() > 0:
                                    page.locator(btn_sel).click()
                                    break
                            except Exception:
                                continue
                        page.wait_for_load_state('networkidle')
                        time.sleep(3)
                    except Exception as login_error:
                        print(f"登录处理警告: {login_error}")

            parsed_url = urlparse(url)
            page_name = ""
            if 'p=' in url:
                import urllib.parse
                query_params = urllib.parse.parse_qs(parsed_url.query)
                if 'p' in query_params:
                    page_name = unquote(query_params['p'][0])

            time.sleep(2)

            # 获取Axure主内容区域iframe
            print(f"[Axure解析] 开始获取主内容区域...")
            iframe_content = ""
            main_frame_selectors = [
                'iframe#mainFrame', 'iframe[name="mainFrame"]', 'iframe#mainPanel',
                'iframe[name="mainPanel"]', '#mainFrame', '[name="mainFrame"]', 'iframe.mainFrame',
            ]
            for selector in main_frame_selectors:
                try:
                    frame_element = page.locator(selector)
                    if frame_element.count() > 0:
                        frame_element.wait_for(state='attached', timeout=5000)
                        frame = page.frame(name='mainFrame') or page.frame(url=lambda u: 'mainFrame' in str(u) or '.html' in str(u))
                        if frame:
                            iframe_content = frame.content()
                            print(f"[Axure解析] 通过选择器 {selector} 获取到mainFrame内容: {len(iframe_content)} 字符")
                            break
                except Exception:
                    continue

            if not iframe_content or len(iframe_content) < 500:
                print(f"[Axure解析] 选择器方式未找到，尝试遍历所有frames...")
                frames = page.frames
                best_frame_content = ""
                for i, frame in enumerate(frames):
                    try:
                        frame_url = frame.url
                        frame_name = frame.name
                        content = frame.content()
                        content_len = len(content)
                        print(f"[Axure解析] Frame {i}: name={frame_name}, url={(frame_url or '')[:50]}..., 内容长度={content_len}")
                        if frame == page.main_frame:
                            continue
                        frame_url_lower = (frame_url or '').lower()
                        frame_name_lower = (frame_name or '').lower()
                        if any(keyword in frame_url_lower or keyword in frame_name_lower
                               for keyword in ['sitemap', 'toc', 'nav', 'menu', 'tree', 'left']):
                            continue
                        if content_len > len(best_frame_content):
                            best_frame_content = content
                    except Exception:
                        continue
                if best_frame_content:
                    iframe_content = best_frame_content

            if not iframe_content:
                print(f"[Axure解析] 未找到iframe，使用整页内容")
                iframe_content = page.content()

            print(f"[Axure解析] 最终获取内容长度: {len(iframe_content)}")

            target_frame = page
            for frame in page.frames:
                frame_url = frame.url or ''
                frame_name = frame.name or ''
                if any(kw in frame_url.lower() or kw in frame_name.lower()
                       for kw in ['sitemap', 'toc', 'nav', 'menu', 'tree', 'left']):
                    continue
                if frame != page.main_frame and len(frame_url) > 10:
                    target_frame = frame
                    break

            soup = BeautifulSoup(iframe_content, 'html.parser')
            full_texts = []
            incremental_texts = []
            tables_data = []

            for tag in soup(['script', 'style', 'noscript', 'link', 'meta']):
                tag.decompose()

            axure_ui_keywords = [
                'preview', 'inspect', 'share', 'adaptive', 'comments', 'hotspots',
                'collapse all', 'scale to', 'default scale', 'user scale',
                'show note markers', 'copyright', 'axure', 'prototype',
                'close', 'variables', 'zoom', 'pages', 'masters', 'console',
                'colors', 'assets', 'size and position', 'download all',
                'copied to clipboard', 'typography', 'typeface', 'fill color',
                'border', 'shadows', 'no notes for this page', 'add comment',
                'mark all read', 'rotation', 'radius', 'padding', 'opacity',
                'width:', 'height:', 'align:', 'position:', 'size:',
                'add a comment', 'give feedback', 'ask a question', 'request a change',
                'sitemap', 'outline', 'notes', 'interactions', 'documentation',
                'publish', 'generate', 'export', 'import', 'settings'
            ]
            axure_exact_keywords = {'content', 'html', 'css', 'other'}
            code_keywords = [
                'function(', 'var ', 'const ', 'let ', 'return ', 'console.',
                'jquery', 'document.', 'window.', '$(', 'css(', 'axure.',
                '{', '}', '===', '!=='
            ]

            def extract_text_smart(element):
                text = element.get_text(strip=True)
                if not text or len(text) < 2:
                    return None
                text_lower = text.lower().strip()
                if text_lower in axure_exact_keywords:
                    return None
                if any(keyword in text_lower for keyword in axure_ui_keywords):
                    return None
                if any(keyword in text for keyword in code_keywords):
                    return None
                if text.isdigit():
                    return None
                if len(text) <= 10 and text.endswith(':'):
                    return None
                if re.match(r'^[A-Za-z:]+$', text) and ':' in text:
                    return None
                if not any(c.isalpha() or c > '\u4e00' for c in text):
                    return None
                if text.isascii() and len(text) < 3:
                    return None
                if text.startswith('\u00d7'):
                    return None
                return text

            for table in soup.find_all('table'):
                rows = []
                for tr in table.find_all('tr'):
                    cells = []
                    for td in tr.find_all(['td', 'th']):
                        cell_text = td.get_text(strip=True)
                        cells.append(cell_text)
                    if cells and any(c for c in cells):
                        rows.append(cells)
                if rows:
                    tables_data.append(rows)

            def normalize_style_sync(style_str):
                return style_str.lower().replace(' ', '').replace('\t', '').replace('\n', '')

            def check_color_in_style_sync(style_str):
                normalized = normalize_style_sync(style_str)
                blue_patterns_normalized = [
                    'color:blue', 'color:#0000ff', 'color:#00f',
                    'color:rgb(0,0,255)', 'color:#0066cc', 'color:#0066ff',
                    'color:#3366ff', 'color:#1e90ff', 'color:#4169e1',
                    'color:#0000cd', 'color:#000080', 'color:#0080ff',
                    'color:#4a90e2', 'color:#5b9bd5', 'color:#2196f3',
                    'color:#1976d2', 'color:dodgerblue', 'color:royalblue',
                    'color:steelblue', 'color:cornflowerblue',
                    'color:red', 'color:#ff0000', 'color:#f00',
                    'color:rgb(255,0,0)', 'color:#dc143c', 'color:#ff4500',
                    'color:#ff6347', 'color:#b22222', 'color:#8b0000',
                    'color:#cc0000', 'color:crimson', 'color:darkred',
                    'color:firebrick',
                ]
                for pattern in blue_patterns_normalized:
                    if pattern in normalized:
                        return True
                if re.search(r'color[:\s]*rgb\s*\(\s*0\s*,\s*0\s*,\s*255\s*\)', style_str, re.IGNORECASE):
                    return True
                if re.search(r'color[:\s]*rgb\s*\(\s*255\s*,\s*0\s*,\s*0\s*\)', style_str, re.IGNORECASE):
                    return True
                return False

            def check_element_color_sync(element):
                style = element.get('style', '')
                if style and check_color_in_style_sync(style):
                    return True
                parent = element.parent
                for _ in range(5):
                    if parent is None or parent.name is None:
                        break
                    parent_style = parent.get('style', '')
                    if parent_style and check_color_in_style_sync(parent_style):
                        return True
                    parent = parent.parent
                return False

            def check_cell_has_blue_color(td_element):
                if check_element_color_sync(td_element):
                    return True
                for child in td_element.find_all(recursive=True):
                    if check_element_color_sync(child):
                        return True
                return False

            # JavaScript获取computed color
            blue_texts_from_js = set()
            try:
                print(f"[Axure解析] 使用JavaScript获取computed color...")
                color_info = target_frame.evaluate("""
                () => {
                    const results = [];
                    const elements = document.querySelectorAll('div, span, p, h1, h2, h3, h4, h5, h6, li, a, td, th, label');
                    for (const el of elements) {
                        const text = el.innerText ? el.innerText.trim() : '';
                        if (text && text.length > 1 && text.length < 500) {
                            const style = window.getComputedStyle(el);
                            const color = style.color;
                            results.push({ text: text.substring(0, 200), color: color });
                        }
                    }
                    return results;
                }
                """)
                if color_info:
                    for info in color_info:
                        color = info.get('color', '')
                        text = info.get('text', '').strip()
                        if not text or not color:
                            continue
                        is_blue = False
                        if 'rgb' in color:
                            try:
                                parts = color.replace('rgb(', '').replace('rgba(', '').replace(')', '').split(',')
                                r, g, b = int(parts[0].strip()), int(parts[1].strip()), int(parts[2].strip())
                                if b > 150 and r < 150:
                                    is_blue = True
                                elif r > 200 and g < 100 and b < 100:
                                    is_blue = True
                            except:
                                pass
                        if is_blue:
                            blue_texts_from_js.add(text)
                            for line in text.split('\n'):
                                line = line.strip()
                                if line and len(line) > 1:
                                    blue_texts_from_js.add(line)
                print(f"[Axure解析] JavaScript识别到 {len(blue_texts_from_js)} 条蓝色/红色文本")
            except Exception as js_err:
                print(f"[Axure解析] JavaScript获取computed color失败: {js_err}")

            def is_text_blue_by_js(text):
                if not text:
                    return False
                text = text.strip()
                if text in blue_texts_from_js:
                    return True
                for blue_text in blue_texts_from_js:
                    if text in blue_text:
                        return True
                return False

            # 提取表格 - 同时检测蓝色行
            incremental_table_rows = []
            for table in soup.find_all('table'):
                current_header = []
                for row_idx, tr in enumerate(table.find_all('tr')):
                    cells = []
                    row_has_blue = False
                    for td in tr.find_all(['td', 'th']):
                        cell_text = td.get_text(strip=True)
                        cell_text = ' '.join(cell_text.split())
                        cells.append(cell_text)
                        if check_cell_has_blue_color(td):
                            row_has_blue = True
                        elif is_text_blue_by_js(cell_text):
                            row_has_blue = True
                    if cells and any(c for c in cells):
                        if row_idx == 0:
                            current_header = cells
                        elif row_has_blue and current_header:
                            incremental_table_rows.append({
                                'header': current_header,
                                'row': cells
                            })

            # 提取非表格文本
            for element in soup.find_all(['div', 'span', 'p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'a']):
                if element.find_parent('table'):
                    continue
                text = extract_text_smart(element)
                if not text:
                    continue
                is_increment = check_element_color_sync(element)
                if not is_increment:
                    is_increment = is_text_blue_by_js(text)
                if is_increment and text not in incremental_texts:
                    incremental_texts.append(text)
                if text not in full_texts:
                    full_texts.append(text)

            browser.close()

            # 构建 Markdown 输出 - 全量内容
            md_parts = []
            if page_name:
                md_parts.append(f"# {page_name}\n")
            if tables_data:
                for idx, table_rows in enumerate(tables_data):
                    if len(table_rows) > 1:
                        max_cols = max(len(row) for row in table_rows)
                        md_parts.append(f"\n## 表格 {idx + 1}\n")
                        header = table_rows[0] if table_rows else []
                        header_padded = header + [''] * (max_cols - len(header))
                        md_parts.append("| " + " | ".join(header_padded) + " |")
                        md_parts.append("| " + " | ".join(['---'] * max_cols) + " |")
                        for row in table_rows[1:]:
                            row_padded = row + [''] * (max_cols - len(row))
                            row_cleaned = [cell.replace('\n', ' ').replace('\r', '').replace('|', '\uff5c') for cell in row_padded]
                            md_parts.append("| " + " | ".join(row_cleaned) + " |")
                        md_parts.append("")
            if full_texts:
                md_parts.append("\n## 页面内容\n")
                for text in full_texts[:200]:
                    if len(text) <= 50 and re.search(r'[：:](|页面|功能|模块|流程|说明|规则|字段|管理|配置)$', text):
                        md_parts.append(f"\n### {text}\n")
                    else:
                        md_parts.append(f"- {text}")
            full_content = "\n".join(md_parts)
            full_content = re.sub(r'\n{3,}', '\n\n', full_content)

            # 构建增量内容
            inc_parts = []
            if incremental_table_rows:
                inc_parts.append("# 增量需求（蓝色/红色标记内容）\n")
                inc_parts.append("## 增量表格字段\n")
                header_groups = {}
                for item in incremental_table_rows:
                    header_key = tuple(item['header'])
                    if header_key not in header_groups:
                        header_groups[header_key] = []
                    header_groups[header_key].append(item['row'])
                for header, rows in header_groups.items():
                    header_list = list(header)
                    max_cols = max(len(header_list), max(len(row) for row in rows))
                    header_padded = header_list + [''] * (max_cols - len(header_list))
                    inc_parts.append("| " + " | ".join(header_padded) + " |")
                    inc_parts.append("| " + " | ".join(['---'] * max_cols) + " |")
                    for row in rows:
                        row_padded = row + [''] * (max_cols - len(row))
                        row_cleaned = [cell.replace('\n', ' ').replace('\r', '').replace('|', '\uff5c') for cell in row_padded]
                        inc_parts.append("| " + " | ".join(row_cleaned) + " |")
                    inc_parts.append("")
            if incremental_texts:
                if not inc_parts:
                    inc_parts.append("# 增量需求（蓝色/红色标记内容）\n")
                if incremental_table_rows:
                    inc_parts.append("## 其他增量内容\n")
                for text in incremental_texts:
                    inc_parts.append(f"- {text}")
            incremental_content = "\n".join(inc_parts) if inc_parts else ""

            print(f"提取完成: 全量内容 {len(full_content)} 字符, 增量内容 {len(incremental_content)} 字符")
            print(f"提取了 {len(tables_data)} 个表格, {len(full_texts)} 条文本, {len(incremental_table_rows)} 条增量表格行")

            # 检测流程图
            flowchart_data = detect_and_extract_flowchart(soup, iframe_content)
            if flowchart_data.get('has_flowchart'):
                print(f"[流程图检测] 检测到流程图，共 {len(flowchart_data.get('nodes', []))} 个节点")

            return {
                'full_content': full_content.strip(),
                'incremental_content': incremental_content.strip(),
                'flowchart_data': flowchart_data
            }

    except ImportError as e:
        raise Exception(f"playwright库未安装，请先运行: pip install playwright && playwright install chromium")
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise Exception(f"获取Axure在线内容失败: {str(e)}")


def _extract_links_from_blue_content(html_content: str, base_url: str) -> List[Dict[str, str]]:
    """
    从HTML内容中提取蓝色/红色文本中的链接（包括文字描述的页面引用）
    [保留此函数作为备用]
    """
    return _extract_page_references_from_text(html_content, base_url)


def _extract_page_references_from_text(text_content: str, base_url: str) -> List[Dict[str, str]]:
    """
    从文本内容中提取页面引用（如"参看xxx页面"）

    Args:
        text_content: 文本内容（可以是增量内容或HTML）
        base_url: 基础URL，用于构建完整链接

    Returns:
        List[Dict]: 包含链接信息的列表 [{'url': '...', 'text': '...', 'page_name': '...'}]
    """
    from urllib.parse import urlparse, unquote

    links = []
    seen_page_names = set()

    try:
        parsed_base = urlparse(base_url)
        base_url_without_query = f"{parsed_base.scheme}://{parsed_base.netloc}{parsed_base.path}"

        reference_patterns = [
            r'参看[「「\[【《]?([^」」\]】》\s，,。.；;：:]+)[」」\]】》]?',
            r'详见[「「\[【《]?([^」」\]】》\s，,。.；;：:]+)[」」\]】》]?',
            r'参见[「「\[【《]?([^」」\]】》\s，,。.；;：:]+)[」」\]】》]?',
            r'见[「「\[【《]?([^」」\]】》\s，,。.；;：:]+)[」」\]】》]?[页原]',
            r'跳转[到至]?[「「\[【《]?([^」」\]】》\s，,。.；;：:]+)[」」\]】》]?',
            r'链接[到至]?[「「\[【《]?([^」」\]】》\s，,。.；;：:]+)[」」\]】》]?',
            r'查看[「「\[【《]?([^」」\]】》\s，,。.；;：:]+)[」」\]】》]?[页原]',
            r'参考[「「\[【《]?([^」」\]】》\s，,。.；;：:]+)[」」\]】》]?[页原]',
            r'[（\(]参[看见][「「\[【《]?([^」」\]】》\s，,。.；;：:\)）]+)[」」\]】》]?[）\)]?',
            r'[（\(]详见[「「\[【《]?([^」」\]】》\s，,。.；;：:\)）]+)[」」\]】》]?[）\)]?',
        ]

        for pattern in reference_patterns:
            matches = re.findall(pattern, text_content)
            for match in matches:
                page_name = match.strip()
                if not page_name or len(page_name) < 2:
                    continue
                page_name = page_name.replace('页面', '').replace('原型', '').replace('页', '').strip()
                page_name = re.sub(r'^[「「\[【《]+|[」」\]】》]+$', '', page_name).strip()
                if not page_name or len(page_name) < 2:
                    continue
                if page_name in seen_page_names:
                    continue
                seen_page_names.add(page_name)
                full_url = f"{base_url_without_query}?p={page_name}"
                links.append({
                    'url': full_url,
                    'text': f"引用: {page_name}",
                    'page_name': page_name
                })
                print(f"[页面引用提取] 找到: '{page_name}' -> {full_url}")

        print(f"[页面引用提取] 共提取到 {len(links)} 个页面引用")
        return links

    except Exception as e:
        print(f"[页面引用提取] 提取失败: {e}")
        import traceback
        traceback.print_exc()
        return []


async def fetch_axure_from_url_async_recursive(
    url: str,
    username: str = None,
    password: str = None,
    wait_time: int = 2,
    max_depth: int = 3,
    enable_recursive: bool = True
) -> Dict[str, Any]:
    """
    递归版本：获取Axure在线原型内容，并递归解析蓝色内容中的链接

    Args:
        url: Axure原型链接
        username: 登录用户名
        password: 登录密码
        wait_time: 页面等待时间
        max_depth: 最大递归深度（默认3层）
        enable_recursive: 是否启用递归解析

    Returns:
        Dict with keys:
        - 'full_content': 主页面全量内容
        - 'incremental_content': 按层级组织的增量内容
        - 'pages': 每个页面的单独内容列表
    """
    visited_urls = set()
    all_results = []
    pages_list = []

    def get_heading_prefix(depth: int) -> str:
        if depth == 1:
            return "#"
        elif depth == 2:
            return "##"
        elif depth == 3:
            return "###"
        else:
            return "####"

    async def fetch_page_recursive(page_url: str, depth: int):
        if page_url in visited_urls:
            print(f"[递归解析] 跳过已访问的页面: {page_url[:50]}...")
            return
        if depth > max_depth:
            print(f"[递归解析] 已达最大深度 {max_depth}，停止递归")
            return

        visited_urls.add(page_url)

        parsed = urlparse(page_url)
        query_params = parse_qs(parsed.query)
        page_name = ""
        if 'p' in query_params:
            page_name = unquote(query_params['p'][0])

        print(f"[递归解析] 深度={depth}/{max_depth}, 页面={page_name or page_url[:50]}...")

        try:
            result = await fetch_axure_from_url_async(
                url=page_url,
                username=username,
                password=password,
                wait_time=wait_time
            )

            full_content = result.get('full_content', '')
            incremental_content = result.get('incremental_content', '')
            raw_html = result.get('raw_html', '')

            pages_list.append({
                'page_name': page_name or f"页面{len(pages_list) + 1}",
                'page_url': page_url,
                'full_content': full_content,
                'incremental_content': incremental_content,
                'depth': depth,
                'has_incremental': bool(incremental_content.strip())
            })

            if incremental_content:
                clean_content = incremental_content.replace('# 增量需求（蓝色/红色标记内容）\n', '').strip()
                clean_lines = []
                for line in clean_content.split('\n'):
                    if line.startswith('- '):
                        clean_lines.append(line[2:])
                    else:
                        clean_lines.append(line)
                all_results.append({
                    'depth': depth,
                    'page_name': page_name or f"页面{len(all_results) + 1}",
                    'content': '\n'.join(clean_lines)
                })

            if enable_recursive and depth < max_depth and incremental_content:
                links = _extract_page_references_from_text(incremental_content, page_url)
                print(f"[递归解析] 从增量内容中提取到 {len(links)} 个页面引用")
                for link_info in links:
                    link_url = link_info['url']
                    if link_url not in visited_urls:
                        try:
                            await fetch_page_recursive(link_url, depth + 1)
                        except Exception as link_error:
                            print(f"[递归解析] 获取链接失败，跳过: {link_url[:50]}... 错误: {link_error}")
                            continue

        except Exception as e:
            print(f"[递归解析] 获取页面失败 ({page_url[:50]}...): {e}")
            return

    print(f"[递归解析] 开始递归解析，最大深度={max_depth}, 启用递归={enable_recursive}")
    await fetch_page_recursive(url, depth=1)

    if not pages_list:
        result = await fetch_axure_from_url_async(
            url=url, username=username, password=password, wait_time=wait_time
        )
        parsed = urlparse(url)
        query_params = parse_qs(parsed.query)
        page_name = unquote(query_params.get('p', ['主页面'])[0])

        pages_list.append({
            'page_name': page_name,
            'page_url': url,
            'full_content': result.get('full_content', ''),
            'incremental_content': result.get('incremental_content', ''),
            'depth': 1,
            'has_incremental': bool(result.get('incremental_content', '').strip())
        })

    final_incremental_parts = []
    for item in all_results:
        depth = item['depth']
        page_name = item['page_name']
        content = item['content']
        heading_prefix = get_heading_prefix(depth)
        final_incremental_parts.append(f"\n{heading_prefix} {page_name}\n")
        for line in content.split('\n'):
            line = line.strip()
            if line:
                final_incremental_parts.append(f"- {line}")

    final_incremental_content = "\n".join(final_incremental_parts).strip()

    main_result = await fetch_axure_from_url_async(
        url=url, username=username, password=password, wait_time=wait_time
    )

    print(f"[递归解析] 完成! 共解析 {len(pages_list)} 个页面")

    return {
        'full_content': main_result.get('full_content', ''),
        'incremental_content': final_incremental_content,
        'pages': pages_list
    }


async def fetch_axure_from_url_async(url: str, username: str = None, password: str = None,
                                     wait_time: int = 2, provider: str = "deepseek") -> Dict[str, str]:
    """
    异步版本：使用无头浏览器获取Axure在线原型内容

    通过线程池运行同步版本，避免 Windows 上 asyncio 与 Playwright 的兼容性问题
    如果检测到流程图，会自动转换为 Mermaid 格式并插入到内容中
    """
    from functools import partial

    func = partial(fetch_axure_from_url, url, username, password, wait_time)
    result = await asyncio.to_thread(func)

    flowchart_data = result.get('flowchart_data', {})
    if flowchart_data.get('has_flowchart'):
        print(f"[流程图处理] 开始将流程图转换为 Mermaid...")
        try:
            mermaid_code = await convert_flowchart_to_mermaid_async(flowchart_data, provider=provider)
            if mermaid_code:
                print(f"[流程图处理] Mermaid 转换成功，代码长度: {len(mermaid_code)}")
                result['mermaid_code'] = mermaid_code
            else:
                print(f"[流程图处理] Mermaid 转换返回空结果")
        except Exception as e:
            print(f"[流程图处理] Mermaid 转换失败: {e}")

    return result
