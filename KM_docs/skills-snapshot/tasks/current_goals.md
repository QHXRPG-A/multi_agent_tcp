# 2026-05-07 Current Short-Term Status

The strict VCS-style workspace contract has landed and is archived in `archive/agents_architecture_archive.md`.

Completed in the latest round:

- GraphRuntime now has a framework tick loop with a default 0.5-second frame interval.
- AgentInstance now tracks a fuller runtime state vocabulary and state history instead of only `busy_count`.
- Runtime-managed per-agent message queues now retain messages that arrive while a CLI-backed AgentNode cannot accept work; ticks dispatch queued messages FIFO, one message per idle agent per frame.
- Codex-backed AgentNode output was verified through `AgentNode -> GraphRuntime -> codex worker`; the final agent reply should be read from `reply.body.codex.final_text`, with `last_message` as its upstream source and `stdout` retained as raw JSONL debug/archive data.
- Windows Codex CLI launch now avoids the `codex.ps1` `WinError 5` issue by preferring the npm `.cmd` shim when resolving Codex commands.
- Agents can call the Workspace API/RPC to create scoped private checkouts from the current temporary integration workspace.
- Agents can edit files in private checkouts and submit changesets back to the temporary integration workspace.
- Scope violations and same-region conflicts block submit and return structured feedback to the agent.
- A repair loop is covered: conflict response -> sync latest integration -> edit private checkout -> resubmit.
- Text merge now prefers Dulwich `merge_blobs()` with `merge3` installed, so non-overlapping same-file edits can merge automatically.
- End-to-end tests cover manager-level and RPC/CLI-level checkout/submit/conflict/sync/resubmit flows.
- Blueprint AgentNode launch creates a private checkout before worker start and launches the worker with that checkout as `cwd`.
- Agent-facing publish areas have been narrowed to run-scope `artifacts` and `reports`; `code` is no longer exposed through `publish` or `publish-file`.
- Agent-facing publish/read/list scopes have been narrowed to the current run; `long_term` is no longer exposed as a publish scope.
- Framework archive flow now writes each run's temporary `shared/` workspace as a named zip in the long-term shared workspace.
- Agents can read long-term run results through `list-archives` and `extract-archive`, with extraction into private workspace.
- Codex-backed Blueprint AgentNode launch now relies on Codex CLI `workspace-write` sandbox semantics: the real project path is exposed as read-only `project_context`, while `--cd` points at the private checkout.
- Codex launch safety now rejects `sandbox=danger-full-access`, `--dangerously-bypass-approvals-and-sandbox`, and `extra_args --add-dir` entries that overlap the read-only project context.
- Current validation snapshot: `python -m pytest test_workspace_api.py test_workspace_manager.py test_agent_runtime.py -q` -> `72 passed`; `python -m pytest test_agent_runtime.py -q` -> `38 passed`.

Updated next short-term focus:

- Most important: complete graph scheduling beyond the minimal single exec path: `parallel`, fan-out/fan-in, `condition`/`switch`, nonblocking join, and deterministic final state aggregation.
- Define the scheduler data model for runnable graph frames: ready nodes, running jobs, blocked joins, completed branches, failed branches, and terminal aggregation.
- Define how fan-in nodes collect upstream outputs, errors, conflicts, artifacts, and accepted changesets before continuing.
- Define how condition/switch routes inspect node output, task status, conflict records, and test results without relying on prompt conventions.
- Define nonblocking join rules: wait-all, wait-any, quorum, timeout, cancellation, and failed-job policy.
- Extend conflict records and reports with task id, changed files, test results, risks, and repair/resubmit history.
- Surface checkout, submit, conflict, sync, and accepted changeset events in the runtime/UI state.
- Define binary, delete/rename, large-file, generated-file, and formatter policies for changeset submit.
- Define long-term archive indexing, pruning, deletion, retention, and streaming read policies.
- Evaluate moving from file/snapshot changesets to Dulwich commit/ref storage after the current RPC contract stabilizes.

High-priority short-term tasks for the full blueprint execution loop:

- [DONE] Integrate VCS-style `checkout/status/diff/submit/sync` into AgentNode prompt contracts and execution context.
- [DONE] Add strict launch mode shape for agents: project root as read-only context, private checkout as writable `cwd`, framework runtime as the only integration writer.
- [DONE] Remove agent-facing `code` publish area and long-term publish scope from Workspace API/RPC and injected docs.
- [DONE] Add framework tick, expanded agent runtime states, and per-agent queued message dispatch for busy CLI-backed AgentNodes.
- [HIGH] Complete full graph scheduling beyond the minimal single exec path: `parallel`, fan-out/fan-in, condition/switch routing, nonblocking job joins, and deterministic end-state aggregation.
- [HIGH] Implement a scheduler-level run state model so every tick can deterministically decide which nodes are ready, blocked, running, joined, failed, skipped, or terminal.
- [HIGH] Define final aggregation semantics for mixed outcomes: success, partial success, failed branch, cancelled branch, unresolved conflict, timeout, and accepted changesets.
- [HIGH] Define and enforce a structured agent task-completion protocol, including status, summary, changed files, accepted changesets, conflicts, shared outputs, artifacts, test results, and follow-up risks.
- [HIGH] Emit durable workspace and task events from the runtime and Workspace API: `CheckoutCreated`, `ChangesetSubmitted`, `ChangesetAccepted`, `ConflictDetected`, `CheckoutSynced`, `WorkspaceChanged`, `ArtifactPublished`, `AgentReportSubmitted`, `TaskCompleted`, and `ReviewRequested`.
- [HIGH] Finish archive policy from temporary run workspace to long-term shared workspace: index changesets/conflicts/artifacts/reports, define retention/deletion, and represent failed or conflicted runs.
- [HIGH] Implement blueprint auto-finish conditions: all required agents complete, all nonblocking jobs settle, shared writes are flushed, conflicts are either resolved or recorded, and the final report is published.
- [HIGH] Surface the full run state in UI: agent status, assigned `cwd`, checkout path, shared outputs, workspace conflicts, accepted changesets, final reports, and archive path.

---

# 2026-05-06 Current Short-Term Status

The blueprint workspace-control loop has been partially completed and archived:

- Agents now receive a framework-maintained Workspace API contract instead of physical shared workspace paths.
- AgentNode `cwd` is the assigned user project workdir; private agent directories are used for CLI-local state and framework context.
- Outcomes are published through `python -m multi_agent_tcp.workspace_api`.
- Shared output paths use read/write locks and version checks for multi-agent cooperation.
- Details are archived in `archive/blueprint_integration_archive.md`.

Next short-term focus:

- Move Workspace API from local context-file CLI to broker/runtime-owned RPC or tool calls.
- Add stronger filesystem/sandbox enforcement so shared outputs cannot be bypassed.
- Add Workspace API events (`WorkspaceChanged`, conflict records) and UI surfacing.
- Add optional Dulwich commit/ref merge for `shared/code/`.

High-priority short-term tasks for the full blueprint execution loop:

- [HIGH] Complete full graph scheduling beyond the minimal single exec path: parallel branches, fan-out/fan-in, condition/switch routing, nonblocking job joins, and deterministic end-state aggregation.
- [HIGH] Add project workdir change collection after each agent task: scan the assigned `cwd`, compute diffs against the run baseline, attribute changed files to agents, detect conflicts, and record results in the run manifest.
- [HIGH] Expose the super-agent-only workdir assignment framework API: only `SuperAgentProfile` may request downstream workdir reassignment; the runtime must kill and relaunch the target agent with the same config plus the new `cwd`.
- [HIGH] Harden agent state tracking for reassignment and lifecycle decisions: at minimum support `idle`, `running`, `waiting`, `failed`, `completed`, `restarting`, and `disconnected`; return `AGENT_BUSY` when a workdir assignment targets an active agent.
- [HIGH] Define and enforce a structured agent task-completion protocol, including status, summary, changed files, shared outputs, artifacts, test results, and follow-up risks.
- [HIGH] Emit durable workspace and task events from the runtime and Workspace API: `WorkspaceChanged`, `ConflictDetected`, `ArtifactPublished`, `AgentReportSubmitted`, `TaskCompleted`, and `ReviewRequested`.
- [HIGH] Define archive policy from temporary run workspace to long-term shared workspace: what to archive, how to index it, how to keep code diffs/artifacts/reports, and how to represent failed or conflicted runs.
- [HIGH] Implement blueprint auto-finish conditions: all required agents complete, all nonblocking jobs settle, shared writes are flushed, conflicts are either resolved or recorded, and the final report is published.
- [HIGH] Surface the full run state in UI: agent status, assigned `cwd`, shared outputs, workspace conflicts, changed files, final reports, and archive path.
- [HIGH] Keep all agents started at blueprint launch; any later workdir reassignment must go through the explicit runtime API, not a data edge or prompt convention.

---

# 当前短期目标总览

本文件提炼当前 `multi_agent_tcp` skill 相关的近期工程目标，来源主要包括：

- `KM_docs/multi-cli-node-workflow-brainstorm.md`
- `KM_docs/vendor-ryvencore-qt-node-appearance.md`
- `KM_docs/ryvencore-vs-ue5-blueprint-gaps-2-4-8.md`

## 当前主线

### 1. 多 CLI agent 接入基线

目标：把当前围绕 CodeMaker 的执行桥接，逐步演化为可扩展的多 CLI adapter 体系。

近期关注：
- 硬化已落地的 `CodexAdapter` 与 `codex_bridge.py`
- 为 `cli_kind=codex` / `mode=codex-worker` 增加 registry / cluster 示例和端到端 smoke
- 将临时 `CODEX_HOME` 强隔离自动绑定到 agent 独立目录或 run workspace
- 继续完善 AgentNode 的授权 skills / SkillSpace view 到 Codex 执行上下文的注入策略
- 保持 `CodeMakerAdapter` 完整兼容现有行为

详见：[`multi_cli_adapter_tasks.md`](multi_cli_adapter_tasks.md)

### 2. 节点运行时与图编译方向

目标：把 `run_single` / `run_parallel` / `run_chain` / `run_parallel_reduce` 上升为节点图的消息调度原语，而不是最终用户只通过 Python API 手写编排；Agent 节点本身应绑定图运行期长生命周期 CLI agent 实例。

近期关注：
- AgentNode prompt contract：只向下游 agent 暴露上下文、用户设置、授权 skills、接口文档与输出格式
- Ryven + GraphRuntime 融合的阶段推进清单：
  1. Ryven Flow -> `GraphDefinition` 编译 + `validate_runnable`（已完成）
  2. 只跑 blocking `AgentNode` 的最小链路
  3. 显示每个节点的运行状态和最终结果
  4. 接 nonblocking job / manifest / workspace event
  5. 做更强的类型系统、Inspector、上下文推荐
- AgentNode / registry / registry-ui 的 skill selection 已支持 `none` / `all` / `selected` / `upstream`，下一步是把 `upstream` 与图上游超级 agent 配置流打通
- SkillSpace view 已可接入 CodexAdapter prompt/context；下一步是临时 `CODEX_HOME` 或等价强隔离机制
- 处理节点、I/O 节点、条件路由与完整图执行入口
- 非阻塞 job 的取消、恢复、超时、失败重试和持久 runner
- 共享工作区 lock / lease、归档索引、归档删除 API

详见：[`node_runtime_tasks.md`](node_runtime_tasks.md)

### 3. vendored Ryven / UI / 蓝图方向

目标：为未来可视化节点编辑器与蓝图体验增强建立可持续演进的基础。

近期关注：
- 理清 `ryvencore_qt` 视觉层结构
- 识别节点主题与外观改造落点
- 继续推进 `AgentNode` Ryven wrapper 到完整蓝图执行链路：blocking 最小运行链路、运行按钮、事件展示、输出端口展示
- 沉淀对标 UE5 蓝图的高优先级改进项

详见：[`vendor_ryven_tasks.md`](vendor_ryven_tasks.md)

### 4. 蓝图最小闭环优先级

目标：先把“能画、能编译、能跑、能看结果”做成一条最短路径，再逐步扩展到完整工作流。

近期关注：
- 只保留 `Start -> blocking AgentNode -> End` 的最小执行链路
- 由 `compile_ryven_flow()` 产出 `GraphDefinition`，由图运行器直接消费
- 先回写节点运行状态与最终结果，再做更复杂的事件总线
- 先打通 UI 运行按钮和后端执行入口，再补非阻塞 job、路由节点、Inspector
- 先用当前 `AgentNode` wrapper 的统一 schema 跑通保存、编译、执行三段式闭环

详见：[`node_runtime_tasks.md`](node_runtime_tasks.md) 与 [`vendor_ryven_tasks.md`](vendor_ryven_tasks.md)

## 当前代码状态速览（2026-05-04）

- 多 CLI adapter：基础 adapter 边界已落地，`CodeMakerAdapter` 已兼容现有 `codemaker run` 行为；`cli_kind`、`adapter_options`、`extra_env` 已进入 `WorkerConfig` / registry / AgentNode 相关路径。真实 `CodexAdapter` 与 `codex_bridge.py` 已落地，支持 `codex exec`、stdin prompt、`--json`、`--output-last-message`、`--cd`、`--model`、`--image`、超时杀进程树和 `body.codex.final_text` 结果解析；`__main__.py agent --mode` 已支持 `codex-worker`。Claude CLI 未在本机 PATH 中发现。Codex 临时 `CODEX_HOME` 自动隔离、adapter 显式配置校验、registry-ui 按 `cli_kind` 差异化渲染仍未完成。
- 节点运行时：`AgentNode`、`GraphRuntime`、`BrokerAgentRuntime` 已落地，支持图运行内 `node_id -> AgentInstance` 懒启动、绑定和复用；`AgentNode.node_id` 已改为框架自动分配，用户侧不再必填；`blocking` / `nonblocking` 字段、非阻塞 job、事件模型、共享工作区 manifest、`MultiModalEnvelope`、DAG/路由节点最小 primitives 已落地。`GraphDefinition` 已新增 `BlueprintTerminalNode` / `terminal_nodes` / `validate_runnable()`，可表达 Start/End 唯一性、DAG 与 start -> end 可达约束；`GraphEdge.edge_type` 已能区分 `exec` / `data`，`validate_runnable()` 只把 `exec` 边作为控制流路径。共享工作区已接入 vendored Dulwich，并实现用户可指定长期目录、长期/临时生命周期、完整目录归档、job 隔离、diff、scope 校验、文本三方 merge、冲突检测和 agent 只读访问策略。新增 SkillSpace、agent 独立目录与 SuperAgentProfile，支持以 hash 列表为下游 agent materialize 授权 skills；`AgentSkillSelection` 已支持 `none` / `all` / `selected` / `upstream`，并同步到 registry / registry-ui；`AgentSkillView` 已可生成 Codex execution context / adapter options。CodexAdapter 已绑定私有 `CODEX_HOME`，并通过 `workspace-write` sandbox + private checkout `cwd` + 危险参数拒绝来收敛严格启动边界。blocking AgentNode 最小图运行链路、处理/I/O/条件节点、持久事件总线、取消/恢复、lock / lease、Git 对象级 commit/ref merge 仍未完成；非 Codex CLI 若进入 strict launch mode，需要单独评估等价隔离能力。
- Ryven / UI：`python -m multi_agent_tcp ryven`、`ryven_launcher.py` 与 vendored 视觉层入口识别已完成；`ryven_blueprint_nodes` 已提供 `AgentNode` wrapper、隐藏的 `BlueprintStart` / `BlueprintEnd`、基础配置表单和 Start/End 自动注入/删除保护；`compile_ryven_flow()` 已可把 live Ryven flow 编译为 `GraphDefinition`，并保留端口标签和 `exec` / `data` 边语义。实际节点外观改造、运行按钮/事件展示、registry-ui skill selection 控件联动、`--skip-dialog` 封装、Windows `.bat` 和预加载入口仍未完成。
- 轻量验证：`test_agent_runtime.py` 已覆盖 adapter 消息解析、扩展字段序列化、CodeMaker/Codex adapter 复用、Codex worker config、AgentNode model 映射、GraphRuntime 懒启动复用、非阻塞 job、manifest、MultiModalEnvelope、DAG/路由、AgentSkillSelection、AgentNode UI 配置 round-trip、runnable graph 校验和 Ryven live flow 编译；`test_workspace_manager.py` 已覆盖共享工作区生命周期、自定义长期目录、只读访问策略、隔离、diff、merge、冲突检测、共享读写锁和归档；`test_workspace_api.py` 已覆盖 Workspace API 文本/二进制发布、list/read、stale version、API 层读写锁阻塞和路径逃逸拒绝；`test_skill_space.py` 已覆盖 SkillSpace、agent 私有目录、超级 agent skill 分配和 Codex adapter options；`test_codex_cli_smoke.py` 已覆盖 Codex CLI smoke；`test_registry_skill_selection.py` 已覆盖 registry 对 `none` / `all` / `selected` / `upstream` 的解析和 `show-registry` 输出。当前已补 `pytest.ini` 排除 vendored/generated 依赖树，运行 `python -m pytest -q`，结果 `59 passed`。

## 最小闭环判断

当前最值得优先完成的闭环是：

1. Ryven 中拖出 `Start`、一个 `AgentNode`、`End`
2. 保存节点配置，确保前后端共用同一 `AgentNode.to_dict()` schema
3. `compile_ryven_flow()` 生成 `GraphDefinition`
4. `validate_runnable()` 先做结构校验
5. 图运行器执行 `Start -> AgentNode -> End`
6. UI 显示节点运行状态和最终结果

这条链路完成后，再扩展：
- 多个 AgentNode 串联
- `parallel` / `parallel_reduce`
- nonblocking job
- workspace manifest / 事件流
- 复杂类型检查和 Inspector

## 分层规则

- 属于长期稳定知识：回写到 `knowledge_base/`
- 属于近期推进清单：保留在 `tasks/`
- 属于阶段性历史回顾：追加到 `archive/`
