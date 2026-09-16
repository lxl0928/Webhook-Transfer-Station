# Skill 与智能助手设计文档

## 1. 产品行为

登录后，所有业务页面右下角显示智能助手。展开后可新建对话、切换历史、选择单个 Skill 或自动使用已启用的 Skill。聊天使用当前用户个人设置中的 LLM Host、API Key、模型；模型必须支持 Chat Completions 格式的 `tools` / `tool_calls`。不支持工具调用的模型只能返回文本，不能完成平台操作。

支持查询规则、日志与用户资料，创建/修改/删除规则，更新用户资料和模型配置，修改密码，重试失败消息，检测健康，以及管理 Skill。业务数据通过受控工具访问。查询直接执行；修改操作显示实际工具名称、参数和确认按钮，由登录用户确认或取消。模型回答“已确认”不会执行操作。

涉及源站密钥、目标 Webhook URL、机器人签名密钥、LLM API Key 或密码时，在确认表单填写。这些表单字段不进入模型上下文或聊天记录。更新时留空保留原值；清空现有密钥请使用相应业务设置页面。聊天正文、选中 Skill 的说明以及查询的业务数据会发送到用户配置的模型服务，请勿把秘密直接粘贴到正文。

Skill 管理支持自定义新增、编辑、启停、删除、导出 SKILL.md；内置 Skill 可编辑、启停、恢复默认，不能删除/改名。每个用户独立配置。Skill 是操作说明加工具白名单，不是上传后执行的 Python/Shell 程序；前端与后端没有动态代码执行接口。

## 2. 为什么本版不实现 MCP Server

当前客户端是站内 Vue 聊天组件，服务端就是 FastAPI。后端作为模型工具调用的执行方，直接使用 Pydantic 工具定义和既有业务函数，能复用 JWT 用户身份、校验和数据库事务。增加 MCP Server 会新增协议入口、外部客户端鉴权和连接管理，但不会增强当前站内功能，因此本版采用 **REST + 服务端工具调用**。

如果未来需要 Claude Desktop、其他外部 Agent 等客户端接入，可以为 `agent_tools.TOOLS` 和执行层添加 MCP 协议适配；外部认证、租户映射、操作确认和审计必须单独设计，不能把当前 JWT 或模型 API Key 直接充当通用 MCP 凭证。现在没有 `/mcp` 端点，也没有承诺可被外部 MCP 客户端直接连接。

## 3. 内置模块

| Skill | 主要功能 |
|---|---|
| query-webhook-rule | 规则分页查询和详情 |
| create-webhook-rule | 创建规则；支持 Gitee/夜莺/通用来源与三平台 @ |
| update-webhook-rule | 规则部分更新、启停 |
| delete-webhook-rule | 删除规则 |
| update-user-info | 用户资料查询和修改 |
| configure-llm | 模型 Host、模型名、API Key 配置 |
| change-user-password | 通过确认表单修改密码 |
| query-webhook-log | 日志筛选和详情 |
| retry-webhook-message | 失败消息重试 |
| check-system-health | 后端、PostgreSQL、LLM 健康检测 |
| manage-skills | Skill 列表、详情、新增、编辑、删除、恢复默认 |

代码内置文件在 `backend/app/builtin_skills/<name>/SKILL.md`，随 Python 包和 Docker 镜像发布。首次访问 Skill 或聊天时，为当前用户复制到数据库，后续不会覆盖用户编辑；恢复默认会显式重置指定内置项。共 20 个注册工具，目录由 `/api/skills/tools` 返回，包括参数 JSON Schema、是否修改和表单字段。

自定义 Skill 示例：

```yaml
name: failed-alert-review
description: 帮助管理员分析最近失败的告警
instructions: 先查询最近失败的日志，再逐条查看原因。建议重试前说明重复通知风险。
tools: [query_webhook_logs, get_webhook_log, retry_webhook_message]
enabled: true
```

## 4. 数据结构与迁移

迁移 `0003` 新增四表，不改动既有规则与消息快照：

- `tb_skill`：所属用户、名称、描述、说明、工具列表、内置/启用标志和时间；用户+名称唯一。
- `tb_chat_conversation`：所属用户、标题、创建/更新时间、处理租约和到期时间。
- `tb_chat_message`：对话、role、加密的完整 wire 消息体、Trace ID、创建时间。
- `tb_chat_action`：对话、工具名称、加密参数、授权 Skill ID、对象状态指纹、状态、加密结果、Trace ID、创建/过期/完成时间。

消息、操作参数与结果使用已有 Fernet 密钥加密。标题保存为明文简短摘要；删除对话会删除其聊天消息和操作记录，已经完成的业务修改不会撤销。生产环境应按自身审计要求备份数据库；本版没有自动清理或无限历史检索。

## 5. 工具执行与安全边界

1. JWT 解析为当前用户；所有会话、Skill、规则和日志按该用户隔离。
2. 启用 Skill 的工具并集，或单个指定 Skill 的工具，组成模型可见目录；只允许调用代码注册的工具。
3. Pydantic 严格校验输入，禁止额外字段；日志等外部文本在系统提示中被标记为不可信资料。
4. 查询工具直接调用现有接口业务函数；工具结果做已有敏感字段脱敏并截断超长内容。
5. 写工具只创建 15 分钟有效的操作草案；记录不可由前端改写的参数和目标对象状态指纹。
6. 用户确认时再次验证所属用户、Skill 仍启用且授权工具、对象未发生变化；对话/操作/对象使用数据库锁保护，成功的重复确认返回已有结果。
7. 确认表单只允许该工具声明的密钥字段。调用现有业务函数时延迟提交，操作结果与业务修改在同一事务提交。参数错误不提交业务修改，可修正表单重试。失败消息重试本身仍可能产生重复群消息，确认卡会提示。
8. 用户取消不会执行业务变更。已过期、权限失效或对象变化的操作需要重新生成。

没有任意 URL 请求、任意 REST 路径代理、SQL、Shell、代码解释器或模型自行批准工具。LLM Host 与目标群 URL 沿用现有允许列表和官方域名校验。聊天工具并非权限系统替代品；自定义 Skill 只能从既有、按用户鉴权的能力中选择。

## 6. REST 接口

所有接口需要 Bearer JWT，并沿用 X-Trace-Id 和请求 cost 日志。完整参数可见 FastAPI `/docs`。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET/POST | `/api/skills` | 列表/新增 |
| GET | `/api/skills/tools` | 工具参数与目录 |
| GET/PUT/PATCH/DELETE | `/api/skills/{id}` | 详情/完整更新/启停/删除 |
| POST | `/api/skills/{id}/reset` | 恢复内置项 |
| GET | `/api/skills/{id}/export` | 下载 SKILL.md |
| GET/POST | `/api/chat/conversations` | 最近 50 个对话/新建 |
| GET/DELETE | `/api/chat/conversations/{id}` | 消息与操作详情/删除 |
| POST | `/api/chat/conversations/{id}/messages` | 同步对话，content + 可选 skill_id |
| POST | `/api/chat/conversations/{id}/actions/{action_id}/decision` | approve/reject，附可选 secrets |

聊天每轮最长 55 秒、最多 4 轮模型请求、8 次工具调用；单条输入最多 4000 字符，对话达到约 200 条 wire 消息后要求新建。上下文保留最近最多 40 条 wire 消息，按用户轮次起点裁切，历史上限约 60000 JSON 字符；Skill 说明合计超过 40000 字符时要求指定单个 Skill。并非长期记忆系统。模型输出不是可信执行回执，执行状态以确认卡为准。

对话使用 90 秒数据库租约防止重复发起并行轮次，进程异常后可超时恢复；正常结束或失败时释放。存在未过期待确认操作时不能继续发送消息，可先确认/取消，或新建对话。界面暂不使用 SSE 流式输出，等待期间显示处理状态。数据库事务时间与模型等待分离，写操作与审计保持原子提交。

## 7. 部署与验收

无需新增容器、消息代理或 MCP 端口。更新镜像后执行 `alembic upgrade head`；Compose 的 migrate 服务已经负责迁移。内置 Skill 文件通过 setuptools package-data 纳入安装包。沿用前端 65 秒与 nginx 70 秒超时配置。

验收分三层：pytest + 真实 PostgreSQL 验证权限/事务/并发，MockTransport 验证模型 wire 协议，本地模拟模型配合浏览器验证完整交互。真实模型的 function calling 兼容性、效果与费用需要使用实际供应商配置完成联调，不能用模拟通过代替。
