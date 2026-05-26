# GuLiCode Collaboration Server 服务端开发技术设计

## 目标

本文定义 GuLiCode 未来远程协作服务端的工程边界、核心接口和开发约束。它结合了 `multi_agent_tcp` 当前架构，以及 dreamyouxi 博客《离开电脑也不停工：手机指挥 Claude 数字团队多 agent 干活》的实践经验。

核心结论：

- GuLiCode Collaboration Server 负责账号、权限、消息存盘、运行记录索引、事件转发、移动端访问和审计。
- Python Runtime 的 `GraphRuntimeControlPlane` / `GraphRuntime` 是调度事实源，服务端不能重新实现调度语义。
- `CLIWorkerBackend` 只是执行适配层，Codex、CodeMaker、Claude 或其它 CLI worker 都应被视为可替换后端。
- 远程服务应驱动现有 runtime / desktop / worker 能力，而不是另起一套并行执行系统。
- 公网链路优先使用成熟 TLS、代理和隧道能力，不自造加密协议。

本文不是数据库 schema 定稿，也不是具体框架选型文档。它的作用是让后续服务端实现保持同一组架构边界。

## 背景与约束

博客实践验证了一个关键产品需求：用户离开电脑后，仍然希望通过手机继续指挥本机 agent 执行代码修改、测试、部署和长任务监控。这个需求不能简单理解为“把 AI 搬到云上”，因为当前工作流存在两个硬约束。

第一，本地资源不能随意搬到云端。本地仓库、未提交修改、SSH 私钥、VPN、`.env`、客户数据和内部接口都是 agent 工作上下文的一部分。把这些全部同步到云端既不现实，也会扩大合规和安全风险。

第二，AI 的代码改动需要 IDE 级 review。Diff、Source Control、Go to Definition、Find References、Debugger 和全局符号搜索仍然由 GuLiCode Desktop / VSCode 类本地工具承担。远程服务端的价值是让用户可以移动端派单、看状态、做审批，而不是取代本地 IDE。

因此，GuLiCode 服务端的设计原则是：

```text
移动端 / Web 客户端
  -> 远程协作服务端
  -> 本机或受控环境中的 Python Runtime
  -> GraphRuntimeControlPlane / GraphRuntime
  -> CLIWorkerBackend
  -> Codex / CodeMaker / Claude 等 worker
```

服务端是控制面代理、消息存盘层和协作同步层，不是调度器本身。

## 架构分层

| 层 | 技术形态 | 职责 | 不负责 |
| --- | --- | --- | --- |
| Client / PWA | GuLiCode Desktop、Web、移动端 PWA | 登录、项目选择、top-agent 指令、运行状态、事件流、报告和产物入口 | 不直接访问 runtime token，不直接写项目目录 |
| GuLiCode Collaboration Server | 长期运行的远程服务 | 用户、权限、消息存盘、run 索引、事件转发、审计、移动端入口 | 不计算队列、batch、join、workspace merge |
| Python Runtime Service | 本机或受控运行环境中的 Python 服务 | `GraphRuntimeControlPlane`、`GraphRuntime`、workspace、MCP、run 生命周期 | 不负责多用户账号、远程会话登录态 |
| Worker Backend | `CLIWorkerBackend`、AgentTCP、CLI adapter | 启动或绑定具体 CLI worker，传递 prompt，解析结果 | 不拥有产品调度语义 |

推荐端到端形态：

```text
Browser / PWA
  │ HTTPS + Cookie
  ▼
GuLiCode Collaboration Server
  │ Server-Sent Events / WebSocket
  │ RPC proxy with service token
  ▼
Python Runtime Service
  │ GraphRuntimeControlPlane
  ▼
GraphRuntime
  │ queues / outgoing batches / joins / workspace events
  ▼
CLIWorkerBackend
  │ Codex / CodeMaker / Claude adapter
  ▼
Agent process
```

在单用户自托管形态下，公网入口可以复用博客中的部署经验：公网 VPS 上 Caddy 负责 HTTPS 和反向代理，本机主动建立 SSH 反向隧道，Python 服务只监听 `127.0.0.1`。多用户托管形态下，可以把隧道替换为受控 agent gateway，但仍应保留“本地 runtime 不直接暴露公网”的边界。

## 服务端职责

### 必须拥有的事实

GuLiCode Collaboration Server 可以持久化下列事实：

- 用户、项目成员、角色、权限。
- 登录会话、刷新令牌、设备信息、IP 限速记录。
- user message、top-agent instruction、用户确认或拒绝记录。
- start plan 原文、run metadata、run owner、project binding。
- runtime event journal 的镜像副本。
- agent utterance 摘要、工具调用卡片、错误摘要。
- reports、artifacts、changesets 的索引和展示元数据。
- 审计日志，包括 auth、run control、message send、runtime proxy、permission deny。

这些事实服务查询、审计和跨端同步。它们不是 runtime 调度的来源。

### 不能拥有的事实

服务端不得自行维护或推导下列调度状态：

- AgentNode 是否应该入队。
- outgoing batch 是否完整。
- fan-in join 是否满足。
- Agent 任务是否可以标记 completed。
- workspace changeset 是否可以合并。
- project 目录中的最终代码状态。
- 某个 runtime event 是否应该推进下一步图执行。

这些判断属于 `GraphRuntime` 和 workspace API / MCP 工具边界。服务端只能转发请求、缓存响应、订阅事件和展示结果。

## 核心流程

### 登录与项目选择

1. 用户通过 Web / PWA / Desktop 登录 Collaboration Server。
2. 服务端校验 cookie session 或兼容 Basic Auth 的调试入口。
3. 客户端请求 `GET /projects`，服务端返回用户可访问的项目列表。
4. 用户选择项目后，服务端返回项目的 run 列表、可用 blueprint、最近事件和权限摘要。

项目记录应绑定到一个 runtime endpoint，而不是直接绑定到项目物理路径。物理路径、runtime token、workspace RPC token 只存在于服务端和 Python Runtime 的受控通道中。

### 创建运行

1. 用户在客户端输入 top-agent 指令，或选择已有 blueprint 并提交 start plan。
2. 客户端调用 `POST /runs`。
3. 服务端写入 user message / instruction / start plan 原文。
4. 服务端检查用户对项目和 blueprint 的权限。
5. 服务端把 start plan 转发给 Python Runtime 的 `runtime start` 控制面。
6. Python Runtime 校验计划并创建 live run。
7. 服务端记录 run metadata，并把 runtime 返回的 run id、初始 status、事件 cursor 返回客户端。

服务端不能在本地“模拟启动成功”。如果 runtime start 失败，`POST /runs` 必须返回明确错误，并保留审计记录。

### 运行中事件回流

1. 客户端建立 `GET /stream?runId=...`。
2. 服务端校验用户是否能读取该 run。
3. 服务端从 runtime 订阅或轮询 status / events。
4. 服务端把 runtime events 规范化为前端事件：
   - node queued / running / completed / failed
   - outgoing batch open / complete
   - join pending / satisfied / failed
   - agent utterance
   - tool card
   - report / artifact / changeset index
   - workspace conflict
5. 客户端按事件更新 run panel、节点图、时间线和报告入口。

推荐第一版使用 SSE，因为运行状态主要是 server-to-client。未来若需要多人共同编辑、实时输入、协同光标或双向 presence，再扩展 WebSocket。

### 结束与归档

1. 用户点击 complete / cancel / fail / pause / archive。
2. 客户端调用 `POST /runs/:id/end`。
3. 服务端校验权限并转发到 runtime control-plane。
4. Runtime 执行 `end_run` 和归档逻辑。
5. 服务端记录最终状态和审计日志。

归档文件、changeset、reports、artifacts 的权威来源仍是 workspace / archive。服务端可以保存索引，不能把自己的索引当作归档事实。

## API 草案

所有 API 默认返回 JSON。错误格式应稳定，便于客户端展示和测试。

```json
{
  "ok": false,
  "code": "RUNTIME_UNAVAILABLE",
  "message": "Python runtime is not reachable",
  "requestId": "req_..."
}
```

### Auth

| Method | Path | 说明 |
| --- | --- | --- |
| `POST` | `/auth/login` | 校验用户名密码，设置 `httponly` cookie |
| `POST` | `/auth/logout` | 清理当前 session |
| `GET` | `/me` | 返回当前用户、权限和设备摘要 |

登录态建议：

- 浏览器使用 `httponly`、`secure`、`sameSite=lax` cookie。
- 调试、自检和脚本入口可以兼容 Basic Auth。
- session 签名密钥保存在服务端文件或 secret manager 中，重启不应导致所有用户被迫登出。

### Project

| Method | Path | 说明 |
| --- | --- | --- |
| `GET` | `/projects` | 返回当前用户可访问项目 |
| `GET` | `/projects/:projectId/runs` | 返回项目 run 列表和摘要 |
| `GET` | `/projects/:projectId/blueprints` | 返回项目 blueprint 列表 |

项目返回值不暴露真实 runtime token、workspace RPC token、Codex home 或 agent 私有路径。

### Run Control

| Method | Path | 说明 |
| --- | --- | --- |
| `POST` | `/runs` | 创建 run，并把 start plan 转发给 runtime |
| `GET` | `/runs/:runId` | 返回 run metadata |
| `GET` | `/runs/:runId/status` | 返回 runtime status snapshot |
| `GET` | `/runs/:runId/events` | 返回事件分页 |
| `POST` | `/runs/:runId/end` | complete / cancel / fail / pause / archive |

`POST /runs` 请求示例：

```json
{
  "projectId": "proj_123",
  "blueprintId": "review-flow",
  "instruction": "检查 parser 改动并补测试",
  "startPlan": {
    "reason": "User requested parser review",
    "start_node_ids": ["planner"],
    "initial_messages": []
  }
}
```

服务端处理顺序必须是：权限校验、写入用户指令、转发 runtime、记录 runtime 响应。不要先生成一个本地 run 状态再异步“补启动”，否则移动端会看到虚假的 running 状态。

### Event Stream

| Method | Path | 说明 |
| --- | --- | --- |
| `GET` | `/stream?runId=...&cursor=...` | SSE 事件流 |

SSE 事件建议：

```text
event: runtime.status
id: 42
data: {"runId":"run_1","status":"running","agents":{}}

event: agent.utterance
id: 43
data: {"runId":"run_1","nodeId":"coder","taskId":"task_1","said":"..."}

event: workspace.report
id: 44
data: {"runId":"run_1","area":"reports","path":"blueprint_result.json","version":2}
```

代理层必须关闭响应缓冲。使用 Caddy 时，应保留类似 `flush_interval -1` 的配置，避免流式事件等响应结束后才一次性下发。

## Runtime 集成约定

服务端与 Python Runtime 的集成应复用当前控制面语义：

- 读组织结构：`organization` / top-agent context。
- 启动：`runtime start`。
- 状态：`runtime status` / `explain_status`。
- 消息：message batch、message stage、agent dispatch。
- 汇聚：join create、join contribute。
- 结束：`runtime end`。
- top-agent 可见发言：`top_agent.utterances`。

实现时可以通过本地 RPC、HTTP bridge、Unix/Windows 本地进程通信或受控 gateway 连接 runtime。无论底层通信方式是什么，服务端接口都必须把 runtime 当作事实源。

### 缓存规则

服务端可以缓存：

- 最近一次 status snapshot。
- event journal 的已转发 cursor。
- report / artifact / changeset 索引。
- run 结束后的最终摘要。

缓存失效或冲突时：

- live run 以 runtime 当前响应为准。
- ended / archived run 以 workspace archive 和 runtime final manifest 为准。
- 服务端缓存缺失时可以重建索引，但不能改写 workspace 事实。

### Workspace 规则

代码协作仍遵守当前三空间模型：

- project code root 是最终代码目标，Agent 可读但不能直接写。
- private checkout 是 Agent 可写工作区。
- shared workspace 保存 reports、artifacts、manifest、changeset 引用和日志。

服务端不得提供“直接写项目文件”的 API。任何代码修改必须走 Agent private checkout 和 framework workspace / MCP 工具，最终通过 changeset submit 进入项目目录。

## 安全设计

### TLS 与公网入口

公网链路必须使用成熟 TLS。推荐路线：

```text
Browser / PWA
  -> HTTPS
  -> Caddy / Nginx / managed LB
  -> Collaboration Server
  -> Runtime gateway / SSH reverse tunnel / local RPC
  -> Python Runtime
```

不要使用“WebSocket + 自定义加密”替代 TLS。自定义应用层加密容易遗漏重放、防降级、证书校验、密钥轮换和错误处理。

单用户自托管部署可以沿用博客实践：

- 本机 Python Runtime 只监听 `127.0.0.1`。
- 本机主动发起 SSH 反向隧道到 VPS。
- VPS 上 Caddy 负责 HTTPS、证书续期和反代。
- 服务端和 runtime token 不进入浏览器。

### 登录防护

登录防护采用“宽锁不严锁”：

- 第 1 层：用户名密码或 Basic Auth，成功后写 `httponly` cookie。
- 第 2 层：同 IP 短窗口错误次数限速，例如 5 分钟内 10 次。
- 第 3 层：单日错误次数硬锁，跨重启保留，次日重置。
- 正确密码永远允许放行，锁定只拦截错误尝试。

这样可以避免攻击者通过反复错误登录把合法用户锁在外面。

### Token 隔离

以下字段不得返回给浏览器：

- runtime RPC token。
- workspace RPC token。
- MCP bearer token。
- Codex home、agent private dir、真实 skill-space 源路径。
- 服务端到 runtime 的 service token。
- SSH 隧道、VPS 内部端口、反代 upstream secret。

前端只拿用户态 session 和展示需要的索引。需要调用 runtime 的动作由服务端代发。

### 审计

至少记录：

- 登录成功、失败、锁定、解锁。
- 项目读取、run 创建、run 结束。
- top-agent 指令和用户确认。
- runtime proxy 请求和返回状态。
- 权限拒绝。
- 事件流连接、断开和重连。

审计日志可以先使用 append-only 文件或数据库表。关键要求是不可被普通前端请求改写。

## 移动端与 PWA 要求

移动端是该服务的主场景，第一版 Web UI 至少需要：

- `100dvh` 和 safe-area 处理，避免 iOS 地址栏和 Home indicator 遮挡。
- 输入框 `font-size: 16px`，避免 iOS 聚焦自动放大。
- 桌面端 Enter 发送，移动端 Enter 换行。
- 事件流断线后按 cursor 重连。
- 历史消息分页加载，首屏只拉最近记录。
- 流式期间纯文本渲染，消息结束后再做 Markdown sanitize 和渲染。
- 工具调用卡片和 Agent 发言可折叠。

这些是产品可用性的基础，不是后期 polish。

## MVP 范围

第一阶段只做远程运行观察和控制闭环：

- 用户登录和项目列表。
- run 创建、status、events、end。
- SSE 事件流。
- runtime unavailable 的清晰错误。
- reports / artifacts / changesets 索引展示。
- 基础审计和登录限速。

第一阶段不做：

- 多人同时编辑 blueprint。
- 服务端自行调度 Agent。
- 直接在线改项目文件。
- 自定义加密协议。
- 完整数据库迁移体系。
- 云端复制本地仓库。

第二阶段再补：

- 多用户项目成员和权限模型。
- run 历史搜索。
- 更完整的 artifact 浏览。
- WebSocket 双向协作。
- runtime gateway 高可用。
- 更强的审计查询和告警。

## 测试计划

### API contract

- 未登录访问项目返回 401。
- 无项目权限访问 run 返回 403。
- `POST /runs` 正确转发 start plan。
- runtime 返回失败时，服务端返回稳定错误格式。
- `POST /runs/:id/end` 只接受受支持 action。

### Runtime 集成

- 使用 mock `GraphRuntimeControlPlane` 验证服务端只转发请求，不私自推进状态。
- runtime status 改变后，服务端缓存不能覆盖新事实。
- runtime unavailable 时，run 创建失败并写审计。
- run ended 后继续发送控制请求返回明确错误。

### 流式

- SSE 可以连续推送 status、utterance、tool、report 事件。
- 代理关闭缓冲后，事件逐条到达。
- 客户端带 cursor 重连后不丢事件、不重复应用已确认事件。
- 长连接断开时服务端清理连接状态，不泄漏订阅。

### 安全

- 短窗口错误密码触发 IP 限速。
- 单日错误次数触发硬锁。
- 正确密码在锁定状态下仍可放行。
- token、private path、workspace RPC 信息不出现在前端 payload。
- 审计日志记录 auth、run control、permission deny。

### 回归场景

- runtime 断开。
- runtime 重启后 run 状态恢复或返回清晰不可恢复错误。
- event journal 重复投递。
- workspace conflict。
- Agent 失败。
- report / artifact 缺失。
- 移动端后台恢复后重连事件流。

## 开发原则

- 先接 runtime 控制面，再做 UI 丰富度。
- 先保证错误清晰，再考虑自动恢复。
- 先使用 SSE，等双向协作需求明确后再引入 WebSocket。
- 先持久化事实索引，不复制 workspace 内容。
- 先用成熟 TLS / 反代 / 隧道，不自造安全协议。
- 命名上始终区分 Collaboration Server、Python Runtime、Worker Backend。

## 参考

- dreamyouxi 博客：《离开电脑也不停工：手机指挥 Claude 数字团队多 agent 干活》，https://dreamyouxi.com/blog/1724
- `docs/gulicode_blueprint_workbench_design.md`
- `docs/workspace_api.md`
- `KM_docs/skills-snapshot/knowledge_base/core_architecture.md`
- `KM_docs/skills-snapshot/knowledge_base/dispatch_workflows.md`
