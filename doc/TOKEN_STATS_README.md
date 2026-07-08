# IP 和 Token 统计功能使用说明

## 功能概述

本功能用于统计 AiToCase_v2 系统的使用情况,包括:
- 记录每个访问 IP 的使用情况
- 统计每次 API 调用的 Token 消耗
- 提供可视化统计面板

## 新增文件

1. **token_stats.py** - Token 统计核心模块
2. **templates/stats.html** - 统计可视化页面

## 修改文件

1. **main.py** - 添加统计中间件和 API 路由
2. **llms.py** - 在 API 调用中提取 Token 信息

## 统计 API 接口

### 1. 获取总体统计信息
```
GET /api/stats/summary?days=30
```
**参数:**
- `days`: 统计最近多少天的数据(默认 30 天)

**返回示例:**
```json
{
  "success": true,
  "summary": {
    "total_requests": 150,
    "success_requests": 145,
    "error_requests": 5,
    "total_tokens": 125000,
    "prompt_tokens": 75000,
    "completion_tokens": 50000,
    "unique_ips": 12,
    "providers": {
      "azure": 100,
      "deepseek": 50
    },
    "endpoints": {
      "/api/testcase/generate/stream": 120,
      "/api/chroma/query": 30
    }
  },
  "ip_details": {...}
}
```

### 2. 获取 IP 列表
```
GET /api/stats/ip-list?days=30
```
**参数:**
- `days`: 统计最近多少天的数据

**返回示例:**
```json
{
  "success": true,
  "ip_list": [
    {
      "ip": "192.168.1.100",
      "total_requests": 50,
      "success_requests": 48,
      "error_requests": 2,
      "total_tokens": 45000,
      "prompt_tokens": 27000,
      "completion_tokens": 18000,
      "providers": {"azure": 40, "deepseek": 10},
      "endpoints": {"/api/testcase/generate/stream": 45},
      "first_seen": "2024-01-01T10:00:00",
      "last_seen": "2024-01-30T15:30:00"
    }
  ],
  "total_ips": 1
}
```

### 3. 获取指定 IP 的详细统计
```
GET /api/stats/ip/{ip}?days=30
```
**参数:**
- `ip`: IP 地址(URL 编码)
- `days`: 统计天数

### 4. 获取最近调用记录
```
GET /api/stats/recent?limit=100&days=7
```
**参数:**
- `limit`: 返回记录数量限制(默认 100)
- `days`: 统计天数(默认 7)

### 5. 清理旧统计数据
```
POST /api/stats/clear
Content-Type: application/json

{
  "days": 90
}
```
**参数:**
- `days`: 保留最近多少天的数据(默认 90 天)

## 可视化统计页面

访问 `http://localhost:8001/stats` 即可查看统计面板,包含:

### 总体概览
- 总请求数、成功/失败请求数
- 总 Token 消耗量
- 唯一 IP 数量
- 模型提供商分布
- API 端点分布

### IP 列表
- 所有访问过系统的 IP 地址
- 每个 IP 的请求数、Token 消耗
- 首次和最后使用时间

### 最近记录
- 最近的 API 调用详细记录
- 包含时间、IP、端点、提供商、Token 消耗等信息

## 数据存储

统计数据存储在 `token_stats.json` 文件中(项目根目录),格式如下:

```json
{
  "records": [
    {
      "timestamp": "2024-01-15T10:30:00",
      "ip": "192.168.1.100",
      "endpoint": "/api/testcase/generate/stream",
      "provider": "azure",
      "model": "gpt-4",
      "prompt_tokens": 1500,
      "completion_tokens": 800,
      "total_tokens": 2300,
      "status": "success",
      "error_message": ""
    }
  ]
}
```

## 已集成统计的 API 端点

目前已添加统计记录的 API:

1. `/api/testcase/generate/stream` - 测试用例生成(流式)
2. `/api/refine` - AI 优化需求文档
3. `/api/chroma/query` - Chroma 向量检索(含 AI 整理)

## 扩展统计

如需在其他 API 端点添加统计,参考以下模式:

```python
@app.post("/api/your-endpoint")
async def your_endpoint(request: YourRequest, http_request: Request):
    client_ip = get_client_ip(http_request)
    
    try:
        # 调用 LLM API
        result = await call_llm_api(prompt, provider=request.provider)
        
        # 提取 Token 信息
        token_usage = result.get("_token_usage", {})
        
        # 记录统计
        token_stats_manager.record_usage(
            ip=client_ip,
            endpoint="/api/your-endpoint",
            provider=request.provider,
            prompt_tokens=token_usage.get("prompt_tokens", 0),
            completion_tokens=token_usage.get("completion_tokens", 0),
            total_tokens=token_usage.get("total_tokens", 0),
            model=token_usage.get("model", ""),
            status="success"
        )
        
        return {"success": True, ...}
    except Exception as e:
        # 记录错误
        token_stats_manager.record_usage(
            ip=client_ip,
            endpoint="/api/your-endpoint",
            provider=request.provider,
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            model="",
            status="error",
            error_message=str(e)
        )
        raise
```

## IP 获取说明

系统会通过以下方式获取客户端真实 IP:
1. `X-Forwarded-For` 请求头(经过代理的情况)
2. `X-Real-IP` 请求头
3. 直接连接地址

## 数据清理建议

建议定期清理旧数据,避免文件过大:

```bash
# 清理 90 天前的数据
curl -X POST http://localhost:8001/api/stats/clear \
  -H "Content-Type: application/json" \
  -d '{"days": 90}'
```

或者通过 Crontab 定时执行:
```bash
# 每月 1 号凌晨 2 点清理 90 天前的数据
0 2 1 * * curl -X POST http://localhost:8001/api/stats/clear -H "Content-Type: application/json" -d '{"days": 90}'
```

## 注意事项

1. **性能影响**: 统计记录采用同步写入,对性能影响极小(通常 < 1ms)
2. **存储空间**: 每条记录约 300 字节,10 万条约 30MB
3. **隐私保护**: IP 地址仅用于统计分析,不会泄露用户信息
4. **生产环境**: 建议将 `token_stats.json` 加入 `.gitignore`

## 故障排查

### 统计数据未更新
- 检查 `token_stats.json` 文件权限
- 查看控制台是否有 `[TokenStats] 记录统计失败` 错误

### Token 数量为 0
- 确认 LLM API 返回中包含 `usage` 字段
- 检查 `llms.py` 中的 `_token_usage` 提取逻辑

### 统计页面无法访问
- 确认服务正常运行在 8001 端口
- 访问 `http://localhost:8001/stats`

## 未来优化方向

1. 使用数据库(如 SQLite)替代 JSON 文件存储
2. 添加更多可视化图表(折线图、饼图等)
3. 支持按用户/项目维度统计
4. 添加 Token 消耗预警功能
5. 支持导出统计报表(CSV/Excel)
