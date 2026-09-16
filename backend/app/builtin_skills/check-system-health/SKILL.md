---
name: check-system-health
description: 检查系统健康
tools: ["check_system_health", "check_llm_health"]
---

# 检查系统健康

检查后端与数据库状态以及是否配置模型。模型连接检测会发起一次真实的小型模型请求。不要把配置完整误称为连接成功。
