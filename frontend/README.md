# 前端开发指南

[返回项目总览](../README.md) · [后端开发指南](../backend/README.md)

面向第一次使用 Vue 的开发者。目标是让你能启动页面、登录、修改组件、检查接口请求，并完成生产构建。先按顺序跑通，不需要先学习 Docker 网络或自行编写登录接口。

## 先理解开发环境

| 名称 | 用途 |
| --- | --- |
| Node.js / npm | 运行前端构建工具、安装依赖；浏览器并不直接运行 Node |
| Vue3 | 编写页面和交互，文件扩展名 `.vue` |
| TypeScript | 为 JavaScript 添加类型检查，扩展名 `.ts` |
| Element Plus | 按钮、表格、表单、抽屉等组件 |
| Vite | 本地开发服务器、热更新及构建 |
| Axios | 请求后端 API；统一客户端在 `src/api.ts` |
| nginx | Docker 部署时提供静态页面并转发 API，本地 Vite 开发不需要单独安装 |

前端项目没有模拟登录或独立数据库。**只启动 Vite 可以显示登录页，但需要后端和 PostgreSQL 才能登录、加载业务数据**。worker 负责中转消息，不影响基本页面加载。

## 第一步：准备 Node.js

使用 Node.js **22**，与项目 Docker/CI 一致。安装后重新打开终端，在任意目录检查：

```bash
node --version
npm --version
```

`node --version` 应显示 `v22.x.x`。如果已经安装 Node 版本管理器，可以用它切换版本；没有的话直接安装 Node 22 即可。以下终端命令以 macOS/Linux/WSL2 为例。

## 第二步：先准备可用的后端

选择下面一种方式，不要同时启动两套占用 8000 的 API。

### 方式 A：前后端都在本机开发

按 [后端指南的第一步至第五步](../backend/README.md#第一步准备开发环境) 完成：

1. 用 Docker 启动 PostgreSQL。
2. 安装 Python 依赖，生成 backend/.env。
3. 执行数据库迁移和管理员初始化。
4. 启动本地 API，监听 `127.0.0.1:8000`。
5. 需要测试消息投递时另开终端启动 worker。

这是需要同时修改 Python 与 Vue 时的推荐方式。

### 方式 B：只开发前端，后端放在 Docker

这种方式无需本地 Python 虚拟环境；根配置初始化脚本仍需要 Python 3。先启动 Docker，在**项目根目录**生成 `.env`（已有文件则跳过）：

```bash
python3 scripts/init_env.py
```

仍在根目录执行：

```bash
docker compose up -d postgres
docker compose build backend
docker compose run --rm migrate
```

确认迁移命令成功后，**在该终端保持 API 运行**：

```bash
docker compose run --rm --no-deps -p 127.0.0.1:8000:8000 backend
```

这会启动临时 API 容器并发布本机 8000，刚好符合 Vite 的默认代理目标。`--no-deps` 表示不重复启动依赖，所以上面的数据库和迁移步骤不能省略；`--rm` 在退出后删除临时容器，不删除数据库卷。

如果需要实际中转消息，在另一个终端、**项目根目录**执行：

```bash
docker compose run --rm --no-deps worker
```

worker 使用上面构建的同一个后端镜像。若此前启动过整套项目，可先在根目录执行 `docker compose stop frontend backend worker`，只保留 PostgreSQL，再按上述步骤启动，避免混用两套应用进程。

### 检查后端是否就绪

任意目录执行：

```bash
curl -i http://127.0.0.1:8000/health/ready
```

预期 HTTP 200，数据库状态为 `ok`。浏览器打开 <http://127.0.0.1:8000/docs> 能看到接口文档。若这里失败，先修复后端；调整 Vue 页面无法解决数据库连接问题。

## 第三步：安装依赖并启动页面

新开终端，从**项目根目录**进入 frontend：

```bash
cd frontend
npm ci
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

`npm ci` 根据 package-lock.json 安装确定版本的依赖。看到 Vite 的 Local 地址后访问 <http://localhost:5173>。`--strictPort` 让端口占用时直接报错，避免 Vite 悄悄切换端口导致生成的回调地址不一致。

这个终端需要保持运行；Ctrl+C 停止前端服务器。以后再次开发不需要每次重新安装，进入 frontend 后启动 dev 即可；依赖锁文件更新后再运行 `npm ci`。

如果采用本地后端方式，推荐 `backend/.env` 的 `PUBLIC_BASE_URL=http://localhost:5173`。如果采用 Docker 后端方式且需要生成指向 Vite 的回调 URL，在根 `.env` 设置同样的值后重新启动临时 API/worker 容器。PUBLIC_BASE_URL 不是前端 API baseURL，不能靠它改变 Vite 代理目标。

## 第四步：登录并确认链路

默认首次账号为 `admin` / `Admin#123.`；若后端已改密码或初始化账号配置，使用实际账号。

登录成功后：

1. 进入「中转规则」，没有数据时应显示空列表，而不是网络错误。
2. 进入「个人设置」，应能看到用户资料。
3. 进入「Skill 管理」，应显示 11 个内置 Skill（以及此前添加的自定义项）。
4. 点击右下角「智能助手」，应能打开聊天面板。真正对话需用户配置支持工具调用的 LLM；没有配置时出现提示属于正常情况。

在浏览器开发者工具的 **Network（网络）** 面板中查看 `/api/auth/login`、`/api/users/me` 等请求。成功应为 200，响应 Header 中应有 `X-Trace-Id`。

不用真实群机器人或付费模型，也可以开发登录、规则表单、日志空状态、Skill 编辑和聊天布局。真实模型检测及消息投递会调用实际外部服务；自动化模拟测试由后端 pytest 提供。

## 页面如何调用后端

### 本地开发：Vite 代理

页面使用相对地址：

```ts
import { api } from "./api";

// 该导入示例适用于 src/ 下的文件；views/ 下应改为 ../api
const response = await api.get("/api/users/me");
console.log(response.data.username);
```

浏览器实际请求 `http://localhost:5173/api/users/me`。`vite.config.ts` 将它转发到 `http://127.0.0.1:8000/api/users/me`，无需在每个页面硬编码后端地址。

目前代理前缀为 `/api`、`/webhooks`、`/health`、`/docs`、`/openapi.json`。API 不在本机 8000 时修改 vite.config.ts 中的 `target`，然后重启 Vite；本项目没有预置 `VITE_API_BASE_URL` 环境变量。

如果已通过完整 Compose 在 8080 运行项目，也可以把 Vite target 改为 `http://127.0.0.1:8080`，经过 nginx 访问 API；与默认 8000 路线二选一即可。

### 部署环境：nginx 代理

Docker 构建时把 `npm run build` 生成的 dist 复制到 nginx 镜像。浏览器访问 8080，nginx 提供页面，并按 nginx.conf 把 API 转发到 Compose 内部的 `http://backend:8000`。

`backend` 是 Docker 网络内的服务名，不是浏览器能直接访问的公共域名。本地 Vite 和生产 nginx 是两套代理配置，修改其中一个不会自动更新另一个。两种方式都让浏览器使用同源请求，正常开发不需要额外配置 CORS。

### 登录状态与错误处理

`src/api.ts` 负责：

- 从 sessionStorage 读取登录 token，自动添加 `Authorization: Bearer ...`。
- 生成并发送 X-Trace-Id，错误提示中展示响应 trace，便于后端查日志。
- 统一错误提示；非登录接口返回 401 时清除登录状态并跳转登录页。
- 设置 65 秒请求超时；聊天每轮后端限制为 55 秒，生产 nginx 读取超时为 70 秒。

新增业务请求请复用 `api`，不要在每个页面另建 Axios 客户端。不要把后端数据库密码、JWT 签名密钥或模型 API Key 写入源码、console.log 或 Vite 环境变量。

## 第五步：做一次小修改

### 修改已有页面，观察热更新

1. 保持后端和 Vite 运行。
2. 打开 `src/views/Webhooks.vue`，找到页面按钮中的“新增中转”。
3. 临时改成“新增中转规则”，保存文件。
4. 浏览器按钮文字应自动更新，无需重新运行构建。
5. 观察控制台是否报错，再决定保留修改或恢复原文。

### 新增一个简单页面

创建 `src/views/Help.vue`：

```vue
<template>
  <section>
    <h1>使用帮助</h1>
    <p>先配置中转规则，再将回调地址填写到源站。</p>
    <el-button type="primary" @click="$router.push('/webhooks')">
      查看中转规则
    </el-button>
  </section>
</template>
```

在 `src/router.ts` 的 routes 数组中、兜底路由之前增加：

```ts
{ path: "/help", component: () => import("./views/Help.vue") },
```

登录后访问 `http://localhost:5173/#/help`。路由使用 hash 模式，因此 URL 带 `#`。需要侧边栏入口时，在 `src/App.vue` 的导航里添加 `<router-link to="/help">使用帮助</router-link>`，并在 titles 映射中增加 `"/help": "使用帮助"`。

本例的 ElButton 已在 main.ts 注册；使用新的 Element Plus 组件时先检查是否已注册，需要时在组件内导入或在 main.ts 补充注册。现有页面采用 `<script setup lang="ts">`，优先沿用该写法。

## 页面和文件导航

| 文件 | 修改什么时看它 |
| --- | --- |
| `src/main.ts` | 应用入口、Element Plus 组件注册 |
| `src/App.vue` | 侧边栏、顶部导航、全局布局、聊天入口 |
| `src/router.ts` | 路由、登录跳转 |
| `src/api.ts` | Axios、拦截器、业务 TypeScript 类型 |
| `src/style.css` | 公共样式、响应式布局 |
| `src/views/Login.vue` | 登录页 |
| `src/views/Webhooks.vue` | 中转规则、模板和 @ 人员表单 |
| `src/views/Logs.vue` | 消息日志、详情、失败重试 |
| `src/views/Profile.vue` | 用户资料、密码、模型配置和健康检测 |
| `src/views/Skills.vue` | Skill 新增、编辑、启停、恢复和导出 |
| `src/components/BusinessIcon.vue` | 统一来源、平台、事件和状态图标；保留旁边的文字标签 |
| `src/components/ChatAssistant.vue` | 全局聊天、历史、工具草案、确认表单 |
| `vite.config.ts` | 本地代理与构建拆包 |
| `nginx.conf`、`Dockerfile` | 部署时静态文件和反向代理 |

规则表单涉及后端校验，新增字段需要同步前端类型、表单和后端 schemas/models；不要只加一个输入框就认为数据已经持久化。编辑已保存的密钥通常以“已配置，留空保留”显示，后端不会回传明文。

聊天中的修改、删除、重试必须走确认接口，不能由前端根据模型文本直接调用任意接口。确认成功后全局页面会刷新数据；密码修改后需要重新登录。新增聊天业务能力应先在后端注册工具，再配置 Skill，详见 [后端 Skill 开发](../backend/README.md#skill-与聊天开发)。

## 检查、构建与交付

在 **frontend 目录**执行：

```bash
npm run lint
npm run build
```

lint 使用 ESLint，警告也会使检查失败；build 先执行 TypeScript/Vue 类型检查，再输出 `dist/`。修改后应同时通过两条命令。不要直接编辑 dist，下一次构建会覆盖它。

查看静态构建效果可运行：

```bash
npm run preview -- --host 127.0.0.1
```

访问终端打印的地址。当前安装的 Vite 默认让 preview 沿用 `server.proxy`，因此后端仍需在代理目标地址运行；preview 本身不会启动后端。它只提供已有 dist 的预览，没有源码热更新，也不代表 nginx 部署验证。日常联调使用 Vite dev，完整部署验证使用根目录的 `docker compose up -d --build`。

本项目当前没有配置前端单元测试脚本。不要运行不存在的 `npm test`；先完成 lint、类型/生产构建，再在浏览器验证修改页面、登录跳转、空列表、错误提示和窄屏布局。涉及接口语义的验证在后端 pytest 中完成。

## 常见错误与排查顺序

| 现象 | 处理 |
| --- | --- |
| `node` / `npm` command not found | 安装 Node 22，重新打开终端，核对版本 |
| 找不到 package.json | 当前目录不对，进入 frontend 后运行 npm 命令 |
| npm ci 下载失败 | 查看第一条错误，检查包仓库网络；不要先删除 package-lock.json |
| 5173 被占用 | 停止旧 Vite；或换端口，并同步 PUBLIC_BASE_URL。使用 strictPort 避免误访问旧实例 |
| 页面打开但登录时代理 ECONNREFUSED | Vite 正常，目标 API 未启动或端口不对；先 curl 8000/health/ready |
| API 404 / 返回 HTML | 请求路径或代理配置不匹配；业务接口一般以 /api 开头 |
| 登录 401 | 核对实际账号密码；改了初始化 ADMIN_PASSWORD 不会重置已有用户 |
| 登录后马上回到登录页 | token 已失效、JWT_SECRET 不一致或后端切换了数据库；重新登录并核对配置 |
| 报 CORS | 检查是否绕开了相对路径代理，直接写了另一个域名/端口 |
| 前端改了但 Docker 页面没更新 | Docker 使用构建后的静态文件，需要重新 build；即时热更新用 Vite |
| 新 Element Plus 标签未渲染 | 检查组件注册或显式导入 |
| 聊天没有模型响应 | 去个人设置配置/检测模型；确认 Host 允许列表、API Key、模型工具调用能力 |
| 消息一直 pending | 这是 worker 消费问题，不是前端刷新问题；查看后端指南 |

向后端同学提供错误时，附上请求路径、HTTP 状态、页面操作和 X-Trace-Id，不附密码/API Key/Authorization token。不要只截图“请求失败”而遗漏 Network 中的实际响应。

## 进一步阅读

- [项目总览：部署、端口、接入流程](../README.md)
- [后端指南：模板、鉴权与 @ 人员](../backend/README.md#回调接入与消息规则)
- [Skill 与智能助手设计](../docs/m04_Skill与智能助手设计文档.md)
- [已执行验收与尚未联调的外部服务](../docs/验收记录.md)

### 规则表单的源站鉴权

「源站回调鉴权」默认开启。关闭时隐藏鉴权方式和回调密钥输入框，并显示 URL 持有者可触发的提示。开启时，没有已保存密钥的规则必须填写至少 8 位密钥；已配置的规则可留空保留。该开关与「目标机器人签名密钥」独立，对应 API 字段 source_auth_enabled。

### 助手 Markdown 预览

助手回复（含历史消息）使用 `MarkdownPreview.vue` 渲染标题、表格、列表、引用、链接、行内代码和代码块。`src/markdown.ts` 使用 markdown-it 解析，再经 DOMPurify 标签与属性允许列表过滤，保留表格中的 `<br>` 换行及 `{{payload}}` 等模板原文，移除脚本、事件属性和图片等内容。用户输入、工具 JSON 和操作确认参数仍以纯文本展示。

修改渲染逻辑后，在 `frontend` 目录运行 `npm test` 执行格式与安全过滤测试，再运行 `npm run lint` 和 `npm run build`。新增依赖后，其他开发环境先执行 `npm ci`。
