# IP 和 Token 统计功能 - 快速开始

## 📦 新增内容

### 文件清单
- ✅ `token_stats.py` - 统计核心模块
- ✅ `templates/stats.html` - 统计可视化页面
- ✅ `test_token_stats.py` - 测试脚本
- ✅ `TOKEN_STATS_README.md` - 详细使用文档
- ✅ `.gitignore` - 排除统计数据文件

### 修改文件
- ✅ `main.py` - 添加统计 API 和中间件
- ✅ `llms.py` - 提取 Token 使用信息

## 🚀 快速使用

### 1. 启动服务
```bash
cd AiToCase_v2
python main.py
```

### 2. 访问统计页面
打开浏览器访问:
```
http://localhost:8001/stats
```

### 3. 使用统计 API

#### 查看总体统计
```bash
curl http://localhost:8001/api/stats/summary?days=30
```

#### 查看 IP 列表
```bash
curl http://localhost:8001/api/stats/ip-list?days=30
```

#### 查看最近记录
```bash
curl http://localhost:8001/api/stats/recent?limit=50&days=7
```

### 4. 运行测试
```bash
python test_token_stats.py
```

## 📊 功能特性

### 自动记录
每次调用以下 API 时会自动记录:
- IP 地址
- API 端点
- 模型提供商 (Azure/DeepSeek/阿里云/豆包)
- Token 消耗 (输入/输出/总计)
- 调用状态 (成功/失败)

### 统计维度
1. **按 IP 统计** - 每个 IP 的使用情况
2. **按时间统计** - 支持 7/30/90/365 天
3. **按模型统计** - 不同模型的调用分布
4. **按端点统计** - 各 API 的使用频率

### 可视化面板
统计页面包含:
- 📈 总体概览卡片
- 🌍 IP 列表及排名
- 📝 最近调用记录
- 🎨 彩色标签区分模型提供商

## 💡 使用示例

### 示例 1: 查看本月统计
访问 `http://localhost:8001/stats`,选择"最近 30 天"

### 示例 2: 查看某个 IP 的详细使用情况
```bash
curl http://localhost:8001/api/stats/ip/192.168.1.100?days=30
```

### 示例 3: 清理旧数据
```bash
curl -X POST http://localhost:8001/api/stats/clear \
  -H "Content-Type: application/json" \
  -d '{"days": 90}'
```

## 🔧 配置说明

### 数据存储位置
统计数据保存在: `AiToCase_v2/token_stats.json`

### 自动创建
首次使用时会自动创建该文件,无需手动配置

### 数据格式
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
      "status": "success"
    }
  ]
}
```

## 📝 注意事项

1. **性能影响**: 统计记录对性能影响极小 (< 1ms)
2. **存储空间**: 10 万条约 30MB
3. **定期清理**: 建议每月清理 90 天前的数据
4. **隐私保护**: IP 仅用于统计分析

## ❓ 常见问题

### Q: 为什么 Token 数量是 0?
A: 部分 API (如 /api/refine) 暂未集成 Token 提取,会记录为 0

### Q: 统计页面打不开?
A: 确保服务已启动,访问 `http://localhost:8001/stats`

### Q: 如何导出数据?
A: 可以通过 API 获取 JSON 数据,自行转换为 Excel

### Q: 会影响现有功能吗?
A: 不会,统计功能是透明的,不影响原有业务逻辑

## 🎯 下一步

查看详细文档: [TOKEN_STATS_README.md](TOKEN_STATS_README.md)

## 📞 技术支持

如有问题,请查看:
1. 控制台日志中的 `[TokenStats]` 标记
2. `token_stats.json` 文件是否存在
3. 测试脚本输出
