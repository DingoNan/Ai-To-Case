import xmind
import re
import os
from collections import defaultdict

import re


def test_cases_to_xmind(test_cases_data: dict, xmind_path: str, root_title: str = "测试用例", menu1: str = "", menu2: str = ""):
    """
    直接从测试用例数据生成 XMind 文件，保留换行符

    Args:
        test_cases_data: 测试用例字典，格式为 {"test_cases": [...]}
        xmind_path: 输出的 XMind 文件路径
        root_title: 根节点标题
        menu1: 菜单1名称（可选）
        menu2: 菜单2名称（可选）
    """
    # 加载模板
    blank_template = os.path.join(os.path.dirname(__file__), 'blank.xmind')
    workbook = xmind.load(blank_template)
    sheet = workbook.getPrimarySheet()
    sheet.setTitle(root_title)
    root = sheet.getRootTopic()
    root.setTitle(root_title)

    # 按模块分组
    modules = {}
    for case in test_cases_data.get("test_cases", []):
        module = case.get("test_module", "未分类")
        if module not in modules:
            modules[module] = []
        modules[module].append(case)

    # 创建模块节点
    for module, cases in modules.items():
        module_topic = root.addSubTopic()
        module_topic.setTitle(module)

        # 创建菜单层级
        current_parent = module_topic
        if menu1:
            menu1_topic = current_parent.addSubTopic()
            menu1_topic.setTitle(menu1)
            current_parent = menu1_topic

            if menu2:
                menu2_topic = current_parent.addSubTopic()
                menu2_topic.setTitle(menu2)
                current_parent = menu2_topic

        # 创建测试用例节点
        for case in cases:
            title = case.get("title", "")
            steps = case.get("steps", "")
            expected_result = case.get("expected_result", "")

            # 用例标题
            case_topic = current_parent.addSubTopic()
            case_topic.setTitle(title)

            # 处理测试步骤：将分号、句号等分隔符替换为换行
            if steps:
                # 替换各种分隔符为换行符
                steps_processed = steps
                # 处理中文分号
                steps_processed = steps_processed.replace('；', '\n')
                # 处理英文分号
                steps_processed = steps_processed.replace(';', '\n')
                # 如果步骤是用数字编号的，确保每个编号前都有换行
                import re
                steps_processed = re.sub(r'(?<!\n)\s*(?=\d+\.)', '\n', steps_processed)
                # 去除开头可能的换行
                steps_processed = steps_processed.strip()

                steps_topic = case_topic.addSubTopic()
                steps_topic.setTitle(steps_processed)

                # 处理预期结果：作为测试步骤的子节点，保留换行符
                if expected_result:
                    result_processed = expected_result
                    result_processed = result_processed.replace('；', '\n')
                    result_processed = result_processed.replace(';', '\n')
                    result_processed = re.sub(r'(?<!\n)\s*(?=\d+\.)', '\n', result_processed)
                    result_processed = result_processed.strip()

                    result_topic = steps_topic.addSubTopic()
                    result_topic.setTitle(result_processed)
            elif expected_result:
                # 如果没有测试步骤但有预期结果
                result_processed = expected_result
                result_processed = result_processed.replace('；', '\n')
                result_processed = result_processed.replace(';', '\n')
                result_processed = re.sub(r'(?<!\n)\s*(?=\d+\.)', '\n', result_processed)
                result_processed = result_processed.strip()

                result_topic = case_topic.addSubTopic()
                result_topic.setTitle(result_processed)

    # 保存文件
    xmind.save(workbook, xmind_path)


def test_cases_to_xmind_text(test_cases_data: dict, root_title: str = "测试用例", menu1: str = "", menu2: str = "") -> str:
    """
    将测试用例数据转换为可直接粘贴到 XMind 的 Tab 缩进文本格式

    Args:
        test_cases_data: 测试用例字典，格式为 {"test_cases": [...]}
        root_title: 根节点标题
        menu1: 菜单1名称（可选）
        menu2: 菜单2名称（可选）

    Returns:
        str: Tab 缩进格式的文本，可直接粘贴到 XMind
    """
    lines = [root_title]

    # 按模块分组
    modules = {}
    for case in test_cases_data.get("test_cases", []):
        module = case.get("test_module", "未分类")
        if module not in modules:
            modules[module] = []
        modules[module].append(case)

    for module, cases in modules.items():
        # 模块名称 (第1级缩进)
        lines.append(f"\t{module}")

        # 计算用例的基础缩进级别
        base_indent = 1  # 模块是第1级

        # 菜单1 (如果有，第2级缩进)
        if menu1:
            base_indent += 1
            lines.append("\t" * base_indent + menu1)

            # 菜单2 (如果有，第3级缩进)
            if menu2:
                base_indent += 1
                lines.append("\t" * base_indent + menu2)

        for case in cases:
            title = case.get("title", "")
            steps = case.get("steps", "")
            expected_result = case.get("expected_result", "")

            # 用例标题 - 只显示标题，不要case_id
            case_indent = "\t" * (base_indent + 1)
            lines.append(f"{case_indent}{title}")

            # 测试步骤 - 多行用空格拼接成一行（用于粘贴到XMind）
            detail_indent = "\t" * (base_indent + 2)
            if steps:
                step_lines = [line.strip() for line in steps.strip().split('\n') if line.strip()]
                steps_joined = ' '.join(step_lines)
                lines.append(f"{detail_indent}{steps_joined}")

                # 预期结果 - 作为测试步骤的子主题，多行用空格拼接
                if expected_result:
                    result_indent = "\t" * (base_indent + 3)
                    result_lines = [line.strip() for line in expected_result.strip().split('\n') if line.strip()]
                    results_joined = ' '.join(result_lines)
                    lines.append(f"{result_indent}{results_joined}")
            elif expected_result:
                # 如果没有测试步骤但有预期结果，预期结果直接放在用例标题下面
                result_lines = [line.strip() for line in expected_result.strip().split('\n') if line.strip()]
                results_joined = ' '.join(result_lines)
                lines.append(f"{detail_indent}{results_joined}")

    return '\n'.join(lines)


def flatten_md(md: str) -> str:
    """
    仅处理 ##### / ######
    把标题行 + 后面紧跟的 1./2./3.… 全部用 \n 拼成一行
    作为新的标题内容，不再丢弃任何 1. 2. 3.
    """
    # 按空行（2+ 换行）切分成块
    blocks = re.split(r'(?:\r?\n){2,}', md.strip())

    def process_block(block: str) -> str:
        # 匹配 5/6 级标题行
        m = re.match(r'^(#{5,6})\s+(.*)', block)
        if not m:
            return block

        level = m.group(1)
        # 整块内容去掉开头的 “##### ” 或 “###### ”
        body = block[m.end():]
        # 取出所有 1./2./3./… 行
        items = re.findall(r'^\s*(\d+\..*)', block[m.end():], flags=re.M)
        # 把标题行本身也当作第一项
        items.insert(0, m.group(2).strip())
        merged = r'\n'.join(item.strip() for item in items)
        return f"{level} {merged}"

    return '\n\n'.join(process_block(b) for b in blocks)

def parse_md_text(md_text: str):
    import re
    from collections import defaultdict

    def split_title(title: str) -> str:
        return title.replace('\\n', '\n')

    lines = md_text.splitlines()
    nodes, children = {}, defaultdict(list)

    def make_key(parent_path, title):
        return parent_path + (title,)

    def get_or_create(parent_path, title):
        key = make_key(parent_path, title)
        if key not in nodes:
            nodes[key] = {'title': title, 'children': []}
            children[parent_path].append(key)
        return key

    # 需要跳过的标题（不创建节点，但内容合并为一个主题）
    skip_titles = {'测试步骤', '预期结果'}
    # 需要捕获内容的标题
    capture_titles = {'测试步骤', '预期结果', '前置条件', '优先级', '备注'}

    cur_path = ()
    buffer = []
    capture_mode = False
    skip_current_title = False
    is_expected_result = False  # 标记当前是否是预期结果
    last_steps_path = None  # 记录测试步骤创建的主题路径

    for line in lines:
        line = line.rstrip()
        m = re.match(r'^(#+)\s*(.*)', line)
        if m:
            # 落盘缓冲区
            if buffer:
                text = '\n'.join(buffer).strip()
                if text:
                    if skip_current_title:
                        if is_expected_result and last_steps_path is not None:
                            # 预期结果：作为测试步骤的子节点
                            get_or_create(last_steps_path, text)
                        else:
                            # 测试步骤：创建节点并记录路径
                            new_key = get_or_create(cur_path, text)
                            last_steps_path = new_key
                    else:
                        # 其他标题：按原来的方式处理
                        items = re.split(r'\n\s*(?=\d+\.)', text)
                        for item in items:
                            item = item.strip()
                            if item:
                                get_or_create(cur_path, item)
                        last_steps_path = None  # 重置
                buffer.clear()

            level = len(m.group(1))
            title = split_title(m.group(2).strip())

            # 检查是否是需要跳过的标题
            title_clean = title.rstrip(':').rstrip('：')  # 去掉末尾的冒号
            if title_clean in skip_titles:
                skip_current_title = True
                capture_mode = True
                is_expected_result = (title_clean == '预期结果')
                # 不创建这个标题节点，保持 cur_path 不变
                cur_path = cur_path[:level - 1]
            else:
                skip_current_title = False
                is_expected_result = False
                last_steps_path = None  # 遇到非跳过标题，重置
                cur_path = cur_path[:level - 1]
                cur_path = get_or_create(cur_path, title)
                capture_mode = any(k in title.lower() for k in capture_titles)
        else:
            if capture_mode:
                buffer.append(line)
            else:
                content = line.strip()
                if content:
                    get_or_create(cur_path, content)

    # 文件末尾落盘
    if buffer:
        text = '\n'.join(buffer).strip()
        if text:
            if skip_current_title:
                if is_expected_result and last_steps_path is not None:
                    # 预期结果：作为测试步骤的子节点
                    get_or_create(last_steps_path, text)
                else:
                    # 测试步骤：创建节点
                    get_or_create(cur_path, text)
            else:
                # 其他标题：按原来的方式处理
                items = re.split(r'\n\s*(?=\d+\.)', text)
                for item in items:
                    item = item.strip()
                    if item:
                        get_or_create(cur_path, item)

    def build_recursive(key):
        node = nodes[key]
        return {
            'title': node['title'],
            'children': [build_recursive(k) for k in children[key]]
        }

    root_key = ()
    if root_key not in children:
        return {'title': 'Root', 'children': []}

    return {'title': 'Root', 'children': [build_recursive(k) for k in children[root_key]]}
# ---------- XMind 写入 ----------
def add_topics(parent, nodes):
    """递归添加子节点到 XMind"""
    for node in nodes:
        topic = parent.addSubTopic()
        topic.setTitle(node['title'])
        add_topics(topic, node['children'])

def md_to_xmind(md_text, xmind_path):
    md_text_new = flatten_md(md_text)
    tree = parse_md_text(md_text_new)
    print('解析并去重后的树结构:\n', tree)

    # 打开/新建工作簿
    # if os.path.exists(xmind_path):
    #     workbook = xmind.load(xmind_path)
    # else:
    #     workbook = xmind.load('new.xmind')

    blank_template = os.path.join(os.path.dirname(__file__), 'blank.xmind')
    workbook = xmind.load(blank_template)  # ✅ 关键修复
    sheet = workbook.getPrimarySheet()
    sheet.setTitle("From Markdown")
    root = sheet.getRootTopic()
    root.setTitle(tree['title'])
    add_topics(root, tree['children'])
    xmind.save(workbook, xmind_path)
