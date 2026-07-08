"""OCR 识别模块

包含 OCR 识别函数（含熔断机制：并发限制/超时控制/失败重试）。
"""
import asyncio
import base64
from llms import call_vision_api
from .config import _get_ocr_semaphore, OCR_TIMEOUT, OCR_MAX_RETRIES


async def ocr_image_async(uploaded_files, vision_provider: str = "aliyun", custom_prompt: str = None):
    """
    使用视觉大模型识别图片内容，支持多张图片并发处理（异步版本）
    内置熔断机制：并发限制 / 超时控制 / 失败重试

    Args:
        uploaded_files: 单个图片字节或图片字节列表
        vision_provider: 视觉模型提供商，"aliyun" 或 "deepseek"（默认 aliyun）
        custom_prompt: 自定义识别提示词，为空则使用默认提示词

    Returns:
        tuple: (识别文本, token用量字典)
        token用量字典格式: {"prompt_tokens": int, "completion_tokens": int, "total_tokens": int, "model": str}
    """
    # 处理上传的文件对象
    if not uploaded_files:
        return ""
    input_list = [uploaded_files] if isinstance(uploaded_files, bytes) else uploaded_files

    # 使用自定义提示词或默认提示词
    if custom_prompt and custom_prompt.strip():
        prompt = custom_prompt.strip()
    else:
        # 默认表格识别提示词
        prompt = """请识别这张图片中的所有文字内容，并100%还原原始格式和布局。

要求：
1. 如果图片包含表格，必须使用 Markdown 表格格式输出，示例：
   | 列1 | 列2 | 列3 |
   | --- | --- | --- |
   | 数据1 | 数据2 | 数据3 |

2. 表格要求：
   - 完整保留所有行和列，不要遗漏任何单元格
   - 如果有合并单元格，在对应位置重复内容或留空
   - 保持原表格的列数一致
   - 表头和数据行都要完整输出

3. 【重要】如果是非表格内容（如表单、字段列表、按钮、标签等）：
   - 同一行的内容必须保持在同一行，用空格或制表符分隔，绝对不要换行
   - 横向排列的元素必须保持横向排列，例如：字段1  字段2  字段3  字段4
   - 保持原始的相对位置关系，左边的在左边，右边的在右边
   - 不要把横向的内容拆分成多行垂直排列
   - 示例：如果图片中 "姓名" "年龄" "性别" 在同一行，输出应该是：姓名  年龄  性别

4. 只输出识别到的内容，不要添加任何解释、说明或总结

5. 保持原文的语言（中文/英文等），不要翻译"""

    async def process_single_image(idx: int, file_bytes: bytes):
        """处理单张图片（带熔断：信号量+超时+重试）"""
        async with _get_ocr_semaphore():
            for attempt in range(OCR_MAX_RETRIES + 1):
                try:
                    image_base64 = base64.b64encode(file_bytes).decode('utf-8')
                    result = await asyncio.wait_for(
                        call_vision_api(image_base64, prompt, provider=vision_provider),
                        timeout=OCR_TIMEOUT
                    )

                    if "error" in result:
                        if attempt < OCR_MAX_RETRIES:
                            print(f"[OCR] 图片 {idx+1} 第{attempt+1}次失败: {result['error']}，正在重试...")
                            continue
                        return idx, f"图片 {idx + 1}: 识别失败: {result['error']}", None

                    choices = result.get("choices", [])
                    if choices:
                        content = choices[0].get("message", {}).get("content", "")
                        if content:
                            token_usage = result.get("_token_usage", None)
                            return idx, content, token_usage
                    return idx, f"图片 {idx + 1}: 未识别到文字", None
                except asyncio.TimeoutError:
                    if attempt < OCR_MAX_RETRIES:
                        print(f"[OCR] 图片 {idx+1} 第{attempt+1}次超时，正在重试...")
                        continue
                    return idx, f"图片 {idx + 1}: 识别超时", None
                except Exception as e:
                    if attempt < OCR_MAX_RETRIES:
                        print(f"[OCR] 图片 {idx+1} 第{attempt+1}次异常: {e}，正在重试...")
                        continue
                    return idx, f"图片 {idx + 1}: 识别处理失败: {str(e)}", None

    # 并发处理所有图片（信号量控制并发数）
    tasks = [process_single_image(idx, fb) for idx, fb in enumerate(input_list)]
    results = await asyncio.gather(*tasks)
    # 按原始顺序排序
    results.sort(key=lambda x: x[0])

    # 格式化输出，同时累积 token 用量
    all_results = []
    total_token_usage = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "model": ""
    }
    for idx, content, token_usage in results:
        if len(input_list) > 1:
            all_results.append(f"=== 图片 {idx + 1} ===\n{content}")
        else:
            all_results.append(content)
        
        if token_usage:
            total_token_usage["prompt_tokens"] += token_usage.get("prompt_tokens", 0)
            total_token_usage["completion_tokens"] += token_usage.get("completion_tokens", 0)
            total_token_usage["total_tokens"] += token_usage.get("total_tokens", 0)
            model_name = token_usage.get("model", "") or ""
            if model_name and model_name not in total_token_usage["model"]:
                total_token_usage["model"] = model_name

    final_result = "\n\n".join(all_results)
    print("Vision OCR Result:", final_result)
    return final_result, total_token_usage


def _structure_ocr_result(ocr_lines):
    """
    根据 OCR 返回的坐标信息，识别表格结构并格式化输出

    Args:
        ocr_lines: PaddleOCR 返回的识别结果列表，每项为 [[[x1,y1], [x2,y2], [x3,y3], [x4,y4]], (text, confidence)]

    Returns:
        str: 结构化的文本，表格用制表符分隔
    """
    if not ocr_lines:
        return ""

    # 提取每个文本块的信息：文本、中心y坐标、中心x坐标、高度
    text_blocks = []
    for line in ocr_lines:
        box = line[0]  # [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
        text = line[1][0]  # 文本内容

        # 计算边界框的中心坐标和高度
        y_coords = [point[1] for point in box]
        x_coords = [point[0] for point in box]
        center_y = sum(y_coords) / 4
        center_x = sum(x_coords) / 4
        height = max(y_coords) - min(y_coords)
        min_x = min(x_coords)

        text_blocks.append({
            'text': text,
            'center_y': center_y,
            'center_x': center_x,
            'min_x': min_x,
            'height': height
        })

    if not text_blocks:
        return ""

    # 计算平均行高，用于判断是否在同一行
    avg_height = sum(b['height'] for b in text_blocks) / len(text_blocks)
    row_threshold = avg_height * 0.6  # 行间距阈值

    # 按 y 坐标排序
    text_blocks.sort(key=lambda b: b['center_y'])

    # 分组：将 y 坐标相近的文本块归为同一行
    rows = []
    current_row = [text_blocks[0]]

    for block in text_blocks[1:]:
        # 如果当前块与当前行的 y 坐标差距小于阈值，认为在同一行
        if abs(block['center_y'] - current_row[0]['center_y']) < row_threshold:
            current_row.append(block)
        else:
            rows.append(current_row)
            current_row = [block]

    rows.append(current_row)

    # 判断是否是表格结构（多行且每行有多列）
    multi_col_rows = sum(1 for row in rows if len(row) > 1)
    is_table = multi_col_rows >= 2  # 至少2行有多列才认为是表格

    # 格式化输出
    result_lines = []
    for row in rows:
        # 按 x 坐标排序（从左到右）
        row.sort(key=lambda b: b['min_x'])

        if is_table and len(row) > 1:
            # 表格行：用制表符分隔
            line_text = "\t".join(b['text'] for b in row)
        else:
            # 普通行：用空格连接或直接输出
            line_text = " ".join(b['text'] for b in row)

        result_lines.append(line_text)

    return "\n".join(result_lines)
