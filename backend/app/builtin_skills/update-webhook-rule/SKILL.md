---
name: update-webhook-rule
description: 修改与启停中转规则
tools: ["list_webhook_rules", "get_webhook_rule", "update_webhook_rule"]
---

# 修改与启停中转规则

先查询确认 wid 及现有字段，只提交用户要求变化的字段。可修改 @ 人员、模板和启停状态。切换目标平台需新目标地址，凭证在确认表单填写。

源站回调鉴权由 source_auth_enabled 控制，默认开启。用户明确要求关闭时可设为 false，此时无需源站密钥；告知持有回调 URL 的人即可触发。重新开启必须提供密钥或已有保存的密钥。目标机器人签名配置不受此开关影响。
