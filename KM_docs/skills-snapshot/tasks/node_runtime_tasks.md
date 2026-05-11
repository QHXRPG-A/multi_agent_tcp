# 节点运行时与图编译方向任务

> 当前定位：本文件只记录 GraphRuntime / graph scheduling / AgentNode runtime 的任务。旧 Ryven `Start -> AgentNode -> End` 最小闭环是历史阶段，不是当前 GuLiCode 产品主线。当前优先级以 `current_goals.md` 和 `multi_agent_communication_tasks.md` 为准。

## 目标

把 GraphRuntime 运行时、节点队列、消息批次、fan-out/fan-in、workspace/events 和最终状态聚合打磨成 GuLiCode desktop 可依赖的执行底座。

## 近期任务

### 当前最高优先级：嵌套环 / 分支环递归处理

当前 `ring session` 只覆盖一个简单单向环的单轮执行。下一步最高优先级是把复杂环结构纳入运行时语义：

1. 自动识别嵌套环、共享节点环、分支环和重叠 SCC，区分可折叠子环与需要拒绝的歧义结构。
2. 将内层环折叠为外层视角中的环类 `Agent`，让外层只看到普通节点，不直接调度内层回路。
3. 定义父子 `ring session` 生命周期：父会话触发子会话、子审核官 final output 回填父会话、父会话继续单轮推进。
4. 定义跨层入口消息合并、动态可达节点继承、审核官幂等输出、超时、失败、取消和迟到消息处理。
5. 保持当前简单单环实现为 base case，不把多轮回流或无序反流混进本轮设计。

### 多 Agent 通信设计

当前节点运行时方向的首要任务拆解见 [`multi_agent_communication_tasks.md`](multi_agent_communication_tasks.md)。历史设计稿可参考 skill 根目录的 `多agents通信设计.md`，不要再使用旧 `F:\src\ryven_demo` 作为默认路径。

已完成第一阶段：

- 一对多 outgoing batch 暂存与完整批次入队；
- `remaining_targets` 补齐提醒；
- 从 `GraphDefinition` 自动生成 `agent_connections`；
- `agent_organization_view()` 初版组织视图；
- 启动点由 GuLiCode / 顶层 Agent 显式指定，框架只校验；
- GuLiCode 顶层 Agent rule / skill / start plan validation 骨架。

下一步优先：

1. 组织架构接口；
2. 开始接口；
3. 普通 Agent 消息分发 RPC/tool；
4. 多对一 fan-in / join；
5. 状态查询与结束/最终聚合接口。

### 2026-05-11 环状结构 / ring session runtime

已完成并纳入当前知识：

- 环类 `agent` 对外视为普通 `agent`，对内按单向单轮次执行会话流转；
- `RingSessionEntry` / `RingSessionPlan` / `RingSessionState` 已落地到运行时；
- `GraphDefinition.plan_ring_session()` 与 `plan_ring_session_from_entries()` 已可根据环顺序和入口消息生成会话计划；
- `GraphRuntime.register_ring_session()`、`ring_session_reachable_targets()`、`ring_session_dispatch_targets()`、`ring_session_state()` 已支持动态可达节点、队列门控和审核官 final output；
- 控制面已支持 `ring.register`，并与普通消息批次 / 分发路径共用框架接口；
- 已验证 `python -m pytest test_agent_runtime.py test_graph_control.py test_workspace_api.py test_workspace_manager.py -q` 为 `120 passed`。

短期收口：

1. 优先处理上方“嵌套环 / 分支环递归处理”任务。
2. 把 ring-session 的队列上限、超时、审核官幂等输出、迟到消息阻断，继续保留在 runtime 状态与事件解释里。
3. 继续把 `knowledge_base/ring_structure_solution.md` 作为当前 ring 方案的主文档。

### 历史最小闭环路径（已降级）

以下路径曾用于 Ryven / runtime 融合早期验证，现在只作为历史背景：

1. `Start -> blocking AgentNode -> End`
2. 由 Ryven Flow 编译成 `GraphDefinition`
3. 由一个最薄的图执行器按 `exec` 边跑通
4. 节点运行状态可见，最终结果可见
5. 运行结果先回写到 UI / 日志，后续再进入事件总线

这条路径当时的原则：
- 不先做完整路由系统
- 不先做 nonblocking job 持久化
- 不先做复杂 Inspector / 类型系统
- 不先做分布式 workspace 协作
- 先确保单节点图闭环稳定

这批旧阶段任务中，仍然有效的运行时部分已经迁移到当前 GraphRuntime / GuLiCode 主线；Ryven/editor 专属部分延后。保留以下条目仅用于理解历史来源：

1. AgentNode prompt contract，使下游 agent 只知晓：
   - 传入上下文
   - 用户设置的 agent prompt / model / skills
   - 框架允许暴露的接口文档
   - 可读/可写路径
   - 输出格式
2. `AgentSkillSelection` 到图执行期的授权 skill 注入：
   - `none` / `all` / `selected` / `upstream` 模型已落地
   - registry / registry-ui 已同步
   - 当前仍需把 `upstream` 与图上游超级 agent 的配置流、授权 skill materialize 串起来
3. `AgentSkillView` 与 CodexAdapter 的强隔离：
   - prompt/context 注入已可用
   - 临时 `CODEX_HOME` 已绑定到 agent 私有目录
   - Codex 蓝图启动已使用 `workspace-write` sandbox + private checkout `cwd`，并拒绝 `danger-full-access` 与把真实项目目录加入 `--add-dir`
4. 超级 agent 下游 agent 配置能力：
   - model
   - skills
   - prompt contract
   - write/artifact scope
5. 处理节点、I/O 节点和条件 `switch` 路由。
6. 可订阅/可持久化事件流，以及 `WorkspaceChanged`、`ReviewRequested` 的实际触发点。
7. 非阻塞 job 的取消、恢复、超时、失败重试和持久 runner。
8. 共享工作区 lock / lease、Dulwich commit/ref merge、归档删除 API、归档索引和空间清理策略。
9. Ryven + GraphRuntime 融合顺序：
   - 第一步：Ryven Flow -> `GraphDefinition` 编译 + `validate_runnable`（已完成）
   - 第二步：只跑 blocking `AgentNode` 的最小链路
   - 第三步：显示每个节点的运行状态和最终结果
   - 第四步：接 nonblocking job / manifest / workspace event
   - 第五步：做更强的类型系统、Inspector、上下文推荐

### Ryven 最小闭环方案备忘（延后）

如果未来重新启动 Ryven/editor 方向，可参考以下策略：

1. 先把图执行器限制为单一执行路径，只支持 `Start -> AgentNode -> End`
2. 只允许一个 blocking AgentNode 先跑通完整回路
3. 把 `AgentNode` 的输入输出先固化为最少端口语义：
   - `in` 端口接 exec
   - `prompt` 端口接 data
   - `out` 端口继续 exec
   - `result` 端口回传 data
4. 先在 UI 中展示执行中 / 完成 / 失败三态
5. 结果先显示在节点面板或日志窗，不急着做复杂事件面板
6. 通过一个显式“Run Blueprint”动作触发运行，而不是一开始就做自动调度

### 工作区职责对齐

短期需要把工作区模型从“job worktree 自动合并”调整为更清晰的三层：

1. `base/`：本次蓝图运行开始时的项目基线，用于 diff / merge / conflict 判断。
2. `agents/<agent_id>/private/`：agent 私有 scratch 空间，存放临时文件、缓存、授权 skills view、CLI 会话数据等；蓝图结束后销毁，不归档、不自动合并。
3. `shared/`：本次蓝图运行的临时共享成果空间，存放代码修改、生成图片、生成文本、报告、manifest 等其它 agent 需要读取或最终需要归档的产物。

必须对齐的规则：

- agent 私有空间可以是独立目录，也可以后续升级为 Git/Dulwich worktree；但语义上它不是成果目录。
- 私有空间内容不自动进入 `shared/`；agent 需要显式发布成果到共享空间。
- 共享空间写入必须有竞态处理，至少先落地文件级 lock / lease + manifest 记录；后续再升级到 Dulwich commit/ref merge。
- 多 agent 同路径写入时不能静默覆盖，必须返回冲突状态并保留足够信息给人工或上层 agent 解决。

## 当前代码对照状态（2026-05-04）

已完成：

1. 已新增 `graph_runtime.py`，包含 `AgentNode`、`AgentInstance`、`GraphRuntime`、`BrokerAgentRuntime`。
2. `AgentNode` 已具备与 `WorkerConfig` / registry 扩展对齐的基础字段：`node_id`、`agent_id`、`cli_kind`、`model`、`cwd`、`skills`、`timeout_sec`、`prompt_via_file`、`command`、`adapter_options`、`extra_env`、`external`。
3. `GraphRuntime.ensure_agent()` 已实现同一次图运行内的 `node_id -> AgentInstance` 绑定与复用；首次经过节点可调用 `cluster.ensure_worker()` 懒启动 worker。
4. `GraphRuntime.send_agent_message()` 已把 Agent 节点消息发送映射到 `cluster.run_single()`，并明确把 cluster 方法视作消息调度原语，而不是每次节点经过都 spawn/teardown。
5. `BrokerAgentRuntime` 已提供连接已有 broker 并向 worker 发送单条消息的轻量运行时。
6. `AgentNode.execution_mode` 已支持 `blocking` / `nonblocking` 字段校验；`GraphRuntime.send_agent_message()` 会把 `nonblocking` 节点转为 job 提交响应。
7. 已新增 `GraphJob`、`GraphEvent`、`WorkspaceManifest`，形成非阻塞 job、事件模型与共享工作区 manifest 的最小可序列化基线。
8. 已新增 `MultiModalEnvelope` / `normalize_envelope`，作为节点端口统一数据容器。
9. 已新增 `RouteNode`、`GraphEdge`、`GraphDefinition`、`GraphExecutor`，支持 DAG 环检测和 `sequence` / `parallel` / `parallel_reduce` 路由到 cluster 原语的最小实现。
10. 已新增 `dulwich_vendor.py` 与 `workspace_manager.py`，接入 vendored Dulwich，并实现用户可指定的项目级长期共享工作区、蓝图运行级临时共享工作区、完整目录归档、job 隔离 worktree、diff、scope 校验、文本三方 merge 和冲突检测。
11. 长期共享工作区支持默认 `<project>/.multi_agent_workspace/`，也支持用户显式传入 `workspace_root`；当它位于工程目录内时，运行快照会排除该目录。agent 访问上下文会把长期共享工作区暴露为 `readonly_shared_workspaces`，并拒绝把它纳入 `write_scope` / `artifact_scope`。
12. 已新增 `SkillSpace`、`AgentSkillView`、`SuperAgentProfile`：框架私有维护 hash -> skill 的映射，按 hash 列表将授权 skills 复制到当前 agent 独立目录，并为超级 agent 提供下游 skill 分配校验。
13. `test_agent_runtime.py` 已覆盖 AgentNode 字段解析、WorkerConfig 转换、GraphRuntime 懒启动与复用、非阻塞 job 事件和 manifest、MultiModalEnvelope、DAG 环检测、路由节点调度。
14. `test_workspace_manager.py` 已覆盖 Dulwich backend、完整目录归档、自定义长期共享目录、只读访问策略、job diff、scope violation、无冲突合并、同文件冲突和 failed run 归档。
15. `test_skill_space.py` 已覆盖 hash skill 映射、agent 独立目录 materialize、未知 hash 拒绝、超级 agent 分配权限和 workspace manager 的 agent 目录集成。
16. `AgentSkillView` 已新增 `codex_execution_context()` 与 `codex_adapter_options()`，可向 CodexAdapter 暴露 agent 独立目录、cache、授权 skills 目录、skill hash 列表与授权 skill catalog。
17. `AgentNode.node_id` 已改为框架自动分配；用户配置侧不再需要填图内部节点 ID。
18. `AgentSkillSelection` 已落地并同步到 registry / registry-ui，支持 `none`、`all`、`selected`、`upstream`；旧 `skills` 列表兼容为 `selected`。registry 静态注入中 `upstream` 不解析 skill，留给图运行时超级 agent 授权。
19. `test_registry_skill_selection.py` 已覆盖 registry 对 skill selection 的解析、catalog 注入和 `show-registry` 输出。
20. `AgentNode.to_dict()` 已补齐，便于 Ryven wrapper、项目保存和 runtime 编译复用同一后端 schema。
21. `GraphDefinition` 已新增 `BlueprintTerminalNode`、`terminal_nodes` 和 `validate_runnable()`，可校验 Start/End 唯一性、DAG 与 start -> end 有向路径。
22. `GraphEdge` 已新增 `edge_type`，用于记录端口连接语义；`validate_runnable()` 只使用 `exec` 边判断 Start -> End 控制流路径，`data` 边不会误判为可运行路径。
23. `compile_ryven_flow()` 已可把 live Ryven flow 编译为 `GraphDefinition`：`BlueprintStart` / `BlueprintEnd` 编译为 `BlueprintTerminalNode`，Ryven `AgentNode` wrapper 编译为后端 `AgentNode`，Ryven 连接编译为带端口名和 `edge_type` 的 `GraphEdge`。

部分完成：

1. 节点分类目前只落地了 Agent 节点；处理节点、路由节点、I/O 节点仍停留在设计任务。
2. Agent 节点生命周期已有“首次绑定/后续复用/运行时 close 清理绑定”的基础实现；由 cluster 拥有的 worker 进程 teardown 仍委托给 cluster，尚未形成完整图运行失败/取消收尾协议。
3. 图编译目前已有路由节点到 `run_chain` / `run_parallel` / `run_parallel_reduce` 的最小映射，并新增 runnable blueprint 起止约束；Ryven flow -> `GraphDefinition` 编译已落地第一版，但还没有图级 blocking 执行入口和事件回流 UI。
4. 共享工作区已有隔离目录、diff、merge、冲突检测、完整目录归档和 runtime 只读策略；Codex strict launch 依赖 `workspace-write` sandbox 和启动参数校验；lock / lease、持久 runner、Git 对象级 commit/ref merge 仍未做。
5. 工作区模型已开始向 `base/` + `shared/` + `agents/<agent_id>/private/` 拆分：私有目录只作为 scratch，归档前丢弃；共享目录保留成果，并已有最小文件级 lease API。完整运行期竞态处理、manifest 协议和 Dulwich commit/ref merge 仍未完成。
6. 事件模型目前是内存列表和 manifest 更新；还不是跨进程事件总线。
7. SkillSpace 目前提供目录级隔离与 prompt/context 暴露；已可生成 CodexAdapter options，但尚未把临时 `CODEX_HOME` 自动绑定到 CLI 运行时做强隔离。
8. `upstream` skill selection 的运行时授权模型已有校验基础，但还没有完整接入图上游超级 agent 的 UI/编排配置流。

未完成 / 下一步：

1. 完成 graph scheduling beyond minimal single exec path：parallel branches、fan-out/fan-in、condition/switch routing、nonblocking job joins、deterministic final state aggregation。
2. 把 ordinary-Agent dispatch 绑定到当前 task envelope、outgoing batch 和 `required_outgoing_targets`。
3. 把 workspace/VCS API、artifact/report publish API 统一绑定到当前任务信封和 Agent scope。
4. Surface runtime events to GuLiCode desktop：queued、dispatching、running、waiting_for_reply、join waiting、completed、failed、cancelled、workspace changed。
5. 将 `AgentSkillView` / Codex adapter options 自动并入 AgentNode / WorkerConfig 创建路径。
6. 将 `upstream` skill selection 与图上游超级 agent 配置流打通，并在需要时由运行时 materialize 授权 skills。
7. 实现超级 agent 除 skill 分配外的下游 agent 配置能力。
8. Ryven/editor 相关的 Run Blueprint、Start/End 最小链路、Inspector 和节点视觉改造延后到明确需要 visual editor 时。

## 2026-05-11 `GraphDefinition.agent_cycle_groups()`（已落地）

- 新增 `GraphDefinition.agent_cycle_groups()`：在仅 **`exec` 边** 的子图上做 SCC；若 SCC 为环（含多点 SCC 或带自环的单点），则输出该 SCC 内所有 **Agent** 的 `node_id`，格式为二维列表，例如 `[["a", "b", "c"], ["d", "e", "f"]]`；无环图返回 `[]`。
- 环若经过 **`RouteNode`（或其它非 Agent 节点）** 仍可被识别，因为 SCC 在**全节点**上计算，返回时再筛成仅 agent id。
- 代码：`graph_runtime.py`；测试：`test_agent_runtime.py`（含上述两例）；该文件 pytest 在合入时为 **64 passed**。
- 后续可选（未做）：再包一层，同时输出「每个环对应的原始 SCC 节点全集」便于调试图结构。

## 依赖知识

- [`../knowledge_base/multi_cli_workflow.md`](../knowledge_base/multi_cli_workflow.md)
- [`../knowledge_base/agent_node_ryven_integration.md`](../knowledge_base/agent_node_ryven_integration.md)
- [`../knowledge_base/core_architecture.md`](../knowledge_base/core_architecture.md)
- [`../knowledge_base/cluster_api.md`](../knowledge_base/cluster_api.md)

## 2026-05-06 workspace alignment progress

- `workspace_manager.py` now splits each blueprint run into `base/`, `shared/`, and `agents/<agent_id>/private/`.
- `agents/<agent_id>/private/` is private scratch and CLI state. It is not an outcome worktree, is not auto-merged, and is discarded by `archive_run()` before archival.
- `shared/code/` is the per-run code outcome area, `shared/artifacts/` stores generated assets, and `shared/reports/` stores reports and structured results. These paths are preserved in the run archive.
- `shared/.locks/`, `acquire_shared_lease()`, `release_shared_lease()`, and `write_shared_text()` provide the first file-level lease and manifest path to prevent silent same-path overwrites.
- `ryven_blueprint.py` now points AgentNode `cwd` at private scratch and injects the Workspace API contract instead of exposing shared workspace paths as the primary interface.
- `codemaker_bridge.py` now consumes the same `prompt_preamble` and `execution_context` fields as `codex_bridge.py`, so both CodeMaker and Codex CLI-backed AgentNodes receive the workspace contract in their actual prompt.
- The blueprint controller writes `shared/reports/blueprint_result.json` before archive, recording run status, events, result, and the private workspace mapping.
- Compatibility note: legacy `prepare_job()` / `merge_job()` remains for old isolated-worktree tests and later Dulwich merge experiments, but the minimum blueprint run path no longer auto-merges private scratch as task output.

2026-05-06 follow-up:

- Added `docs/workspace_api.md` as the framework-maintained Workspace API contract for blueprint agents.
- Added `workspace_api.py` with `publish`, `publish-file`, `read`, and `list` commands. Agents publish to logical areas (`code`, `artifacts`, `reports`) instead of writing to physical shared workspace paths.
- Blueprint AgentNode startup now injects the Workspace API document and command contract, not the shared workspace paths. Agent `cwd` is private scratch; the API context is provided through `MULTI_AGENT_WORKSPACE_CONTEXT`.
- `publish` and `publish-file` go through `DulwichWorkspaceManager` shared write APIs and lease/manifest recording.
- Shared files now use a per-path read/write lock: concurrent reads are allowed, but any active writer blocks readers and writers, and active readers block writers.
- Workspace API also exposes per-path write versions: agents can `read --json`, edit privately, then `publish --expected-version N` to avoid stale overwrites during multi-agent edits.
- Remaining caveat: this is a controlled CLI API and prompt contract, not a full security boundary for every possible CLI backend. Codex strict launch currently relies on Codex `workspace-write` sandbox semantics; other backends need separate evaluation before being treated as strict.

Still pending:
- Move Workspace API from local context-file CLI to a broker-side or runtime-owned RPC/tool protocol.
- Add conflict records, conservative three-way merge, or Dulwich commit/ref merge for `shared/code/`.
- Wire `WorkspaceChanged` and `ReviewRequested` events to shared manifest updates.
- Define UI-visible policies for binary artifacts, deletes/renames, and scope violations.

## 2026-05-06 archived task status

Completed and archived into `archive/blueprint_integration_archive.md`:

- Blueprint run workspace split: `base/`, private scratch, and shared outcome areas.
- AgentNode startup now uses private scratch as `cwd`.
- Framework-maintained Workspace API document is injected into agents at startup.
- `workspace_api.py` provides controlled `publish`, `publish-file`, `read`, and `list` commands.
- Workspace API writes go through manager-owned lease and manifest recording.
- Shared files have per-path read/write locks: concurrent reads are allowed, writers are exclusive.
- Shared files have per-path versions for read-modify-write: `read --json` plus `publish --expected-version N`.
- Pytest coverage now includes Workspace API binary stale-version conflicts, API-level reader/writer blocking, active-reader publish blocking, path escape rejection, and the private `agents/<agent_id>/private/` SkillSpace integration expectation. Full project pytest is configured to skip vendored/generated dependency trees and currently passes with `59 passed`.

Current short-term follow-up:

- Promote Workspace API from local context-file CLI to broker/runtime-owned RPC or tool calls.
- Add conflict records and optional Dulwich commit/ref merge for `shared/code/`.
- Emit `WorkspaceChanged` events from Workspace API publish/read flows and surface them in the UI.
- Define UI-visible policies for binary artifacts, deletes/renames, and scope violations.

## 2026-05-07 VCS-style workspace task update

The file/snapshot VCS-style workspace MVP is now implemented and tested in the codebase.

Completed:

- `checkout/status/diff/submit/sync` exist at manager, RPC, and CLI levels.
- Agent private checkouts are now compatible with two code modes:
  - legacy `snapshot_copy`, copied from current `run.integration_dir`;
  - active `project_reference`, fetched on demand from the project directory.
- `workspace_api checkout --path <relative-file-or-dir>` supports focused task-level materialization; `--scope-path` remains available for broader scopes.
- In `project_reference`, empty scope no longer means full-project checkout/write access; it starts empty and rejects out-of-scope submit changes.
- Each checkout keeps its own base snapshot under `agents/<agent_id>/private/state/base`.
- Submit compares checkout base, current code target, and agent checkout to decide accept/conflict.
- In `project_reference`, accepted changes write back to the project directory; temporary shared workspace records changeset/conflict metadata rather than serving as code integration storage.
- Conflict responses are structured and preserved over RPC.
- The conflict repair loop is tested end to end.
- Text merge uses Dulwich `merge_blobs()` when available and falls back to conservative conflict behavior otherwise.
- `merge3` is recorded as the recommended dependency for Dulwich hunk-level text merging.

Next runtime tasks:

1. Continue reducing remaining legacy `integration_dir` / `shared_code` wording in status surfaces and docs by using the code-source/code-target abstraction.
2. Prefer `checkout --path -> edit -> status/diff -> submit` for source edits; keep `publish` for reports/artifacts, summaries, references, and non-source outputs.
3. Launch strict agents with project context read-only and private checkout writable.
4. Attach changeset ids, conflict ids, test results, and repair attempts to `TaskCompleted` / final blueprint reports.
5. Surface `CheckoutCreated`, `ChangesetSubmitted`, `ChangesetAccepted`, `ConflictDetected`, `CheckoutSynced`, and `WorkspaceChanged` in the UI/runtime event stream.
6. Define submit policies for binary files, deletes, renames, formatter-only changes, generated files, and large files.
7. After the file/snapshot RPC contract stabilizes, evaluate Dulwich commit/ref storage for baseline and integration refs.

## 2026-05-07 runtime tick and graph scheduling priority update

Completed:

- `GraphRuntime` now has a framework tick loop with a default 0.5-second frame interval.
- `AgentInstance` now tracks a fuller lifecycle state vocabulary and state history, covering startup, idle, queued, dispatching, running, waiting for reply, processing reply, failure, timeout, cancellation, restart, and stop phases.
- Runtime-managed per-agent queues now retain messages that arrive while a CLI-backed AgentNode cannot accept work.
- Each tick can dispatch queued messages FIFO, one message per idle agent per frame.
- Codex-backed AgentNode output was verified through the real `AgentNode -> GraphRuntime -> codex worker` path.
- Codex final reply display should use `reply.body.codex.final_text`; raw `stdout` remains JSONL debug/archive data, and `stderr` should be treated as diagnostic noise unless an error needs inspection.
- Windows Codex command resolution now avoids `.ps1` direct execution and prefers npm `.cmd` shims.

New top priority:

1. Complete graph scheduling beyond the minimal single exec path:
   - `parallel` branches;
   - fan-out/fan-in;
   - `condition` / `switch` routing;
   - nonblocking job joins;
   - deterministic final state aggregation.
2. Define scheduler frame semantics:
   - ready nodes;
   - blocked nodes;
   - running nodes/jobs;
   - completed branches;
   - failed/cancelled/timed-out branches;
   - join nodes waiting for upstream requirements;
   - terminal aggregation.
3. Define fan-out semantics:
   - how one upstream output becomes multiple downstream tasks;
   - how source metadata, task id, branch id, and parent output are carried;
   - how branch-level errors are reported without losing successful sibling outputs.
4. Define fan-in semantics:
   - wait-all, wait-any, quorum, and timeout policies;
   - how accepted changesets, conflicts, artifacts, reports, and test results are merged into the fan-in input.
5. Define condition/switch semantics:
   - routing based on structured output/status, not prompt text alone;
   - first-match vs multi-match behavior;
   - default/fallback branch behavior;
   - error branch behavior.
6. Define nonblocking join semantics:
   - join by job id, branch id, node id, or named group;
   - cancellation and retry policy;
   - timeout policy;
   - partial completion policy.
7. Define deterministic end-state aggregation:
   - final graph status must be reproducible from scheduler state and event history;
   - final report should explicitly distinguish success, partial success, failure, cancellation, unresolved conflict, and timeout;
   - aggregation should include changed files, accepted changesets, conflicts, artifacts, reports, test results, and follow-up risks.
