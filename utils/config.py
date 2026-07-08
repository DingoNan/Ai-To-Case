"""全局配置常量模块

包含路径配置、OCR 并发控制等所有从环境变量读取的配置项。
"""
import os
import asyncio

# ==================== 路径配置（通过环境变量覆盖，默认使用相对路径）====================
VECTOR_DB_PATH = os.getenv("VECTOR_DB_PATH", "./DB/vector_db")
CHROMA_DB_PATH = os.getenv("CHROMA_DB_PATH", "./DB/chroma_db")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "./models/Ceceliachenen/paraphrase-multilingual-MiniLM-L12-v2")

# 通义千问Embedding配置
DASHSCOPE_EMBEDDING_MODEL = "text-embedding-v3"  # 通义文本嵌入模型111

# OCR 并发控制（熔断机制）
_OCR_SEMAPHORE = None


def _get_ocr_semaphore():
    """获取 OCR 并发信号量（惰性初始化，避免模块导入时创建）"""
    global _OCR_SEMAPHORE
    if _OCR_SEMAPHORE is None:
        _OCR_SEMAPHORE = asyncio.Semaphore(int(os.getenv("OCR_MAX_CONCURRENT", "5")))
    return _OCR_SEMAPHORE


OCR_TIMEOUT = int(os.getenv("OCR_TIMEOUT", "60"))  # 单张图片超时（秒）
OCR_MAX_RETRIES = int(os.getenv("OCR_MAX_RETRIES", "2"))  # 失败重试次数


# 知识库存储路径
def _get_knowledge_base_path():
    """获取知识库存储路径"""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "knowledge_bases")


KNOWLEDGE_BASE_PATH = os.getenv("KNOWLEDGE_BASE_PATH", _get_knowledge_base_path())

# 确保知识库目录存在
os.makedirs(KNOWLEDGE_BASE_PATH, exist_ok=True)
