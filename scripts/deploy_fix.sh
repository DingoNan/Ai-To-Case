#!/bin/bash
# AiToCase_v2 Docker 部署修复脚本

set -e  # 遇到错误时退出

echo "======================================"
echo "  AiToCase_v2 Docker 部署修复"
echo "======================================"
echo ""

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查 Docker
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ 错误: Docker 未安装${NC}"
    exit 1
fi

echo -e "${GREEN}✓${NC} Docker 已安装"
echo ""

# 步骤 1: 停止并删除旧容器
echo -e "${YELLOW}步骤 1: 清理旧容器...${NC}"
docker stop AiToCase-Prodv2 2>/dev/null || true
docker rm AiToCase-Prodv2 2>/dev/null || true
echo -e "${GREEN}✓${NC} 旧容器已清理"
echo ""

# 步骤 2: 检查必要文件
echo -e "${YELLOW}步骤 2: 检查必要文件...${NC}"
REQUIRED_FILES=(
    "main.py"
    "llms.py"
    "utils.py"
    "utils_enhanced_kb.py"
    "utils_sitemap_kb.py"
    "token_stats.py"
    "md_to_xmind_utils.py"
    "prompts.json"
    ".env"
)

MISSING_FILES=()
for file in "${REQUIRED_FILES[@]}"; do
    if [ ! -f "$file" ]; then
        MISSING_FILES+=("$file")
        echo -e "${RED}✗${NC} 缺少: $file"
    else
        echo -e "${GREEN}✓${NC} 存在: $file"
    fi
done

# 检查目录
if [ ! -d "templates" ]; then
    echo -e "${RED}✗${NC} 缺少目录: templates/"
    MISSING_FILES+=("templates/")
else
    echo -e "${GREEN}✓${NC} 存在: templates/"
fi

if [ ! -d "static" ]; then
    echo -e "${RED}✗${NC} 缺少目录: static/"
    MISSING_FILES+=("static/")
else
    echo -e "${GREEN}✓${NC} 存在: static/"
fi

if [ ${#MISSING_FILES[@]} -ne 0 ]; then
    echo ""
    echo -e "${RED}❌ 错误: 缺少以下文件/目录:${NC}"
    for file in "${MISSING_FILES[@]}"; do
        echo "  - $file"
    done
    echo ""
    echo "请确保从源代码目录复制所有必要文件"
    exit 1
fi

echo ""
echo -e "${GREEN}✓${NC} 所有必要文件已就绪"
echo ""

# 步骤 3: 构建 Docker 镜像
echo -e "${YELLOW}步骤 3: 构建 Docker 镜像...${NC}"
docker build -t aitocase:2.2 .

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓${NC} 镜像构建成功"
else
    echo -e "${RED}❌ 镜像构建失败${NC}"
    exit 1
fi
echo ""

# 步骤 4: 启动容器
echo -e "${YELLOW}步骤 4: 启动容器...${NC}"
docker run -idt \
  -p 8001:8001 \
  --name AiToCase-Prodv2 \
  -v $(pwd)/token_stats.json:/app/token_stats.json \
  -v $(pwd)/knowledge_bases:/app/knowledge_bases \
  -v /etc/localtime:/etc/localtime:ro \
  -v /etc/timezone:/etc/timezone:ro \
  -e TZ=Asia/Shanghai \
  --restart=always \
  aitocase:2.3

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓${NC} 容器启动成功"
else
    echo -e "${RED}❌ 容器启动失败${NC}"
    exit 1
fi
echo ""

# 步骤 5: 等待服务启动
echo -e "${YELLOW}步骤 5: 等待服务启动...${NC}"
sleep 5

# 步骤 6: 测试服务
echo -e "${YELLOW}步骤 6: 测试服务...${NC}"

# 测试主页
if curl -s http://localhost:8001/ > /dev/null 2>&1; then
    echo -e "${GREEN}✓${NC} 主页访问成功"
else
    echo -e "${RED}✗${NC} 主页访问失败"
    echo "查看日志:"
    docker logs --tail 50 AiToCase-Prodv2
    exit 1
fi

# 测试统计页面
if curl -s http://localhost:8001/stats > /dev/null 2>&1; then
    echo -e "${GREEN}✓${NC} 统计页面访问成功"
else
    echo -e "${YELLOW}⚠${NC} 统计页面访问失败(可能正常,如果还没有统计数据)"
fi

# 测试 API
if curl -s http://localhost:8001/api/stats/summary > /dev/null 2>&1; then
    echo -e "${GREEN}✓${NC} API 访问成功"
else
    echo -e "${RED}✗${NC} API 访问失败"
fi

echo ""
echo "======================================"
echo -e "${GREEN}✅ 部署完成!${NC}"
echo "======================================"
echo ""

# 获取服务器 IP
SERVER_IP=$(hostname -I | awk '{print $1}')

echo "📍 访问地址:"
echo "   主页:     http://${SERVER_IP}:8001"
echo "   统计:     http://${SERVER_IP}:8001/stats"
echo ""
echo "📋 常用命令:"
echo "   查看日志:   docker logs -f AiToCase-Prodv2"
echo "   停止服务:   docker stop AiToCase-Prodv2"
echo "   重启服务:   docker restart AiToCase-Prodv2"
echo "   进入容器:   docker exec -it AiToCase-Prodv2 bash"
echo ""
echo "💡 提示:"
echo "   - 统计数据保存在: $(pwd)/token_stats.json"
echo "   - 知识库保存在:   $(pwd)/knowledge_bases/"
echo "   - 定期备份以上数据"
echo ""
