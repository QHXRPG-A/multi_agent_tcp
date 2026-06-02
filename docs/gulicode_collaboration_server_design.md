# GuLiCode Collaboration Server 服务端开发技术设计

## 当前结论

GuLiCode Collaboration Server 是移动端和未来远程协作入口的服务端边界。它负责账号、权限、会话、消息存盘、运行索引、事件转发、审计和移动端 API，不负责多 Agent 调度。

当前事实源分层必须保持清晰：

```text
Mobile PWA / Web / GuLiCode Desktop
  -> GuLiCode Collaboration Server
  -> DesktopBlueprintService / GraphRuntimeControlPlane
  -> GraphRuntime
  -> AgentNode queues / outgoing batches / joins / workspace events
  -> CLIWorkerBackend
  -> Codex / Codex / other CLI worker
```

核心开发原则：

- `/mobile` 当前是只读前端 mock，不能作为后端 API 合同。
- `GraphRuntimeControlPlane` / `GraphRuntime` 继续是调度事实源。
- Collaboration Server 只代理、持久化、审计和投影 runtime 事实。
- 移动端第一版优先实现只读查看、安全事件流和索引展示。
- run 创建、消息发送、审批和 end/control 作为已定义但 capability-gated 的第二阶段能力。
- 浏览器不得获得 runtime token、workspace RPC token、MCP bearer token、private checkout path、Codex home 或 service token。

## Mock 与源码观察

### 当前 mock 状态

`archive/frontend/mock/` 明确记录：mock 归档只描述展示状态和验证结果，不是后端合同。

当前 `/mobile` mock 已从 2026-05-27 的项目/run/action 第一版，收敛到 2026-05-28 的三页只读结构：

- `Top Agent`：只读 mock 对话，不发送消息。
- `蓝图`：只读结构图、运行状态、Agent 信息 sheet、Diff 摘要。
- `待定`：保留空状态。

已移出当前 active mock 的能力不能直接进入第一阶段服务端范围：

- project selector
- create run
- run control
- approval / archive actions
- long event stream cards
- report list
- tool cards as full mobile workflow

这些能力可以进入后续 capability gate，但不能被描述成当前移动端必须立即接入的 UI 合同。

### 当前源码状态

`GuLiCode/packages/app/src/mobile/*` 当前只依赖 `mobileMockData` 和本地展示状态。`mobile-state.ts` 中的类型服务 mock 组件，不是公共后端 DTO。

`GuLiCode/packages/app/src/entry.tsx` 对 `/mobile` 做独立入口处理，只包 `PlatformProvider` 和 `AppBaseProviders`，没有接入 desktop `AppInterface`、`GlobalSDKProvider` 或 `GlobalSyncProvider`。这意味着移动端真实接入需要一个独立的 Collaboration Server client，而不是直接复用桌面 runtime provider。

`GuLiCode/packages/app/vite.config.ts` 已经把运行敏感路径配置为 `NetworkOnly`：

- `/auth/*`
- `/api/*`
- `/runs/*`
- `/stream`

这个约束必须保留。PWA 只能缓存 shell 和静态资源，不缓存登录态、runtime status、SSE stream 或 run payload。

### 当前 runtime / desktop bridge 状态

Python 侧已有可复用能力：

- `desktop_blueprint_service.py`
  - `blueprint.list`
  - `blueprint.open`
  - `blueprint.save`
  - `blueprint.validate`
  - `blueprint.listRuns`
  - `blueprint.start`
  - `blueprint.status`
  - `blueprint.recentEvents`
  - `blueprint.agentInfo`
  - `blueprint.queueAgentMessage`
  - `blueprint.agentStreamToken`
  - `blueprint.runDiff`
  - `blueprint.changesetDiff`
  - `blueprint.end`
- `graph_control.py`
  - `GraphRuntimeControlPlane`
  - organization read
  - top-agent context / explain status / utterances
  - run validate/start/status/end
  - message batch/stage
  - agent dispatch
  - join create/contribute
- `graph_runtime.py`
  - `status_snapshot()`
  - `explain_status()`
  - event journal
  - agent stream events
  - workspace state projection
- `workspace_api.py` / `workspace_rpc.py`
  - checkout/status/diff/submit
  - publish/publish-file
  - run-scoped reports/artifacts
  - private checkout boundary

Collaboration Server 第一版应复用这些接口，不重写调度器、workspace merge、join、batch 或 Agent queue。

## 服务端需要开发的模块

建议新增 Python 服务端边界，保持在 `multi_agent_tcp` 包内，避免引入第二套 Node 服务端：

| 模块 | 职责 | 不负责 |
| --- | --- | --- |
| `collaboration_server.py` | Starlette app、路由、middleware、SSE endpoint、启动入口 | 不实现 runtime 调度 |
| `collaboration_store.py` | sqlite3 schema、事务、查询、索引、审计写入 | 不保存 secret 明文到前端 payload |
| `collaboration_auth.py` | 登录、session cookie、CSRF 基础策略、限速、用户上下文 | 不把 Basic Auth 作为正式移动端登录态 |
| `collaboration_runtime_bridge.py` | 调用 `DesktopBlueprintService` / runtime RPC，做安全投影 | 不计算 queue/batch/join/final status |
| `collaboration_events.py` | runtime event journal 镜像、cursor、SSE replay、断线重连 | 不制造 runtime event |
| `collaboration_projection.py` | 把 runtime status/diff/report/artifact 转成移动端 DTO | 不复用 mock 类型作为合同 |

### 账号与权限

第一版要实现：

- 用户表和密码哈希。
- `httponly`、`secure`、`sameSite=lax` cookie session。
- session 过期、注销和设备/IP 摘要。
- 项目成员与角色。
- run 读权限、控制权限和审批权限。
- 登录失败短窗口限速与审计。

调试入口可以保留 Basic Auth 兼容层，但只能用于本地开发或自动化诊断，不作为移动端正式身份体系。

### 项目与 runtime binding

项目记录绑定到 runtime endpoint / desktop bridge handle，而不是把真实项目物理路径直接交给浏览器。

服务端持久化：

- `projectId`
- display name
- owner / members / role
- runtime binding id
- blueprint ids and display metadata
- safe last-run summary

服务端内部可以保存受控 runtime endpoint、service token、项目路径或桌面 bridge 连接信息，但这些字段不得出现在前端 payload。

### Run 索引与消息存盘

服务端需要持久化：

- server-side run id 与 runtime run id 的绑定。
- project binding、blueprint id、owner、created/updated/ended timestamps。
- user instruction、Top Agent message、用户确认/拒绝记录。
- runtime status 的最近投影。
- runtime event journal 镜像。
- report / artifact / changeset 索引。
- audit log。

服务端不得把本地 pending/running/completed 状态当成调度事实。live run 状态以 runtime 当前响应为准；ended run 以 runtime final manifest / workspace archive 为准。

### Event journal 与 SSE

第一版事件流使用 SSE，不使用 WebSocket 作为移动端主事件协议。

要求：

- 每条前端事件有单调 cursor。
- `GET /api/runs/:runId/events?cursor=...` 返回分页历史。
- `GET /api/runs/:runId/stream?cursor=...` 从 cursor 后 replay，再继续推送 live events。
- 客户端重连后不丢事件，不重复应用已确认事件。
- 服务端断开连接时清理订阅状态。
- 代理层关闭响应缓冲，确保事件逐条到达。

桌面本地 Agent transcript 已有 WebSocket bridge，这是 desktop runtime 的既有实现；它不改变移动端第一版 SSE-first 的服务端设计。

## API / DTO 草案

所有正式 HTTP API 使用 `/api` 前缀。成功响应统一包含 `ok: true`，失败响应统一包含稳定错误码和 request id。

成功响应示例：

```json
{
  "ok": true,
  "project": {
    "id": "proj_123",
    "name": "multi_agent_tcp"
  }
}
```

失败响应示例：

```json
{
  "ok": false,
  "code": "RUNTIME_UNAVAILABLE",
  "message": "Python runtime is not reachable",
  "requestId": "req_abc123"
}
```

### 第一版只读与索引 API

| Method | Path | 说明 |
| --- | --- | --- |
| `GET` | `/api/health` | 服务端健康检查，不泄漏 runtime secret |
| `POST` | `/api/auth/login` | 登录并设置 `httponly` cookie |
| `POST` | `/api/auth/logout` | 注销当前 session |
| `GET` | `/api/me` | 当前用户、设备和权限摘要 |
| `GET` | `/api/projects` | 当前用户可访问项目 |
| `GET` | `/api/projects/:projectId/runs` | 项目 run 列表 |
| `GET` | `/api/runs/:runId` | run metadata 和 safe summary |
| `GET` | `/api/runs/:runId/status` | runtime status 投影 |
| `GET` | `/api/runs/:runId/events?cursor=...` | runtime event journal 分页 |
| `GET` | `/api/runs/:runId/stream?cursor=...` | SSE 事件流 |
| `GET` | `/api/runs/:runId/agents/:nodeId` | Agent panel snapshot |
| `GET` | `/api/runs/:runId/diff` | run-scoped diff summary |
| `GET` | `/api/runs/:runId/changesets/:changesetId/diff` | changeset diff detail |
| `GET` | `/api/runs/:runId/reports` | report 索引 |
| `GET` | `/api/runs/:runId/artifacts` | artifact 索引 |

### 第二阶段 capability-gated 写操作

| Method | Path | 说明 | Gate |
| --- | --- | --- | --- |
| `POST` | `/api/runs` | 创建 run，转发 start plan 到 runtime | `run:create` |
| `POST` | `/api/runs/:runId/messages` | 向 Top Agent 或指定 AgentNode 发送用户消息 | `run:message` |
| `POST` | `/api/runs/:runId/end` | complete / cancel / fail / pause | `run:end` |
| `POST` | `/api/runs/:runId/approvals` | 记录审批、拒绝或人工确认 | `run:approve` |

写操作处理顺序固定为：

1. 校验 session。
2. 校验项目/run 权限。
3. 校验 capability gate。
4. 写入用户意图或审批原文。
5. 调用 runtime bridge。
6. 持久化 runtime 响应或错误摘要。
7. 写审计日志。

如果 runtime 调用失败，不得先返回本地模拟成功状态。

### DTO 投影

DTO 只定义服务端投影，不复用 `mobile-state.ts` 中的 mock 类型名作为后端合同。

`ProjectSummary`：

```ts
type ProjectSummary = {
  id: string
  name: string
  role: "owner" | "operator" | "viewer"
  latestRun?: RunSummary
  capabilities: string[]
}
```

`RunSummary`：

```ts
type RunSummary = {
  id: string
  projectId: string
  blueprintId: string
  title: string
  status: "running" | "completed" | "cancelled" | "failed" | "paused" | "unknown"
  createdAt: string
  updatedAt: string
  endedAt?: string
  currentNodeIds: string[]
  unreadEventCount?: number
}
```

`RunStatusProjection`：

```ts
type RunStatusProjection = {
  run: RunSummary
  blueprint: BlueprintStructureProjection
  agents: AgentPanelSnapshot[]
  pending: {
    queuedMessages: number
    waitingOutgoingBatches: number
    waitingJoins: number
    runningJobs: number
  }
  outputs: {
    reports: ReportIndexItem[]
    artifacts: ArtifactIndexItem[]
    diff?: RunDiffSummary
  }
  lastCursor: string
}
```

`BlueprintStructureProjection`：

```ts
type BlueprintStructureProjection = {
  nodes: Array<{
    id: string
    label: string
    role?: string
    state: "idle" | "queued" | "running" | "completed" | "failed" | "unknown"
    upstreamNodeIds: string[]
    downstreamNodeIds: string[]
  }>
  edges: Array<{
    source: string
    target: string
    kind: "exec" | "data" | "unknown"
  }>
}
```

`AgentPanelSnapshot`：

```ts
type AgentPanelSnapshot = {
  nodeId: string
  agentId: string
  cliKind?: string
  state: string
  taskStatus?: string
  queueSize: number
  messagesSent: number
  busyCount: number
  updatedAt?: string
  recentEvents: RuntimeEvent[]
}
```

`RuntimeEvent`：

```ts
type RuntimeEvent = {
  cursor: string
  runId: string
  type:
    | "runtime.status"
    | "agent.status"
    | "agent.utterance"
    | "agent.tool"
    | "workspace.report"
    | "workspace.artifact"
    | "workspace.changeset"
    | "workspace.conflict"
    | "run.completed"
    | "run.failed"
  occurredAt: string
  nodeId?: string
  agentId?: string
  payload: Record<string, unknown>
}
```

`RunDiffSummary`：

```ts
type RunDiffSummary = {
  total: number
  accepted: number
  conflict: number
  rejected: number
  pending: number
  files: number
  additions: number
  deletions: number
  changesets: Array<{
    id: string
    status: string
    summary: string
    files: string[]
  }>
}
```

`ReportIndexItem` / `ArtifactIndexItem`：

```ts
type ReportIndexItem = {
  id: string
  title: string
  path: string
  mediaType: string
  createdAt?: string
  ownerNodeId?: string
}

type ArtifactIndexItem = {
  id: string
  title: string
  path: string
  mediaType: string
  bytes?: number
  createdAt?: string
  ownerNodeId?: string
}
```

## Runtime / Desktop Bridge 集成

Collaboration Server 的 bridge 层只做安全调用与投影。

### 读取映射

| Collaboration API | Runtime / Desktop source |
| --- | --- |
| project run list | `blueprint.listRuns` + server project binding |
| run detail | server run index + `blueprint.status` |
| run status | `GraphRuntime.status_snapshot(graph=...)` |
| status explanation | `GraphRuntime.explain_status(graph=...)` |
| event page | `blueprint.recentEvents` / runtime event journal mirror |
| Agent sheet | `blueprint.agentInfo` |
| run diff | `blueprint.runDiff` |
| changeset diff | `blueprint.changesetDiff` |
| reports/artifacts | runtime workspace projection / archive index |

### 写入映射

| Collaboration API | Runtime / Desktop source | 约束 |
| --- | --- | --- |
| create run | `blueprint.start` / `run.start` | start plan 必须完整，服务端不补计划 |
| send message | `blueprint.queueAgentMessage` | 必须 live run + capability gate |
| end run | `blueprint.end` / `run.end` | 不重复结束 terminal run |
| approval | server audit + optional runtime control | 第一版只存盘，是否触发 runtime 后置 |

### 禁止 bridge 做的事

- 自行判断 AgentNode 是否应该入队。
- 自行补齐 outgoing batch。
- 自行判定 fan-in join 是否满足。
- 自行标记 Agent 任务完成。
- 自行合并 workspace changeset。
- 自行修改 project code root。
- 从事件流推导并推进下一步图执行。

这些语义属于 `GraphRuntime`、workspace manager、MCP 工具和 control plane。

## 技术调整

### 服务端技术栈

第一版固定使用仓库已有 Python 依赖：

- `Starlette`：HTTP app、middleware、routing、SSE `StreamingResponse`。
- `uvicorn`：本地或远程服务启动。
- `httpx`：服务端到 runtime / desktop bridge 的 HTTP client。
- `sqlite3`：第一版持久化，不新增数据库依赖。

不引入：

- FastAPI
- Express / Next.js 服务端
- 新的 Vue / React / Flutter 移动端工程
- 自定义加密协议
- 服务端自建多 Agent 调度器

### sqlite3 持久化

第一版 schema 至少覆盖：

- `users`
- `sessions`
- `projects`
- `project_members`
- `runtime_bindings`
- `runs`
- `messages`
- `runtime_events`
- `report_indexes`
- `artifact_indexes`
- `changeset_indexes`
- `audit_logs`
- `login_attempts`

写入要求：

- 所有 run control、message send、approval、runtime proxy 请求都写 audit。
- event journal append-only。
- token / secret 不进普通查询 payload。
- 对外 id 使用 opaque id，不暴露本地路径推导信息。

### SSE 实现要求

使用 Starlette `StreamingResponse` 输出标准 SSE：

```text
id: 42
event: runtime.status
data: {"runId":"run_1","status":"running"}
```

实现规则：

- `id` 使用服务端 event cursor。
- 支持 `cursor` query 参数。
- 支持 heartbeat 注释行，避免代理 idle timeout。
- 断线后客户端按最后确认 cursor 重连。
- runtime unavailable 时发送明确错误事件并关闭流，或让 HTTP 请求返回稳定错误。
- Caddy / Nginx 反代必须关闭 SSE 响应缓冲。

### PWA / Mobile 调整

移动端接入顺序：

1. 新增 Collaboration Server client。
2. `/mobile` 启动时先读 `/api/me` 和 `/api/projects`。
3. 将 `mobileMockData.messages` 替换为 server message/run projection。
4. 将蓝图结构、运行状态、Agent sheet、Diff 摘要分别替换为对应 API。
5. 接入 SSE cursor 重连。
6. 最后再打开消息发送、run control 或 approval gate。

保持不变：

- `/auth/*`、`/api/*`、`/runs/*`、`/stream` 继续 `NetworkOnly`。
- PWA 只缓存 shell、图标、字体、CSS、JS。
- 移动端不得直连 Python Runtime、Workspace RPC、MCP bearer endpoint 或 desktop local token。

## 分阶段开发

### 阶段 1：只读移动协作闭环

必须完成：

- Starlette 服务入口。
- sqlite3 store 与迁移初始化。
- 登录、session、logout、`/api/me`。
- 项目列表和项目权限。
- run 列表、run detail、run status。
- runtime event journal 镜像。
- SSE stream + cursor replay。
- Agent panel snapshot。
- run diff / changeset diff summary。
- report / artifact index。
- 审计日志。
- payload secret scrubber。

不做：

- 移动端发消息。
- 移动端启动 run。
- 移动端结束 run。
- 移动端审批触发 runtime 行为。
- 多人实时编辑或 presence。

### 阶段 2：受控写操作

在阶段 1 稳定后开启：

- `POST /api/runs`
- `POST /api/runs/:runId/messages`
- `POST /api/runs/:runId/end`
- `POST /api/runs/:runId/approvals`

要求：

- 所有写操作 capability-gated。
- runtime unavailable 必须返回明确错误。
- 所有用户原文、runtime 响应和失败摘要写审计。
- 移动端 UI 必须能表达 disabled / readonly / permission denied 状态。

### 阶段 3：多人和托管化

后置能力：

- 多用户项目成员管理。
- 更完整的 run 历史搜索。
- artifact 浏览和下载策略。
- runtime gateway 高可用。
- 告警和审计查询。
- WebSocket 双向协作，仅当需要多人编辑、presence 或低延迟双向输入时引入。

## 测试计划

### 文档更新验证

- 用 UTF-8 读取本文，确认中文无乱码。
- 用 `rg` 检查旧的 mock-contract、博客中心、WebSocket-first、移动端直连 runtime 等表述已清理。
- 确认本文不把 `mobile-state.ts` 的 mock 类型当作后端合同。

### 后续服务端测试

Auth / permission：

- 未登录访问 `/api/projects` 返回 401。
- 无项目权限访问 run 返回 403。
- 登录失败触发 IP 短窗口限速。
- 正确密码在错误尝试限速策略下仍有明确处理路径。

Runtime bridge：

- `POST /api/runs` 在 runtime unavailable 时失败并写审计。
- run status 来自 runtime bridge，不使用服务端本地猜测。
- terminal run 重复 end 不重复调用 runtime。
- mock `GraphRuntimeControlPlane` 验证服务端只转发请求，不私自推进状态。

SSE / events：

- cursor replay 不丢事件。
- cursor replay 不重复应用已确认事件。
- 长连接断开后清理订阅状态。
- 代理关闭缓冲后事件逐条到达。

Secret boundary：

- payload 不包含 runtime token。
- payload 不包含 workspace RPC token。
- payload 不包含 MCP bearer token。
- payload 不包含 private checkout path。
- payload 不包含 Codex home。
- payload 不包含 service token。

Reports / artifacts / diff：

- diff 只暴露授权 changeset 索引和 detail。
- rejected/conflict changeset 不进入 accepted diff 渲染输入。
- report/artifact 缺失返回稳定 404。
- artifact path 不能路径穿越。

PWA：

- `/auth/*`、`/api/*`、`/runs/*`、`/stream` 不被 service worker 缓存。
- 离线时只展示 shell 或明确离线状态，不展示过期 runtime status。
- 背景恢复后用 cursor 重连 SSE。

## 不做事项与边界

第一版明确不做：

- 不把 mock data shape 当后端 API。
- 不让移动端直连 Python Runtime。
- 不让移动端访问 workspace RPC、MCP bearer endpoint 或 desktop local service token。
- 不在服务端直接写项目目录。
- 不在服务端复制 `GraphRuntime` 调度语义。
- 不在服务端合并 changeset。
- 不把 shared workspace 描述成源码集成区；它是 reports、artifacts、manifest、changeset 引用、冲突记录和日志的协作记录区。
- 不用 WebSocket 替代第一版 SSE 事件流。
- 不自定义加密协议替代 TLS。
- 不新增第二套移动端框架。

命名上始终区分：

- GuLiCode Collaboration Server：账号、权限、存盘、审计、移动 API、事件转发。
- DesktopBlueprintService / Python Runtime：本地 runtime bridge 和 control-plane 实现。
- `GraphRuntimeControlPlane` / `GraphRuntime`：调度事实源。
- `CLIWorkerBackend`：Codex、Codex 或其他 CLI worker 的执行适配层。

## 参考输入

- `archive/frontend/mock/README.md`
- `archive/frontend/mock/gulicode_mobile_top_tabs_mock_2026-05-28.md`
- `archive/frontend/mock/gulicode_mobile_blueprint_structure_map_2026-05-28.md`
- `archive/frontend/mock/gulicode_mobile_agent_info_sheet_mock_2026-05-28.md`
- `GuLiCode/packages/app/src/mobile/mobile-state.ts`
- `GuLiCode/packages/app/src/mobile/mock-data.ts`
- `GuLiCode/packages/app/src/entry.tsx`
- `GuLiCode/packages/app/vite.config.ts`
- `desktop_blueprint_service.py`
- `graph_control.py`
- `graph_runtime.py`
- `docs/workspace_api.md`
- `KM_docs/skills-snapshot/knowledge_base/core_architecture.md`
- `KM_docs/skills-snapshot/knowledge_base/dispatch_workflows.md`
- `KM_docs/skills-snapshot/archive/runtime-backend/blueprint_api_bridge_2026-05-16.md`
- `KM_docs/skills-snapshot/archive/runtime-backend/blueprint_runtime_middle_layer_2026-05-16.md`
- `KM_docs/skills-snapshot/archive/runtime-backend/blueprint_run_mcp_runtime_2026-05-19.md`
