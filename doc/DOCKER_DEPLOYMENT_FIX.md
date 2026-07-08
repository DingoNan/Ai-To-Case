# AiToCase_v2 Docker 部署问题修复指南

## 🔍 问题分析

### 错误信息
```
TypeError: unhashable type: 'dict'
```

### 根本原因
1. **Dockerfile 缺少新增文件**: `token_stats.py`, `utils_enhanced_kb.py`, `utils_sitemap_kb.py`
2. **卷挂载问题**: 使用 `-v /soft/AiToCase_v2:/app/` 会覆盖容器内的文件
3. **依赖版本兼容性**: Starlette/FastAPI 版本可能不兼容

## ✅ 解决方案

### 方案 1: 重新构建镜像(推荐)

#### 1. 更新 Dockerfile
已更新,包含所有必要文件:
```dockerfile
COPY utils_enhanced_kb.py .
COPY utils_sitemap_kb.py .
COPY token_stats.py .
```

#### 2. 重新构建镜像
```bash
cd /soft/AiToCase_v2
docker build -t aitocase:2.2 .
```

#### 3. 删除旧容器
```bash
docker stop AiToCase-Prodv2
docker rm AiToCase-Prodv2
```

#### 4. 启动新容器(不使用卷挂载测试)
```bash
docker run -idt \
  -p 8001:8001 \
  --name AiToCase-Prodv2 \
  --restart=always \
  aitocase:2.2
```

#### 5. 测试访问
```bash
curl http://localhost:8001/
```

### 方案 2: 修复卷挂载问题

如果必须使用卷挂载,请确保宿主机目录包含所有必要文件:

```bash
# 检查宿主机目录
ls -la /soft/AiToCase_v2/

# 应该包含以下文件:
# main.py
# llms.py
# utils.py
# utils_enhanced_kb.py     ← 必须有
# utils_sitemap_kb.py      ← 必须有
# token_stats.py           ← 必须有
# md_to_xmind_utils.py
# prompts.json
# token_stats.json         ← 自动创建
# static/
# templates/
# .env
```

#### 如果缺少文件,从源代码复制:
```bash
# 假设源代码在 /root/AiToCase_v2_source
cp /root/AiToCase_v2_source/utils_enhanced_kb.py /soft/AiToCase_v2/
cp /root/AiToCase_v2_source/utils_sitemap_kb.py /soft/AiCase_v2/
cp /root/AiToCase_v2_source/token_stats.py /soft/AiToCase_v2/
```

### 方案 3: 使用 Docker Compose(最佳实践)

创建 `docker-compose.yml`:
```yaml
version: '3.8'

services:
  aitocase:
    build: .
    image: aitocase:2.2
    container_name: AiToCase-Prodv2
    ports:
      - "8001:8001"
    volumes:
      - ./token_stats.json:/app/token_stats.json  # 只挂载数据文件
      - ./knowledge_bases:/app/knowledge_bases    # 挂载知识库
    environment:
      - TZ=Asia/Shanghai
    restart: always
```

启动:
```bash
docker-compose up -d --build
```

## 📦 完整的 Dockerfile

```dockerfile
# Dockerfile
FROM python:3.12

# 安装系统依赖(OCR/图形库)
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

# 设置工作目录
WORKDIR /app

# 复制依赖文件
COPY requirements-new.txt .

# 安装Python依赖(使用阿里云镜像)
RUN pip install --no-cache-dir -r requirements-new.txt -i https://mirrors.aliyun.com/pypi/simple

# 复制项目文件
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

# 创建空的数据文件(运行时会自动填充)
RUN touch token_stats.json

# 暴露FastAPI端口
EXPOSE 8001

# 启动命令
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
```

## 🔧 部署检查清单

### 构建前检查
- [ ] 所有 `.py` 文件都在目录中
- [ ] `templates/` 目录包含 `index.html` 和 `stats.html`
- [ ] `static/` 目录包含 CSS 和图片
- [ ] `.env` 文件配置正确
- [ ] `prompts.json` 存在

### 构建后检查
```bash
# 查看镜像
docker images | grep aitocase

# 检查容器状态
docker ps -a | grep AiToCase

# 查看日志
docker logs -f AiToCase-Prodv2
```

### 运行时检查
```bash
# 测试主页
curl http://localhost:8001/

# 测试统计页面
curl http://localhost:8001/stats

# 测试 API
curl http://localhost:8001/api/stats/summary

# 进入容器检查文件
docker exec -it AiToCase-Prodv2 ls -la /app/
```

## 🐛 常见问题

### Q1: 仍然提示 500 错误
**解决**: 检查容器内文件是否完整
```bash
docker exec -it AiToCase-Prodv2 ls -la /app/
docker exec -it AiToCase-Prodv2 cat /app/main.py | head -20
```

### Q2: token_stats.json 权限问题
**解决**: 修改文件权限
```bash
docker exec -it AiToCase-Prodv2 chmod 666 /app/token_stats.json
```

### Q3: 模板文件找不到
**解决**: 检查 templates 目录
```bash
docker exec -it AiToCase-Prodv2 ls -la /app/templates/
```

### Q4: 环境变量未加载
**解决**: 检查 .env 文件
```bash
docker exec -it AiToCase-Prodv2 cat /app/.env
```

## 📊 监控和维护

### 查看日志
```bash
docker logs -f AiToCase-Prodv2
```

### 查看统计文件
```bash
docker exec -it AiToCase-Prodv2 cat /app/token_stats.json | python -m json.tool
```

### 备份数据
```bash
docker cp AiToCase-Prodv2:/app/token_stats.json ./token_stats_backup.json
```

### 清理旧容器
```bash
docker stop AiToCase-Prodv2
docker rm AiToCase-Prodv2
docker rmi aitocase:2.1  # 删除旧镜像
```

## 🚀 快速部署脚本

创建 `deploy.sh`:
```bash
#!/bin/bash

echo "=== AiToCase_v2 Docker 部署 ==="

# 停止并删除旧容器
echo "1. 停止旧容器..."
docker stop AiToCase-Prodv2 2>/dev/null
docker rm AiToCase-Prodv2 2>/dev/null

# 构建新镜像
echo "2. 构建新镜像..."
docker build -t aitocase:2.2 .

# 启动新容器
echo "3. 启动新容器..."
docker run -idt \
  -p 8001:8001 \
  --name AiToCase-Prodv2 \
  --restart=always \
  aitocase:2.2

# 等待启动
echo "4. 等待服务启动..."
sleep 3

# 测试
echo "5. 测试服务..."
curl -s http://localhost:8001/ > /dev/null
if [ $? -eq 0 ]; then
    echo "✅ 部署成功!"
    echo "访问地址: http://$(hostname -I | awk '{print $1}'):8001"
    echo "统计页面: http://$(hostname -I | awk '{print $1}'):8001/stats"
else
    echo "❌ 部署失败,查看日志:"
    docker logs AiToCase-Prodv2
fi
```

使用:
```bash
chmod +x deploy.sh
./deploy.sh
```

## 📝 版本说明

- **v2.1**: 初始版本(缺少统计模块)
- **v2.2**: 添加 IP 和 Token 统计功能,修复 Dockerfile

## 🎯 下一步

部署成功后:
1. 访问 `http://your-server-ip:8001` 使用工具
2. 访问 `http://your-server-ip:8001/stats` 查看统计
3. 定期备份 `token_stats.json`
4. 监控 Docker 容器状态
