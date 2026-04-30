# Agents 架构变更归档

本文件只记录 `multi_agent_tcp` 多 agent 调度主架构方向上的历史变更，便于后续回顾。

## 变更记录

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
