# Agents 架构变更归档

本文件只记录 `multi_agent_tcp` 多 agent 调度主架构方向上的历史变更，便于后续回顾。

## 变更记录

### 2026-05-08 — 多 Agent 通信控制面、顶层 Agent profile 与 run start manifest

#### 摘要
1. 围绕 `多agents通信设计.md`，将顶层 Agent / 普通 Agent 通信治理推进为可测试的非 UI 控制面。
2. 框架继续保留调度、校验、暂存、转发、归档和终止的最终控制权；GuLiCode 顶层 Agent 只提交结构化意图和解释状态。
3. UI 暂未开发，本轮只完成运行时、control plane、RPC/CLI thin client 与文档状态同步。

#### 已落地
1. 顶层 Agent profile：
   - `GuLiCodeTopAgentProfile` 支持 JSON `from_dict()` / `load()` / `save()`。
   - profile 字段包括 `agent_id`、`display_name`、`allowed_run_permissions`、`rule`、`skill`。
   - `runtime validate-start --top-agent-profile ...` 使用 profile 做权限与 start plan 校验。
   - `runtime top-agent-context --top-agent-profile ...` 输出 profile + organization context。
2. 顶层 Agent start plan：
   - `TopAgentTask`、`TopAgentStartPlan`、`TopAgentPlanValidation` 已作为启动计划结构化契约。
   - 校验覆盖 agent 描述完整性、start node 存在性、任务字典对齐、必填字段和顶层 Agent start 权限。
3. 组织架构与普通 Agent scoped view：
   - `GraphDefinition.agent_connections()` 从普通 AgentNode 之间的 `exec` 边生成可通信关系。
   - `GraphDefinition.agent_organization_view()` 返回 graph、agents、agent_connections、start_policy。
   - `scoped_organization_view()` 为普通 Agent 返回自身相关上游、下游与 scope。
4. 消息分发：
   - `OutgoingMessageBatch` / `StagedOutgoingMessage` 支持完整 batch/stage 分发。
   - `message.create_batch` / `message.stage` 通过 control plane / RPC / CLI 暴露。
   - `agent.dispatch` / `runtime agent-dispatch` 提供普通 Agent 单步分发 MVP：按图可达性校验 source/target，创建单 target batch，暂存后进入下游队列。
5. Fan-in / join：
   - `JoinBarrier` / `JoinContribution` 支持 `wait-all`、`wait-any`、`quorum`、`timeout`。
   - ready 后可自动生成 `join_aggregate` 信封并投递给汇聚 Agent。
   - `GraphExecutor.run_blueprint()` 已可从多输入 `exec` 边自动创建 join barrier。
6. 运行状态与结束：
   - `GraphRuntime.status_snapshot()` 聚合 run、Agent、queue、outgoing batch、join、job、recent events、workspace 和 organization。
   - `GraphRuntime.end_run()` 支持 `complete`、`cancel`、`fail`、`pause`、`archive_only`。
   - `cancel` / `fail` 会取消 queued / dispatching messages、未完成 jobs 和 waiting joins。
   - `complete` 生成 `shared/reports/final_report.json`；`complete` / `archive_only` 可接入既有 workspace archive index。
7. Run start manifest：
   - `GraphRuntime.record_start_manifest()` 记录 top-agent profile、start plan、organization snapshot、user goal 和 queued initial messages。
   - `status_snapshot()["run"]["manifest"]` 可查询。
   - 有 `WorkspaceManifest` 和 `manifest_path` 时可写出 workspace JSON。

#### 涉及
- `graph_runtime.py`
- `graph_control.py`
- `__main__.py`
- `__init__.py`
- `test_agent_runtime.py`
- `test_graph_control.py`
- `tasks/current_goals.md`
- `tasks/multi_agent_communication_tasks.md`
- `多agents通信设计.md`

#### 验证
```text
python -m pytest test_graph_control.py test_agent_runtime.py -q
58 passed

python -m pytest test_graph_control.py test_agent_runtime.py test_workspace_api.py test_workspace_manager.py -q
93 passed
```

#### 当前边界
1. `agent.dispatch` 目前按图可达性校验，还没有绑定当前任务信封中的 `required_outgoing_targets`。
2. 普通 Agent 的 rule / skill / tool context 还没有稳定注入到 AgentNode 启动上下文。
3. 非 UI control plane 已具备长生命周期接入基础，但真实 GuLiCode 顶层 Agent 会话尚未接入。
4. 普通 Agent 状态读取权限仍需进一步收敛。
5. UI 状态展示、顶层 Agent 对话入口、changeset/conflict/artifact 可视化均后续再开发。

---

### 2026-05-08 — 顶层 GuLiCode 会话、任务信封约束与状态解释收口

#### 摘要

本轮继续推进 `多agents通信设计.md` 中标记的“仍未完成”项，但继续不开发 UI。重点是把上一轮留下的非 UI control plane 能力收口成可被真实 GuLiCode / 普通 Agent 消费的运行时协议：

1. 顶层 GuLiCode profile 不再只是 rule / skill 文本，而是可以映射为长期运行 worker 的 profile。
2. 普通 Agent 的 `agent.dispatch` 从“按全图可达性临时创建一跳分发”收敛为“必须绑定当前 outgoing batch / 任务信封”。
3. 普通 Agent 每轮消息携带 `framework_context`，明确当前 `outgoing_batch_id`、`required_outgoing_targets`、`remaining_targets`、可达下游和工具约束。
4. 顶层 Agent 状态解释接入 `status_snapshot()`、workspace、队列、join、job 和 recent events，不再依赖自由文本猜测。

#### 已落地

1. 顶层 GuLiCode 可运行 profile：
   - `GuLiCodeTopAgentProfile` 扩展 `cli_kind`、`model`、`cwd`、`timeout_sec`、`prompt_via_file`、`command`、`adapter_options`、`extra_env`、`external`。
   - 新增 `GuLiCodeTopAgentProfile.to_agent_node()`，将顶层 profile 映射为框架拥有的 `AgentNode`，供同一 `GraphRuntime` 绑定长期 worker。
   - profile JSON `load()` / `save()` 保留 rule / skill 文本能力，同时保存运行配置。
2. 顶层 Agent 会话控制面：
   - `GraphRuntimeControlPlane` 新增 `top_agent.start_session`，用于提前绑定 GuLiCode worker。
   - `GraphRuntimeControlPlane` 新增 `top_agent.ask`，将用户自然语言消息、top-agent organization context 和可选状态解释投递给 GuLiCode worker。
   - CLI thin client 新增 `runtime top-agent-start-session` 与 `runtime top-agent-ask`。
3. 状态解释：
   - `GraphRuntime.explain_status()` 基于 `status_snapshot()` 生成顶层 Agent 可读摘要。
   - 解释结果包含 run 状态、Agent state 分组、queued / dispatching message 数量、waiting outgoing batch、waiting join、running / failed job、workspace conflicts、reports、artifacts、recent events key 摘要和 recommended actions。
   - control plane 新增 `top_agent.explain_status`，CLI thin client 新增 `runtime explain-status`。
4. 普通 Agent 消息上下文：
   - 新增 `ordinary_agent_framework_context()`，为普通 Agent 构造 scoped organization、message envelope、`agent.dispatch` 工具说明和通信规则。
   - 新增 `inject_framework_context()`，把 `framework_context` 注入每轮消息的 `context` 字段，并保留已有 user context。
   - `run.start` 会为带下游的 start node 创建本轮 outgoing batch，并把 `required_outgoing_targets` / `remaining_targets` 注入初始 `top_agent_task`。
   - 新增 `agent.context` / `runtime agent-context`，用于读取普通 Agent 当前 batch 的工具上下文。
5. `agent.dispatch` 信封约束：
   - `agent.dispatch` 现在必须携带当前 `batch_id`。
   - source 必须匹配 batch owner。
   - target 必须属于该 batch 的 `required_target_node_ids`。
   - 分发不再仅按全图可达性临时创建单 target batch；当前 outgoing batch 是普通 Agent 本轮通信的权威信封。
   - 投递给下游的消息会注入下游自己的下一轮 `framework_context`；若下游还有下游节点，控制面会为其创建下一轮 outgoing batch。
6. 文档同步：
   - `多agents通信设计.md` 的落地优先级、当前开发进度和“仍未完成”已同步。
   - UI 状态展示仍明确暂不开发，后续 UI 只消费已有 headless 状态 / 解释接口。

#### 涉及

- `graph_runtime.py`
- `graph_control.py`
- `__main__.py`
- `__init__.py`
- `test_graph_control.py`
- `多agents通信设计.md`

#### 验证

```text
python -m pytest test_graph_control.py -q
5 passed

python -m pytest test_agent_runtime.py test_graph_control.py -q
59 passed

python -m pytest test_graph_control.py test_agent_runtime.py test_workspace_api.py test_workspace_manager.py -q
94 passed

python -m py_compile graph_runtime.py graph_control.py __main__.py __init__.py
```

#### 关闭的上一轮边界

1. `agent.dispatch` 已绑定当前任务信封中的 `required_outgoing_targets`。
2. 普通 Agent 的 tool context 已作为 `framework_context` 注入到消息上下文。
3. 非 UI control plane 已接入 GuLiCode 顶层 Agent 长生命周期 worker 边界。
4. 顶层 Agent 状态解释已接入事件和快照，而不是自由文本猜测。

#### 当前边界

1. UI 状态展示仍不开发；后续 UI 应消费 `status_snapshot()` / `explain_status()` / RPC thin client，不复制状态聚合逻辑。
2. GuLiCode / Codex CLI 的底层 adapter 仍是“长生命周期 worker 边界 + 每条消息调用 CLI”的兼容形态；若 CLI 后续支持真正交互式 session，可在 adapter 内替换实现，不改变 control plane 协议。
3. `framework_context` 已进入消息信封，但仍需和真实 AgentNode 启动 prompt / skill 注入链路做端到端联调，确认各 CLI adapter 都稳定消费 `context` 字段。
4. 权限收敛仍可继续加强：workspace/VCS API、artifact/report publish API 后续也应绑定当前任务信封和 Agent scope。

---

### 2026-05-03 — AgentNode skill selection 模型同步到 registry 与 registry-ui

#### 摘要
1. `AgentNode` 的用户可配置 skill 从单一 `skills` 列表升级为 `AgentSkillSelection`，支持 `none` / `all` / `selected` / `upstream` 四种模式；旧 `skills` 列表继续兼容为 `selected`。
2. `AgentNode.node_id` 改为框架自动分配，避免把图内部节点 ID 暴露为用户必填字段。
3. `registry.py` 新增 profile 级 `skill_selection` 解析：`none` 不注入 skill，`all` 注入 manifest 中全部 skill，`selected` 注入显式选择项，`upstream` 留给图运行时超级 agent 授权解析。
4. `registry_ui.py` 的 agent 编辑界面新增 skill mode 下拉选择，可直接选择 `none` / `all` / `selected` / `upstream`；`selected` 模式保留 skill 多选，并提供全选与清空。
5. `show-registry` / session snapshot 输出携带 `skill_selection`，同时保留 legacy `skills` 镜像，便于旧配置与旧调用路径平滑过渡。

#### 涉及
- `graph_runtime.py`
- `registry.py`
- `registry_ui.py`
- `__init__.py`
- `test_agent_runtime.py`
- `test_registry_skill_selection.py`

#### 验证
1. `python -m py_compile registry.py registry_ui.py test_registry_skill_selection.py`
2. `python -m pytest test_agent_runtime.py test_codex_cli_smoke.py test_skill_injection.py test_skill_space.py test_workspace_manager.py test_registry_skill_selection.py -q`：`39 passed`

#### 当前边界
1. registry 层的 skill 标识仍是 `skill_list/manifest.json` 中的 skill 名称；为复用图运行时模型，暂存在 `AgentSkillSelection.skill_hashes` 字段中。
2. `upstream` 在 registry 静态 prompt 注入中不会解析 skill，实际授权仍由图运行时 `SuperAgentProfile.validate_assignment()` 负责。
3. registry-ui 目前只保存模式，不判断当前 agent 是否确实有超级 agent 上游；该约束保留在运行时。

---

### 2026-05-03 — CodexAdapter 最小执行器落地：接入 `codex exec` 与 `codex-worker`

#### 摘要
1. 基于此前 Codex CLI spike，新增真实 `CodexAdapter` 与 `codex_bridge.py`，把 `codex exec` 纳入现有 `CLIAdapter` 边界。
2. 支持 `cli_kind=codex` / `mode=codex-worker` 的 worker 启动路径，`__main__.py agent --mode` 已开放 `codex-worker`。
3. `WorkerConfig(cli_kind="codex", model=...)` 会序列化为 Codex 运行配置，并将 `AgentNode.model` 映射到 `codex exec --model`。
4. `codex_bridge.py` 支持 stdin prompt、`--json`、`--output-last-message`、`--cd`、`--model`、`--image`、超时杀进程树、可选临时/指定 `CODEX_HOME`。
5. `WorkerResult` 解析新增 `body.codex.final_text` / `last_message` 路径，使 `run_single`、`run_parallel`、`run_parallel_reduce` 上层结果视图保持统一。
6. `AgentSkillView` 新增 Codex 执行上下文与 adapter options 生成方法，先以 prompt preamble + execution_context 方式暴露授权 skill view，不暴露 SkillSpace 私有路径。

#### 涉及
- `codex_bridge.py`
- `adapters.py`
- `cluster.py`
- `__main__.py`
- `skill_space.py`
- `__init__.py`
- `test_agent_runtime.py`
- `test_skill_space.py`
- `test_codex_cli_smoke.py`

#### 验证
1. `python -m py_compile adapters.py codex_bridge.py cluster.py __main__.py skill_space.py __init__.py`
2. `python -m pytest test_agent_runtime.py test_codex_cli_smoke.py test_skill_injection.py test_skill_space.py test_workspace_manager.py -q`：`31 passed`
3. `python -m multi_agent_tcp agent --help` 已显示 `codex-worker`。

#### 当前边界
1. Codex adapter 仍采用 per-message `codex exec` 子进程；`CLIAdapter` 边界是长生命周期 worker 对象，不代表 Codex CLI 内部会话已持久复用。
2. `AgentSkillView` 已接入 Codex prompt/context，但临时 `CODEX_HOME` 的自动隔离策略尚未和运行时 workspace 生命周期完整联动。
3. Claude CLI 仍未确认，不能预设调用方式。
4. registry-ui 尚未按 `cli_kind` 渲染差异化字段与 model 候选。

---

### 2026-04-30 — 基于 `KM_docs` 同步 skill：新增知识库模块、短期任务目录与仓库镜像快照

#### 摘要
1. 基于 `KM_docs` 中新增的多 CLI 工作流、vendor UI 与蓝图差距文档，扩展 Cursor skill 的知识入口。
2. 在 `knowledge_base/` 下新增多 CLI 节点工作流、vendored Ryven 视觉层、蓝图改进方向等模块文档。
3. 在 skill 根目录下新增 `tasks/`，把短期目标与长期知识分层。
4. 将仓库内 `KM_docs/skills-snapshot/` 的旧式单文件快照改为对本地 Cursor skill 目录的完整镜像。

#### 涉及
- `SKILL.md`
- `knowledge_base/`
- `tasks/`
- `KM_docs/skills-snapshot/`

---

### 2026-04-26 — 仅文档/skill 同步：对齐当前仓库路径与文档范围

#### 摘要
1. 按当前仓库实际结构，补充说明根包入口文件位置与常见本机路径。
2. 将 `README.md`、`GUIDE_FOR_CODEMAKER.md`、`examples/HOWTO.txt` 明确纳入归档对照范围。
3. 区分主架构知识与专题运行基线知识，避免所有变更继续堆叠在单一总归档文件中。

#### 涉及
- `SKILL.md`
- `knowledge_base/`

---

### 2026-04-25 — 归档结构重组：agent 主架构与专题归档并列维护

#### 摘要
1. 在 skill 目录下新增 `archive/` 子目录，按主题拆分长期归档。
2. 新增 agent 架构专题归档，记录多 agent 调度主架构与归档拆分背景。
3. 明确蓝图运行基线、GuLiCode 运行基线与主架构需要并列归档，而不是继续堆在一个总历史文件中。

#### 涉及
- `archive/agents_architecture_archive.md`
- `SKILL.md`

---

### 2026-04-21 — Skill 归档迁出：历史归档从 `SKILL.md` 迁移到独立文档

#### 摘要
1. 减少 `SKILL.md` 体积，将“最近归档”和“变更记录”迁出为独立历史文档。
2. 让 `SKILL.md` 只保留当前有效方法、核心架构与入口索引。

#### 涉及
- `SKILL.md`
- `ARCHIVE.md`

---

### 2026-04-21 — GitHub 地址与一键 git 同步说明

#### 摘要
1. 补充公开仓库地址 `https://github.com/QHXRPG-A/multi_agent_tcp`，并说明 `multi_agent_tcp/` 为独立 git 根。
2. 增加拉取更新与一键提交推送的常用命令。
3. 强调“只更新 Cursor skill”时仅维护本 skill 文档，不改 `.codemaker` 副本。

#### 涉及
- `SKILL.md`

---

### 2026-04-17 — v0.5.1：异步 dispatch 与状态文件轮询

#### 摘要
1. 新增 `dispatch --async`，后台异步执行并立即返回 `job_id` 与 `status_file`。
2. 增加 job 跟踪与状态落盘能力，完成时将 result 嵌入状态文件。
3. 新增 `dispatch-status` 作为终端轮询备选方案。
4. 将推荐轮询方式改为直接读取 `status_file`，降低审批、超时和中断风险。

#### 涉及
- `__main__.py`
- `GUIDE_FOR_CODEMAKER.md`
- `SKILL.md`

---

### 2026-04-17 — v0.5.0：show-registry / dispatch 两步 LLM 调用流程

#### 摘要
1. 新增 `show-registry` 只读查询入口。
2. 新增 `dispatch` 一站式并行执行入口，自动加载 registry、校验 agent、注入 skills 并返回结构化结果。
3. 新增 `CodeMakerCluster.create_from_registry()` 与 `_inject_skills()` 自动 skill 注入能力。
4. 将 session-gated 流程标记为 legacy，推荐改用 `show-registry` → `dispatch`。

#### 涉及
- `cluster.py`
- `registry.py`
- `__main__.py`
- `__init__.py`
- `GUIDE_FOR_CODEMAKER.md`
- `SKILL.md`

---

### 2026-04-17 — v0.4.1：Registry UI

#### 摘要
1. 新增 `registry_ui.py` Tkinter 桌面应用，用于可视化管理 `agents_registry.json`。
2. 增加深色主题卡片网格、编辑对话框、模型实时下拉、skill 多选弹窗、撤销/保存状态管理等能力。
3. 在 CLI 中新增 `registry-ui` 子命令。

#### 涉及
- `registry_ui.py`
- `__main__.py`
- `SKILL.md`

---

### 2026-04-17 — v0.4.0：Agents 配置表、Skill 合并体系与 Session-gated dispatch

#### 摘要
1. 新增 `agents_registry.json` 与 `AgentsRegistry` 配置体系。
2. 新增 `init_skill_list.py`，合并 `.codemaker/skills` 与 `.cursor/skills` 到 `skill_list/`。
3. 引入 `catalog` 按需读取模式，替代全量 skill 注入。
4. 新增 `list-agents` / `run-agent` session-gated 分发流程。

#### 涉及
- `registry.py`
- `init_skill_list.py`
- `agents_registry.json`
- `test_skill_injection.py`
- `__main__.py`
- `__init__.py`
- `.gitignore`
- `SKILL.md`

---

### 2026-04-17 — v0.3.0：结构化结果、fan-out→reduce 与 LLM 精简序列化

#### 摘要
1. 新增 `WorkerResult`、`ParallelResult`、`ReduceResult` 类型。
2. `run_parallel()` 返回结构化结果；新增 `run_parallel_reduce()`。
3. 增加 `to_dict()` / `to_raw_dict()` 双序列化。
4. 修复 broker 中 `gather_reply` 消息泄漏问题。

#### 涉及
- `cluster.py`
- `broker.py`
- `__init__.py`
- `__main__.py`
- `demo_gclient_three_search.py`
- `examples/HOWTO.txt`
- `SKILL.md`

---

### 2026-04-17 — 失败重试、Broker 并发安全与心跳修复

#### 摘要
1. `run_parallel()` 支持基于可重试错误模式的串行重试。
2. broker 的 gather 执行改为非阻塞任务，避免心跳被阻塞。
3. 为每个连接增加写锁，避免并发写导致帧交错。
4. CLI 与 demo 同步新增重试参数。

#### 涉及
- `cluster.py`
- `broker.py`
- `__init__.py`
- `__main__.py`
- `demo_gclient_three_search.py`
- `SKILL.md`

---

### 2026-04-16 — 仅文档/skill 同步：确认与代码一致

#### 摘要
1. 全量比对 `cluster.py`、`__main__.py`、`__init__.py`、demo 与 examples 配置，确认 `SKILL.md` 中的架构、API、CLI 与协议描述与代码一致。
2. 本轮无代码变更，仅新增归档记录。

#### 涉及
- `SKILL.md`

---

### 2026-04-16 — CodeMakerCluster API、Demo 落地与框架定调

#### 摘要
1. 新增 `cluster.py` 中的 `WorkerConfig` 与 `CodeMakerCluster` 门面。
2. 新增 `cluster start`、`run-parallel`、`run-chain` CLI。
3. demo 重写为基于 `CodeMakerCluster`。
4. 增加示例配置与 HOWTO 快速开始章节。

#### 涉及
- `cluster.py`
- `__main__.py`
- `__init__.py`
- `demo_three_codemakers.py`
- `demo_gclient_three_search.py`
- `examples/cluster.json`
- `examples/tasks_parallel.json`
- `examples/tasks_chain.json`
- `examples/HOWTO.txt`
- `SKILL.md`

---

### 2026-04-16 — CodeMaker CLI 合规排查与文件名修正

#### 摘要
1. 增加模型前缀校验。
2. 增加 `permission` 配置检查。
3. 增加 `prompt_via_file='never'` + 非 ASCII 的风险告警。
4. 修正 `codemaker_cli.md` 文件名引用。

#### 涉及
- `codemaker_bridge.py`
- `codemaker_cli.md`
- `SKILL.md`
- demo 脚本
- `examples/HOWTO.txt`

---

### 2026-04-16 — 日志落盘、端口冲突检测、进程树清理与心跳探活

#### 摘要
1. 增加 `log_setup.py` 日志落盘。
2. 增加端口冲突检测。
3. 增加 `_proc_utils.py` 进程树清理。
4. 实现请求-应答式心跳与 gather 断连感知。

#### 涉及
- `log_setup.py`
- `_proc_utils.py`
- `broker.py`
- `SKILL.md`

---

### 2026-04-16 — batch_gather、可观测性与输出过滤

#### 摘要
1. 建立 `batch_gather` 并行聚合协议与 `GatherState`。
2. 增加 gclient 并行搜索 demo。
3. 增加结构化日志前缀。
4. 增加 NDJSON 文本提取能力。

#### 涉及
- `broker.py`
- `client.py`
- `protocol.py`
- `demo_gclient_three_search.py`
- `SKILL.md`

---

### 2026-04-16 — orchestrate 与初版框架

#### 摘要
1. 增加 orchestrate 配方 CLI。
2. 落地初版 broker / agent / codemaker-worker。

#### 涉及
- `orchestrate.py`
- `broker.py`
- `client.py`
- `codemaker_bridge.py`
- `SKILL.md`

---

## 当前主架构知识

---

### 2026-05-03 — 节点运行时、共享工作区与 SkillSpace 阶段落地

#### 摘要

本轮把多 CLI / 节点化方向从文档任务推进为一组可测试的运行时 primitives，并为后续 CodexAdapter 与蓝图执行器建立隔离边界。

#### 已落地

1. **Adapter 边界**
   - 新增 `adapters.py`。
   - 落地 `CLIAdapter`、`CodeMakerAdapter`、`AgentMessage`、`AdapterResult`。
   - `CodeMakerAdapter` 继续兼容现有 `codemaker run` per-message 执行方式。

2. **节点运行时 primitives**
   - 新增 `graph_runtime.py`。
   - 落地 `AgentNode`、`AgentInstance`、`GraphRuntime`、`BrokerAgentRuntime`。
   - 支持 `execution_mode: blocking | nonblocking`。
   - 新增 `GraphJob`、`GraphEvent`、`WorkspaceManifest`。
   - 新增 `MultiModalEnvelope` / `normalize_envelope`。
   - 新增 `RouteNode`、`GraphEdge`、`GraphDefinition`、`GraphExecutor`。

3. **共享工作区生命周期**
   - 新增 `dulwich_vendor.py` 与 `workspace_manager.py`。
   - vendored Dulwich 到 `vendor/dulwich`，通过 `.gitignore` 排除第三方源码。
   - 支持用户指定长期共享工作区 `workspace_root`；默认 `<project>/.multi_agent_workspace/`。
   - 长期共享工作区允许 agent 读取，但不允许写入；当前为 runtime policy，OS ACL / 沙箱级强制尚未实现。
   - 每次蓝图运行创建 `runs/active/<run_id>`。
   - 每个 job 创建隔离 `jobs/<job_id>/worktree`。
   - 支持完整目录归档到 `runs/archived/<run_id>` 或 `runs/failed/<run_id>`。
   - 支持 diff、scope 校验、文本三方 merge、冲突检测。

4. **SkillSpace 与 agent 独立目录**
   - 新增 `skill_space.py`。
   - `SkillSpace` 私有维护 `hash -> skill` 映射。
   - 下游 agent 只拿到 hash 列表，框架负责将授权 skill 复制到 agent 独立目录。
   - agent 独立目录位于 `runs/active/<run_id>/agents/<agent_id>/`。
   - `AgentSkillView` 生成 agent 可见 context 与 catalog prompt。
   - `SuperAgentProfile` 支持查看可分配 skill catalog，并校验给下游 agent 指定的 skill hash 列表。

5. **Codex adapter spike**
   - 本机确认 Codex CLI：`codex-cli 0.125.0`。
   - `codex exec` 支持 stdin prompt、`--json`、`--output-last-message`、`--cd`、`--model`、`--image`。
   - Claude CLI 当前未在 PATH 中发现，不预设调用方式。

#### 测试覆盖

- `test_agent_runtime.py`
- `test_workspace_manager.py`
- `test_skill_space.py`
- `test_codex_cli_smoke.py`

当前相关测试通过：`26 passed`。

#### 当前边界

1. 还没有真实 `CodexAdapter` / `ClaudeAdapter`。
2. SkillSpace 尚未接入 CodexAdapter 的临时 `CODEX_HOME` 强隔离。
3. 共享工作区还没有 lock / lease、OS ACL / 沙箱级只读强制、持久 runner、Dulwich commit/ref merge、归档删除 API。
4. 图运行时还不是完整图编译器；处理节点、I/O 节点、条件路由、事件总线仍待实现。
5. 超级 agent 当前只实现 skill 分配权限模型，其它下游 agent 配置能力后续再做。

#### 维护建议

1. 近期重点转向 `CodexAdapter`：`cli_kind=codex`、`mode=codex-worker`、model 映射、prompt contract、SkillSpace view 注入。
2. AgentNode 对下游 agent 应屏蔽框架技术细节，只暴露上下文、用户设置、授权 skills、接口文档与输出格式。
3. `multi-agent-tcp` 框架维护 skill 不应默认注入普通下游 agent，避免泄露框架内部实现。

### 背景

`multi_agent_tcp` 的核心仍然是多 agent 编排框架：通过 broker、registry、dispatch 与 cluster API，让多个 CodeMaker CLI worker 在同一框架下并行、串行或归约执行任务。

### 当前 agent 主架构要点

#### 1. Cluster 门面

`cluster.py` 提供：

- `CodeMakerCluster.create_from_registry()`：推荐入口，按 registry 创建 worker，并自动注入 skill
- `create()` / `connect()`：手动创建或连接已运行集群
- `run_parallel()` / `run_parallel_reduce()` / `run_chain()` / `run_single()`
- 重试与结果包装：`WorkerResult`、`ParallelResult`、`ReduceResult`

#### 2. Registry 驱动

`registry.py` + `agents_registry.json` 管理：

- agent_id / display_name / model / cwd / timeout_sec / enabled
- skill catalog 构建与 prompt 注入
- legacy session-gated agent dispatch

#### 3. Broker / Client 通信层

- `broker.py`：单端口 TCP broker，负责 register / send / broadcast / ping / `batch_gather`
- `client.py`：AgentTCPClient，封装 gather、pump、send 和消息接收
- `protocol.py`：4 字节长度前缀 + UTF-8 JSON frame

#### 4. 推荐 LLM 工作流

当前推荐协调路径仍然是：

1. `show-registry`
2. `dispatch`（可同步，也可 `--async`）
3. 长任务优先使用 `status_file` + read 工具轮询

#### 5. Skill 注入策略

推荐 `catalog` 模式：

- 不把完整 `SKILL.md` 一次性灌入 prompt
- 先给 agent 发轻量 skill 目录表
- 需要时再读取对应 `SKILL.md`

### 后续建议

1. 将 agent 主架构与蓝图/GuLiCode 归档并列维护。
2. 保持 `SKILL.md` 只写当前有效工作方法与核心架构，不堆大量过程性叙事。
3. 对新增运行基线（Ryven / GuLiCode）的后续裁剪，也应记录对 `multi_agent_tcp` agent 架构的影响。
---

### 2026-05-07 - VCS-style workspace changeset loop and Dulwich text merge MVP

#### Summary

This round advanced the shared workspace model from report/artifact publishing and legacy job worktree merging toward a framework-owned VCS-style changeset loop for multi-agent code collaboration.

The implemented flow is:

```text
run integration workspace
  -> scoped agent checkout
  -> private agent edits
  -> status/diff
  -> submit changeset
  -> framework merge or structured conflict
  -> sync and resubmit repair loop
```

#### Landed

1. Added VCS-style workspace concepts in `workspace_manager.py`:
   - `AgentCheckout`
   - `ChangesetSubmitResult`
   - `checkout_agent()`
   - `status_checkout()`
   - `diff_checkout()`
   - `submit_checkout()`
   - `sync_checkout()`
2. `checkout_agent()` now copies scoped files from the current run integration workspace, not the original run base. The checkout stores its own base snapshot in `agents/<agent_id>/private/state/base`.
3. `submit_checkout()` validates write scope, computes changes relative to the checkout base snapshot, compares with latest `run.integration_dir`, and either applies accepted changes or returns structured conflict data.
4. Conflict detection now uses a three-way view:
   - checkout base snapshot
   - latest integration file
   - agent private checkout file
5. The Workspace API and RPC server now expose:
   - `checkout`
   - `status`
   - `diff`
   - `submit`
   - `sync`
6. RPC responses now preserve legitimate `ok: false, status: "conflict"` results instead of converting them into transport errors.
7. Text merge now prefers `dulwich.merge.merge_blobs()` and falls back to the previous conservative merge logic when Dulwich or its merge backend is unavailable. Dulwich hunk-level merge requires the `merge3` Python package.
8. Added changeset and conflict archive records under run directories:
   - `changesets/<changeset_id>/changeset.json`
   - `changesets/<changeset_id>/patch.diff`
   - `changesets/<changeset_id>/submit_result.json`
   - `conflicts/<conflict_id>/conflict.json`
9. `docs/workspace_api.md` now documents the VCS-style code flow for agents.
10. `README.md` now records `merge3` as the recommended runtime dependency for Dulwich-powered text merges.

#### Verified behavior

Tests now cover:

- scoped checkout from current integration workspace into private agent checkout;
- private file edits submitted back into the temporary integration workspace;
- scope violations blocked before merge;
- same-file same-region conflicts returned to the agent and not applied;
- conflict repair loop: conflict -> sync -> edit -> resubmit -> accepted;
- RPC/CLI end-to-end conflict loop with two agents;
- Dulwich hunk-level merge accepting non-overlapping edits in the same text file.

Full validation after this round:

```text
python -m pytest -q
74 passed
```

#### Remaining boundaries

1. This is still a file/snapshot changeset backend, not Dulwich commit/ref storage.
2. The authoritative writer is the framework runtime, but OS/sandbox-level enforcement still needs to prevent direct writes outside private checkouts.
3. Rename detection, binary merge policy, delete/rename interaction, and large-file handling still need explicit rules.
4. Workspace events exist as manifest records, but a durable cross-process event bus and UI surfacing are still pending.
5. Blueprint AgentNode launch policy still needs to wire strict read-only project context plus writable checkout into Codex/OpenCode execution modes.

---

### 2026-05-07 - Strict Workspace API cleanup and long-term archive read model

#### Summary

This round completed the agent-facing workspace contract cleanup around code changes, temporary shared outputs, and long-term shared memory.

The current contract is:

```text
agent code edits:
  checkout -> edit private checkout -> status/diff -> submit

agent run outputs:
  publish / publish-file only for run-scope reports and artifacts

long-term shared workspace:
  framework writes named run archive zips
  agents list/extract archives into private workspace for reading
```

#### Landed

1. Removed agent-facing `code` from Workspace API publish areas:
   - `VALID_AREAS` is now only `artifacts` and `reports`.
   - `publish --area code` and `publish-file --area code` are no longer exposed by parser help or RPC context.
   - Blueprint execution context now advertises only `["artifacts", "reports"]` as publish areas.
2. Removed agent-facing publish/read/list `--scope` handling:
   - `publish`, `publish-file`, `read`, and `list` now operate on the current run workspace only.
   - `long_term` is no longer exposed as a publish scope.
   - RPC publish/read/list no longer resolve long-term workspace runs.
3. Added framework-owned long-term archive flow:
   - `archive_run()` compresses the temporary run `shared/` workspace into `.multi_agent_workspace/shared/archives/<run_id>-<status>.zip`.
   - Archive metadata is recorded in `.multi_agent_workspace/shared/archives/manifest.json`.
4. Added read-only archive APIs for agents:
   - `list-archives`
   - `extract-archive`
   - extraction targets the requesting agent's private workspace under `extracted_archives/`.
5. Updated agent-injected Workspace API documentation and removed stale design-document references to old `code` publish areas and long-term publish scopes.
6. Blueprint AgentNode launch now creates a private checkout before worker start, launches with checkout as `cwd`, injects RPC Workspace API context, and presents archive read commands for long-term results.

#### Verified behavior

Validation after this round:

```text
python -m pytest test_workspace_api.py test_workspace_manager.py test_agent_runtime.py
66 passed
```

#### Current boundaries

1. Long-term archive deletion, pruning, indexing/search, and retention policies are still pending.
2. The archive reader extracts zip contents into private workspace; a streaming read API may be useful later for large archives.
3. OS/sandbox-level enforcement should still be tightened so non-cooperative tools cannot write outside the private checkout.
4. Rename, binary, large-file, generated-file, and formatter policies for changeset submit still need explicit rules.

---

### 2026-05-07 - Codex strict launch sandbox guard

#### Summary

This round closed the short-term strict-launch concern for Codex-backed Blueprint AgentNodes by relying on Codex CLI sandbox semantics instead of adding a broader runtime dirty-scan policy.

The current Codex launch contract is:

```text
real project path
  -> exposed to the agent as read-only project_context

private agent checkout
  -> passed to Codex as cwd / --cd
  -> writable under Codex workspace-write sandbox
```

#### Landed

1. Confirmed local Codex CLI behavior (`codex-cli 0.125.0`):
   - `--sandbox workspace-write --cd <checkout>` allows writes in the working root;
   - directories outside `--cd` can be read but are not writable unless explicitly added.
2. Blueprint Codex AgentNodes continue to default to `sandbox=workspace-write` and private checkout `cwd`.
3. Added Codex launch safety validation at the bridge/config layer:
   - reject `sandbox=danger-full-access`;
   - reject `extra_args` that request `--sandbox danger-full-access` or `-s danger-full-access`;
   - reject `--dangerously-bypass-approvals-and-sandbox`;
   - reject `extra_args --add-dir <path>` when the added directory overlaps the read-only project context.
4. Reused the same validation from blueprint workspace application, so dangerous Codex options are rejected before the worker launch configuration is accepted.
5. Preserved user-facing semantics: users may still configure a real project directory as AgentNode `cwd`; blueprint runtime treats it as read-only `project_context` and launches Codex from the private checkout.

#### Affected Code

- `multi_agent_tcp/codex_bridge.py`
- `multi_agent_tcp/ryven_blueprint.py`
- `multi_agent_tcp/test_agent_runtime.py`

#### Validation

```text
python -m pytest test_agent_runtime.py -q
35 passed

python -m pytest test_workspace_api.py test_workspace_manager.py test_agent_runtime.py -q
70 passed
```

#### Current conclusion

For Codex-backed blueprint agents, the earlier short-term task "add runtime/tool-layer checks for direct writes outside checkout paths" is no longer tracked as an active task. The current boundary is Codex `workspace-write` sandbox plus launch-time rejection of writable `project_context` escape hatches.

This conclusion is Codex-specific. Other CLI adapters without equivalent sandbox semantics should be evaluated separately if they are brought into strict launch mode.
