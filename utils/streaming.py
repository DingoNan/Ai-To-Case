"""流式测试用例生成模块"""
import re
import json
from llms import call_llm_api_stream
from .text import build_system_message, _fix_json_control_chars


async def generate_test_cases_stream(
        requirement_text: str,
        test_level: str,
        test_module: str,
        test_case_count: int,
        system_message: str,
        provider: str | None = None,
        prompt: str = ""
):
    """
    流式生成测试用例，逐块返回内容
    
    现在会从流式API最后一条消息中提取 token_usage 并传递到 complete 事件中

    Yields:
        dict: 包含类型和内容的字典
            - {"type": "chunk", "content": str}: 流式文本片段
            - {"type": "complete", "content": str, "test_cases": dict, "_token_usage": dict}: 完成时返回完整内容和解析后的测试用例
            - {"type": "error", "content": str}: 错误信息
    """
    # 如果未提供system_message，则构建它
    if system_message is None:
        system_message = build_system_message(
            requirement_text, test_level, test_module, test_case_count, prompt
        )

    full_content = ""
    token_usage = {}
    try:
        print("发送给到大模型的提示词为: " + system_message)
        # 流式调用大模型API
        async for chunk in call_llm_api_stream(system_message, provider=provider):
            # 检查是否为错误
            if isinstance(chunk, dict) and "error" in chunk:
                yield {"type": "error", "content": chunk.get("error")}
                return

            # 检查是否为 token_usage 信息（流式API最后一条消息）
            if isinstance(chunk, dict) and "_token_usage" in chunk:
                token_usage = chunk["_token_usage"]
                continue

            # 累积内容
            full_content += chunk
            # 返回流式片段
            yield {"type": "chunk", "content": chunk}

        # 流式完成后，解析完整的JSON
        try:
            # 先修复JSON中的控制字符
            fixed_content = _fix_json_control_chars(full_content)
            # 尝试直接解析整个内容
            test_cases = json.loads(fixed_content)

            # 验证结构是否正确
            if "test_cases" not in test_cases or not isinstance(test_cases["test_cases"], list):
                raise ValueError("生成的测试用例格式不正确")

            yield {"type": "complete", "content": full_content, "test_cases": test_cases, "_token_usage": token_usage}
        except json.JSONDecodeError:
            # 如果直接解析失败，尝试提取JSON部分
            json_pattern = r'\{[\s\S]*\}'
            match = re.search(json_pattern, full_content)

            if match:
                json_str = match.group(0)
                # 修复JSON中的控制字符
                fixed_json_str = _fix_json_control_chars(json_str)
                test_cases = json.loads(fixed_json_str)

                # 验证结构是否正确
                if "test_cases" not in test_cases or not isinstance(test_cases["test_cases"], list):
                    raise ValueError("生成的测试用例格式不正确")

                yield {"type": "complete", "content": full_content, "test_cases": test_cases, "_token_usage": token_usage}
            else:
                yield {"type": "error", "content": "无法从API响应中提取JSON"}

    except Exception as e:
        yield {"type": "error", "content": f"生成测试用例失败: {str(e)}"}
