"""文本处理模块

包含 JSON 修复和系统提示词构建功能。
"""
import re


def _fix_json_control_chars(json_str: str) -> str:
    """
    修复JSON字符串中的控制字符问题
    大模型返回的JSON中，字符串字段可能包含真实的换行符、制表符等，
    需要将其转换为转义序列才能正确解析
    """
    # 在JSON字符串值内部，将真实的控制字符替换为转义序列
    # 匹配JSON字符串值: "..." 但不匹配已转义的
    def fix_string_value(match):
        s = match.group(0)
        # 替换未转义的控制字符
        # 注意：要保留已经转义的 \n \r \t
        result = []
        i = 0
        while i < len(s):
            if s[i] == '\\' and i + 1 < len(s):
                # 已转义的字符，保留
                result.append(s[i:i+2])
                i += 2
            elif s[i] == '\n':
                result.append('\\n')
                i += 1
            elif s[i] == '\r':
                result.append('\\r')
                i += 1
            elif s[i] == '\t':
                result.append('\\t')
                i += 1
            elif ord(s[i]) < 32:
                # 其他控制字符替换为空格
                result.append(' ')
                i += 1
            else:
                result.append(s[i])
                i += 1
        return ''.join(result)

    # 匹配JSON字符串（包括多行）
    # 这个正则匹配 "..." 形式的字符串，处理转义引号
    pattern = r'"(?:[^"\\]|\\.)*"'

    try:
        fixed = re.sub(pattern, fix_string_value, json_str, flags=re.DOTALL)
        return fixed
    except Exception:
        # 如果正则处理失败，尝试简单替换
        return json_str.replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')


def build_system_message(
        requirement_text: str,
        test_level: str,
        test_module: str,
        test_case_count: int,
        prompt: str = ""
) -> str:
    """
    构建系统提示词（不调用大模型）

    Args:
        requirement_text: 需求描述文本
        test_level: 测试级别
        test_priority: 测试优先级
        test_case_count: 测试用例数量
        prompt: 额外的提示词

    Returns:
        str: 完整的系统提示词
    """
    if prompt and test_case_count > 0:
        # 使用用户提供的提示词模板
        return prompt.format(
            requirement_text=requirement_text,
            test_level=test_level,
            test_module=test_module,
            test_case_count=test_case_count
        )
    elif prompt and test_case_count == -1:
        # 1. 把模板里的"请生成 X 条"替换成让 AI 自己决定
        prompt = prompt.replace(
            "请生成 {test_case_count} 个测试用例",
            "请根据你对需求描述的理解，全面输出合理的测试用例条数"
        )

        # 2. 组装其余变量（不再给 test_case_count 赋值）
        return prompt.format(
            requirement_text=requirement_text,
            test_level=test_level,
            test_module=test_module
            # test_case_count 不再传
        )
    else:
        # 使用默认提示词模板
        return f"""
你是一名资深测试工程师，擅长从需求文档中提取关键功能点并设计覆盖全场景的测试用例。请根据用户提供的需求文档，严格按照以下要求输出测试用例：

## 输入处理要求
1. 逐项解析需求文档中的功能点、业务规则和约束条件
2. 识别显性需求（文档明确描述）和隐性需求（行业常识/用户体验）
3. 特别注意边界条件、异常流程和关联功能影响

需求描述:
{requirement_text}


测试用例数量: 请生成 {test_case_count} 个测试用例


请确保测试用例全面覆盖以下测试类型:
1. 功能测试 - 验证功能是否按照需求正确实现
2. 主流程测试 - 验证核心业务流程正常工作
3. 边界条件测试 - 验证系统在极限值和边界情况下的表现
4. 异常情况测试 - 验证系统对错误输入和异常情况的处理
5. 用户界面测试 - 验证UI元素的正确显示和交互(如适用)

每个测试用例必须包含以下信息:
- 模块名称
- 唯一的测试用例ID (格式为TC-xxx，从001开始递增)
- 测试优先级 (与输入参数保持一致)
- 清晰简洁的测试标题
- 详细的前置条件
- 明确的测试步骤 (每个步骤单独一行，使用换行符分隔)
- 具体的预期结果 (每项单独一行，使用换行符分隔)

请直接输出符合以下格式的JSON，不要包含任何额外的说明、注释或Markdown标记:

{{
  "test_cases": [
    {{
      "test_module": "{test_module}",
      "case_id": "TC-001",
      "priority": "高/中/低",
      "title": "测试用例标题",
      "precondition": "测试前置条件",
      "steps": "1. 打开系统登录页面\n2. 输入用户名和密码\n3. 点击登录按钮",
      "expected_result": "1. 登录页面正常显示\n2. 用户名和密码输入框可用\n3. 成功登录进入首页"
    }}
  ]
}}

重要提示:
1. 确保生成的JSON格式完全有效且可直接解析
2. 所有字段必须填写完整，不能有空值
3. 不要输出JSON Schema或其他格式
4. 测试用例应直接关联需求，确保需求的每个方面都有测试覆盖
5. 测试步骤必须每个步骤单独一行，使用换行符 \\n 分隔，不要用分号或其他符号分隔
6. 预期结果必须每项单独一行，使用换行符 \\n 分隔，不要用分号或其他符号分隔
7. 换行符在JSON中表示为 \\n（两个字符：反斜杠+n）
"""
