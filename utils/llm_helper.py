"""LLM 辅助函数模块

包含需求精炼（refine_requirements）函数。
"""
import asyncio
from llms import call_llm_api


def refine_requirements_markdown(requirement_text: str, provider: str | None = None) -> str:
    """
    Use LLM to refine and structure requirement text into strict Markdown sections.
    Returns Markdown string.
    同步版本 - 用于非async上下文
    """
    prompt = f"""
你是一名文档整理专家。请将以下从原型提取的文字整理为清晰的Markdown格式，要求：

1. **保持原型的原始结构和层级关系**，不要改变内容的组织方式

2. **表格处理（重要）**：
   - 如果内容包含表格数据（如用 | 分隔的内容，或者有明显的行列结构），必须转换为标准Markdown表格
   - 表格格式示例：
     ```
     | 列1 | 列2 | 列3 | 列4 |
     |-----|-----|-----|-----|
     | 数据1 | 数据2 | 数据3 | 数据4 |
     ```
   - 表头行和数据行之间必须有 `|-----|-----|` 分隔线
   - 确保每行的列数一致
   - 如果原文有类似"模块|功能|类型|说明"这样的结构，识别为表格并格式化

3. 使用合适的Markdown标记：
   - 标题用 # ## ###
   - 列表用 - 或 1. 2. 3.
   - 重要内容可以用 **加粗**
   - 代码或技术术语用 `反引号`

4. 清理格式问题：
   - 去除多余的空行和空格
   - 修复破碎的句子
   - 合并重复的内容

5. **不要添加原文没有的内容**，不要臆造字段或功能

6. **不要改变原型的结构**，如果原型是按页面/模块组织的，保持这种组织方式

7. 如果有"参看原型"、"详情参看"等引用，保留这些引用关系

待整理内容：
{requirement_text}
"""

    try:
        resp = asyncio.run(call_llm_api(prompt, provider=provider))
        content = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
        return content.strip() if content else requirement_text
    except Exception:
        return requirement_text


async def refine_requirements_markdown_async(requirement_text: str, provider: str | None = None) -> str:
    """
    Use LLM to refine and structure requirement text into strict Markdown sections.
    Returns Markdown string.
    异步版本 - 用于async上下文（如FastAPI）
    """
    print(f"[DEBUG] refine_requirements_markdown_async 被调用, provider={provider}, 文本长度={len(requirement_text)}")

    prompt = f"""
你是一名文档整理专家。请将以下从原型提取的文字整理为清晰的Markdown格式，要求：

1. **保持原型的原始结构和层级关系**，不要改变内容的组织方式，去掉菜单功能描述，只保留页面主要功能描述和介绍

2. **表格处理（重要）**：
   - 如果内容包含表格数据，必须转换为标准 Markdown 表格格式
   - 标准格式示例：
     ```
     | 列1 | 列2 | 列3 |
     |-----|-----|-----|
     | 数据1 | 数据2 | 数据3 |
     ```
   - 确保每行的列数一致，表头和分隔符完整
   - 识别"字段|类型|说明"等结构并格式化为表格

3. **流程图处理（重要）**：
   - 如果内容描述了流程、步骤、状态转换，请用 Mermaid 流程图格式输出
   - 格式示例：
     ```mermaid
     flowchart TD
         A[开始] --> B{{判断条件}}
         B -->|是| C[执行操作1]
         B -->|否| D[执行操作2]
         C --> E[结束]
         D --> E
     ```
   - 状态流转用 `stateDiagram-v2`
   - 时序图用 `sequenceDiagram`

4. 使用合适的Markdown标记：
   - 标题用 # ## ###
   - 列表用 - 或 1. 2. 3.
   - 重要内容可以用 **加粗**
   - 代码或技术术语用 `反引号`

5. 清理格式问题：
   - 去除多余的空行和空格
   - 修复破碎的句子
   - 合并重复的内容

6. **不要添加原文没有的内容**，不要臆造字段或功能

7. **不要改变原型的结构**，保持按页面/模块组织的方式

8. 保留"参看原型"、"详情参看"等引用关系

9.你只需要返回待整理的内容即可 不要返回其他内容

待整理内容：
{requirement_text}
"""

    try:
        print(f"[DEBUG] 开始调用LLM API...")
        resp = await call_llm_api(prompt, provider=provider)
        print(f"[DEBUG] LLM API调用完成, 响应: {str(resp)[:200]}...")
        content = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
        if content:
            print(f"[DEBUG] AI结构化成功, 结果长度={len(content)}")
            return content.strip()
        else:
            print(f"[DEBUG] AI返回内容为空，使用原始文本")
            return requirement_text
    except Exception as e:
        print(f"[DEBUG] AI结构化失败: {e}")
        import traceback
        traceback.print_exc()
        return requirement_text
