# 蓝图 Diff 开发技术设计

## 目标

本文只定义 **蓝图运行时 Diff** 的开发边界：在蓝图运行过程中，多个 Agent 通过 MCP `workspace_submit` 提交出来的变更，需要被收集成一个 run-scoped diff 集合，并在蓝图界面提供一个展示区域承接这个集合。

核心结论：

- GuLiCode 原有右侧全局 `更改` / Review 体系完整保留，不重写、不替代、不改变默认交互。
- 新增能力是：蓝图运行时产生并被 accepted 的 diff，也会纳入原有全局 diff 体系。
- 蓝图 Diff 展示区域只面向当前单次 blueprint run。
- 蓝图 Diff 不读取 Agent private checkout，不展示 Agent 尚未通过 MCP `workspace_submit` 的私有修改。
- 蓝图 Diff 的事实源是 MCP `workspace_submit` 后形成的 changeset/archive。
- 不把多 Agent 同路径 diff 压平成无来源文件列表；必须保留 Agent / task / changeset provenance。

本文是工程设计稿，只定义接口、数据流和 UI 边界，不实现 API 或 UI。

## 术语定义

- `蓝图 Diff`: 当前单次 blueprint run 内，由 Agent 通过 MCP `workspace_submit` 形成的 changeset 集合。
- `accepted`: runtime/workspace 已发出 `ChangesetAccepted`，且该 changeset 已由 runtime/workspace 应用到 run integration 或全局 diff 事实源；不是前端本地标记。
- `acceptedDiffs`: 从 run base 到当前 run integration 的净 diff，不是把多个 changeset patch 简单拼接。
- `全局 Diff`: GuLiCode 右侧原有 `更改` / Review 数据源。蓝图只在 accepted 后追加输入或触发刷新，不改全局 Review UI。

## 范围收窄

### 本次要做

- 为蓝图运行时增加一个 run-scoped `蓝图 Diff` 展示区域。
- 收集当前 run 内 Agent 通过 MCP `workspace_submit` 提交出的 changeset。
- 按 Agent / task / changeset 展示文件、状态、增删行和来源颜色。
- 支持查看单 changeset diff 和本次 run 的 accepted 净 diff。
- 当 changeset accepted 后，同步触发原有全局 diff 区刷新，让蓝图变更也出现在右侧全局 `更改` 中。

### 不做

- 不重写右侧全局 diff 面板。
- 不改变全局 diff 的 Git / snapshot / Review UI 体系。
- 不读取 Agent private checkout 来做 UI 展示。
- 不接入 Codex turn diff / fileChange 作为蓝图 Diff 的事实源。
- 不把蓝图 Diff 作为最终项目级 review 入口；最终入口仍是原有全局 `更改`。

## 两个 Diff 区域

### 蓝图 Diff 区

位置：蓝图工具栏第二行，`添加节点` / `蓝图通用配置` 之后，右侧运行时按钮之前。

建议形态：

```text
[添加节点] [蓝图通用配置] [蓝图 Diff v]                         [刷新] [运行时] [3 条边] [适配] [重置视图] [重置]
```

职责：

- 展示当前 active blueprint run 的 Agent changeset 集合。
- 按 Agent / task / changeset 分组。
- 用不同颜色标识不同 Agent。
- 显示 submitted / pending / accepted / conflict / rejected / failed 状态。
- 提供单 changeset diff 详情入口。
- 展示本次 run accepted diff 的聚合摘要。

边界：

- 只显示当前 run。
- 只显示 MCP `workspace_submit` 后的 changeset。
- 不显示全局历史变更。
- 不显示 private checkout 未提交变更。

### 全局 Diff 区

位置：右侧原有 `更改` / Review 区。

保留原则：

- 保留现有 `SessionSidePanel`、`SessionReviewTab`、`utils/diffs.ts`、`@opencode-ai/ui/session-review` 等全局展示链路。
- Git 项目仍按现有 Git/VCS diff 逻辑工作。
- 无 Git 项目仍按现有 session snapshot diff / 文本 diff 逻辑工作。
- 蓝图开发只增加一个入口：当蓝图 changeset accepted 后，由 runtime/workspace 将该 changeset 应用到全局 diff 事实源，并通知全局 diff 体系刷新。

同步语义：

- `submitted/pending`：只更新蓝图 Diff 区。
- `accepted`：蓝图 Diff 区更新，同时全局 Diff 区刷新。
- `conflict/rejected/failed`：只更新蓝图 Diff 区，不进入全局 accepted diff。

## 数据事实源

### Runtime / Workspace

当前事实链路：

```text
Agent edits private checkout
  -> Agent calls MCP workspace_submit
  -> WorkspaceManager.submit_checkout()
  -> FileChange[]
  -> ChangesetSubmitted / ChangesetAccepted / ConflictDetected
  -> changesets/<changeset_id>/changeset.json
  -> changesets/<changeset_id>/patch.diff
  -> changesets/<changeset_id>/submit_result.json
```

蓝图 Diff 只从 `submit_checkout()` 之后的 changeset/archive 取数。

关键对象：

- `FileChange`: 文件路径、状态、增删行、hash、patch。
- `ChangesetSubmitResult`: changeset id、状态、文件列表、冲突、archive path。
- `ChangesetSubmitted`: changeset 已提交，可进入蓝图 Diff 区。
- `ChangesetAccepted`: changeset 已由 runtime/workspace 应用到 run integration 或全局 diff 事实源，需要同时刷新蓝图 Diff 区和全局 Diff 区。
- `ConflictDetected`: 只进入蓝图 Diff 的冲突列表。

### 前端 Diff Item

正式 diff 渲染继续使用既有兼容形状：

```ts
type ReviewDiff = {
  file: string
  patch: string
  additions: number
  deletions: number
  status?: "added" | "deleted" | "modified"
}
```

转换规则：

| `FileChange` | `ReviewDiff` |
| --- | --- |
| `path` | `file` |
| `patch` | `patch` |
| `additions` | `additions` |
| `deletions` | `deletions` |
| `status` | `status` |

Agent / task / changeset 元数据放在外层，不污染 `ReviewDiff`。

## 蓝图 Diff 数据模型

### Changeset Summary

```ts
type BlueprintChangesetSummary = {
  changesetId: string
  runId: string
  agentId: string
  nodeId?: string
  taskId?: string
  status: "submitted" | "pending" | "accepted" | "conflict" | "rejected" | "failed"
  files: Array<{
    file: string
    status?: "added" | "deleted" | "modified"
    additions?: number
    deletions?: number
    binary?: boolean
  }>
  totals: {
    files: number
    additions: number
    deletions: number
  }
  summary?: string
  archivePath?: string
  createdAt?: string
}
```

### Changeset Detail

```ts
type BlueprintChangesetDetail = BlueprintChangesetSummary & {
  diffs: ReviewDiff[]
  conflicts?: BlueprintConflict[]
}
```

### Run Diff

```ts
type BlueprintRunDiff = {
  runId: string
  revision: number
  totals: {
    files: number
    additions: number
    deletions: number
    submitted: number
    pending: number
    accepted: number
    conflicts: number
    rejected: number
  }
  changesets: BlueprintChangesetSummary[]
  acceptedDiffs: ReviewDiff[]
}
```

语义：

- `changesets` 保留所有当前 run 内 MCP `workspace_submit` 后的 changeset。
- `acceptedDiffs` 只包含当前 run 已 accepted 的净 diff，口径是 run base 到当前 run integration。
- 同一路径在 `acceptedDiffs` 中只出现一次。
- 同一路径在不同 `changeset detail` 中可以重复，因为来源不同。

## 事件与查询

### `workspace.diff.changed`

用于通知前端某个 run 的 changeset 状态变化。

```json
{
  "type": "workspace.diff.changed",
  "properties": {
    "runId": "run-123",
    "revision": 17,
    "changesetId": "cs-abc",
    "agentId": "test-agent-2",
    "nodeId": "agent-test-agent-2",
    "taskId": "task-12",
    "status": "accepted",
    "files": [
      {"file": "tests/runtime.test.ts", "status": "added", "additions": 31, "deletions": 0}
    ],
    "totals": {"files": 1, "additions": 31, "deletions": 0}
  }
}
```

处理规则：

- `submitted/pending`：invalidate 蓝图 run changeset query。
- `accepted`：invalidate 蓝图 run changeset query，同时 invalidate 全局 diff query。
- `conflict/rejected/failed`：invalidate 蓝图 run changeset query，不刷新全局 accepted diff。

事件不传完整 patch。

### 查询

```http
GET /runs/:runId/diffs?mode=blueprint-run
GET /runs/:runId/diffs?changesetId=cs-abc
GET /runs/:runId/diffs?agentId=test-agent-1
```

可选控制接口：

```http
POST /runs/:runId/changesets/:changesetId/accept
POST /runs/:runId/changesets/:changesetId/reject
```

如果当前 runtime 仍是 submit 后自动 accept，第一版不显示 `采纳` / `回退` 按钮。只有 `status=pending` 且后端已提供 accept/reject 控制入口时，蓝图 Diff 区才显示这些操作。

## 前端状态

推荐 query key：

```text
blueprint scoped:
  ["blueprint-run-diffs", runId]
  ["blueprint-run-changesets", runId]
  ["blueprint-run-changeset-diff", runId, changesetId]

global scoped:
  existing global diff query keys remain unchanged
```

刷新规则：

```text
workspace.diff.changed(runId, status)
  -> invalidate ["blueprint-run-diffs", runId]
  -> invalidate ["blueprint-run-changesets", runId]
  -> if selected changeset matches:
       invalidate ["blueprint-run-changeset-diff", runId, changesetId]
  -> if status == accepted:
       invalidate existing global diff query
```

本地 UI 状态只保存：

- Popover open/closed。
- 当前展开的 Agent / changeset。
- 当前 selected file。

不要把完整 patch 同时复制进蓝图 store 和全局 store。

## UI 展示

### 按钮

按钮文案：

```text
蓝图 Diff
蓝图 Diff 3
待采纳 1
冲突 1
```

状态：

- 无 active run：禁用或显示空态。
- active run 无 MCP `workspace_submit`：显示 `本次蓝图暂无提交变更`。
- 有 pending：显示 `待采纳 N`。
- 有 accepted：显示文件数或 changeset 数。
- 有 conflict/rejected/failed：显示 warning/error tone。

### 浮层

```text
本次蓝图 Diff                         run-xxx / revision 17
Agents 3 | Changesets 4 | 文件 8 | 待采纳 1 | 冲突 1

Agent test-agent-1       蓝色
  task: 修改配置加载
  cs-a1   accepted       2 files   +20 -3   [查看]

Agent test-agent-2       紫色
  task: 补测试
  cs-b7   pending        1 file    +31 -0   [查看] [采纳] [回退]

Agent test-agent-3       绿色
  task: 调整文档
  cs-c2   conflict       1 file    +20 -5   [查看冲突]
```

`采纳` / `回退` 只在 `status=pending` 且后端已提供 accept/reject 控制入口时显示；自动 accept 模式下 pending 行只显示查看入口。

Agent 颜色：

```ts
const AGENT_COLORS = ["#38bdf8", "#a78bfa", "#34d399", "#f59e0b", "#f472b6", "#22d3ee"]
function agentColor(agentId: string) {
  return AGENT_COLORS[stableHash(agentId) % AGENT_COLORS.length]
}
```

颜色只做辅助，必须同时显示 Agent / node / task 文本。

## 全局 Diff 接入

全局 diff 体系保持原样，只增加蓝图 accepted diff 的输入；不改全局 Review UI。

接入规则：

- Git 项目：accepted changeset 由 runtime/workspace 按现有写入路径应用到全局 diff 所读取的工作区，原有 Git diff 自然显示蓝图变更。
- 无 Git 项目：accepted changeset 写入 project/global scoped changeset archive 或全局 diff index，作为现有文本 diff 来源之一。
- 删除会话不应删除已进入全局源的蓝图 accepted changeset。
- 未 submit、pending、conflict、rejected、failed 的 changeset 不进入全局 diff。

这意味着蓝图 Diff 开发只需要在 accepted 事件处触发全局 diff 刷新，或在无 Git 模式写入全局 diff index；不改全局 Review 组件。

## 错误处理

- `RUN_NOT_FOUND`: run 不存在或已清理。
- `CHANGESET_NOT_FOUND`: changeset id 不存在。
- `DIFF_NOT_AVAILABLE`: `patch.diff` 缺失或归档不完整。
- `DIFF_TOO_LARGE`: 需要按文件或确认后加载。
- `BINARY_DIFF_UNSUPPORTED`: 二进制不能文本渲染。
- `ARCHIVE_UNAVAILABLE`: run archive 不可读。
- `CHANGESET_NOT_PENDING`: changeset 已 accepted/rejected，不能再次采纳或回退。
- `GLOBAL_DIFF_UPDATE_FAILED`: accepted changeset 同步到全局 diff 源失败。

不要在 patch 缺失时返回空 diff。空 diff 表示确实没有变更，读取失败必须返回错误。

## 测试计划

### 蓝图 Diff

- active run 无 MCP `workspace_submit` 时，按钮显示空态。
- Agent private checkout 有修改但未 submit 时，蓝图 Diff 数量仍为 0。
- `workspace.diff.changed(submitted)` 到达后，蓝图列表出现 changeset。
- `workspace.diff.changed(accepted)` 到达后，本次 run accepted diff 更新。
- conflict/rejected/failed 只出现在蓝图列表，不进入 accepted 净 diff。
- 同一路径被多个 Agent 修改时，changeset detail 保留各自来源。

### 全局 Diff 接入

- accepted changeset 到达后，全局 diff 查询被刷新。
- Git 项目中，accepted changeset 进入工作区后，右侧全局 diff 能通过原有 Git diff 看到。
- 无 Git 项目中，accepted changeset 写入全局 diff index 后，右侧全局 diff 能通过文本 diff 看到。
- pending/conflict/rejected/failed 不进入全局 diff。
- 删除会话后，已进入全局源的蓝图 accepted changeset 仍可见。

### UI

- `蓝图 Diff` 按钮展开、收起、Esc 和外部点击关闭。
- Popover 不推动 canvas、runtime panel、右侧全局 diff 区。
- Agent 颜色稳定，刷新后同一 Agent 颜色不变。
- 大 patch 默认只显示摘要，详情懒加载。
- 二进制文件显示 metadata，不进入文本 diff renderer。

## 推荐落点

- `desktop_blueprint_service.py`: 投影 run-scoped changeset 事件，并在 accepted 时触发全局 diff 刷新或写入全局 diff index。
- `workspace_manager.py`: 提供 changeset detail 读取 helper，避免前端理解 archive 目录结构。
- `GraphRuntimeControlPlane`: 如果需要手动采纳/回退，暴露 changeset accept/reject 控制入口。
- `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.tsx`: 增加 run-scoped `蓝图 Diff` 按钮和 Popover 浮层。
- `GuLiCode/packages/app/src/pages/session/review-tab.tsx`: 继续复用，不把多 Agent 元数据塞入 diff item。

推荐实现顺序：

1. run-scoped changeset query 和蓝图工具栏展示区域。
2. 单 changeset detail 和本次 run accepted 净 diff。
3. accepted changeset 接入原有全局 diff 刷新。
4. pending review gate 和真实采纳/回退。
