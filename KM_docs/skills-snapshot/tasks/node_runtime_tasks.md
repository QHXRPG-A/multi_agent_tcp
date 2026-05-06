# 节点运行时与图编译方向任务

## 目标

把当前 cluster / broker 编排能力，逐步抬升为面向节点图的执行运行时与编译目标。

## 近期任务

### 最小闭环优先路径

短期内优先只做一条可落地的主线：

1. `Start -> blocking AgentNode -> End`
2. 由 Ryven Flow 编译成 `GraphDefinition`
3. 由一个最薄的图执行器按 `exec` 边跑通
4. 节点运行状态可见，最终结果可见
5. 运行结果先回写到 UI / 日志，后续再进入事件总线

这条路径的原则：
- 不先做完整路由系统
- 不先做 nonblocking job 持久化
- 不先做复杂 Inspector / 类型系统
- 不先做分布式 workspace 协作
- 先确保单节点图闭环稳定

1. 完善 AgentNode prompt contract，使下游 agent 只知晓：
   - 传入上下文
   - 用户设置的 agent prompt / model / skills
   - 框架允许暴露的接口文档
   - 可读/可写路径
   - 输出格式
2. 继续打通 `AgentSkillSelection` 到图执行期的授权 skill 注入：
   - `none` / `all` / `selected` / `upstream` 模型已落地
   - registry / registry-ui 已同步
   - 下一步把 `upstream` 与图上游超级 agent 的配置流、授权 skill materialize 串起来
3. 完善 `AgentSkillView` 与 CodexAdapter 的强隔离：
   - prompt/context 注入已可用
   - 下一步绑定临时 `CODEX_HOME`
   - 后续接入 sandbox / writable path policy
4. 为超级 agent 增加下游 agent 配置能力：
   - model
   - skills
   - prompt contract
   - write/artifact scope
5. 补处理节点、I/O 节点和条件 `switch` 路由。
6. 把内存事件模型扩展为可订阅/可持久化事件流，并补 `WorkspaceChanged`、`ReviewRequested` 的实际触发点。
7. 为非阻塞 job 增加取消、恢复、超时、失败重试和持久 runner。
8. 为共享工作区增加 lock / lease、Dulwich commit/ref merge、归档删除 API、归档索引和空间清理策略。
9. 按 Ryven + GraphRuntime 融合顺序推进图执行链路：
   - 第一步：Ryven Flow -> `GraphDefinition` 编译 + `validate_runnable`（已完成）
   - 第二步：只跑 blocking `AgentNode` 的最小链路
   - 第三步：显示每个节点的运行状态和最终结果
   - 第四步：接 nonblocking job / manifest / workspace event
   - 第五步：做更强的类型系统、Inspector、上下文推荐

### 最小闭环方案备忘

短期最实用的实现策略是：

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
4. 共享工作区已有隔离目录、diff、merge、冲突检测、完整目录归档和 runtime 只读策略；lock / lease、OS ACL / 沙箱级只读强制、持久 runner、Git 对象级 commit/ref merge 仍未做。
5. 工作区模型已开始向 `base/` + `shared/` + `agents/<agent_id>/private/` 拆分：私有目录只作为 scratch，归档前丢弃；共享目录保留成果，并已有最小文件级 lease API。完整运行期竞态处理、manifest 协议和 Dulwich commit/ref merge 仍未完成。
6. 事件模型目前是内存列表和 manifest 更新；还不是跨进程事件总线。
7. SkillSpace 目前提供目录级隔离与 prompt/context 暴露；已可生成 CodexAdapter options，但尚未把临时 `CODEX_HOME` 自动绑定到 CLI 运行时做强隔离。
8. `upstream` skill selection 的运行时授权模型已有校验基础，但还没有完整接入图上游超级 agent 的 UI/编排配置流。

未完成 / 下一步：

1. 先落地最小闭环：`Start -> blocking AgentNode -> End` 的图级执行入口、状态回写和结果展示。
2. 给 UI 补一个明确的 Run 入口，把运行触发从手工调用收敛到统一动作。
3. 让 `AgentNode.result` 的 data 输出能进入下游节点 prompt，先支持一跳传递。
4. 先定义最少的运行态事件：`queued` / `running` / `completed` / `failed`。
5. 拆分 agent 私有 scratch 空间与临时共享成果空间，停止把私有 worktree 自动 merge 当作成果发布机制。
6. 给临时共享空间增加基础竞态处理：文件级 lock / lease、写入 manifest、冲突记录。
7. 完成后再补处理节点、I/O 节点和条件 `switch` 路由。
8. 再把内存事件模型扩展为可订阅/可持久化事件流，并补 `WorkspaceChanged`、`ReviewRequested` 的实际触发点。
9. 再为非阻塞 job 增加取消、恢复、超时、失败重试和持久 runner。
10. 再为共享工作区增加 Dulwich commit/ref merge、归档删除 API、归档索引和空间清理策略。
11. 把 `AgentSkillView` 的 Codex options 自动并入 AgentNode / WorkerConfig 创建路径。
12. 将 `upstream` skill selection 与图上游超级 agent 配置流打通，并在需要时由运行时 materialize 授权 skills。
13. 实现超级 agent 除 skill 分配外的下游 agent 配置能力。
14. 建立更强的端口类型系统、Inspector 数据预览和上下文推荐能力。

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
- Remaining caveat: this is a controlled CLI API and prompt contract, not a full security boundary. A stronger version should move the context behind a broker-side RPC/token service and add OS/sandbox-level write restrictions.

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

Current short-term follow-up:

- Promote Workspace API from local context-file CLI to broker/runtime-owned RPC or tool calls.
- Add stronger filesystem enforcement so agents cannot bypass the API by direct shared-path writes.
- Add conflict records and optional Dulwich commit/ref merge for `shared/code/`.
- Emit `WorkspaceChanged` events from Workspace API publish/read flows and surface them in the UI.
- Define UI-visible policies for binary artifacts, deletes/renames, and scope violations.
