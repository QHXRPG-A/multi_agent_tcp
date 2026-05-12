# GuLiCode Blueprint Workbench 技术设计

## 目标

本文描述如何将当前 `multi_agent_tcp` 蓝图能力接入 GuLiCode 桌面 app，成为项目级 Blueprint Workbench 模块。

核心结论：

- GuLiCode 主应用继续使用现有 `SolidJS + Vite + Electron` 技术栈。
- 蓝图 UI 进入 `GuLiCode/packages/app`，作为项目级模块，而不是写死在 Electron renderer 中。
- 运行时调度继续由 Python `GraphRuntimeControlPlane` / `GraphRuntime` 承担。
- 未来多用户服务端只负责用户、权限、消息存盘、消息转发、运行记录索引和协作同步，不复制 Python runtime 的调度语义。
- 已废弃的 Start / End 终端节点机制不再作为 GuLiCode 蓝图模块的核心设计。

## 术语边界

后续开发中应避免笼统使用“后端”一词。建议拆成以下三层：

| 名称 | 技术栈 | 职责 | 不负责 |
| --- | --- | --- | --- |
| GuLiCode Desktop App | Electron + SolidJS + Vite | 桌面壳、项目导航、Blueprint Workbench UI、本地能力桥接 | 不直接执行 Python，不持有调度真相 |
| Python Runtime | Python | `GraphRuntimeControlPlane`、`GraphRuntime`、AgentNode 队列、outgoing batch、join、workspace、events | 不负责多用户账号、远程消息存盘、协作广播 |
| GuLiCode Collaboration Server | 待定，长期服务端 | 用户、项目、权限、消息存盘、消息转发、订阅广播、run/event 索引 | 不重新实现 GraphRuntime 调度 |
| Worker Backend | Python adapter / CLI / TCP | 具体执行 Agent 任务，例如 Codex、CodeMaker、CLI worker | 不等同于产品服务端，也不拥有蓝图调度语义 |

## 当前基础

GuLiCode 桌面端分层已经适合接入蓝图模块：

```text
GuLiCode/packages/desktop-electron
  -> Electron main / preload / renderer shell
  -> 注入 Platform、sidecar server、MemoryRouter
  -> 渲染 packages/app 的 AppInterface

GuLiCode/packages/app
  -> SolidJS 应用层
  -> 路由、项目 layout、session 页面、provider、query、同步状态

multi_agent_tcp
  -> GraphRuntimeControlPlane
  -> GraphRuntime
  -> workspace/events/AgentNode/CLIWorkerBackend
```

因此蓝图工作台应主要落在：

```text
GuLiCode/packages/app/src/pages/blueprint.tsx
GuLiCode/packages/app/src/context/blueprint.tsx
GuLiCode/packages/app/src/components/blueprint/
GuLiCode/packages/desktop-electron/src/main/blueprint-runtime.ts
GuLiCode/packages/desktop-electron/src/preload/types.ts
GuLiCode/packages/desktop-electron/src/preload/index.ts
GuLiCode/packages/desktop-electron/src/main/ipc.ts
```

Python 侧应补一个面向桌面 app 的服务外壳：

```text
multi_agent_tcp/desktop_blueprint_service.py
```

该服务外壳负责把项目目录、蓝图文件、runtime 实例、run 状态和事件查询整理成桌面 app 可消费的 API。

## 源码入口定位

接入前先看 GuLiCode 当前源码结构，蓝图入口不应凭空加在 Electron renderer 或单独窗口中，而应贴合现有项目级导航。

### 1. 页面路由入口

主路由定义在：

```text
GuLiCode/packages/app/src/app.tsx
```

当前结构：

```tsx
<Route path="/" component={HomeRoute} />
<Route path="/:dir" component={DirectoryLayout}>
  <Route path="/" component={SessionIndexRoute} />
  <Route path="/session/:id?" component={SessionRoute} />
</Route>
```

蓝图页面应作为 `/:dir` 的子路由加入：

```tsx
const BlueprintRoute = lazy(() => import("@/pages/blueprint"))

<Route path="/:dir" component={DirectoryLayout}>
  <Route path="/" component={SessionIndexRoute} />
  <Route path="/session/:id?" component={SessionRoute} />
  <Route path="/blueprint/:blueprintId?/:runId?" component={BlueprintRoute} />
</Route>
```

原因：

- `DirectoryLayout` 会解析 `params.dir`。
- `DirectoryLayout` 内部提供 `SDKProvider`、`SyncProvider`、`DirectoryDataProvider`、`LocalProvider`。
- 蓝图模块需要当前项目目录、项目同步数据、SDK client 和本地项目上下文。

不要把蓝图页面挂到根路由 `/blueprint`，否则会失去当前项目目录语义。

### 2. 侧栏可见入口

项目侧栏主体在：

```text
GuLiCode/packages/app/src/pages/layout.tsx
```

真实入口区域是 `SidebarPanel`。当前在项目展开后，非 workspace 模式会先显示一个 `New session` 按钮，然后显示 `LocalWorkspace`：

```tsx
<Button
  size="large"
  icon="new-session"
  class="w-full"
  onClick={() => navigateWithSidebarReset(`/${base64Encode(dir)}/session`)}
>
  {language.t("command.session.new")}
</Button>

<LocalWorkspace ... />
```

蓝图入口建议放在同一区域，作为项目级工具按钮，与 `New session` 同级：

```tsx
<div class="shrink-0 py-4 flex flex-col gap-2">
  <Button
    size="large"
    icon="new-session"
    class="w-full"
    onClick={() => navigateWithSidebarReset(`/${base64Encode(dir)}/session`)}
  >
    {language.t("command.session.new")}
  </Button>

  <Button
    size="large"
    icon="task"
    variant="ghost"
    class="w-full"
    onClick={() => navigateWithSidebarReset(`/${base64Encode(dir)}/blueprint`)}
  >
    {language.t("command.blueprint.open")}
  </Button>
</div>
```

如果 workspace 功能开启，`SortableWorkspace` 会按 worktree 展示多个目录。此时蓝图入口应跟随具体 workspace directory，而不是只跟 root project：

```text
workspace directory -> /<base64Encode(directory)>/blueprint
```

这能保证蓝图运行目标是当前 workspace，而不是误跑到 root project。

### 3. 项目 rail 不是第一入口

左侧窄 rail 在：

```text
GuLiCode/packages/app/src/pages/layout/sidebar-shell.tsx
```

这里目前只承载：

- 项目 tile 列表
- 打开项目按钮
- settings
- help

不建议第一阶段把蓝图放进 rail。rail 是全局项目切换区，不是项目内功能区。蓝图属于当前项目或当前 workspace，应放在展开面板中。

### 4. 命令面板入口

GuLiCode 有统一命令系统：

```text
GuLiCode/packages/app/src/context/command.tsx
GuLiCode/packages/app/src/pages/layout.tsx
```

`layout.tsx` 已通过 `command.register("layout", ...)` 注册全局 layout 命令。蓝图应补一个命令入口：

```ts
{
  id: "blueprint.open",
  title: language.t("command.blueprint.open"),
  category: language.t("command.category.navigation"),
  onSelect: () => {
    const dir = currentDir()
    if (!dir) return
    navigateWithSidebarReset(`/${base64Encode(dir)}/blueprint`)
  },
}
```

这样用户可以通过 command palette 打开 Blueprint Workbench，也方便后续绑定快捷键。

### 5. 需要新增的 i18n key

至少补：

```text
command.blueprint.open = Open blueprint
blueprint.title = Blueprint
blueprint.empty.title = No blueprints
blueprint.empty.description = Create or open a blueprint for this project.
```

多语言文件很多，第一步可以先补 `en.ts`、`zh.ts`、`zht.ts`，或沿用项目现有新增文案策略。

### 6. 不建议放的位置

不要放在：

- `GuLiCode/packages/desktop-electron/src/renderer/index.tsx`：这里只是桌面 shell，负责注入 `Platform` 和渲染 `AppInterface`。
- `GuLiCode/packages/desktop-electron/src/main/index.ts`：这里负责应用生命周期和本地服务启动，不负责业务 UI 入口。
- 根路由 `/blueprint`：蓝图是项目级模块，需要 `/:dir` 上下文。
- 左侧窄 rail 第一层：rail 是项目切换，不是项目内工作台入口。

## 产品形态

Blueprint Workbench 是项目级工作台，不是替代 session 的新聊天页。

建议新增路由：

```text
/:dir/blueprint
/:dir/blueprint/:blueprintId
/:dir/blueprint/:blueprintId/run/:runId
```

第一阶段视图：

- 蓝图列表
- 蓝图详情
- 节点图画布
- 节点 inspector
- 运行控制栏
- runtime status 面板
- event timeline
- reports / artifacts / changesets 入口

侧栏入口应接入现有项目/工作区导航体系。蓝图模块属于当前项目，不应成为独立 Electron 窗口能力。

## 蓝图语义

GuLiCode 蓝图应表示“多 Agent 组织图 + run 控制台”，而不是 Start / End 工作流编辑器。

当前语义应收敛为：

```text
BlueprintGraph
  -> organization view
  -> top-agent selected start nodes
  -> TopAgentStartPlan
  -> runtime.start
  -> status/events
  -> runtime.end / archive
```

可继承现有 Python 蓝图编辑器的设计思想：

- 视觉节点包装运行时 `AgentNode` 配置。
- 节点配置保存为与 `AgentNode.to_dict()` / `AgentNode.from_dict()` 兼容的数据。
- 编辑器输出中间 IR，不直接操作 runtime 内部对象。
- `exec`、`condition`、`data` 等边要区分语义。
- UI 可以做即时校验和提示，但最终调度事实来自 Python runtime。
- runtime events 映射为画布节点状态覆盖。

不再继承：

- Start / End 终端节点。
- “必须存在从 Start 到 End 的 exec 路径”的可运行约束。
- Ryven / Qt 的 nodes package、FlowView hook、GUI widget 表单和项目文件格式。

## 前端实现

前端继续使用 SolidJS。

建议结构：

```text
packages/app/src/pages/blueprint.tsx
packages/app/src/context/blueprint.tsx
packages/app/src/components/blueprint/blueprint-canvas.tsx
packages/app/src/components/blueprint/blueprint-node.tsx
packages/app/src/components/blueprint/blueprint-edge-layer.tsx
packages/app/src/components/blueprint/blueprint-inspector.tsx
packages/app/src/components/blueprint/blueprint-run-panel.tsx
packages/app/src/components/blueprint/blueprint-event-timeline.tsx
packages/app/src/components/blueprint/blueprint-artifacts.tsx
```

第一版画布建议自研：

- HTML 渲染节点。
- SVG 渲染连线。
- `elkjs` 做自动布局。
- Solid store 管理选中节点、视口、编辑草稿、运行态覆盖。
- `@tanstack/solid-query` 拉取蓝图列表、蓝图详情、运行状态和事件。

暂不建议第一阶段引入 React Flow / Svelte Flow / Rete.js。它们功能成熟，但会引入第二 UI 栈或渲染岛，应该等 Workbench 的数据模型和运行闭环稳定后再评估。

## 桌面桥接

Electron renderer 当前处于 sandbox / context isolation 模式。蓝图本地能力必须通过 preload 暴露受控 API，不能让 renderer 直接执行 Python。

建议在 preload 暴露：

```ts
type BlueprintAPI = {
  list(projectDir: string): Promise<BlueprintSummary[]>
  open(projectDir: string, blueprintId: string): Promise<BlueprintDocument>
  save(projectDir: string, document: BlueprintDocument): Promise<BlueprintDocument>
  validate(projectDir: string, blueprintId: string): Promise<BlueprintValidationResult>
  start(projectDir: string, blueprintId: string, plan: TopAgentStartPlan): Promise<BlueprintRunStartResult>
  status(runId: string): Promise<BlueprintRunStatus>
  end(runId: string, action: "complete" | "cancel" | "fail" | "pause", reason?: string): Promise<BlueprintRunEndResult>
  recentEvents(runId: string, limit?: number): Promise<BlueprintEvent[]>
}
```

Electron main 负责：

- 启动或连接 Python desktop blueprint service。
- 选择本地端口。
- 保存并保护 runtime token。
- 校验 projectDir 是否来自 GuLiCode 已打开项目。
- 在 app 退出时关闭 Python 子进程。
- 将 Python service 错误转换成 renderer 可展示的错误对象。

renderer 只看到 `window.api.blueprint.*`，不看到 Python 命令、token、真实 RPC URL 或本地私有路径细节。

## Python Runtime 服务外壳

`desktop_blueprint_service.py` 应作为桌面 app 和 runtime control plane 之间的薄服务层。

建议职责：

- 管理 projectDir 到 blueprint catalog 的映射。
- 读取 / 保存蓝图 JSON。
- 将蓝图 JSON 转换为 `GraphDefinition`。
- 调用 `GraphRuntimeControlPlane.handle_request()`。
- 管理 runId 到 live runtime/control-plane 实例的映射。
- 暴露 list/open/save/validate/start/status/end/events。
- 统一错误格式。

第一阶段可以基于当前 `GraphRuntimeRPCServer` 的 JSON RPC 风格扩展。长期需要事件流时，再补 SSE 或 WebSocket。

关键原则：

- Python Runtime 是调度事实来源。
- UI 不复制 queue、batch、join、workspace 的推导逻辑。
- Collaboration Server 即使存在，也只持久化和转发 runtime 产生的事实。

## 数据存储

建议优先复用 `.multi_agent_workspace`：

```text
<project>/.multi_agent_workspace/
  blueprints/
    <blueprintId>.json
  runs/
    <runId>/
      run_manifest.json
      events.jsonl
      reports/
      artifacts/
      changesets/
```

蓝图文档建议拆成两部分：

```json
{
  "schema_version": 1,
  "id": "review-flow",
  "name": "Review Flow",
  "graph": {
    "agent_nodes": {},
    "route_nodes": {},
    "edges": []
  },
  "ui": {
    "nodes": {},
    "viewport": {}
  }
}
```

`graph` 是 runtime 可理解的语义层。`ui` 是 Workbench 私有视觉层，包括坐标、折叠状态、颜色、分组、视口等。

## 运行流程

本地桌面 MVP：

```text
User opens project
  -> GuLiCode loads Blueprint Workbench
  -> Workbench calls blueprint.list(projectDir)
  -> User opens blueprint
  -> Workbench calls blueprint.open(projectDir, id)
  -> User asks top agent / selects start nodes
  -> Workbench builds TopAgentStartPlan
  -> Workbench calls blueprint.start(projectDir, id, plan)
  -> Python Runtime schedules AgentNodes
  -> Workbench polls status/recentEvents
  -> UI overlays node status and event timeline
  -> User ends/archives run through runtime control plane
```

未来多用户版本：

```text
Client A / Client B
  -> GuLiCode Collaboration Server
  -> stores user messages and subscriptions
  -> forwards run control request to Python Runtime
  -> persists runtime events and run records
  -> broadcasts updates to clients
```

在多用户版本中，Collaboration Server 可以缓存和转发 runtime 状态，但不能把缓存当作调度真相。冲突时以 Python Runtime 的 control-plane 响应为准。

## 事件与状态

Workbench 需要把 runtime 信息映射成 UI 状态：

| Runtime 信息 | UI 表现 |
| --- | --- |
| queued message | 节点显示 queued |
| active job | 节点显示 running |
| completed contribution | 节点显示 completed |
| failed job/event | 节点显示 failed |
| open outgoing batch | 边或目标节点显示 waiting dispatch |
| pending join | join 相关节点显示 waiting |
| workspace conflict | 节点或 run panel 显示 conflict |
| artifact/report | 节点 inspector 提供入口 |

状态映射应集中在前端 `BlueprintContext` 或 `runtime-status-mapper.ts`，不要散落在画布组件里。

## 未来协作服务端

未来用户增加后，服务端要承担消息存盘与转发。建议命名为 GuLiCode Collaboration Server 或 GuLiCode Service，避免称为“后端”导致和 Python Runtime 混淆。

它可以存储：

- 用户消息。
- top-agent 指令。
- start plan。
- run metadata。
- event journal。
- agent utterance 摘要。
- artifact/report/changeset 索引。
- 蓝图编辑协作状态。
- 用户权限和项目成员关系。

它不应负责：

- 计算 AgentNode 是否进入队列。
- 判断 outgoing batch 是否完整。
- 判断 join 是否满足。
- 自行推进 GraphRuntime 状态。
- 直接修改 workspace changeset 事实。

服务端与 Python Runtime 的关系是控制面代理和事实持久化，不是调度替代。

## 实施阶段

### Phase 1: 本地只读 Workbench

- 新增 blueprint route。
- 新增 `BlueprintContext`。
- Electron preload 暴露 list/open/status/events。
- Python service 支持读取蓝图、返回 organization view。
- Solid 画布展示节点和连线。

### Phase 2: 本地运行闭环

- 支持 top-agent start plan。
- 支持 run start/status/end。
- 支持节点运行状态覆盖。
- 支持 event timeline。
- 支持 reports/artifacts 入口。

### Phase 3: 编辑能力

- 支持新增/删除 AgentNode。
- 支持编辑 AgentNode 配置。
- 支持连线编辑。
- 支持保存 blueprint JSON。
- 支持 Python runtime validate。
- 支持自动布局和基础 undo/redo。

### Phase 4: 协作服务端接入

- 服务端存盘用户消息和 run records。
- 服务端转发 runtime control request。
- 服务端广播 runtime events。
- 多客户端订阅同一 project/run。
- 权限、审计、运行历史索引。

## 风险

- 名词混乱：必须区分 Python Runtime、Collaboration Server 和 Worker Backend。
- 语义漂移：前端不要复制调度规则。
- 过早引入复杂图编辑器：会拖慢数据模型收敛。
- 本地进程生命周期：Electron main 必须可靠关闭 Python service。
- 多用户同步：服务端缓存状态不能覆盖 runtime 事实。
- 蓝图 schema 演进：需要 `schema_version` 和迁移策略。

## 推荐下一步

先做最小闭环：

1. 定义 `BlueprintDocument` JSON schema。
2. 新增 Python `desktop_blueprint_service.py`。
3. 新增 Electron `blueprint-runtime.ts` 和 preload API。
4. 新增 `/:dir/blueprint` 页面。
5. 展示一张现有复杂蓝图 fixture。
6. 接 `status_snapshot()` 做节点状态覆盖。

完成后再进入编辑器能力建设。
