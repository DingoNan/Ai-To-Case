# AI测试用例生成系统 - 详细设计文档

**文档编号**: AiToCase-SDD-001  
**版本**: V2.0  
**编制日期**: 2025年3月  
**项目名称**: AI测试用例生成系统 (AiToCase)  
**项目版本**: V2.0

---

## 1. 系统架构设计

### 1.1 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                         Web层 (FastAPI)                        │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐  │
│  │ 页面路由 │ │ API路由  │ │ 静态文件 │ │ 模板引擎 │ │ SSE流  │  │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                        业务逻辑层                               │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐          │
│  │ 文档解析模块 │ │ 向量检索模块  │ │ 测试用例生成 │          │
│  │              │ │              │ │    模块      │          │
│  └──────────────┘ └──────────────┘ └──────────────┘          │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐          │
│  │  知识库管理  │ │  导出模块    │ │  AI整理优化  │          │
│  │    模块      │ │              │ │    模块      │          │
│  └──────────────┘ └──────────────┘ └──────────────┘          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                         数据层                                   │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐          │
│  │  LlamaIndex  │ │   Chroma     │ │  文件系统    │          │
│  │  向量库      │ │  向量数据库  │ │  (临时文件)  │          │
│  └──────────────┘ └──────────────┘ └──────────────┘          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                       外部服务层                                │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐       │
│  │ DeepSeek │ │ 阿里云   │ │  字节跳动 │ │   Azure  │       │
│  │   API    │ │ DashScope│ │   豆包    │ │  OpenAI  │       │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘       │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 模块划分

| 模块名称 | 文件 | 职责 |
|----------|------|------|
| Web服务模块 | main.py | FastAPI应用、路由定义、数据模型 |
| LLM调用模块 | llms.py | 多提供商API封装 |
| 基础工具模块 | utils.py | 文档解析、向量库、OCR、Axure解析 |
| 增强知识库模块 | utils_enhanced_kb.py | 增强版知识库管理 |
| Sitemap知识库模块 | utils_sitemap_kb.py | 基于Sitemap的知识库 |
| XMind导出模块 | md_to_xmind_utils.py | 测试用例转XMind格式 |

---

## 2. 数据模型设计

### 2.1 请求数据模型

```python
class GenerateRequest(BaseModel):
    """测试用例生成请求"""
    requirement_text: str           # 需求描述
    context_text: str = ""          # 上下文（全量内容）
    test_module: str = "模块"       # 模块名称
    menu1: str = ""                # 菜单1
    menu2: str = ""                # 菜单2
    test_case_count: int = 10      # 用例数量
    prompt: str = ""               # 自定义提示词
    provider: str = "azure"        # LLM提供商
    source_type: str = "manual-input"  # 来源类型
```

```python
class CreateKnowledgeBaseRequest(BaseModel):
    """创建知识库请求"""
    name: str                       # 知识库名称
    axure_url: str                 # Axure URL
    vision_provider: str = "doubao" # 视觉模型提供商
    username: str = ""              # 登录用户名
    password: str = ""              # 登录密码
    use_ai_refine: bool = False    # 是否AI整理
    max_concurrent: int = 5          # 最大并发数
```

```python
class ChromaQueryRequest(BaseModel):
    """Chroma向量检索请求"""
    collection_name: str            # 集合名称
    query_text: str                # 查询文本
    top_k: int = 5                 # 返回数量
    use_ai_refine: bool = False   # 是否AI整理
    provider: str = "azure"        # LLM提供商
```

### 2.2 响应数据模型

```python
# 测试用例JSON格式
{
    "test_cases": [
        {
            "test_module": "模块名称",
            "case_id": "TC-001",
            "priority": "高",
            "title": "测试用例标题",
            "precondition": "前置条件描述",
            "steps": "1. 步骤一\n2. 步骤二\n3. 步骤三",
            "expected_result": "1. 预期结果一\n2. 预期结果二"
        }
    ]
}
```

---

## 3. 核心模块设计

### 3.1 LLM调用模块 (llms.py)

#### 3.1.1 模块职责

统一封装多提供商LLM API调用，支持同步和流式两种模式。

#### 3.1.2 核心函数

| 函数名 | 输入 | 输出 | 说明 |
|--------|------|------|------|
| call_llm_api() | prompt, provider | dict | 同步调用LLM |
| call_llm_api_stream() | prompt, provider | AsyncIterator | 流式调用LLM |
| call_vision_api() | image_base64, prompt, provider | dict | 视觉模型调用 |

#### 3.1.3 提供商配置

```python
# DeepSeek
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_MODEL = "deepseek-chat"
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"

# 阿里云DashScope
ALIYUN_API_KEY = os.getenv("ALIYUN_API_KEY")
ALIYUN_MODEL = "qwen-plus"
ALIYUN_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

# 字节跳动豆包
DOUBAO_API_KEY = os.getenv("DOUBAO_API_KEY")
DOUBAO_MODEL = "doubao-1-5-pro-32k-250115"
DOUBAO_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"

# Azure OpenAI
AZURE_API_KEY = os.getenv("AZURE_API_KEY")
AZURE_DEPLOYMENT = os.getenv("AZURE_DEPLOYMENT")
AZURE_BASE_URL = os.getenv("AZURE_BASE_URL")
AZURE_API_VERSION = "2024-08-01-preview"
```

### 3.2 文档解析模块 (utils.py)

#### 3.2.1 文档解析器

| 解析器 | 支持格式 | 说明 |
|--------|----------|------|
| parse_pdf_to_text() | .pdf | 使用PyMuPDF解析 |
| parse_word_to_text() | .docx, .doc | 使用python-docx解析 |
| parse_markdown_with_images() | .md | Markdown解析+图片OCR |
| parse_axure_zip_to_text() | .zip | Axure ZIP包解析 |
| parse_axure_html_to_text() | .html, .htm | Axure HTML解析 |

#### 3.2.2 Axure解析流程

```
Axure文件 ──▶ ZIP/HTML解析 ──▶ 提取页面内容
                                      │
                                      ▼
                              分离全量/增量内容
                                      │
                                      ▼
                              Markdown格式化
                                      │
                                      ▼
                              返回结构化内容
```

### 3.3 向量检索模块

#### 3.3.1 LlamaIndex向量库

```python
# 配置
VECTOR_DB_PATH = r"D:\python\PythonProject\vector_db2"
EMBEDDING_MODEL = r"D:\python\models\Ceceliachenen\paraphrase-multilingual-MiniLM-L12-v2"

# 核心函数
init_vector_db(file_bytes, filename)  # 初始化向量库
query_vector_db(persist_dir, question)  # 向量检索
```

#### 3.3.2 Chroma向量库

```python
# 配置
CHROMA_DB_PATH = r"D:\python\PythonProject\chroma_db"
DASHSCOPE_EMBEDDING_MODEL = "text-embedding-v3"

# 核心函数
init_chroma_vector_db(file_bytes, filename)  # Chroma向量化
query_chroma_vector_db(collection_name, query_text, top_k)  # Chroma检索
list_chroma_collections()  # 列出所有集合
delete_chroma_collection(name)  # 删除集合
```

### 3.4 测试用例生成模块

#### 3.4.1 核心流程

```python
async def generate_test_cases_stream(
    requirement_text: str,      # 需求文本
    test_level: str,            # 测试级别
    test_module: str,           # 模块名称
    test_case_count: int,       # 用例数量
    system_message: str,        # 系统提示词
    provider: str,              # LLM提供商
    prompt: str                 # 提示词模板
):
    # 1. 构建系统提示词
    system_msg = build_system_message(...)
    
    # 2. 流式调用LLM
    async for chunk in call_llm_api_stream(...):
        yield {"type": "chunk", "content": chunk}
    
    # 3. 解析JSON结果
    test_cases = json.loads(full_content)
    yield {"type": "complete", "test_cases": test_cases}
```

#### 3.4.2 提示词模板

```python
# prompts.json 配置
{
    "prompt_default": "你是一名资深测试工程师...",
    "prompt_field": "...",
    "promptAgain": "..."
}
```

### 3.5 知识库管理模块

#### 3.5.1 增强版知识库 (utils_enhanced_kb.py)

**Phase 2: 增强版Axure解析**
- 使用sitemap.js获取所有页面列表
- 并发获取页面内容
- 识别蓝色字体标记的增量内容

**Phase 3: 分层向量化存储**
```
┌─────────────────────────────────────┐
│           Chroma 集合              │
├─────────────────────────────────────┤
│  tier_page    - 单页内容向量       │
│  tier_incremental - 增量内容向量    │
│  tier_module  - 模块级内容向量       │
└─────────────────────────────────────┘
```

**Phase 4: AI关联分析**
- 使用LLM分析页面关联关系
- 构建页面关系图谱

**Phase 5: 智能召回系统**
- 增量+全量上下文召回
- 多种召回策略：
  - auto: 自动选择
  - incremental_with_context: 增量+上下文
  - page_level: 页面级
  - module_level: 模块级

#### 3.5.2 Sitemap知识库 (utils_sitemap_kb.py)

```python
# 核心功能
fetch_all_pages_from_sitemap()    # 获取所有页面
analyze_page_relationships_with_ai()  # AI分析页面关联
build_three_tier_vectors()       # 构建三层向量
store_vectors_to_chroma()         # 存储到Chroma
```

### 3.6 XMind导出模块 (md_to_xmind_utils.py)

#### 3.6.1 导出结构

```
测试用例 (根)
├── 模块1
│   ├── 菜单1 (可选)
│   │   ├── 菜单2 (可选)
│   │   │   └── 用例1
│   │   │       ├── 步骤
│   │   │       └── 预期结果
│   │   └── 用例2
│   └── 用例3
└── 模块2
    └── ...
```

#### 3.6.2 核心函数

```python
test_cases_to_xmind()     # 生成XMind文件
test_cases_to_xmind_text() # 生成XMind粘贴文本
md_to_xmind()            # Markdown转XMind
```

---

## 4. API接口设计

### 4.1 页面路由

| 路由 | 方法 | 说明 |
|------|------|------|
| / | GET | 首页 |

### 4.2 文档上传API

| 路由 | 方法 | 说明 |
|------|------|------|
| /api/upload/document | POST | 上传文档并向量化(LlamaIndex) |
| /api/upload/axure | POST | 上传Axure文件解析 |
| /api/upload/images | POST | 上传图片OCR识别 |
| /api/fetch/axure-url | POST | 在线获取Axure内容 |

### 4.3 向量检索API

| 路由 | 方法 | 说明 |
|------|------|------|
| /api/vector/query | POST | LlamaIndex向量检索 |
| /api/chroma/upload | POST | Chroma向量化 |
| /api/chroma/query | POST | Chroma向量检索 |
| /api/chroma/collections | GET | 获取所有集合 |
| /api/chroma/collection/{name} | DELETE | 删除集合 |

### 4.4 测试用例生成API

| 路由 | 方法 | 说明 |
|------|------|------|
| /api/testcase/generate | POST | 非流式生成 |
| /api/testcase/generate/stream | POST | 流式生成(SSE) |
| /api/refine | POST | AI优化需求文档 |

### 4.5 知识库管理API

| 路由 | 方法 | 说明 |
|------|------|------|
| /api/kb/list | GET | 获取知识库列表 |
| /api/kb/create | POST | 创建知识库 |
| /api/kb/{collection_name} | DELETE | 删除知识库 |
| /api/kb/recall | POST | 召回相关内容 |
| /api/kb/generate-test-cases | POST | 从知识库生成用例 |
| /api/kb/enhanced/list | GET | 增强版知识库列表 |
| /api/kb/enhanced/create | POST | 创建增强版知识库 |
| /api/kb/enhanced/smart-recall | POST | 智能召回 |
| /api/kb/enhanced/generate-test-cases | POST | 智能生成用例 |

### 4.6 导出API

| 路由 | 方法 | 说明 |
|------|------|------|
| /api/export/csv | POST | 导出CSV |
| /api/export/markdown | POST | 导出Markdown |
| /api/export/xmind | POST | 导出XMind |
| /api/export/xmind-text | POST | 获取XMind文本 |

---

## 5. 前端设计

### 5.1 页面结构

```html
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>AI测试用例生成系统</title>
    <link rel="stylesheet" href="/static/css/style.css">
    <link rel="icon" type="image/png" href="/static/img/logo.png">
</head>
<body>
    <div class="container">
        <header>
            <h1><img src="/static/img/logo.png">AI测试用例生成模块·AiToCase</h1>
        </header>
        <div class="main-content">
            <!-- 左侧：输入区域 -->
            <div class="left-panel">...</div>
            <!-- 右侧：输出区域 -->
            <div class="right-panel">...</div>
        </div>
    </div>
</body>
</html>
```

### 5.2 样式文件

- **位置**: static/css/style.css
- **特点**: 简洁的响应式设计

### 5.3 第三方库

| 库名 | 用途 |
|------|------|
| marked.js | Markdown渲染 |
| mermaid.js | 流程图渲染 |
| turndown.js | HTML转Markdown |

---

## 6. 配置设计

### 6.1 环境变量 (.env)

```env
# DeepSeek
DEEPSEEK_API_KEY=your_deepseek_api_key

# 阿里云
ALIYUN_API_KEY=your_aliyun_api_key

# 字节跳动
DOUBAO_API_KEY=your_doubao_api_key

# Azure
AZURE_API_KEY=your_azure_api_key
AZURE_BASE_URL=https://xxx.openai.azure.com
AZURE_DEPLOYMENT=your_deployment

# Axure登录（可选）
AXURE_USERNAME=your_username
AXURE_PASSWORD=your_password

# 默认LLM提供商
LLM_PROVIDER=deepseek
```

### 6.2 路径配置

```python
# Windows
VECTOR_DB_PATH = r"D:\python\PythonProject\vector_db2"
CHROMA_DB_PATH = r"D:\python\PythonProject\chroma_db"
EMBEDDING_MODEL = r"D:\python\models\Ceceliachenen\paraphrase-multilingual-MiniLM-L12-v2"

# Linux
VECTOR_DB_PATH = r"//xdd/application/AITestCaseDemo/PythonProject/vector_db"
CHROMA_DB_PATH = r"//xdd/application/AITestCaseDemo/PythonProject/chroma_db"
```

---

## 7. 错误处理设计

### 7.1 异常类型

| 异常类型 | 代码 | 说明 |
|----------|------|------|
| ValidationError | 400 | 请求参数验证失败 |
| HTTPException | 400-599 | HTTP异常 |
| JSONDecodeError | 500 | JSON解析失败 |
| APIError | 500 | 外部API调用失败 |

### 7.2 错误响应格式

```json
{
    "detail": "错误描述信息"
}
```

---

## 8. 安全设计

### 8.1 API密钥管理

- 所有API密钥通过环境变量配置
- 配置文件(.env)不提交到版本控制
- 代码中不硬编码任何密钥

### 8.2 文件上传安全

- 限制允许的文件类型
- 检查文件大小
- 使用临时文件处理

### 8.3 请求验证

- 使用Pydantic进行请求体验证
- 参数类型检查
- 必填参数验证

---

## 9. 性能优化

### 9.1 异步处理

- 使用FastAPI异步框架
- 异步文件解析
- 异步LLM调用

### 9.2 并发控制

- Axure页面获取支持配置并发数
- 图片OCR支持并发处理

### 9.3 流式响应

- SSE实现实时流式输出
- 减少用户等待时间

---

## 10. 部署设计

### 10.1 依赖环境

- Python 3.11+
- Windows / Linux / macOS

### 10.2 启动方式

```bash
# 方式1：直接运行
python main.py

# 方式2：使用uvicorn
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# 访问
http://localhost:8000
```

### 10.3 目录结构

```
AiToCase_v2/
├── doc/                    # 文档目录
├── static/                # 静态资源
│   ├── css/
│   └── img/
├── templates/            # HTML模板
├── knowledge_bases/     # 知识库存储
├── venv/                # 虚拟环境
└── ...
```

---

**文档结束**
