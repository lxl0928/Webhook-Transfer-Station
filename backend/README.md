# 后端开发指南

[返回项目总览](../README.md) · [前端开发指南](../frontend/README.md)

面向第一次使用 FastAPI 的开发者。本指南按“准备环境 → 启动数据库 → 配置 → 建表 → API → worker → 调试 → 测试”的顺序展开；先把流程跑通，再修改业务代码。

## 你将运行什么

- **PostgreSQL**：存放用户、规则、消息队列、日志、Skill 和聊天记录。
- **API**：FastAPI HTTP 服务，监听 8000，负责接收回调和管理操作。
- **worker**：独立 Python 进程，没有 HTTP 端口，负责消费数据库中的消息。
- **Alembic / bootstrap**：一次性执行的建表/升级和管理员初始化命令。

API 与 worker 必须连接同一个数据库，并使用相同 ENCRYPTION_KEY。无需额外 Redis；生产运行依赖 PostgreSQL，SQLite 仅用于部分测试。

## 第一步：准备开发环境

需要 Python **3.12**（与项目 Docker/CI 一致）、运行中的 Docker 和 Compose 插件。Windows 推荐在 WSL2 中执行本指南；以下 `.venv/bin/` 路径不适用于原生 PowerShell。

在**项目根目录**打开终端：

```bash
python3 --version
docker compose version
docker info
```

确认 Python 为 3.12；若默认 `python3` 不是该版本，请先安装 Python 3.12，并在下条命令中使用 `python3.12`。

```bash
python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install -r backend/requirements.lock
backend/.venv/bin/python -m pip install -e 'backend[dev]'
```

`.venv` 是项目独立的 Python 环境；使用其完整路径执行命令，无需先 `activate`。`requirements.lock` 固定依赖版本，`[dev]` 安装测试/lint 工具，`-e` 让源码修改直接被 Python 导入。

编辑器选择解释器 `backend/.venv/bin/python`，避免“终端能运行、编辑器却提示缺少模块”。已有 `.venv` 可复用，不必重建。

## 第二步：启动 PostgreSQL

在**项目根目录**执行；已有根目录 `.env` 时跳过初始化脚本：

```bash
python3 scripts/init_env.py
```

然后执行：

```bash
docker compose up -d postgres
docker compose ps postgres
docker compose exec postgres sh -c 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```

等待容器健康且输出 `accepting connections`；刚启动时尚未就绪可稍后重试。当前 Compose 已把数据库映射到本机 `5432`，所以不需要另写端口覆盖文件。

如果 5432 被其他程序占用，在根目录 `.env` 添加 `POSTGRES_PORT=55432`，再次执行 `docker compose up -d postgres`，并让下一步 DATABASE_URL 使用 55432。不要修改容器内的 5432。

本地调试只需要 Compose 的 postgres 服务。若此前运行过整套 Compose，可先在根目录执行 `docker compose stop frontend backend worker`，避免本地 worker 与容器 worker 同时消费调试消息；不要删除已有数据库卷。

## 第三步：生成 backend/.env

根目录 `.env` 供 Compose 使用；本地 Python 在**当前工作目录**查找 `.env`，所以接下来始终从 `backend/` 启动。直接复制根配置还不够，需要补 DATABASE_URL。

进入 **backend 目录**：

```bash
cd backend
```

首次配置可复制执行下面的 Python 命令。它从根配置读取数据库账号和密钥，写入 `backend/.env`，不在终端输出密钥；如果文件已存在，会拒绝覆盖。

```bash
cd backend

python3 init_backend_env.py

```

已有 `backend/.env` 时用编辑器核对以下字段，保留原密钥；不要把占位文字直接复制为真实密钥：

```dotenv
DATABASE_URL=postgresql+asyncpg://数据库用户:URL编码后的密码@127.0.0.1:5432/数据库名
JWT_SECRET=与根目录一致的真实JWT密钥
ENCRYPTION_KEY=与根目录一致的真实Fernet密钥
PUBLIC_BASE_URL=http://localhost:5173
LLM_ALLOWED_HOSTS=api.openai.com
```

只通过 API 调试时也可把 PUBLIC_BASE_URL 改为 `http://localhost:8000`；通过前端 Vite 调试则用 5173。它只影响生成的回调地址，不决定 API 监听端口，也不会启动服务。

环境变量优先于 `.env`。若终端以前设置过 DATABASE_URL 等变量，应核对或取消对应的 `export`。配置修改后重启 API 和 worker；修改根 `.env` 不会自动更新 backend/.env。

## 第四步：建表并初始化管理员

在 **backend 目录**执行：

```bash
.venv/bin/alembic upgrade head
.venv/bin/python -m app.bootstrap
.venv/bin/alembic current
```

预期当前迁移为 `0003 (head)`。`upgrade head` 会把数据库升级到当前代码版本；bootstrap 只创建不存在的管理员，不会覆盖已有账号密码。

默认账号 `admin` / `Admin#123.`。若修改过 ADMIN 配置或数据库中已有账号，使用相应的实际账号。

## 第五步：分别启动 API 和 worker

**终端 A：工作目录 backend，保持运行：**

```bash
.venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --no-access-log
```

预期出现 `Application startup complete` 和 `Uvicorn running on http://127.0.0.1:8000`。`--reload` 让 API 在 Python 源码变更后自动重启。

**终端 B：新开终端，从项目根目录进入 backend，保持运行：**

```bash
cd backend
.venv/bin/python -m app.worker
```

worker 空闲时不一定持续输出日志；没有连接错误且进程持续运行即可。修改 worker 相关代码后需 Ctrl+C 停止并重新启动，它没有自动 reload。

**终端 C：任意目录，检查服务：**

```bash
curl -i http://127.0.0.1:8000/health/live
curl -i http://127.0.0.1:8000/health/ready
```

两者预期 HTTP 200；ready 应包含 PostgreSQL `ok`。打开 <http://127.0.0.1:8000/docs>。8000 提供接口而非 Vue 页面，直接访问 `/` 返回 404 不表示启动失败。

需要管理界面时，按 [前端指南](../frontend/README.md) 在另一终端启动 Vite。停止开发时在 API、worker、Vite 各终端 Ctrl+C；数据库可在根目录用 `docker compose stop postgres` 停止并保留数据。

## 第六步：用 /docs 调试第一个接口

1. 展开 `POST /api/auth/login`，点击 **Try it out**。
2. 使用实际账户填写 JSON，点击 **Execute**：

   ```json
   { "username": "admin", "password": "Admin#123." }
   ```

3. 响应应为 HTTP 200，复制 `access_token` 的值（不含 JSON 引号）。
4. 点击页面的 **Authorize**，在 HTTP Bearer 输入框粘贴 token 本身，然后确认。
5. 执行 `GET /api/users/me`，应看到用户资料和模型配置状态，不返回 API Key 明文。
6. 执行 `GET /api/skills`，首次访问会初始化当前用户的 11 个内置 Skill。

调试时可通过 curl 自行传递 `Authorization: Bearer <token>` 和 `X-Trace-Id: local-debug-001`。响应带 X-Trace-Id，API 终端记录相同 trace 与请求 `cost_ms`；用于关联一次请求，不要把 token 或密码写进调试日志。

## 代码放在哪里，如何开始修改

| 文件 / 目录 | 职责 |
| --- | --- |
| `app/main.py` | FastAPI 入口、路由注册、异常处理 |
| `app/api.py` | 认证、个人设置、规则、日志、回调与健康接口 |
| `app/schemas.py` | 请求/响应字段与输入校验 |
| `app/models.py` | SQLAlchemy 数据表模型 |
| `app/db.py`、`app/deps.py` | 数据库会话、登录鉴权依赖 |
| `app/config.py`、`app/security.py` | 配置、密码/JWT、加密与脱敏 |
| `app/sources.py`、`app/templates.py` | 源站事件解析和模板变量 |
| `app/outbound.py` | 模型请求、三平台消息及签名 |
| `app/worker.py` | 领取任务、执行投递、处理超时任务 |
| `app/skills.py`、`app/skill_schemas.py` | Skill 管理接口与校验 |
| `app/chat.py`、`app/agent_tools.py` | 对话和受控工具执行 |
| `app/builtin_skills/*/SKILL.md` | 随包分发的内置说明与工具白名单 |
| `alembic/versions/` | 表结构迁移历史 |
| `tests/` | API、worker、平台适配和聊天测试 |

建议第一次修改先从一个只读接口或输入校验开始：找到 api.py 对应路由 → 查看 schemas.py → 在 `/docs` 试请求 → 添加覆盖新行为的 pytest → 运行检查。不要绕过 current_user 或直接接受客户端传入的 user_id 作为数据归属。

修改数据库字段时，仅改 models.py 不会改变已存在的数据库。在开发库先完成已有迁移，再编辑模型并生成新迁移：

```bash
# 工作目录：backend；修改 models.py 后执行
.venv/bin/alembic revision --autogenerate -m "describe your change"
# 先阅读生成的迁移，确认没有意外删除表或字段，再执行
.venv/bin/alembic upgrade head
.venv/bin/alembic check
```

不要修改已部署的历史迁移文件来实现新需求。升级生产库前先备份。涉及模型/平台格式时通过 mock HTTP 验证，不把真实付费调用和群通知放进普通单元测试。

## 检查与测试

以下所有命令在 **backend 目录**执行：

```bash
.venv/bin/ruff check app tests alembic
.venv/bin/ruff format --check app tests alembic
.venv/bin/pytest -q
# 只跑聊天与 Skill 测试
.venv/bin/pytest -q tests/test_chat.py
```

普通测试用临时 SQLite 和模拟 HTTP，不需要先启动 API/worker，也不依赖生产数据库；PostgreSQL 专用并发测试会跳过。测试会覆盖自己的数据库与加密配置，不要删改这些隔离逻辑。

需要验证 PostgreSQL 并发锁时，单独启动一次性测试数据库，**不要使用业务库**：

```bash
# 任意目录；55433 专用于测试，如被占用请换端口并同步下方 URL
docker run -d --name station-pg-unit-test   -e POSTGRES_USER=test -e POSTGRES_PASSWORD=test -e POSTGRES_DB=station_test   -p 127.0.0.1:55433:5432 postgres:16-alpine
docker exec station-pg-unit-test pg_isready -U test -d station_test
```

等待 `accepting connections` 后，在 **backend 目录**运行：

```bash
TEST_POSTGRES_URL='postgresql+asyncpg://test:test@127.0.0.1:55433/station_test' .venv/bin/pytest -q
```

每个测试在临时 schema 中建表并清理，真实库测试包含 worker 与聊天确认的并发校验。完成后删除刚创建的测试容器：

```bash
docker rm -f -v station-pg-unit-test
```

这条清理命令仅用于上述一次性测试容器。迁移 downgrade 可能删除数据，只在专门的空测试数据库进行，不在开发业务库或生产库试运行。

## 后端配置参考

配置定义在 `app/config.py`。密钥和数据库连接见第三步；其他常用项：

| 变量 | 默认 | 含义 |
| --- | --- | --- |
| TOKEN_EXPIRE_MINUTES | 120 | JWT 有效时间（分钟） |
| MAX_PAYLOAD_BYTES | 1048576 | 回调请求体上限（字节），nginx 也有限制 |
| WORKER_POLL_SECONDS | 2 | 无任务时的轮询间隔 |
| WORKER_LEASE_SECONDS | 300 | processing 任务超时检查阈值 |
| OUTBOUND_TIMEOUT_SECONDS | 45 | 外部 HTTP 请求超时 |
| LOGIN_MAX_ATTEMPTS | 10 | 登录限流阈值 |
| LLM_ALLOWED_HOSTS | api.openai.com | 允许的模型域名，逗号分隔 |
| ALLOW_HTTP_LLM | false | 可信内网模型是否允许 HTTP |

本地可写入 backend/.env；Compose 运行时需要在公共 `backend-env` 中显式传入新增变量，仅在根 `.env` 增加未引用变量不会自动传给容器。

API Key 和机器人 URL 等加密存储；丢失 ENCRYPTION_KEY 会导致旧凭证、快照、聊天记录无法解密。更换 Key 不会自动迁移数据。

## 回调接入与消息规则

以下是后端协议说明；网页接入流程见 [项目总览](../README.md#从-gitee-到群消息)。示例 curl 中的 8080 适用于 Compose；仅启动本地 API 时改用 8000，启动了 Vite 时可使用 5173。curl 中的占位符必须换成实际规则值，运行投递测试可能向真实群发送消息。

### 模板示例

源站模板：

```text
仓库：{{repository}}
事件：{{event}}
原始内容：{{payload}}
```

LLM 提示词：

```text
请将仓库事件整理为简洁的中文团队通知，包含作者、事件类型、关键变更与链接。
只依据输入内容，不推测未给出的信息。控制在 500 字以内。
```

目标模板：

```text
[{{source_name}}] {{event}}
{{llm_output}}
```

可用变量：`payload,event,repository,source_url,source_type,source_info,source_name,llm_output`。模板是纯文本，不是 JSON；系统自动包装平台 JSON，正确转义引号和换行。支持安全的 JSON 路径取值，例如 `{{payload.events.0.rule_name}}`、`{{source_info.team}}`，缺失字段输出空字符串；不支持表达式、对象属性调用或二次模板展开。企业微信文本上限按 2048 UTF-8 字节校验，建议中文摘要 500 字以内；超限记录失败，不会静默截断。

### 不依赖 Gitee 的接收测试

先创建一条关闭 LLM 的规则，将下面 wid、仓库和密钥替换为实际配置。此命令会入队并最终向配置的目标群发送消息：

```bash
curl -i 'http://localhost:8080/webhooks?wid=<你的32位wid>' \
  -H 'Content-Type: application/json' \
  -H 'X-Gitee-Event: Push Hook' \
  -H 'X-Gitee-Token: <规则中填写的回调密钥>' \
  -H 'X-Trace-Id: local-check-001' \
  -d '{"repository":{"html_url":"https://gitee.com/team/repo"},"ref":"refs/heads/main","commits":[{"message":"测试消息"}]}'
```

Gitee 返回 202，夜莺/通用源站返回 200，均表示已经持久化接受，不代表目标投递成功。通过日志详情查看最终状态。

## 配置 @ 人员

在中转规则的「目标群机器人」中填写 @ 成员，支持多个 ID / 手机号（换行或逗号分隔），也可以启用「@所有人」。无需在提示词里让 LLM 生成 @ 语法，系统会在最终消息封装阶段自动添加，日志中的 `output_payload` 可查看实际结果。


| 目标   | 人员标识                                    | 实际输出                                             |
| ---- | --------------------------------------- | ------------------------------------------------ |
| 飞书   | 群成员 Open ID（`ou_...`），不支持手机号或普通 user_id | text 中的 `<at user_id="ou_...">成员</at>`           |
| 企业微信 | user ID 或成员绑定的手机号                       | text.mentioned_list / text.mentioned_mobile_list |
| 钉钉   | user ID 或成员绑定的手机号                       | at.atUserIds / at.atMobiles，以及文本中的 @ 标记          |


@所有人使用飞书 `user_id="all"`、企业微信 `mentioned_list=["@all"]`、钉钉 `isAtAll=true`。不与指定人员混用，默认关闭；成员需属于目标群，具体提醒效果受机器人及群权限影响。飞书自定义机器人本身不提供通讯录查询，本平台不自动查询或转换人员 ID。

API 字段示例（以企业微信/钉钉为例）：

```json
"target_mentions": {
  "all": false,
  "user_ids": ["zhangsan"],
  "mobiles": ["13800138000"]
}
```

`target_mentions` 不填表示不 @，空对象可清除现有 @ 配置。编辑界面会回显并保存人员配置，切换平台会清空人员，防止误用其他平台的 ID。消息接收时将人员配置冻结到快照；后续修改不影响已入队消息。模型输出中的飞书 `<at>` 标签会被转成普通文字，仅规则配置决定实际 @ 人员。

## 夜莺与通用服务回调

新增规则时选择「夜莺」或「通用回调」，源站地址可选，仅用于展示，不校验仓库字段，也不会请求该地址。非 Gitee 源站事件过滤留空即接收全部。


| 鉴权方式      | 源站配置                                           |
| --------- | ---------------------------------------------- |
| 请求头（推荐）   | 默认 `X-Webhook-Token: <回调密钥>`；可在规则中修改 Header 名称 |
| Bearer    | `Authorization: Bearer <回调密钥>`                 |
| URL Token | URL 追加 `&token=<URL编码后的回调密钥>`，适合只能填写 URL 的源站   |


三种模式只验证当前所选方式；通用源站不读取 payload.password 作为密钥。URL Token 只用于源站回调，不是管理员 JWT。完整带 token 的 URL 属于凭证，系统不会在规则查询中回显；复制 URL 后手动追加密钥。请求日志不记录查询串。

夜莺新版本可使用 Callback 通知媒介配置 POST URL 和鉴权 Header，旧版本只能填回调地址时选 URL Token。接收 JSON 单条对象、数组或 `{ "events": [...] }`；原始内容会完整保留（敏感键脱敏），批量数据作为一条消息处理，不拆分。未提供 `X-Webhook-Event` 时：`is_recovered=true/1/"true"/"1"` 为 `recovery`，数组或 events 数组为 `alert_batch`，其他为 `alert`。可通过源模板提取 `{{payload.rule_name}}`、`{{payload.events.0.rule_name}}`。

夜莺接入协议参考：[官方 Callback 文档](https://flashcat.cloud/docs/content/flashcat-monitor/nightingale-v8/usage/notify-channel/callback/)。不同版本可自定义消息结构，字段以实际回调为准。

通用源站支持：

- `application/json`（含 `+json` 类型）：对象、数组、字符串、数字或布尔；拒绝 null 和 NaN/Infinity。
- `text/plain`：UTF-8 文本。
- `application/x-www-form-urlencoded`：字段转换为对象，同名多个值保留数组，最多 1000 个字段。

不接受二进制附件、multipart、XML 或 GET 验证回调；此类协议需额外适配，并非无需适配就兼容所有专有签名协议。事件名优先使用 `X-Webhook-Event`，否则读取字符串 `event_type` / `event`，不符合标识格式时回退为 `webhook`。事件标识限制为 1–32 位字母、数字及 `_ . : -`。

通用服务示例：

```bash
curl -i 'http://localhost:8080/webhooks?wid=<通用规则wid>' \
  -H 'Content-Type: application/json' \
  -H 'X-Webhook-Token: <规则回调密钥>' \
  -H 'X-Webhook-Event: service.error' \
  -H 'X-Webhook-Delivery: unique-event-occurrence-id' \
  -d '{"service":"order-api","error":{"message":"数据库连接超时"},"severity":"critical"}'
```

非 Gitee 通过 `X-Webhook-Delivery` 去重；不要将夜莺会被多次更新的告警 id 单独作为每次通知的 delivery ID，否则可能把恢复事件误判重复。不提供 Header 则每次独立处理。

## 消息处理语义

- 所有通过校验的消息保存脱敏输入。密码、token、Key 等已知键名会替换为 `[REDACTED]`，不保存原始请求 Headers。
- 接收时冻结并加密规则与 LLM 配置。编辑 / 停用 / 删除规则不取消已入队任务；历史日志仍保留。
- 支持 `X-Gitee-Delivery` 存在时的重复回调去重；不假设 Gitee 总是发送此 Header。没有稳定 delivery ID 时每次回调都视为独立消息。
- 网络发送与数据库不是原子事务，不承诺恰好一次投递。未知结果不自动重发，管理员确认目标后再重试。
- 失败重试沿用接收时的配置；修改当前 Key 不会更新旧快照。每条日志展示最近一次尝试的结果和总尝试次数。
- 模型或目标机器人错误、网络超时、非法响应均记录失败。HTTP 200 且平台业务码为 0 才算投递成功。

## Skill 与聊天开发

聊天使用当前用户保存的模型配置，要求 Chat Completions 的 `tools/tool_calls`。11 个内置 Skill 会按用户复制到数据库；修改磁盘 SKILL.md 不会自动覆盖已有用户编辑，需要显式恢复默认才能采用新内容。

扩展能力时先在 agent_tools.py 注册工具名称、严格参数模型、是否修改数据和敏感表单字段，复用现有鉴权业务逻辑，再将工具名加入相应 Skill。自定义 Skill 只能选择已有工具，不能上传代码或指定任意 HTTP 地址执行。

读工具直接查询；写工具生成 15 分钟有效的草案，用户点击确认后再次验证归属、权限、对象状态，并在单事务中提交业务修改和操作结果。不能添加让模型自己调用的“自动确认”工具。记录和参数加密存储，敏感表单不写进聊天上下文。

站内不运行 MCP Server，复用 REST 与工具层；设计和接口清单见 [m04](../docs/m04_Skill与智能助手设计文档.md)。

## 常见错误与排查顺序

| 错误 / 现象 | 原因及处理 |
| --- | --- |
| `ConnectionRefusedError` | DATABASE_URL 地址没有数据库监听。先看根目录 `docker compose ps postgres`，再 pg_isready；核对宿主机端口 |
| 无法解析 `postgres` | 这个名称供 Compose 容器内部使用。本地 Python 改用 127.0.0.1 |
| `password authentication failed` | backend/.env 与实际数据库密码不同；修改根 POSTGRES_PASSWORD 不会更新旧数据卷里的密码 |
| `relation ... does not exist` | 数据库已连接但没建表/升级；在 backend 执行 `alembic upgrade head` |
| JWT_SECRET / ENCRYPTION_KEY 校验报错 | 当前目录不是 backend、缺少 backend/.env，或填入了占位值；检查终端已有环境变量 |
| `No module named app` / 找不到 .venv | 使用正确目录与解释器，确认已经安装 `-e 'backend[dev]'` |
| 8000 address already in use | 关闭重复启动的 API；如果换端口，必须同步前端 Vite 代理 |
| 登录 401 | 账号/密码不匹配，或旧 token 失效；初始化变量不会重置已有密码 |
| 回调 401/403 | 检查 wid、源站鉴权模式、回调密钥、Gitee 仓库地址 |
| 回调成功但消息 pending | worker 未启动或连接了不同数据库 |
| 消息 failed | 在日志详情看模型/平台错误；检查允许域名、Key、群机器人签名、关键词/IP 策略及文本长度 |
| 聊天能回答却不执行操作 | 检查模型的工具调用支持、Skill 是否启用、是否已确认操作卡 |
| `canceled` / Ctrl+C 后停止 | 这是进程取消的表现；真正原因看此前日志，不能仅凭 canceled 判断数据库故障 |

worker 接收时冻结配置，修改规则/Key 不会修复旧消息快照。重试仍用旧快照，且可能产生重复消息；先检查目标实际接收情况。

官方接入参考：[Gitee](https://gitee.com/help)、[飞书机器人](https://open.feishu.cn/document/client-docs/bot-v3/add-custom-bot)、[企业微信机器人](https://developer.work.weixin.qq.com/document/path/91770)、[钉钉机器人](https://open.dingtalk.com/document/robots/custom-robot-access)。平台权限以实际配置和官方说明为准。
