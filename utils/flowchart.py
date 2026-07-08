"""流程图检测与 Mermaid 转换模块"""
import re
from typing import Dict, Any, List
from llms import call_llm_api


def detect_and_extract_flowchart(soup, iframe_content: str) -> Dict[str, Any]:
    """
    检测并提取Axure页面中的流程图元素

    Args:
        soup: BeautifulSoup对象
        iframe_content: 原始HTML内容

    Returns:
        Dict包含:
        - has_flowchart: 是否检测到流程图
        - nodes: 节点列表 [{text, x, y, width, height, shape_type}]
        - description: 流程图的文字描述
    """
    result = {
        'has_flowchart': False,
        'nodes': [],
        'connections': [],
        'description': ''
    }

    # 检测流程图的特征
    # 1. Axure 使用 img 标签引用外部 SVG 作为连接线/箭头
    has_connector_images = False
    connector_count = 0

    for img in soup.find_all('img'):
        src = img.get('src', '')
        img_id = img.get('id', '')
        if ('_seg' in src.lower() or '_seg' in img_id.lower() or
            'arrow' in src.lower() or 'connector' in src.lower() or
            (src.endswith('.svg') and '/images/' in src)):
            connector_count += 1
            if connector_count >= 2:
                has_connector_images = True

    # 2. 也检查内嵌 SVG 元素
    svg_elements = soup.find_all('svg')
    has_svg_lines = False
    for svg in svg_elements:
        if svg.find_all(['path', 'line', 'polyline']):
            has_svg_lines = True
            break

    # 3. 检测带有位置信息的形状元素
    positioned_elements = []
    flowchart_keywords = ['开始', '结束', '判断', '是', '否', 'yes', 'no', 'start', 'end',
                          '流程', '步骤', '条件', '分支', '循环', '处理', '输入', '输出',
                          '提交', '审核', '审批', '通过', '拒绝', '完成', '发起', '申请']

    # 查找所有绝对定位的div元素
    for div in soup.find_all('div', style=True):
        style = div.get('style', '')
        if 'position' in style.lower() and ('left' in style.lower() or 'top' in style.lower()):
            text = div.get_text(strip=True)
            if text and len(text) < 100:
                left_match = re.search(r'left:\s*(-?\d+(?:\.\d+)?)\s*px', style, re.IGNORECASE)
                top_match = re.search(r'top:\s*(-?\d+(?:\.\d+)?)\s*px', style, re.IGNORECASE)
                width_match = re.search(r'width:\s*(-?\d+(?:\.\d+)?)\s*px', style, re.IGNORECASE)
                height_match = re.search(r'height:\s*(-?\d+(?:\.\d+)?)\s*px', style, re.IGNORECASE)

                if left_match and top_match:
                    node = {
                        'text': text,
                        'x': float(left_match.group(1)),
                        'y': float(top_match.group(1)),
                        'width': float(width_match.group(1)) if width_match else 100,
                        'height': float(height_match.group(1)) if height_match else 50,
                        'shape_type': 'process'
                    }

                    text_lower = text.lower()
                    if any(k in text_lower for k in ['开始', 'start', '起始', '发起']):
                        node['shape_type'] = 'start'
                    elif any(k in text_lower for k in ['结束', 'end', '完成', '终止']):
                        node['shape_type'] = 'end'
                    elif any(k in text_lower for k in ['判断', '条件', '是否', '?', '？', '审核', '审批']):
                        node['shape_type'] = 'decision'
                    elif text in ['是', '否', 'yes', 'no', 'Y', 'N', '通过', '拒绝', '同意', '不同意']:
                        node['shape_type'] = 'label'

                    positioned_elements.append(node)

    has_flowchart_keywords = any(
        any(kw in node['text'].lower() for kw in flowchart_keywords)
        for node in positioned_elements
    )

    if len(positioned_elements) >= 3 and (has_connector_images or has_svg_lines or has_flowchart_keywords):
        result['has_flowchart'] = True
        result['nodes'] = positioned_elements
        result['connector_count'] = connector_count

        sorted_nodes = sorted(positioned_elements, key=lambda n: (n['y'], n['x']))

        descriptions = []
        for i, node in enumerate(sorted_nodes):
            if node['shape_type'] != 'label':
                descriptions.append(f"{i+1}. [{node['shape_type']}] {node['text']}")

        result['description'] = '\n'.join(descriptions)
        print(f"[流程图检测] 检测到 {len(positioned_elements)} 个节点, {connector_count} 个连接线图片")

    return result


async def convert_flowchart_to_mermaid_async(flowchart_data: Dict[str, Any], provider: str = "deepseek") -> str:
    """
    调用AI将流程图描述转换为Mermaid代码（异步版本）

    Args:
        flowchart_data: detect_and_extract_flowchart返回的数据
        provider: LLM提供商

    Returns:
        Mermaid格式的流程图代码
    """
    if not flowchart_data.get('has_flowchart') or not flowchart_data.get('nodes'):
        return ""

    # 构建提示词
    nodes_desc = []
    for node in flowchart_data['nodes']:
        if node['shape_type'] != 'label':
            nodes_desc.append(f"- 类型:{node['shape_type']}, 文字:「{node['text']}」, 位置:(x={node['x']}, y={node['y']})")

    labels = [n for n in flowchart_data['nodes'] if n['shape_type'] == 'label']
    labels_desc = ', '.join([f"「{l['text']}」" for l in labels]) if labels else "无"

    prompt = f"""请根据以下从Axure原型中提取的流程图元素，生成Mermaid格式的流程图代码。

## 提取的节点信息（按位置排序，y值越小越靠上）:
{chr(10).join(nodes_desc)}

## 连接线上的标签文字:
{labels_desc}

## 要求:
1. 使用 flowchart TD（从上到下）或 flowchart LR（从左到右）格式
2. 根据节点的位置关系（y值）推断连接顺序
3. 开始节点使用圆角矩形 ([文字])
4. 结束节点使用圆角矩形 ([文字])
5. 判断/条件节点使用菱形 {{文字}}
6. 普通处理节点使用矩形 [文字]
7. 如果有"是/否"等标签，添加到连接线上
8. 只输出Mermaid代码，不要其他解释

## 示例输出格式:
```mermaid
flowchart TD
    A([开始]) --> B[处理步骤1]
    B --> C{{判断条件}}
    C -->|是| D[处理步骤2]
    C -->|否| E[处理步骤3]
    D --> F([结束])
    E --> F
```

请生成Mermaid代码:"""

    try:
        response = await call_llm_api(prompt, provider=provider)
        content = response.get("choices", [{}])[0].get("message", {}).get("content", "")

        if not content:
            return ""

        # 提取代码块中的内容
        if '```mermaid' in content:
            match = re.search(r'```mermaid\s*([\s\S]*?)\s*```', content)
            if match:
                return match.group(1).strip()
        elif '```' in content:
            match = re.search(r'```\s*([\s\S]*?)\s*```', content)
            if match:
                return match.group(1).strip()

        if content.strip().startswith('flowchart'):
            return content.strip()

        return ""
    except Exception as e:
        print(f"[流程图转换] AI转换失败: {e}")
        return ""
