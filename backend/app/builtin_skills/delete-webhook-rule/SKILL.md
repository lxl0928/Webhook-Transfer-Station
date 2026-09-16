---
name: delete-webhook-rule
description: 删除中转规则
tools: ["list_webhook_rules", "get_webhook_rule", "delete_webhook_rule"]
---

# 删除中转规则

先定位具体规则并解释删除后不再接收新事件，但历史日志与已入队任务仍保留。只生成待确认删除，不声称已删除。
