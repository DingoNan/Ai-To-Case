# 🎯 IP 和 Token 统计功能 - 演示指南

## 快速验证步骤

### 步骤 1: 启动服务
```bash
cd d:\Vs_Code_Files\OpenCode\New_Project\AiToCase_v2
python main.py
```

等待看到:
```
INFO:     Uvicorn running on http://0.0.0.0:8001
```

### 步骤 2: 访问统计页面
打开浏览器访问:
```
http://localhost:8001/stats
```

你应该能看到一个漂亮的统计面板,显示:
- 📊 总体概览卡片
- 🌍 IP 列表
- 📝 最近记录

### 步骤 3: 生成测试用例 (触发统计记录)
打开另一个终端,运行:
```bash
curl -X POST http://localhost:8001/api/testcase/generate/stream \
  -H "Content-Type: application/json" \
  -d '{
    "requirement_text": "用户登录功能，支持用户名密码登录和验证码",
    "test_module": "登录模块",
    "test_case_count": 5,
    "provider": "azure"
  }'
```

或使用浏览器访问主页:
```
http://localhost:8001/
```
然后使用界面生成测试用例。

### 步骤 4: 查看统计更新
刷新统计页面 `http://localhost:8001/stats`,你应该能看到:
- 总请求数 +1
- Token 消耗有数据
- IP 列表中出现你的 IP
- 最近记录中有一条新记录

### 步骤 5: 运行测试脚本
```bash
python test_token_stats.py
```

测试脚本会自动:
1. 检查服务是否运行
2. 测试所有统计 API
3. 显示统计结果

## 📸 预期效果

### 统计页面效果
```
┌─────────────────────────────────────────┐
│  📊 Token 使用统计面板                   │
├─────────────────────────────────────────┤
│  时间范围: [最近 30 天 ▼] [刷新] [IP列表] │
├─────────────────────────────────────────┤
│  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐   │
│  │总请求│ │成功  │ │失败  │ │Token │   │
│  │  150 │ │ 145  │ │  5   │ │125K  │   │
│  └──────┘ └──────┘ └──────┘ └──────┘   │
├─────────────────────────────────────────┤
│  模型提供商分布                           │
│  ┌─────────────────────────────────┐   │
│  │ azure    │ 100  │ 66.7%         │   │
│  │ deepseek │  50  │ 33.3%         │   │
│  └─────────────────────────────────┘   │
└─────────────────────────────────────────┘
```

### API 返回示例
```json
{
  "success": true,
  "summary": {
    "total_requests": 1,
    "success_requests": 1,
    "error_requests": 0,
    "total_tokens": 2300,
    "prompt_tokens": 1500,
    "completion_tokens": 800,
    "unique_ips": 1,
    "providers": {
      "azure": 1
    }
  }
}
```

## 🔍 验证要点

### ✅ 检查清单
- [ ] 服务正常启动在 8001 端口
- [ ] 统计页面可以访问
- [ ] 页面显示统计卡片
- [ ] 生成测试用例后统计数据更新
- [ ] IP 列表显示正确的 IP
- [ ] Token 数量有数据 (不为 0)
- [ ] 最近记录中有新条目
- [ ] 测试脚本全部通过

### 🐛 问题排查

#### 问题 1: 统计页面 404
**原因**: 服务未启动或端口错误
**解决**: 
```bash
python main.py
# 确认显示: Uvicorn running on http://0.0.0.0:8001
```

#### 问题 2: Token 数量为 0
**原因**: API 未返回 usage 字段
**解决**: 
- 检查 LLM API 配置是否正确
- 查看控制台是否有错误日志
- 确认使用支持的 provider (azure/deepseek/aliyun/doubao)

#### 问题 3: IP 显示为 127.0.0.1
**原因**: 本地访问,这是正常的
**说明**: 
- 本地访问会显示 127.0.0.1 或 ::1
- 远程访问会显示真实 IP
- 通过代理访问会显示 X-Forwarded-For 中的 IP

#### 问题 4: token_stats.json 不存在
**原因**: 首次使用,会自动创建
**解决**: 
- 调用任意 API 后会自动创建
- 检查文件权限是否正常

## 📊 数据查看方式

### 方式 1: Web 界面 (推荐)
```
http://localhost:8001/stats
```

### 方式 2: API 调用
```bash
# 总体统计
curl http://localhost:8001/api/stats/summary?days=30 | python -m json.tool

# IP 列表
curl http://localhost:8001/api/stats/ip-list?days=30 | python -m json.tool

# 最近记录
curl http://localhost:8001/api/stats/recent?limit=10 | python -m json.tool
```

### 方式 3: 直接查看文件
```bash
# Windows
type token_stats.json

# Linux/Mac
cat token_stats.json | python -m json.tool
```

## 🎓 使用场景示例

### 场景 1: 查看团队使用情况
```bash
# 查看本月所有 IP 的使用情况
curl http://localhost:8001/api/stats/ip-list?days=30
```

### 场景 2: 分析 Token 消耗
```bash
# 查看总体 Token 消耗
curl http://localhost:8001/api/stats/summary?days=30
```

### 场景 3: 排查问题
```bash
# 查看最近的失败记录
curl http://localhost:8001/api/stats/recent?limit=50&days=7
# 然后在结果中查找 status: "error"
```

### 场景 4: 清理历史数据
```bash
# 清理 90 天前的数据
curl -X POST http://localhost:8001/api/stats/clear \
  -H "Content-Type: application/json" \
  -d '{"days": 90}'
```

## 💡 最佳实践

1. **定期查看**: 每周查看一次统计面板
2. **定期清理**: 每月清理 90 天前的数据
3. **监控异常**: 关注 Token 消耗突增的 IP
4. **优化成本**: 根据统计数据优化模型使用
5. **备份数据**: 定期备份 token_stats.json

## 🎉 完成!

如果你能看到统计页面并且数据正常更新,说明功能已经成功实现!

有任何问题,请查看:
- 详细文档: `TOKEN_STATS_README.md`
- 快速指南: `STATS_QUICKSTART.md`
- 实现总结: `IMPLEMENTATION_SUMMARY.md`
