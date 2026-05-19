# 多 Agent 通信设计短期任务

## 当前定位

多 Agent 蓝图通信与顶层 Agent 治理是当前主线。优先参考本 skill 的 `knowledge_base/core_architecture.md`、`knowledge_base/gulicode_desktop.md`、`knowledge_base/dispatch_workflows.md`，以及同目录保留的 `多agents通信设计.md` 历史设计稿。

旧路径如 `F:\src\ryven_demo\多agents通信设计.md` 只代表早期材料来源，不应作为当前默认项目路径。

## 2026-05-19 MCP Full-Control Update

MCP is now the high-priority path for exposing framework-owned tools to
Codex-backed AgentNodes. Treat it as a protocol adapter over the existing
runtime/workspace/control-plane implementation, not as a new scheduler.

Completed:

1. One live blueprint run starts one local ASGI/uvicorn MCP runtime handle.
2. The handle mounts `framework_ordinary` at `/ordinary/mcp` and
   `framework_control` at `/control/mcp`.
3. Ordinary MCP exposes Workspace tools, scoped `agent_context`,
   `agent_dispatch`, and scoped `join_contribute`.
4. Control MCP covers the public control plane: organization read,
   top-agent context/start-session/ask/explain/utterances, run
   validate/start/status/end, message batch/stage, control-side
   `agent_dispatch`, join create/contribute, and read-only Workspace inspect.
5. Ordinary `agent_dispatch` uses active token message context
   (`outgoing_batch_id`, `required_outgoing_targets`) and does not scan the
   message journal as the primary path.
6. Framework skill/rule injection remains in place. MCP gives callable tools;
   skill/rules still define the Agent behavior contract.
7. Server-side gates enforce `ask`, `start`, `status`, `end`, `utterances`,
   and debug-only `fixture`; the Codex `enabled_tools` list is not the only
   permission boundary.
8. MCP `runtime_end` now routes through the desktop live close callback when
   available, so backend teardown and MCP token close happen together.
9. The opt-in real Codex MCP smoke passes through the full
   `DesktopBlueprintService` live path with planner -> reviewer dispatch.
10. Codex stderr stream noise and large stdout/stderr transport payloads are
    capped for TCP delivery while full diagnostics remain on disk.

Next required work:

1. Reproduce the original timeout-after-panel-message scenario with MCP
   enabled and compare stream events, MCP calls, and runtime context refresh.
2. Add negative auth/session/path-escape tests with the MCP dependency
   installed in the active desktop runtime.
3. Expose top-agent/operator control and utterance audit in GuLiCode UI without
   giving ordinary Agents global control tools.

短期推进范围只聚焦框架掌握 Agent 间通信和调度权：

- Agent 提交意图；
- 框架负责校验、暂存、提醒、批量投递；
- 消息进入下游 Agent 队列，而不是直接调用进程；
- 框架记录事件；
- 顶层 Agent 负责理解、拆解和解释，但不能绕过框架调度、写入、转发、归档和终止控制。

明确暂不优先：

- Ryven 外观；
- 复杂 Inspector；
- Claude adapter；
- Git commit/ref 存储。

## 已完成阶段

### 1. 一对多消息分发运行时 MVP

已落地到 `multi_agent_tcp.graph_runtime.GraphRuntime`：

- `OutgoingMessageBatch`
- `StagedOutgoingMessage`
- `create_outgoing_batch()`
- `stage_outgoing_message()`
- `dispatch_outgoing_batch()`
- `AgentOutgoingTargetsReminder`

已覆盖语义：

- 框架指定 `required_target_node_ids`；
- Agent 只能给本轮 required targets 暂存消息；
- 空消息也算补齐；
- 同一 target 在批次分发前允许覆盖；
- target 未补齐时不投递任何下游；
- source Agent 回到 `idle` 后，框架发 `remaining_targets` 提醒；
- 全部补齐后，框架一次性把完整批次分别加入下游 Agent 消息队列；
- 下游消息仍由 tick 按 idle 状态逐帧 dispatch。

### 2. 图结构生成 agent_connections

已落地到 `GraphDefinition`：

- `agent_connections()` 从普通 AgentNode 到普通 AgentNode 的 `exec` 边生成可通信关系；
- `data` 边、Start/End terminal 边不进入普通 Agent 通信关系；
- `agent_organization_view()` 提供初版组织视图：`graph`、`agents`、`agent_connections`、`start_policy`；
- `start_policy` 明确启动点由顶层 Agent 显式指定，框架只负责校验；
- `GraphRuntime.create_outgoing_batch_from_graph()` 可以基于图结构创建 outgoing batch，并拒绝不可达 target。

### 3. GuLiCode 顶层 Agent 契约骨架

已落地到 `graph_runtime.py`：

- `GuLiCodeTopAgentProfile`
- `TopAgentTask`
- `TopAgentStartPlan`
- `TopAgentPlanValidation`

已覆盖语义：

- 顶层 Agent rule / skill 文本骨架；
- organization context；
- 启动计划校验；
- `agent_descriptions` 必须覆盖所有 AgentNode；
- `start_nodes` 必须由顶层 Agent 显式提交，且必须来自当前 AgentNode；
- `tasks` 必须与 `start_nodes` 对齐；
- 每个 task 必须有 `goal`、`expected_output`、`acceptance`。

当前验证：

```text
python -m pytest test_agent_runtime.py -q
46 passed

python -m pytest test_workspace_api.py test_workspace_manager.py test_agent_runtime.py -q
81 passed
```

### 4. 多对一 fan-in / join 语义运行时基础

已落地到 `GraphRuntime`：

- `JoinBarrier`
- `JoinContribution`
- `create_join_barrier()`
- `submit_join_contribution()`

已覆盖语义：

- `wait-all`：等待所有 required sources 提交贡献；
- `wait-any`：任一 required source 提交即可 ready；
- `quorum`：达到指定成功贡献数即可 ready；
- `timeout`：未 ready 的 barrier 可转为 `timed_out`；
- 同一 source 在 barrier ready 前允许覆盖贡献；
- 贡献聚合 accepted changesets、conflicts、artifacts、reports、test results 和 source metadata；
- 非 required source 被拒绝；
- 已 ready / timed_out / cancelled 的 barrier 拒绝继续提交。

### 5. 状态查询接口运行时基础

已落地到 `GraphRuntime.status_snapshot()`：

- `run` 状态；
- Agent 状态；
- 队列状态；
- outgoing batch 状态；
- join barrier 状态；
- nonblocking job 状态；
- 最近事件；
- workspace jobs / changesets / conflicts / artifacts / reports；
- 可选附带 `GraphDefinition.agent_organization_view()` 组织架构视图。

### 6. 结束接口与最终状态聚合运行时基础

已落地到 `GraphRuntime`：

- `RunEndResult`
- `end_run()`
- `compute_final_status()`

已覆盖动作：

- `complete`
- `cancel`
- `fail`
- `pause`
- `archive_only`

已覆盖最终状态：

- `success`
- `partial_success`
- `failed`
- `cancelled`
- `conflicted`
- `timed_out`

当前验证：

```text
python -m pytest test_agent_runtime.py -q
50 passed

python -m pytest test_workspace_api.py test_workspace_manager.py test_agent_runtime.py -q
85 passed
```

### 7. 非 UI 控制面基础

已落地到 `graph_control.py` 和 `__main__.py`：

- `graph_definition_from_dict()`
- `load_graph_definition()`
- `scoped_organization_view()`
- `GraphRuntimeControlPlane`
- `GraphRuntimeRPCServer`
- CLI: `python -m multi_agent_tcp organization ...`
- CLI: `python -m multi_agent_tcp runtime validate-start ...`
- CLI: `python -m multi_agent_tcp runtime start/status/end ...`
- CLI: `python -m multi_agent_tcp runtime message-batch/message-stage ...`
- CLI: `python -m multi_agent_tcp runtime join-create/join-contribute ...`

已覆盖语义：

- 组织架构可从 graph JSON 本地读取，也可通过 live runtime RPC 读取；
- 顶层 Agent 可读完整组织视图，普通 Agent 可读自身 scoped organization view；
- start plan 可通过 CLI dry-run 校验；
- live runtime RPC 可执行 `organization.read`、`run.validate_start`、`run.start`、`run.status`、`run.end`、`message.create_batch`、`message.stage`、`join.create`、`join.contribute`；
- CLI 只作为 thin client，不复制 `GraphRuntime` 内部语义。

当前验证：

```text
python -m pytest test_graph_control.py -q
3 passed

python -m pytest test_graph_control.py test_agent_runtime.py test_workspace_api.py test_workspace_manager.py -q
88 passed
```

### 8. Fan-in 聚合投递与结束收口

已落地到 `GraphRuntime`：

- `JoinBarrier.aggregate_message_id`
- `JoinBarrierAggregateQueued`
- `JoinBarrierCancelled`
- `TaskCancelled`
- `RunPendingWorkCancelled`

已覆盖语义：

- `create_join_barrier()` 如果拿到目标 `AgentNode`，会保存为汇聚投递目标；
- barrier ready 后，框架自动生成 `join_aggregate` 信封并进入汇聚 Agent 队列；
- 聚合信封包含 `join_id`、required sources、missing sources、source statuses、accepted changesets、conflicts、artifacts、reports、test results 和 contributions；
- `GraphRuntimeControlPlane.join.create` 会把 graph 中的 target node 传给 runtime，因此 RPC / CLI 创建的 join 也能自动投递；
- `end_run("cancel")` / `end_run("fail")` 会取消 queued / dispatching messages、未完成 jobs 和 waiting joins；
- 取消收口会写入事件，供状态查询、顶层 Agent 解释和后续归档使用。

当前验证：

```text
python -m pytest test_agent_runtime.py test_graph_control.py -q
54 passed

python -m pytest test_graph_control.py test_agent_runtime.py test_workspace_api.py test_workspace_manager.py -q
89 passed
```

### 9. 图调度器自动 fan-in 与 complete/archive 归档索引

已落地到 `GraphExecutor` / `GraphRuntime`：

- `GraphExecutor.run_blueprint()` 从单一路径 runner 升级为顺序 DAG runner；
- AgentNode 只有在所有 exec 上游完成后才会执行；
- 多个 AgentNode 上游进入同一个 AgentNode 时，调度器自动创建 `JoinBarrier`；
- 调度器自动把上游结果作为 join contribution 提交；
- barrier ready 后生成 `join_aggregate` 信封并同步 dispatch 给汇聚 Agent；
- `GraphRuntime.end_run("complete")` 会生成 `shared/reports/final_report.json`；
- 如果传入 `archive_manager` / `archive_run`，`complete` 和 `archive_only` 会调用已有 `archive_run()`，写入 long-term archive manifest；
- `RunEndResult.summary.final_report_path` 指向归档后的真实 report 路径；
- 事件新增 `FinalReportPublished`、`RunArchiveIndexed`。

当前验证：

```text
python -m pytest test_agent_runtime.py test_graph_control.py -q
58 passed

python -m pytest test_graph_control.py test_agent_runtime.py test_workspace_api.py test_workspace_manager.py -q
93 passed
```

## 下一步短期任务

### 2026-05-11 测试优先级补充

本轮对话后，短期重心先放在测试覆盖和可重复启动验证上。

1. 复杂蓝图测试样例：
   - [DONE] 先生成一张覆盖多种连接情况的蓝图图示；
   - [DONE] 本地保存中文 SVG：`docs/blueprints/complex_test_blueprint.svg`；
   - [TODO] 将 SVG 对应结构整理成机器可读 blueprint fixture；
   - [TODO] fixture 至少覆盖串行、一对多 fan-out、多对一 fan-in、条件分支、审查失败回流、集成失败回流、旁路事件、workspace 聚合和最终归档。

2. 复杂蓝图运行时测试：
   - [TODO] 覆盖 `GraphDefinition.agent_organization_view()` 对复杂图的组织视图输出；
   - [TODO] 覆盖 `TopAgentStartPlan` 对复杂图 start nodes、agent descriptions、tasks 的校验；
   - [TODO] 覆盖 `GraphRuntimeControlPlane` start/status/end 在复杂图上的表现；
   - [TODO] 覆盖 outgoing batch 的 required targets、remaining targets、完整批次投递；
   - [TODO] 覆盖 join barrier 的 wait-all / wait-any / quorum / timeout 至少一组组合场景；
   - [TODO] 覆盖失败归因、补丁重试、重新投递测试/实现节点的闭环；
   - [TODO] 覆盖 workspace changeset、artifact、report、test result 进入 join aggregate 和 final report。

3. GuLiCode 顶层测试环境拉起：
   - [DONE] 已验证 `OPENCODE_CONFIG_CONTENT` 能注册 `aiapi_world/gpt-5.5`；
   - [DONE] 已验证 Electron dev 能按测试环境变量拉起 GuLiCode，并进入 sidecar ready / init done；
   - [TODO] 把手动 smoke 流程沉淀成脚本或测试 helper；
   - [TODO] smoke helper 应只在子进程环境中设置测试变量，完成后清理 `bun` / `electron` / `node` 子进程；
   - [TODO] smoke helper 输出只报告 provider/model、ready 阶段和日志路径，不输出凭据。

4. GuLiCode 启动规则来源：
   - [DONE] 固定规则已写入 `knowledge_base/gulicode_desktop.md` 的 `测试环境顶层 GuLiCode 启动规则`；
   - [DONE] `SKILL.md` Query Map 已指向该规则；
   - [TODO] 后续所有 GuLiCode 测试启动优先读取该规则，不再临时猜测 provider/baseURL/model/variant。

1. 暴露稳定组织架构接口：
   - [DONE] 将 `agent_organization_view()` 包装成 runtime/RPC/CLI 可调用接口；
   - [DONE] 顶层 Agent 可读取全图、Agent 列表、边、scope、agent_connections；
   - [DONE] 普通 Agent 只读自身相关组织视图；
   - [TODO] 接入真实长生命周期 run 状态与权限 token 策略。

2. 实现开始接口：
   - [DONE] 接收 `TopAgentStartPlan`；
   - [DONE] 调用 `GuLiCodeTopAgentProfile.validate_start_plan()`；
   - [DONE] 支持从 JSON profile 文件加载 GuLiCode 顶层 Agent rule / skill / permissions；
   - [DONE] 通过 `runtime top-agent-context` 渲染顶层 Agent 可读的 profile + organization context；
   - [DONE] 给指定 start_nodes 投递初始任务；
   - [DONE] 将 user goal、agent descriptions、organization view、start plan、top-agent profile 和 queued initial messages 记录到 runtime run manifest；
   - [DONE] 有 `WorkspaceManifest` 和 `manifest_path` 时写出 workspace JSON。

3. 将消息分发接口暴露给普通 Agent：
   - [DONE] 通过 runtime-owned control plane / RPC / CLI 暴露 `agent.dispatch` / `runtime agent-dispatch` 单步分发入口；
   - [DONE] 普通 Agent 只能向图上可达下游 target 发消息；
   - [DONE] 返回 `staged`、`overwritten`、`ready_to_dispatch`、`remaining_targets`；
   - [TODO] 进一步绑定到当前任务信封的 `required_outgoing_targets` 与 ordinary-Agent tool context。

4. 将 fan-in / join 语义接入图调度器与 RPC/CLI：
   - [DONE] 基于 exec 边自动创建 fan-in barrier；
   - [DONE] barrier ready 后向汇聚 Agent 投递聚合信封；
   - [DONE] timeout / conflict / partial completion 进入运行时状态与事件流；
   - [DONE] 通过 runtime-owned control plane / RPC / CLI 暴露创建、贡献和查询基础。

5. 将状态查询接口暴露到 RPC/CLI/UI：
   - [DONE] 包装 `GraphRuntime.status_snapshot()` 到 runtime control plane / RPC / CLI；
   - [DONE] 顶层 Agent 可读取全局状态；
   - [TODO] 普通 Agent 状态读取权限进一步收敛；
   - [DEFERRED] UI 可展示 run / agent / queue / outgoing / join / workspace 视图。

6. 将结束接口接入 run 生命周期与归档：
   - [DONE] 包装 `GraphRuntime.end_run()` 到 runtime control plane / RPC / CLI；
   - [DONE] cancel / fail 取消未完成 dispatch task、queued/dispatching messages、job 和 waiting barrier；
   - [DONE] complete 后触发最终报告与归档索引；
   - [DONE] archive_only 接入长期共享工作区索引。

## 归档位置

阶段性落地记录追加到：

- `archive/guli_desktop_ui_archive.md`

稳定长期知识后续再沉淀到：

- `knowledge_base/multi_cli_workflow.md`
- `knowledge_base/guli_desktop_ui.md`

---

## 2026-05-09 worker reply / utterance boundary update

Completed:

- Worker replies are reduced to framework-private `AgentUtterance` receipts with `agent_id`, `node_id`, `said`, receive time, and optional task/message identity.
- Raw worker reply payloads, Codex stdout/stderr, and adapter debug bodies are no longer treated as Agent-to-Agent communication or framework facts.
- `top_agent.utterances` is exposed through `GraphRuntimeControlPlane`, RPC, and CLI as `runtime top-agent-utterances`.
- `GuLiCodeTopAgentProfile` default permissions now include `utterances`; profiles without it are denied access to the utterance interface.
- Top-agent and ordinary-agent baseline rule/skill text now describes the utterance boundary:
  - top Agent may inspect utterances through the dedicated interface;
  - ordinary Agents do not receive utterance records or the inspection tool;
  - durable information must be submitted through `agent.dispatch`, Workspace API, `join.contribute`, or later structured task APIs.

Still pending:

- GuLiCode UI should expose utterances only as a top-agent/operator audit view, not as ordinary Agent message context.

## 2026-05-11 prompt/context slimming update

Completed:

- Ordinary-Agent message context is now slimmer. Dynamic `framework_context` keeps `agent_node_id`, `agent_id`, upstream/downstream summaries, compact scoped organization, and the current message envelope.
- Stable tool/rule instructions have moved to framework skill / startup context rather than being repeated in every `framework_context`.
- `reachable_downstream_targets` was removed from the message envelope; use `downstream_agents` plus `required_outgoing_targets`.
- Top-Agent context now uses compact `runtime_context()` and `agent_organization_summary()` instead of forwarding full launch configuration.
- Agent launch materialization now emits `prompt_execution_context`, and Codex/CodeMaker adapters prefer it when formatting actual prompts.
- Full `execution_context` remains available internally for runtime/adapter validation and debugging.

Validation observed in repository:

```text
python -m pytest -q
116 passed
```
