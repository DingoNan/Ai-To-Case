# Dockerfile
FROM python:3.12

# 设置时区为中国时区
ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 安装系统依赖(OCR/图形库)
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    libgl1 \
    tzdata \
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
COPY utils_enhanced_kb.py .
COPY utils_sitemap_kb.py .
COPY md_to_xmind_utils.py .
COPY token_stats.py .
COPY prompts.json .
COPY static/ ./static/
COPY templates/ ./templates/
COPY image/ ./image/
COPY .env .

# 创建统计数据文件（运行时自动创建）
RUN touch token_stats.json

# 暴露FastAPI端口
EXPOSE 8001

# 启动命令
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]