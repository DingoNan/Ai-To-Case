# 🧪 AI 测试用例自动生成平台

> **从需求到测试用例，一键生成。** 上传文档/截图/Axure 原型，AI 自动分析需求并生成结构化测试用例，支持 DeepSeek / 阿里云 Qwen 双引擎。

<p align="center">
  <img alt="Python" src="https://img.shields.io/badge/Python-3.11+-blue?logo=python" />
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-0.115+-green?logo=fastapi" />
  <img alt="LLM" src="https://img.shields.io/badge/LLM-DeepSeek%20%7C%20Qwen-orange" />
</p>

---

## ✨ 三大亮点

| 亮点 | 说明 |
|------|------|
| **📄 多源需求输入** | PDF/Word/Markdown/TXT 文档 + 截图 OCR 识别 + 手动输入，覆盖所有需求来源 |
| **🧠 双 AI 引擎** | DeepSeek（文本生成）+ 阿里云 Qwen-VL（图像识别），按需切换，灵活可控 |
| **📊 全链路可观测** | 自动记录每次调用的模型、Token 消耗、IP 来源，可视化面板一目了然 |

## 🚀 快速体验

### 1. 环境准备

```bash
# 创建环境
conda create --name AITOCASE python=3.12
conda activate AITOCASE

# 安装依赖
pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/

# 配置密钥（复制 .env.example 为 .env 并填入 API Key）
```

### 2. 启动服务

```bash
python main.py
```

打开浏览器访问 **http://localhost:8001** 即可使用。

---

## 🎯 核心功能

### 📥 需求输入（多种方式）
| 方式 | 说明 | 支持的模型 |
|------|------|-----------|
| **上传文档** | PDF / Word / Markdown / TXT，自动解析并向量化存储 | — |
| **截图 OCR** | 上传图片，AI 自动识别图中文字和表格 | 阿里云 Qwen-VL-Plus |
| **手动输入** | 直接粘贴需求文本，支持粘贴图片自动 OCR | 阿里云 Qwen-VL-Plus |
| **Axure 原型** | ~~上传 Axure ZIP/HTML 自动提取需求~~（暂隐藏） | — |

### 🤖 测试用例生成
- **流式生成（SSE）** — 实时显示生成过程，支持断点恢复
- **多格式导出** — CSV / Markdown / XMind，适配不同管理系统
- **语义检索增强** — 自动检索向量库中最相关的需求片段作为上下文

### 📊 Token 使用统计
- **多维度统计面板** — 按**模型**（deepseek-chat / qwen-plus / qwen-vl-plus）、**IP**、**提供商**、**端点** 多维度聚合
- **精细计量** — 区分输入 Token / 输出 Token / 总 Token，支持时间范围筛选
- **可视化** — 访问 `/stats` 查看实时统计面板

### 🧩 向量化检索
| 引擎 | Embedding 模型 | 用途 |
|------|---------------|------|
| **LlamaIndex** | HuggingFace 本地模型 | 通用文档向量化 |
| **Chroma** | 通义千问 text-embedding-v3 | 持久化向量存储 + 语义检索 |

---

## 📁 项目结构

```
AiToCase_v2/
├── main.py                  # FastAPI 主程序（22+ API 端点）
├── llms.py                  # LLM 调用层（DeepSeek + 阿里云，支持流式/非流式）
├── token_stats.py           # Token & IP 统计模块（内存 + JSON 持久化）
│
├── utils/                   # 工具函数包
│   ├── ocr.py               # 图片 OCR（并发控制 / 超时 / 重试熔断）
│   ├── document.py          # 文档解析（PDF / Word / Markdown）
│   ├── chroma.py            # Chroma 向量库 + DashScope Embedding
│   ├── vector.py            # LlamaIndex 向量库
│   ├── axure.py             # Axure 原型解析（ZIP / HTML / 在线）
│   ├── knowledge_base.py    # 知识库管理 + 智能召回
│   ├── streaming.py         # 流式测试用例生成
│   ├── llm_helper.py        # AI 需求精炼
│   ├── flowchart.py         # 流程图检测与 Mermaid 转换
│   ├── text.py              # JSON 修复 & 提示词构建
│   ├── config.py            # 路径常量 & OCR 配置
│   └── helpers.py           # 通用工具函数
│
├── prompts.json             # 提示词配置
├── requirements.txt         # Python 依赖
├── .env.example             # 环境变量模板
├── Dockerfile               # Docker 部署
├── md_to_xmind_utils.py     # Markdown → XMind 转换
│
├── templates/               # Web 页面
│   ├── index.html           # 主界面
│   └── stats.html           # 统计面板
├── static/                  # 静态资源
│   └── css/style.css
├── tests/                   # 单元测试
│   └── test_token_stats.py
└── scripts/                 # 部署脚本
    └── deploy_fix.sh
```

---

## 🔌 API 速览

| 分类 | 接口 | 方法 | 说明 |
|------|------|------|------|
| **文档上传** | `/api/upload/document` | POST | 上传文档并向量化 |
| | `/api/upload/images` | POST | 上传图片 OCR 识别 |
| | `/api/upload/axure` | POST | Axure 原型解析 |
| | `/api/chroma/upload` | POST | Chroma 向量化 |
| **测试用例** | `/api/testcase/generate/stream` | POST | 流式生成（SSE） |
| | `/api/testcase/generate` | POST | 非流式生成 |
| | `/api/refine` | POST | AI 优化需求文档 |
| **向量检索** | `/api/chroma/query` | POST | 语义检索 |
| | `/api/vector/query` | POST | LlamaIndex 检索 |
| **导出** | `/api/export/csv` | POST | 导出 CSV |
| | `/api/export/markdown` | POST | 导出 Markdown |
| | `/api/export/xmind` | POST | 导出 XMind |
| **统计** | `/api/stats/summary` | GET | 统计摘要 |
| | `/api/stats/recent` | GET | 最近调用记录 |
| | `/api/stats/ip-list` | GET | IP 维度统计 |
| | `/api/stats/clear` | POST | 清空统计数据 |
| | `/stats` | GET | **统计面板（可视化）** |

> 全部 API 可通过 `http://localhost:8001/docs`（Swagger UI）交互式调试。

---

## 📊 统计面板

访问 **http://localhost:8001/stats** 查看实时数据：

- **总体概览** — 总请求数、Token 消耗、模型数、IP 数
- **模型用量分布** — 每个模型的调用次数、输入/输出 Token 及占比
- **提供商分布** — DeepSeek vs 阿里云调用量对比
- **IP 统计** — 各 IP 的请求频率与 Token 消耗排行
- **最近记录** — 最近 100 条详细调用日志

数据持久化在 `token_stats.json`，支持 Docker 容器挂载（避免重启丢失）。

---

## 🐳 Docker 部署

```bash
# 构建
docker build -t aitocase:latest .

# 运行（开发）
docker run -d -p 8001:8001 --name aitocase-dev aitocase:latest

# 运行（生产，持久化统计数据）
docker run -d \
  -p 8001:8001 \
  --name aitocase-prod \
  -v $(pwd)/token_stats.json:/app/token_stats.json \
  -v $(pwd)/knowledge_bases:/app/knowledge_bases \
  -e TZ=Asia/Shanghai \
  --restart=always \
  aitocase:latest

# 验证
curl http://localhost:8001/docs
```

---

## ⚙️ 环境变量

| 变量 | 必填 | 说明 | 默认值 |
|------|------|------|--------|
| `DEEPSEEK_API_KEY` | ✅ | DeepSeek API 密钥 | — |
| `ALIYUN_API_KEY` | ✅ | 阿里云 DashScope API 密钥 | — |
| `AI_API_TIMEOUT` | ❌ | API 超时（秒） | 120 |
| `OCR_MAX_CONCURRENT` | ❌ | OCR 最大并发数 | 5 |
| `OCR_TIMEOUT` | ❌ | 单次 OCR 超时（秒） | 60 |
| `OCR_MAX_RETRIES` | ❌ | OCR 失败重试次数 | 2 |
| `VECTOR_DB_PATH` | ❌ | LlamaIndex 向量库路径 | ./DB |
| `CHROMA_DB_PATH` | ❌ | Chroma 向量库路径 | ./chroma_db |

---

## 🧱 技术栈

| 层 | 技术 |
|----|------|
| **Web 框架** | FastAPI + Uvicorn（高性能异步） |
| **LLM** | DeepSeek Chat / 阿里云 Qwen-Plus / Qwen-VL-Plus |
| **向量数据库** | LlamaIndex + Chroma |
| **Embedding** | HuggingFace / 通义千问 text-embedding-v3 |
| **文档解析** | PyMuPDF（PDF）、python-docx（Word）、BeautifulSoup（HTML/MD） |
| **前端** | 原生 HTML/CSS/JS，aiofiles 直接渲染（无 Jinja2 依赖） |
| **数据** | Pandas + NumPy |

---

## 📝 注意事项

1. **至少配置一个 API 密钥** — DeepSeek 或阿里云，否则无法使用 AI 功能
2. **首次运行自动下载 Embedding 模型** — LlamaIndex 需要本地模型，视网速可能需要数分钟
3. **大文件处理** — PDF/Word 解析需要时间，可通过 `AI_API_TIMEOUT` 调整
4. **OCR 熔断保护** — 批量图片默认并发 5 张，超时 60s 自动重试 2 次，防止 API 过载
