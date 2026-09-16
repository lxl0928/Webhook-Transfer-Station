---
name: retry-webhook-message
description: 重试失败消息
tools: ["query_webhook_logs", "get_webhook_log", "retry_webhook_message"]
---

# 重试失败消息

先读取日志确认失败状态，说明未知投递结果重试可能重复。重试使用原配置快照，生成确认请求后等待用户确认。
