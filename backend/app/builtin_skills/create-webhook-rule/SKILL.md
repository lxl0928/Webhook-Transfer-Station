---
name: create-webhook-rule
description: 创建中转规则
tools: ["list_webhook_rules", "create_webhook_rule"]
---

# 创建中转规则

确认来源、鉴权方式、目标平台、事件和提示词。通用源站可不填源地址。先查询避免重复，使用 create_webhook_rule 生成确认草案；回调密钥和目标 URL 由用户在确认卡片的安全输入框填写，不要在聊天中索要密钥。
