# AI 测试用例生成系统

基于 **FastAPI** + **DeepSeek** / **阿里云通义千问** 的智能测试用例自动生成平台，支持多种需求输入方式和多格式导出。

## 功能特性

### 核心功能
- **多格式文档解析** - 支持 PDF、Word（.docx）、Markdown、TXT 文件上传和解析
- **Axure 原型解析** - 支持 Axure 导出的 ZIP 包和 HTML 文件解析，自动提取需求信息
- **图片 OCR 识别** - 支持多张图片的并发 OCR 识别（阿里云 Qwen-VL，含熔断机制）
- **AI 测试用例生成** - 基于需求描述自动生成结构化的测试用例 JSON
- **流式实时生成** - 支持 SSE 流式传输，实时显示生成过程（含错误恢复）
- **多格式导出** - 支持导出为 CSV、Markdown、XMind 格式
- **使用统计** - 自动记录每个 IP 的访问情况和 Token 消耗，支持可视化查看

### 向量化检索
- **LlamaIndex 向量库** - 基于 HuggingFace Embedding 的本地向量化存储
- **Chroma 向量数据库** - 基于通义千问 Embedding 的持久化向量存储
- **语义检索** - 支持需求内容的语义相似度检索

### 支持的 LLM 提供商
| 提供商 | 模型 | 说明 |
|--------|------|------|
| **DeepSeek** | deepseek-chat | 默认文本生成模型 |
| **阿里云 DashScope** | qwen-plus / qwen-vl-plus | 文本生成 + 视觉识别 |

## 项目结构

```
AiToCase_v2/
├── main.py                 # FastAPI 主程序入口
├── llms.py                 # LLM API 调用层（DeepSeek + 阿里云）
├── utils.py                # 工具函数（文档解析、向量库、OCR）
├── utils_enhanced_kb.py    # 增强型知识库工具
├── utils_sitemap_kb.py     # 网站地图知识库工具
├── md_to_xmind_utils.py    # Markdown 转 XMind 工具
├── token_stats.py          # Token 和 IP 统计模块
├── prompts.json            # 提示词配置文件
├── requirements.txt        # Python 依赖包
├── .env                    # 环境变量配置
├── Dockerfile              # Docker 部署配置
├── scripts/                # 部署脚本
│   └── deploy_fix.sh
├── tests/                  # 测试用例
│   └── test_token_stats.py
├── static/                 # 静态资源
│   └── css/style.css
└── templates/              # HTML 模板
    ├── index.html
    └── stats.html
```

## 快速开始

### 环境要求
- Python 3.11+
- Windows / Linux / macOS

### 安装步骤

```bash
# 1. 安装 Miniconda（推荐）
https://www.anaconda.com/download/success

# 2. 创建虚拟环境
conda create --name AITest python=3.12

# 3. 激活环境并安装依赖
conda activate AITest
pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/

# 4. 配置环境变量
# 复制 .env 中的示例值，填入自己的 API 密钥
```

### 环境变量配置

在项目根目录的 `.env` 文件中配置 API 密钥：

```env
# DeepSeek 配置
DEEPSEEK_API_KEY=your_deepseek_api_key
申请地址：https://platform.deepseek.com/api_keys

# 阿里云 DashScope 配置
ALIYUN_API_KEY=your_aliyun_api_key
申请地址：https://bailian.console.aliyun.com/?#/home

# 超时设置（秒）
AI_API_TIMEOUT=120

# OCR 并发控制（可选）
OCR_MAX_CONCURRENT=5
OCR_TIMEOUT=60
OCR_MAX_RETRIES=2
```

### 启动服务

```bash
# 方式1：直接运行
python main.py

# 方式2：使用 uvicorn（支持热重载）
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

访问 http://localhost:8000 即可使用 Web 界面。

## API 接口

### 文档上传与解析

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/upload/document` | POST | 上传文档并向量化（LlamaIndex） |
| `/api/upload/axure` | POST | 上传 Axure 原型包解析 |
| `/api/upload/images` | POST | 上传图片进行 OCR 识别 |
| `/api/chroma/upload` | POST | 上传文档并向量化（Chroma） |

### 向量检索

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/vector/query` | POST | LlamaIndex 向量检索 |
| `/api/chroma/query` | POST | Chroma 向量检索 |
| `/api/chroma/collections` | GET | 获取所有 Chroma 集合 |
| `/api/chroma/collection/{name}` | DELETE | 删除指定集合 |

### 测试用例生成

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/testcase/generate` | POST | 生成测试用例（非流式） |
| `/api/testcase/generate/stream` | POST | 流式生成测试用例（SSE，带错误恢复） |
| `/api/refine` | POST | AI 优化需求文档 |

### 导出功能

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/export/csv` | POST | 导出 CSV 格式 |
| `/api/export/markdown` | POST | 导出 Markdown 格式 |
| `/api/export/xmind` | POST | 导出 XMind 格式 |
| `/api/export/xmind-text` | POST | 获取 XMind 粘贴文本 |

### 使用统计

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/stats/summary` | GET | 获取总体统计摘要 |
| `/api/stats/by-ip` | GET | 按 IP 分组统计 |
| `/api/stats/by-date` | GET | 按日期统计 |
| `/api/stats/records` | GET | 获取详细记录列表 |
| `/api/stats/clear` | POST | 清空统计数据 |
| `/stats` | GET | 统计可视化页面 |

## 测试用例格式

生成的测试用例采用以下 JSON 格式：

```json
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

## 使用流程

1. **上传需求文档** - 支持 PDF、Word、Markdown、TXT 或 Axure 原型
2. **（可选）OCR 识别** - 上传截图自动识别文字（阿里云 Qwen-VL）
3. **向量化存储** - 将需求文档存入向量数据库
4. **检索相关内容** - 通过语义检索获取相关需求
5. **生成测试用例** - AI 自动生成结构化测试用例
6. **导出** - 选择 CSV、Markdown 或 XMind 格式导出
7. **查看统计** - 访问 `/stats` 页面查看 IP 和 Token 使用情况

## 技术栈

- **Web 框架**: FastAPI + Uvicorn
- **模板**: aiofiles 直接读取（轻量，无 Jinja2 依赖）
- **向量数据库**: LlamaIndex + Chroma
- **Embedding**: HuggingFace / 通义千问 text-embedding-v3
- **LLM**: DeepSeek / 阿里云通义千问（Qwen）
- **视觉模型**: 阿里云 Qwen-VL-Plus（含熔断机制）
- **文档解析**: PyMuPDF + python-docx + BeautifulSoup
- **数据处理**: Pandas + NumPy

## 使用统计功能

### 功能说明
系统会自动记录每次 API 调用的以下信息：
- **客户端 IP** - 自动获取真实 IP（支持 X-Forwarded-For 代理）
- **Token 消耗** - prompt_tokens、completion_tokens、total_tokens
- **调用信息** - 端点、模型、提供商、时间戳、状态

### 数据存储
统计数据存储在 `token_stats.json` 文件中，格式如下：
```json
{
  "records": [
    {
      "timestamp": "2026-05-07T10:30:00",
      "ip": "192.168.1.100",
      "endpoint": "/api/testcase/generate/stream",
      "provider": "deepseek",
      "model": "deepseek-chat",
      "prompt_tokens": 1500,
      "completion_tokens": 2300,
      "total_tokens": 3800,
      "status": "success"
    }
  ]
}
```

### 可视化查看
访问 `http://localhost:8000/stats` 即可查看：
- **总体概览** - 总调用次数、总 Token 消耗、独立 IP 数
- **IP 统计** - 每个 IP 的调用次数和 Token 消耗排行
- **详细记录** - 最近 100 条调用记录，支持时间范围筛选

## Docker 部署

### 构建镜像

```bash
docker build -t aitocase:2.3 .
```

### 运行容器

```bash
# 基础运行（开发测试）
docker run -d -p 8000:8000 --name aitocase-dev aitocase:2.3

# 生产环境运行
docker run -d \
  -p 8001:8001 \
  --name AiToCase-Prod \
  -v $(pwd)/token_stats.json:/app/token_stats.json \
  -v $(pwd)/knowledge_bases:/app/knowledge_bases \
  -v /etc/localtime:/etc/localtime:ro \
  -e TZ=Asia/Shanghai \
  --restart=always \
  aitocase:2.3
```

### 验证部署

```bash
# 检查容器状态
docker ps -a | grep aitocase

# 查看实时日志
docker logs -f AiToCase-Prod

# 访问API文档
curl http://localhost:8000/docs
```

## 注意事项

1. **API 密钥** - 至少配置 DeepSeek 或阿里云其中一家 API 密钥
2. **向量模型** - LlamaIndex 需要本地 Embedding 模型，首次运行会自动下载
3. **路径配置** - 向量数据库路径通过环境变量 `VECTOR_DB_PATH` / `CHROMA_DB_PATH` 配置（默认相对路径）
4. **大文件处理** - PDF/Word 文件解析可能需要一些时间，可通过 `AI_API_TIMEOUT` 调整超时
5. **OCR 熔断** - 批量 OCR 任务默认并发 5 张，可通过 `OCR_MAX_CONCURRENT` 调整
# AI 测试用例生成系统

基于 **FastAPI** 和多种大语言模型的智能测试用例自动生成平台，支持多种需求输入方式和多格式导出。

## 功能特性

### 核心功能
- **多格式文档解析** - 支持 PDF、Word（.docx）、Markdown、TXT 文件上传和解析
- **Axure 原型解析** - 支持 Axure 导出的 ZIP 包和 HTML 文件解析，自动提取需求信息
- **图片 OCR 识别** - 支持多张图片的并发 OCR 识别，可识别表格和文字
- **AI 测试用例生成** - 基于需求描述自动生成结构化的测试用例 JSON
- **流式实时生成** - 支持 SSE 流式传输，实时显示生成过程
- **多格式导出** - 支持导出为 CSV、Markdown、XMind 格式
- **使用统计** - 自动记录每个 IP 的访问情况和 Token 消耗，支持可视化查看

### 向量化检索
- **LlamaIndex 向量库** - 基于 HuggingFace Embedding 的本地向量化存储
- **Chroma 向量数据库** - 基于通义千问 Embedding 的持久化向量存储
- **语义检索** - 支持需求内容的语义相似度检索

### 多 LLM 提供商支持
| 提供商 | 模型 | 说明 |
|--------|------|------|
| **DeepSeek** | deepseek-chat | 默认提供商 |
| **阿里云 DashScope** | qwen-plus | 通义千问 |
| **字节跳动豆包** | doubao-1-5-pro | 视觉 + 文本 |

## 项目结构

```
fastapicase/
├── main.py                 # FastAPI 主程序入口
├── llms.py                 # LLM API 调用模块（多提供商支持）
├── utils.py                # 工具函数（文档解析、向量库、OCR）
├── utils_enhanced_kb.py    # 增强型知识库工具
├── utils_sitemap_kb.py     # 网站地图知识库工具
├── md_to_xmind_utils.py    # Markdown 转 XMind 工具
├── token_stats.py          # Token 和 IP 统计模块
├── prompts.json            # 提示词配置文件
├── requirements-new.txt    # Python 依赖包（精简版）
├── requirements.txt        # Python 依赖包（完整版）
├── .env                    # 环境变量配置
├── blank.xmind             # XMind 模板文件
├── token_stats.json        # Token 统计数据（自动生成）
├── static/                 # 静态资源
│   └── css/style.css
└── templates/              # HTML 模板
    ├── index.html
    └── stats.html          # 统计可视化页面
```

## 快速开始

### 环境要求
- Python 3.11+
- Windows / Linux / macOS

### 安装步骤

```bash
# 1. 安装虚拟环境管理工具 下载Miniconda即可
https://www.anaconda.com/download/success

# 2. 创建虚拟环境（推荐）
conda crate --name AITest python=3.12    -- AITest 可以换成自己的名字

# 3. 安装依赖
pip install -r requirements-new.txt -i https://mirrors.aliyun.com/pypi/simple/

# 4. 配置环境变量
# 复制 .env.example 为 .env 并填入 API 密钥
```

### 环境变量配置

在项目根目录创建 `.env` 文件更新为自己的api key：

```env
# DeepSeek 配置
DEEPSEEK_API_KEY=your_deepseek_api_key
申请地址：https://platform.deepseek.com/api_keys

# 阿里云 DashScope 配置
ALIYUN_API_KEY=your_aliyun_api_key
申请地址：https://bailian.console.aliyun.com/?#/home

# 字节跳动豆包配置
DOUBAO_API_KEY=your_doubao_api_key
申请地址：https://console.volcengine.com/ark/region:ark+cn-beijing/apiKey??apikey=%7B%7D
```

### 启动服务

```bash
# 方式1：直接运行
python main.py

# 方式2：使用 uvicorn（支持热重载）
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

访问 http://localhost:8000 即可使用 Web 界面。

## API 接口

### 文档上传与解析

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/upload/document` | POST | 上传文档并向量化（LlamaIndex） |
| `/api/upload/axure` | POST | 上传 Axure 原型包解析 |
| `/api/upload/images` | POST | 上传图片进行 OCR 识别 |
| `/api/chroma/upload` | POST | 上传文档并向量化（Chroma） |

### 向量检索

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/vector/query` | POST | LlamaIndex 向量检索 |
| `/api/chroma/query` | POST | Chroma 向量检索 |
| `/api/chroma/collections` | GET | 获取所有 Chroma 集合 |
| `/api/chroma/collection/{name}` | DELETE | 删除指定集合 |

### 测试用例生成

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/testcase/generate` | POST | 生成测试用例（非流式） |
| `/api/testcase/generate/stream` | POST | 流式生成测试用例（SSE） |
| `/api/refine` | POST | AI 优化需求文档 |

### 导出功能

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/export/csv` | POST | 导出 CSV 格式 |
| `/api/export/markdown` | POST | 导出 Markdown 格式 |
| `/api/export/xmind` | POST | 导出 XMind 格式 |
| `/api/export/xmind-text` | POST | 获取 XMind 粘贴文本 |

### 使用统计

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/stats/summary` | GET | 获取总体统计摘要 |
| `/api/stats/by-ip` | GET | 按 IP 分组统计 |
| `/api/stats/by-date` | GET | 按日期统计 |
| `/api/stats/records` | GET | 获取详细记录列表 |
| `/api/stats/clear` | POST | 清空统计数据 |
| `/stats` | GET | 统计可视化页面 |

## 测试用例格式

生成的测试用例采用以下 JSON 格式：

```json
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

## 使用流程

1. **上传需求文档** - 支持 PDF、Word、Markdown、TXT 或 Axure 原型
2. **（可选）OCR 识别** - 上传截图自动识别文字
3. **向量化存储** - 将需求文档存入向量数据库
4. **检索相关内容** - 通过语义检索获取相关需求
5. **生成测试用例** - AI 自动生成结构化测试用例
6. **导出** - 选择 CSV、Markdown 或 XMind 格式导出
7. **查看统计** - 访问 `/stats` 页面查看 IP 和 Token 使用情况

## 技术栈

- **Web 框架**: FastAPI + Uvicorn
- **模板引擎**: Jinja2
- **向量数据库**: LlamaIndex + Chroma
- **Embedding**: HuggingFace / 通义千问
- **LLM**: DeepSeek / 通义千问 / Azure OpenAI / 豆包
- **文档解析**: PyMuPDF + python-docx + BeautifulSoup
- **数据处理**: Pandas + NumPy

## 使用统计功能

### 功能说明
系统会自动记录每次 API 调用的以下信息：
- **客户端 IP** - 自动获取真实 IP（支持 X-Forwarded-For 代理）
- **Token 消耗** - prompt_tokens、completion_tokens、total_tokens
- **调用信息** - 端点、模型、提供商、时间戳、状态

### 数据存储
统计数据存储在 `token_stats.json` 文件中，格式如下：
```json
{
  "records": [
    {
      "timestamp": "2026-05-07T10:30:00",
      "ip": "192.168.1.100",
      "endpoint": "/api/testcase/generate/stream",
      "provider": "deepseek",
      "model": "deepseek-chat",
      "prompt_tokens": 1500,
      "completion_tokens": 2300,
      "total_tokens": 3800,
      "status": "success"
    }
  ]
}
```

### 可视化查看
访问 `http://localhost:8001/stats` 即可查看：
- **总体概览** - 总调用次数、总 Token 消耗、独立 IP 数
- **IP 统计** - 每个 IP 的调用次数和 Token 消耗排行
- **详细记录** - 最近 100 条调用记录，支持时间范围筛选

### Docker 部署注意事项
在 Docker 环境中运行时，需要挂载统计数据文件以持久化：
```bash
docker run -d \
  -p 8001:8001 \
  --name AiToCase-Prodv2 \
  -v $(pwd)/token_stats.json:/app/token_stats.json \
  -v $(pwd)/knowledge_bases:/app/knowledge_bases \
  -v /etc/localtime:/etc/localtime:ro \
  -v /etc/timezone:/etc/timezone:ro \
  -e TZ=Asia/Shanghai \
  --restart=always \
  aitocase:2.3
```

## 注意事项

1. **API 密钥** - 至少配置一个 LLM 提供商的 API 密钥
2. **向量模型** - LlamaIndex 需要本地 Embedding 模型，首次运行会自动下载
3. **Chroma 存储** - 向量数据默认存储在本地路径，可在 `utils.py` 中修改
4. **大文件处理** - PDF/Word 文件解析可能需要一些时间

```
# Dockerfile
FROM python:3.12

# 安装系统依赖（OCR/图形库）
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

# 设置工作目录
WORKDIR /app

# 复制依赖文件
COPY requirements-new.txt .

# 安装Python依赖（使用阿里云镜像）
RUN pip install --no-cache-dir -r requirements-new.txt -i https://mirrors.aliyun.com/pypi/simple

# 复制项目文件（排除不需要的文件）
COPY main.py .
COPY llms.py .
COPY utils.py .
COPY md_to_xmind_utils.py .
COPY prompts.json .
COPY static/ ./static/
COPY templates/ ./templates/
COPY image/ ./image/
COPY .env .

# 暴露FastAPI端口
EXPOSE 8000

# 启动命令
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

4. **构建 Docker 镜像**
```
# 在项目根目录执行（注意最后的点号）
docker build -t aitocase:2.0 .
```
5. **运行 Docker 容器**
```
# 基础运行（开发测试）
docker run -d -p 8000:8000 --name aitocase-dev aitocase:2.0

# 生产环境运行（推荐配置）
docker run -d \
  -p 8001:8001 \
  --name AiToCase-Prodv2 \
  -e OPENAI_API_KEY=your_api_key \
  -e QIANFAN_AK=your_qianfan_ak \
  -e QIANFAN_SK=your_qianfan_sk \
  -v /soft/AiToCase_v2:/app/ \
  --restart=always \
  aitocase:2.0

```
7. **验证部署**
```
# 检查容器状态
docker ps -a | grep aitocase

# 查看实时日志
docker logs -f aitocase-prod

# 访问API文档
curl http://localhost:8000/docs

```