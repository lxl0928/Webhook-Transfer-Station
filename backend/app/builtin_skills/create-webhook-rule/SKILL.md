---
name: create-webhook-rule
description: 创建中转规则
tools: ["list_webhook_rules", "create_webhook_rule"]
---

# 创建中转规则

确认来源、鉴权方式、目标平台、事件和提示词。通用源站可不填源地址。先查询避免重复，使用 create_webhook_rule 生成确认草案；回调密钥和目标 URL 由用户在确认卡片的安全输入框填写，不要在聊天中索要密钥。

源站回调鉴权由 source_auth_enabled 控制，默认开启。用户明确要求关闭时可设为 false，此时无需源站密钥；告知持有回调 URL 的人即可触发。重新开启必须提供密钥或已有保存的密钥。目标机器人签名配置不受此开关影响。
