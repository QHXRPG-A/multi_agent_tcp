# 蓝图集成变更归档

本文件只记录 `multi_agent_tcp` 在蓝图 / Ryven / vendor GUI 方向上的历史变更，便于后续回顾。

## 变更记录

### 2026-05-08 — 多 Agent 通信设计进入短期任务主线并完成第一阶段落地

#### 摘要

1. 将 `F:\src\ryven_demo\多agents通信设计.md` 明确设为当前多 Agent 蓝图通信与顶层 Agent 治理的首要开发手册。
2. 新增短期任务文档：
   - `tasks/multi_agent_communication_tasks.md`
   - 用于跟踪框架掌握 Agent 间通信与调度权的近期任务。
3. 完成一对多消息分发运行时 MVP：
   - `OutgoingMessageBatch`
   - `StagedOutgoingMessage`
   - `GraphRuntime.create_outgoing_batch()`
   - `GraphRuntime.stage_outgoing_message()`
   - `GraphRuntime.dispatch_outgoing_batch()`
   - `AgentOutgoingTargetsReminder`
4. 明确批量投递语义：
   - Agent 只提交发往 required targets 的消息意图；
   - 框架暂存、校验、提醒、覆盖、补齐；
   - 全部补齐后，完整批次分别进入下游 Agent 消息队列；
   - 后续仍由 tick 按 idle 状态逐帧 dispatch，不直接调用下游进程。
5. 完成图结构通信关系第一版：
   - `GraphDefinition.agent_connections()` 从普通 AgentNode 到普通 AgentNode 的 `exec` 边生成可通信关系；
   - `data` 边和 Start/End terminal 边不进入普通 Agent 通信关系；
   - `GraphRuntime.create_outgoing_batch_from_graph()` 基于图结构校验 required targets。
6. 修正启动点语义：
   - 当前不再把 Start/End 视为启动决策来源；
   - `agent_organization_view()` 不再输出 `recommended_start_nodes`；
   - 新增 `start_policy`，明确启动点由 GuLiCode / 顶层 Agent 显式指定，框架只负责校验。
7. 完成 GuLiCode 顶层 Agent 契约骨架：
   - `GuLiCodeTopAgentProfile`
   - `TopAgentTask`
   - `TopAgentStartPlan`
   - `TopAgentPlanValidation`
   - 覆盖 rule / skill 文本骨架、organization context、启动计划校验。

#### 涉及

- `multi_agent_tcp/graph_runtime.py`
- `multi_agent_tcp/test_agent_runtime.py`
- `multi_agent_tcp/__init__.py`
- `F:\src\ryven_demo\多agents通信设计.md`
- `tasks/current_goals.md`
- `tasks/node_runtime_tasks.md`
- `tasks/multi_agent_communication_tasks.md`

#### 验证

```text
python -m pytest test_agent_runtime.py -q
46 passed

python -m pytest test_workspace_api.py test_workspace_manager.py test_agent_runtime.py -q
81 passed
```

#### 当前结论

多 Agent 蓝图的短期重心已经从“单 Agent 最小执行链路”转到“框架拥有通信与调度权”。顶层 Agent 负责理解、拆解、解释和提交启动计划；普通 Agent 只处理局部任务并提交消息意图；框架负责校验、暂存、补齐提醒、队列投递、事件记录和后续最终聚合。

下一步应继续暴露稳定组织架构接口、开始接口、普通 Agent 消息分发 RPC/tool、多对一 fan-in / join、状态查询接口和结束/最终聚合接口。

---

### 2026-05-04 — Ryven Flow 编译为 GraphDefinition 第一版

#### 摘要
1. 新增 `compile_ryven_flow()`，把 live Ryven flow 编译为后端 `GraphDefinition`，形成“Ryven 前端 + GraphRuntime 后端 + GraphDefinition 中间层”的第一阶段桥接。
2. 编译映射规则落地：`BlueprintStart` / `BlueprintEnd` -> `BlueprintTerminalNode`，Ryven `AgentNode` wrapper -> 后端 `graph_runtime.AgentNode`，Ryven connection -> `GraphEdge`。
3. `GraphEdge` 新增 `edge_type`，从 Ryven port `type_` 保留 `exec` / `data` 语义；端口 label 会进入 `output_port` / `input_port`。
4. `GraphDefinition.validate_runnable()` 调整为只使用 `exec` 边校验 Start -> End 控制流路径，避免把 data 线误判为可运行路径。
5. AgentNode 前后端一致性边界明确：Ryven wrapper 保存后端 `AgentNode.to_dict()` schema，编译时通过 `RuntimeAgentNode.from_dict()` 还原；UI 当前只暴露后端 schema 的字段子集。
6. 当前完成度结论更新：第一步“Ryven Flow -> `GraphDefinition` 编译 + `validate_runnable`”已完成；第二步应推进只跑 blocking `AgentNode` 的最小链路。

#### 涉及
- `multi_agent_tcp/ryven_blueprint.py`
- `multi_agent_tcp/graph_runtime.py`
- `multi_agent_tcp/ryven_blueprint_nodes/nodes.py`
- `multi_agent_tcp/test_agent_runtime.py`
- legacy Ryven node/UI notes now live only in git history; the active skill snapshot no longer keeps a dedicated long-term knowledge file for this track
- `tasks/node_runtime_tasks.md`
- legacy Ryven/editor short-term tasks were removed from the active skill snapshot on 2026-05-13

#### 验证
- `python -m pytest -q test_agent_runtime.py test_registry_skill_selection.py test_skill_space.py test_workspace_manager.py`：`42 passed`
- 覆盖 Ryven live flow 编译、Start/End terminal、两个 AgentNode、`exec` 边、`data` 边与 `validate_runnable()` 的 exec-only 路径校验。

---

### 2026-05-04 — AgentNode 接入 Ryven 节点 UI 第一版

#### 摘要
1. 新增本地 Ryven nodes package 路径 `multi_agent_tcp/ryven_blueprint_nodes/`，通过 `export_nodes()` 导出 `BlueprintStart`、`BlueprintEnd` 和可拖拽的 Ryven wrapper `AgentNode`。
2. `ryven_launcher.py` 默认追加 `-n ryven_blueprint_nodes`，因此 `python -m multi_agent_tcp ryven` 启动后左侧节点库常驻显示 `AgentNode`；Start/End 被标记为隐藏节点，不进入节点库。
3. 新增 `ryven_blueprint.py` hook：自动为每个 flow 补 Start/End，过滤节点库隐藏项，并在 UI 删除路径、`RemoveComponents_Command` 和 core `Flow.remove_node()` 层保护 Start/End 不被删除。
4. `graph_runtime.GraphDefinition` 新增 `BlueprintTerminalNode`、`terminal_nodes` 与 `validate_runnable()`，后端可表达“恰好一个 start、恰好一个 end、DAG、且 start 到 end 有有向路径”的 runnable blueprint 约束。
5. 结论更新：原始 `GraphDefinition` 数据结构不完整支持 Start/End 机制；新增 terminal node 语义和 runnable 校验后可以支持。
6. 当时针对该轮变更曾补充一份 Ryven 节点/UI 长期知识文档，用于记录节点包、flow 生命周期、删除保护、序列化和 GUI/no-gui 验证注意事项；该文档已于 2026-05-13 从当前 active skill snapshot 退役。

#### 涉及
- `multi_agent_tcp/ryven_blueprint_nodes/nodes.py`
- `multi_agent_tcp/ryven_blueprint_nodes/gui.py`
- `multi_agent_tcp/ryven_blueprint.py`
- `multi_agent_tcp/ryven_launcher.py`
- `multi_agent_tcp/graph_runtime.py`
- historical Ryven node/UI notes (retired from the active skill snapshot on 2026-05-13)

#### 验证
- `python -m pytest D:\agents\multi_agent_tcp\test_agent_runtime.py`：`24 passed`
- no-gui 模式下 `import_nodes_package(directory=ryven_blueprint_nodes)` 可导出 `Start / End / AgentNode`
- GUI 独立导入会受 Ryven code editor 初始化断言影响，正式验证路径应使用 `python -m multi_agent_tcp ryven`

---

### 2026-04-26 — 仅文档/skill 同步：对齐当前仓库路径与 vendored Ryven 工作结论

#### 摘要
1. 路径与入口校正：补充当前仓库常见路径 `d:\agents\multi_agent_tcp`，并明确 `multi_agent_tcp/__main__.py`、`multi_agent_tcp/cluster.py`、`multi_agent_tcp/registry.py` 位于根包目录。
2. 文档对齐范围补充：归档时除代码外，同时对照 `README.md`、`GUIDE_FOR_AGENTS.md`、`examples/HOWTO.txt`。
3. vendored Ryven 结论沉淀：记录 `vendor/ryven`、`vendor/ryvencore_qt`、`.venv_vendor_ryven` 的职责与用途，并确认 GUI 启动验证和中文界面定制已完成。
4. 归档协议增强：若后续工作涉及 `vendor/` 方向的重要运行基线、启动验证或 GUI 汉化，应继续沉淀到对应归档中。

#### 涉及
- `SKILL.md`
- `vendor/ryven`
- `vendor/ryvencore_qt`
- `.venv_vendor_ryven`

---

### 2026-04-25 — 归档结构重组：新增专题文档并同步 Ryven 工作结论

#### 摘要
1. 在 skill 目录下新增 `archive/` 子目录，用于按主题拆分长期归档。
2. 新增蓝图专题归档，记录 Ryven 蓝图系统引入、许可判断、vendoring 结构与启动验证。
3. 确认 `Ryven` / `ryven-editor` / `ryvencore-qt` 为 MIT，可在项目中 vendoring 并深度修改，但需保留许可证与来源说明。
4. 验证 vendored Ryven 可在独立虚拟环境中启动，作为后续蓝图系统二开的运行基线。

#### 涉及
- `archive/blueprint_integration_archive.md`
- `multi_agent_tcp/vendor/ryven`
- `multi_agent_tcp/vendor/ryvencore_qt`

---

## 当前结论

### 背景

本方向的工作围绕在 `multi_agent_tcp` 内建立一个可内置、可深改的 Python 可视化蓝图/节点系统基线，最终选择将 Ryven 作为蓝图侧参考实现，并将其源码 vendoring 到项目目录中。

### 结论

- Ryven 主仓与 `ryven-editor`、`ryvencore-qt` 许可证均为 MIT，可复制进项目并做大改，但需保留版权与许可证文本。
- 顶层 README 还提到外部依赖 `ryvencore` 为 LGPL-2.1；本轮未把其源码 vendoring 进项目，仅在运行环境中安装依赖。
- 已将适合深改的核心源码复制到：
  - `multi_agent_tcp/vendor/ryven/ryven/`
  - `multi_agent_tcp/vendor/ryvencore_qt/ryvencore_qt/`
- 已保留许可证与来源说明：
  - `multi_agent_tcp/vendor/ryven/LICENSE`
  - `multi_agent_tcp/vendor/ryven/LICENSE.editor`
  - `multi_agent_tcp/vendor/ryven/LICENSE.ryvencore_qt`
  - `multi_agent_tcp/vendor/ryven/README.vendor.md`

### 结构规划

推荐继续保持以下结构：

```text
multi_agent_tcp/
  vendor/
    ryven/
      ryven/
      LICENSE*
      README.vendor.md
    ryvencore_qt/
      ryvencore_qt/
```

其设计目标是：

- 让上游来源和本地自改代码边界清晰
- 保留可运行蓝图基线
- 避免把第三方依赖的 `site-packages`、虚拟环境或安装元数据一并提交进仓库

### 启动验证结论

本轮已完成 vendored Ryven 的启动验证：

- 新建 `multi_agent_tcp/.venv_vendor_ryven`
- 安装运行依赖：`PySide6`、`qtpy`、`waiting`、`textdistance`、`Jinja2`、`Pygments`、`packaging`、`ryvencore`
- 通过 `PYTHONPATH` 显式指向 vendored 目录启动
- 验证到 GUI 进程可进入运行态

当前的 vendored Ryven 可作为后续多模态蓝图系统二开的启动基线。

### 后续建议

1. 继续让 vendored Ryven 完全自洽，减少对原始 `d:\agents\Ryven` 安装元数据的借用。
2. 为 `multi_agent_tcp` 增加自己的蓝图启动入口和节点包。
3. 在多模态方向上优先规划：
   - 节点端口类型
   - 媒体引用/大对象传输方式
   - 图执行与缓存
# 2026-05-06 Archive Note - Blueprint Workspace API and shared read/write locks

## Summary

1. Aligned blueprint workspace semantics around three run-scoped roles:
   - `agents/<agent_id>/private/` is disposable private scratch and CLI state.
   - `shared/code/`, `shared/artifacts/`, and `shared/reports/` are archived outcome areas.
   - private scratch is discarded before archive and is not auto-merged as output.
2. Replaced "teach agents physical shared paths" with a framework-maintained Workspace API contract:
   - repository API document: `docs/workspace_api.md`;
   - controlled CLI: `workspace_api.py` with `publish`, `publish-file`, `read`, and `list`;
   - AgentNode startup injects the Workspace API document and command contract;
   - AgentNode `cwd` is private scratch, while shared publishing goes through the API.
3. The blueprint runtime writes `shared/reports/blueprint_result.json` before archive.
4. Codex and Codex adapters both consume injected `prompt_preamble` and `execution_context`.
5. Shared writes go through manager-owned manifest/lease APIs.
6. Added per-path read/write locking:
   - concurrent readers are allowed;
   - writers block readers and writers;
   - active readers block writers.
7. Added path write versions:
   - `read --json` returns `version`;
   - `publish --expected-version N` and `publish-file --expected-version N` fail on stale writes.

## Affected Code

- `multi_agent_tcp/workspace_manager.py`
- `multi_agent_tcp/workspace_api.py`

---

# 2026-05-11 Archive Note - Prompt-facing context slimming for ordinary agents and top agent

## Summary

1. Split runtime launch context into internal and prompt-facing views:
   - `execution_context` remains the full framework/internal launch record for adapters and runtime inspection;
   - `prompt_execution_context` is the reduced subset that is merged into the actual CLI prompt.
2. Reduced ordinary-Agent prompt injection:
   - removed raw launch-path exposure such as `project_context`, `checkout_path`, `codex_home`, and other private directories from the prompt-facing view;
   - kept only the minimal code-workspace and workspace-API guidance needed for execution;
   - trimmed `framework_context` to the dynamic batch/organization fields needed for current message handling.
3. Reduced top-Agent prompt-facing organization context:
   - `GuLiCodeTopAgentProfile.organization_context()` now returns a compact runtime-facing top-agent view;
   - the prompt-facing organization summary keeps governance-relevant graph and agent-scoping data without launch internals.
4. Preserved internal diagnostics:
   - the full execution context is still available to the runtime and adapters;
   - tests continue to validate internal launch materialization and actual prompt-merging behavior.
5. Added/updated adapter support:
   - Codex and Codex bridges now prefer `prompt_execution_context` when formatting prompts;
   - both bridges fall back to the full `execution_context` if the reduced prompt view is absent.

## Affected Code

- `multi_agent_tcp/agent_launch_context.py`
- `multi_agent_tcp/graph_control.py`
- `multi_agent_tcp/graph_runtime.py`
- `multi_agent_tcp/codex_bridge.py`
- `multi_agent_tcp/codex_bridge.py`
- `multi_agent_tcp/test_graph_control.py`
- `multi_agent_tcp/test_agent_runtime.py`

## Validation

```text
python -m pytest -q
116 passed
```
- `multi_agent_tcp/ryven_blueprint.py`
- `multi_agent_tcp/codex_bridge.py`
- `multi_agent_tcp/codex_bridge.py`
- `multi_agent_tcp/docs/workspace_api.md`
- `multi_agent_tcp/test_workspace_api.py`
- `multi_agent_tcp/test_workspace_manager.py`
- `multi_agent_tcp/test_agent_runtime.py`
- `multi_agent_tcp/test_skill_space.py`
- `multi_agent_tcp/pytest.ini`

## Validation

- `python -m py_compile workspace_manager.py workspace_api.py test_workspace_manager.py test_workspace_api.py ryven_blueprint.py`
- Direct scripts verified text publishing, binary publishing, concurrent readers, reader-blocks-writer, writer-blocks-reader, and stale version conflict.
- Added pytest coverage for Workspace API binary stale-version conflicts, API-level reader/writer blocking, active-reader publish blocking, and path escape rejection.
- Added `pytest.ini` so project pytest runs do not collect vendored Dulwich, generated `node_modules`, or nested `opencode` tests.
- `python -m pytest -q test_workspace_api.py test_workspace_manager.py`: `22 passed`
- `python -m pytest -q`: `59 passed`

## Current Conclusion

The minimum workspace-control loop is now implemented as a controlled local CLI API plus prompt/API-document injection. This is stronger than plain prompt guidance because shared outcomes go through manager-owned lease, manifest, and version checks. It is still not a full security boundary; a stronger future version should move the Workspace API behind broker/runtime-owned RPC or tool calls and add OS/sandbox-level filesystem restrictions.

---

# 2026-05-07 Archive Note - Blueprint agent workdir semantics and runtime-owned Workspace RPC

## Summary

1. Reframed `AgentNode.cwd` from private scratch to the assigned user project working directory:
   - `cwd="."` resolves to the current blueprint project path;
   - relative `cwd` values resolve under the blueprint project path;
   - agents are allowed to directly edit files under their assigned project workdir.
2. Kept private agent directories for framework-owned state only:
   - Workspace API context file;
   - CLI-local state such as temporary `CODEX_HOME`;
   - copied skill views and cache material.
3. Added runtime-owned Workspace RPC:
   - new `workspace_rpc.py` exposes a local token-guarded RPC service for run-scoped and long-term shared workspace operations;
   - `workspace_api.py` remains the CLI entry point, but can now act as a thin RPC client when context contains `transport=rpc`;
   - blueprint agent context no longer needs shared workspace physical paths.
4. Added `run` and `long_term` Workspace API scopes:
   - `run` targets temporary per-blueprint shared outputs;
   - `long_term` targets project-level shared memory/artifacts retained across runs.
5. Codex workers now default to project workdir execution with `sandbox=workspace-write` unless explicitly overridden.
6. Rejected the earlier idea of a plain `cwd` data input on AgentNode:
   - all agents should be started at blueprint launch;
   - downstream workdir reassignment is not a data-edge convention.
7. Added a super-agent-only workdir reassignment primitive:
   - `SuperAgentProfile.can_assign_downstream_workdir`;
   - optional `assignable_workdir_roots`;
   - `GraphRuntime.assign_agent_workdir()`;
   - `CLIWorkerBackend.restart_worker()` kills and relaunches a worker with the same config plus the new `cwd`.
8. Added basic agent busy tracking:
   - blocking messages and nonblocking jobs increment `AgentInstance.busy_count`;
   - workdir reassignment returns `AGENT_BUSY` when the target agent is executing.
9. Added high-priority short-term tasks for the full blueprint loop:
   - complete graph scheduling;
   - collect project workdir changes;
   - expose super-agent workdir assignment as a framework tool/API;
   - harden agent state tracking;
   - define structured task-completion messages;
   - emit durable workspace/task events;
   - define archive policy;
   - implement auto-finish conditions;
   - surface full run state in UI.

## Affected Code

- `multi_agent_tcp/workspace_rpc.py`
- `multi_agent_tcp/workspace_api.py`
- `multi_agent_tcp/ryven_blueprint.py`
- `multi_agent_tcp/graph_runtime.py`
- `multi_agent_tcp/cluster.py`
- `multi_agent_tcp/skill_space.py`
- `multi_agent_tcp/ryven_blueprint_nodes/gui.py`
- `multi_agent_tcp/ryven_blueprint_nodes/nodes.py`
- `multi_agent_tcp/docs/workspace_api.md`
- `multi_agent_tcp/test_workspace_api.py`
- `multi_agent_tcp/test_agent_runtime.py`
- `multi_agent_tcp/KM_docs/skills-snapshot/tasks/current_goals.md`

## Validation

- `python -m pytest -q`: `64 passed`

## Current Conclusion

The project now treats the user project workdir and shared workspaces as separate surfaces. Agents may directly edit their assigned project workdir, while temporary and long-term shared collaboration data goes through the framework Workspace API. Blueprint runs start all agents up front; later workdir reassignment is reserved for super-agent framework calls and must fail when the target agent is busy.

Remaining short-term work is to expose the reassignment primitive to super agents as a real tool/RPC, collect and attribute direct project workdir modifications, define structured completion messages, and implement durable event/auto-finish/archive policies.

---

# 2026-05-07 Archive Note - Runtime tick, agent states, queued messages, and Codex AgentNode output

## Summary

1. Added a framework-owned runtime tick concept:
   - `GraphRuntime.tick()` is the frame-level maintenance point;
   - the default background tick interval is `0.5` seconds;
   - `GraphRuntime.__aenter__()` starts the tick loop, and callers can also invoke `tick()` manually in tests or host runtimes.
2. Expanded `AgentInstance` from simple `busy_count` tracking into a small runtime state machine:
   - states include `created`, `starting`, `idle`, `queued`, `dispatching`, `running`, `waiting_for_reply`, `processing_reply`, `failed`, `timed_out`, `cancelled`, `disconnected`, `restarting`, `stopping`, and `stopped`;
   - each instance records `state_history`, `current_message_id`, `last_error`, timestamps, and whether it can currently accept another message.
3. Added framework-owned per-agent message queues:
   - if a target AgentNode is not currently able to accept a message, `send_agent_message()` stores a `PendingAgentMessage`;
   - the pending record stores message body, source node/agent, target node/agent, timeout, status, result, error, and timing;
   - each tick dispatches at most one queued message per idle agent, preserving FIFO ordering.
4. Confirmed the intended display fields for Codex-backed AgentNode output:
   - `reply.body.codex.final_text` is the framework-preferred final agent reply;
   - `reply.body.codex.last_message` is the Codex CLI `--output-last-message` result and is used as the primary source for `final_text`;
   - `reply.body.codex.stdout` is the raw JSONL event stream and is useful for archive/debug;
   - `reply.body.codex.stderr` is useful for diagnostics but can contain large CLI warnings and remote plugin sync noise.
5. Fixed a Windows Codex CLI launch compatibility issue:
   - npm may resolve bare `codex` to `codex.ps1`;
   - Python `create_subprocess_exec()` cannot directly execute a `.ps1` script through Windows `CreateProcess`;
   - `codex_bridge.py` now prefers matching `.cmd`/`.exe`/`.bat` shims on Windows, and maps explicit `.ps1` paths to a sibling `.cmd` when available.
6. Produced real AgentNode/Codex output samples in the working repository:
   - `agentnode_codex_output_sample.json` for explicit `codex.cmd`;
   - `agentnode_codex_auto_command_output_sample.json` for bare `command="codex"` after shim resolution.

## Affected Code

- `multi_agent_tcp/graph_runtime.py`
- `multi_agent_tcp/codex_bridge.py`
- `multi_agent_tcp/test_agent_runtime.py`
- `multi_agent_tcp/__init__.py`

## Validation

- `python -m pytest test_agent_runtime.py -q`: `38 passed`
- `python -m pytest test_workspace_api.py test_workspace_manager.py test_agent_runtime.py -q`: `72 passed`
- Manual AgentNode -> GraphRuntime -> Codex worker run with `command="codex"` returned `reply.body.codex.final_text == "CODEX_AUTO_COMMAND_OK"`.

## Current Conclusion

The runtime now has a first framework-level scheduling heartbeat and enough agent state vocabulary to reason about when a CLI-backed AgentNode can accept work. Messages that arrive while an agent is busy are no longer dropped or forced through immediately; they are retained by the framework and released one at a time on later ticks.

The next highest-priority work is no longer basic busy tracking. The short-term center of gravity should move to complete graph scheduling: parallel execution, fan-out/fan-in, condition/switch routing, nonblocking joins, and deterministic final state aggregation.

---

# 2026-05-08 Archive Note - Multi-Agent communication control plane, fan-in scheduling, and final archive indexing

## Summary

This round moved the multi-Agent blueprint communication design from document-only semantics into runtime-owned primitives, non-UI control-plane APIs, deterministic fan-in scheduling, and run-finalization archive indexing.

The current contract is:

```text
top Agent / GuLiCode
  -> reads organization view
  -> validates and submits start plan
  -> queries runtime status
  -> requests end / pause / cancel / archive

ordinary AgentNode
  -> receives queued framework messages
  -> stages outgoing messages only for required targets
  -> contributes structured join results

framework runtime
  -> owns queues, joins, dispatch, status, final aggregation, report, archive
```

## Landed

1. Added framework-owned one-to-many message staging:
   - `OutgoingMessageBatch`
   - `StagedOutgoingMessage`
   - `create_outgoing_batch()`
   - `stage_outgoing_message()`
   - `dispatch_outgoing_batch()`
   - `AgentOutgoingTargetsReminder`
   - complete batches are queued into downstream Agent message queues instead of direct process calls.
2. Added graph-derived Agent communication topology:
   - `GraphDefinition.agent_connections()` derives ordinary Agent-to-Agent exec links;
   - `GraphDefinition.agent_organization_view()` exposes graph, agents, connections, and top-Agent start policy;
   - `GraphRuntime.create_outgoing_batch_from_graph()` validates required targets against graph-derived reachability.
3. Added GuLiCode/top-Agent contract skeleton:
   - `GuLiCodeTopAgentProfile`
   - `TopAgentStartPlan`
   - `TopAgentTask`
   - `TopAgentPlanValidation`
   - start plans require complete Agent descriptions, explicit start nodes, aligned tasks, and required task fields.
4. Added multi-source fan-in runtime primitives:
   - `JoinBarrier`
   - `JoinContribution`
   - `create_join_barrier()`
   - `submit_join_contribution()`
   - policies: `wait-all`, `wait-any`, `quorum`, and timeout;
   - contributions aggregate source metadata, accepted changesets, conflicts, artifacts, reports, and test results.
5. Added automatic fan-in aggregate delivery:
   - when a ready join has a target AgentNode, the runtime queues a `join_aggregate` envelope for the merge Agent;
   - `dispatch_queued_message_now()` lets the graph executor synchronously dispatch that generated aggregate when needed;
   - events include `JoinBarrierAggregateQueued`.
6. Added runtime status and finalization APIs:
   - `GraphRuntime.status_snapshot()`;
   - `RunEndResult`;
   - `GraphRuntime.end_run()`;
   - `compute_final_status()`;
   - final states: `success`, `partial_success`, `failed`, `cancelled`, `conflicted`, `timed_out`.
7. Added cancellation / failure cleanup:
   - `cancel` / `fail` now cancel queued or dispatching messages, unfinished jobs, and waiting joins;
   - events include `TaskCancelled`, `JoinBarrierCancelled`, and `RunPendingWorkCancelled`.
8. Added non-UI runtime control plane:
   - new `graph_control.py`;
   - `graph_definition_from_dict()`;
   - `scoped_organization_view()`;
   - `GraphRuntimeControlPlane`;
   - `GraphRuntimeRPCServer`;
   - CLI thin clients: `organization`, `runtime validate-start`, `runtime start/status/end`, `runtime message-batch/message-stage`, and `runtime join-create/join-contribute`.
9. Upgraded `GraphExecutor.run_blueprint()`:
   - from minimal single-path execution to deterministic sequential DAG execution;
   - AgentNodes wait for all exec predecessors;
   - multi-Agent upstreams automatically create a join barrier;
   - upstream results are submitted as join contributions;
   - the generated `join_aggregate` is dispatched to the merge Agent.
10. Added final report and archive indexing:
   - `complete` writes `shared/reports/final_report.json`;
   - when `archive_manager` and `archive_run` are available, `complete` and `archive_only` call the existing workspace manager `archive_run()` flow;
   - long-term archive manifest indexing reuses the established shared archive mechanism;
   - `RunEndResult.summary.final_report_path` points at the archived final report path when the run is moved.

## Affected Code

- `multi_agent_tcp/graph_runtime.py`
- `multi_agent_tcp/graph_control.py`
- `multi_agent_tcp/__main__.py`
- `multi_agent_tcp/__init__.py`
- `multi_agent_tcp/test_agent_runtime.py`
- `multi_agent_tcp/test_graph_control.py`

## Validation

```text
python -m pytest test_agent_runtime.py test_graph_control.py -q
56 passed

python -m pytest test_graph_control.py test_agent_runtime.py test_workspace_api.py test_workspace_manager.py -q
91 passed
```

## Current Conclusion

The non-UI runtime core now owns the essential multi-Agent communication loop:

- outgoing one-to-many handoff is framework staged and complete-batch dispatched;
- multi-source fan-in is represented by join barriers and structured contributions;
- multi-input exec joins are automatically created by the graph executor;
- status and end controls are available through a runtime control plane, RPC server, and CLI thin clients;
- completion can publish a final report and index the run through the long-term archive flow.

Remaining short-term work should focus on surfaces rather than core semantics:

1. Persist top-Agent profile/rule/skill files instead of keeping the current skeleton only in code.
2. Wire the non-UI control plane into a real long-lived GuLiCode/top-Agent session.
3. Expose ordinary-Agent message staging through Workspace RPC or a runtime-owned tool context.
4. Keep UI surfacing deferred until the non-UI control plane stabilizes further.
