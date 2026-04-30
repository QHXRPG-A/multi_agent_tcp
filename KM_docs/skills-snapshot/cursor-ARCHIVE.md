# multi_agent_tcp — Cursor skill 归档

本文件收录 **multi_agent_tcp** 技能的全部历史归档：`最近归档`（详细条目）与 `变更记录`（简表）。

- **主技能文档**（架构、API、CLI、协议等）：同目录 [`SKILL.md`](SKILL.md)
- **维护约定**：用户触发「归档」时，在 **本文件**「最近归档」**顶部**插入新条；`SKILL.md` 正文与代码对齐时按需修订，不必重复粘贴长归档。

**权威归档日期**：以本文件「最近归档」下**第一条**记录的日期为准。

---

## 最近归档

- **日期**：2026-04-30（项目定位转向：peer-to-peer agent CLI 协作；纯文档/skill 同步，**未改任何 .py 代码**）
- **摘要**：
  1. **取消旧叙事**：把 `multi_agent_tcp` 从「Cursor / CodeMaker 作为上游决策者拉起多 CodeMaker worker」全面转向「多 agent CLI（CodeMaker / Claude Code / Codex / 自研）之间的对等通信、管理、协作」。"上游/下游" / "Cursor 是 orchestrator" / "CodeMaker 是 worker" 等身份级不对称表述退场；改用"本次发起方（initiator）"等单次角色描述。
  2. **SKILL（Cursor + CodeMaker 两份）全文重写**：
     - `.cursor/skills/multi-agent-tcp/SKILL.md`：顶部"框架核心目的"重写为"对等通信总线 + 多 agent 管理"；架构图改为对等节点 + 中心 broker；新增「三种典型协作拓扑」表；命令名与协议描述（`show-registry` / `dispatch` / `batch_gather` / 心跳等）100% 兼容保留；新增「路线图方向」小节同步 ROADMAP P0-P3 中的对等原语方向；保留 GitHub 一键提交流程不变。
     - `.codemaker/skills/multi-agent-tcp/SKILL.md`：5 步工作流结构保留（仍是发起方"先拉一个 N→N-1 派发 + 自留一个 + 不空等"），但"主模型 ↔ agent" 的语义重定为"发起方 ↔ 对等 agent"；trigger words 增补 peer / agent collaboration / agent-to-agent 等关键词。
  3. **ROADMAP.md 全文重写**：设计哲学小节明确"薄通信总线，智能交给每个 agent CLI"；ASCII 架构图重画为多对等节点 + broker；`P0` 新增「CLI Adapter 抽象」（与脑暴文档 §3 对齐）；`P2` 新增「对等通信原语扩展」（Discovery 升级、capability addressing、多轮 conversation_id、per-agent permission、agent-to-agent inline call 模式）；「不做清单」**撤销旧版"模型抽象层不做（绑定 CodeMaker CLI 是优势）"**——明确改为"做最薄的 CLI Adapter，只适配进程 IO，不替代任何 CLI 内部 LLM 推理"，并保留历史变更说明；版本规划 v0.6 / v0.7 / v0.9 与新方向对齐。
  4. **`GUIDE_FOR_CODEMAKER.md` 删除 + 新建 `GUIDE_FOR_AGENTS.md`**：旧文件名把 CodeMaker / Cursor 当成唯一调用方，与新定位冲突。新文件面向"任意 agent CLI / 脚本调用方"，顶部明确「原 `GUIDE_FOR_CODEMAKER.md` 的全部内容已并入本文件」；新增「三种典型发起方」与「场景 2：agent CLI 发起方 - 我自己干一份，让另一个 agent 干另一份」示例，对齐对等协作模式；命令、参数、返回格式与旧版 100% 兼容。
  5. **README.md 重写**：一句话定位换成 "peer-to-peer agent CLI communication bus + multi-agent lifecycle management"；新增「Project pivot」小节说明历史背景；文档地图改为指向 `GUIDE_FOR_AGENTS.md`。
  6. **examples/HOWTO.txt 顶部重写**：标题从 `CodeMaker CLI multi-worker orchestration framework` 改为 `multi_agent_tcp — Peer agent CLI communication bus`；新增 Project pivot 段落；`batch_gather` 描述强调"任意发起方（脚本 / CI / 另一个 agent CLI）的对等 fan-out 原语"；保留所有命令、示例代码、协议字段。
  7. **`KM_docs/multi-cli-node-workflow-brainstorm.md` 局部修订**：§3.1 把「上游编译器」澄清为框架内部的「节点图编译器（GraphCompiler）」并加术语注释；§9 R2 风险点标记为「已于 2026-04-30 本轮合并撤销」；新增 §10「对等通信原语 vs 编排原语」节，列两类原语对照表 + 节点系统位置图 + 旧叙事退场说明；关联文档与修订记录章号顺延（旧 §10/§11 → §11/§12）；新增 v2 修订记录条目。
  8. **CLI 命令名 / 配置 schema / 协议帧格式全部保持兼容**：用户已经在用的 `show-registry` / `dispatch` / `run-parallel` / `run-chain` / `cluster start` / `agents_registry.json` 字段、`batch_gather` 协议等不变，只调整文档对它们的叙事定位，降低用户重学成本。
  9. **`.codemaker/skills/multi-agent-tcp/ARCHIVE.md` 不存在**：本归档仅维护 `.cursor` 一份；`.codemaker` 侧 SKILL.md 已同步重写。
- **涉及**：`README.md`、`ROADMAP.md`、`examples/HOWTO.txt`、`GUIDE_FOR_AGENTS.md`（新建）、`GUIDE_FOR_CODEMAKER.md`（已删除）、`KM_docs/multi-cli-node-workflow-brainstorm.md`、`.cursor/skills/multi-agent-tcp/SKILL.md`、`.cursor/skills/multi-agent-tcp/ARCHIVE.md`（本文件，新增本条）、`.codemaker/skills/multi-agent-tcp/SKILL.md`

- **日期**：2026-04-21（Skill：「最近归档」与「变更记录」迁出至 `ARCHIVE.md`，`SKILL.md` 仅引用）
- **摘要**：减少 `SKILL.md` 体积；新增同目录 `ARCHIVE.md` 承载全部历史条目与简表；更新「归档协议」指向本文件顶部追加新记录。
- **涉及**：`.cursor/skills/multi-agent-tcp/SKILL.md`、`.cursor/skills/multi-agent-tcp/ARCHIVE.md`

- **日期**：2026-04-21（Skill：GitHub 地址 + 一键 git 同步；仅 Cursor skill）
- **摘要**：
  1. **公开仓库**：https://github.com/QHXRPG-A/multi_agent_tcp — `multi_agent_tcp/` 为**独立 git 根**（与上级 `Package/Script/Python` 无父子仓库关系）。
  2. **更新本地**：在仓库根执行 `git fetch origin` → `git pull origin main`；若本地已有提交且需线性历史，可先 `git pull --rebase origin main` 再推送。
  3. **一键提交并推送**（确认 `git status` 无意外文件后）：Git Bash — `git add -A && git commit -m "<摘要>" && git push origin main`；PowerShell — `git add -A; git commit -m "<摘要>"; git push origin main`。
  4. **勿提交**：`logs/`、`sessions/`、`skill_list/`、`__pycache__/` 等已由 `multi_agent_tcp/.gitignore` 排除。
  5. **仅 Cursor**：本条归档与新增小节只维护 `.cursor/skills/multi-agent-tcp/SKILL.md`。
- **涉及**：`.cursor/skills/multi-agent-tcp/SKILL.md`

- **日期**：2026-04-17（v0.5.1：异步 dispatch + 文件轮询 — 解决 LLM 终端超时/审批中断问题）
- **摘要**：
  1. **`dispatch --async`（新）**：后台异步执行 dispatch。立即返回 `job_id` + `status_file` 路径，后台以 detached 进程运行（Windows `DETACHED_PROCESS | CREATE_NO_WINDOW`）。`--tasks-json` 内联 JSON 自动写临时文件避免 Windows 引号问题。
  2. **Job 跟踪基础设施（新）**：`DISPATCH_JOBS_DIR`（`logs/dispatch_jobs/`，已 gitignore）、`_generate_job_id()`（8 位 hex）、`_write_job_status()` / `_read_job_status()`、`_job_file()`。每个 async job 生成 `{job_id}.json`（状态文件）、`{job_id}.log`（子进程 stdout/stderr）、`{job_id}_result.json`（dispatch 结果）。
  3. **`_is_process_alive()`（新）**：跨平台进程存活检测。Windows 用 `ctypes` 调用 `OpenProcess` + `GetExitCodeProcess`（检测 `STILL_ACTIVE=259`）；Linux/macOS 用 `os.kill(pid, 0)`。
  4. **状态文件嵌入 result**：后台 dispatch 完成时，除写 `_result.json` 外，还将完整 result 嵌入 `{job_id}.json` 的 `"result"` 字段。LLM 只需 `read` 一个文件即可拿到结果。
  5. **`dispatch-status` CLI 命令（新）**：`--job-id`（必填）+ `--wait N`（可选，阻塞最多 N 秒，每 3 秒检查一次，完成立即返回）+ `-o`。`_check_job_once()` 读状态文件 + 崩溃检测（PID 不存活则标记 failed）+ 计算 `elapsed_sec` + 完成时读取并嵌入 result。
  6. **文件轮询替代命令轮询（推荐）**：`dispatch --async` 返回 `status_file` 路径，LLM 用 `read` 工具直接读取状态文件轮询。**核心优势**：read 工具无需用户审批、无超时、无轮次中断，比 `dispatch-status` 终端命令可靠性碾压级提升。`dispatch-status` 降级为备选方案。
  7. **`dispatch --async` 返回格式**：`{"job_id", "status", "pid", "message"（指引用 read 工具）, "status_file"（推荐轮询路径）, "poll_command"（备选终端命令）, "output_file"}`。
  8. **`GUIDE_FOR_CODEMAKER.md`（重写 Section 4b）**：异步 dispatch 流程从「终端命令轮询」改为「read 工具读状态文件」；对比表（审批/超时/轮次/token）；推荐轮询策略；`dispatch-status --wait` 降为备选。
  9. **`__init__.py`**：版本未改动（仍为 `0.5.0`，可在下次发版时升 `0.5.1`）。
- **涉及**：`__main__.py`、`GUIDE_FOR_CODEMAKER.md`、`SKILL.md`

- **日期**：2026-04-17（v0.5.0：show-registry / dispatch 两步 LLM 调用流程 + Registry 驱动的 Cluster 创建 + 自动 Skill 注入）
- **摘要**：
  1. **`show-registry` CLI 命令（新）**：只读查询 `agents_registry.json`，返回所有 enabled 的 agent 及其 skills/model/cwd/timeout_sec。不创建 session、无副作用。`registry.py` 新增 `show_registry_response()` 函数。
  2. **`dispatch` CLI 命令（新）**：LLM 推荐入口。接收 `[{"agent_id":"...","prompt":"..."}, ...]` 任务列表（`--tasks` 文件或 `--tasks-json` 内联），自动加载 registry → 验证 agent_id → `create_from_registry` 创建集群 → 注入 Skills → 并行执行 → 返回结构化结果（含 `dispatched_agents` 字段）。支持 `--port`、`--timeout`、`--max-retries`、`--retry-delay-sec`、`--skill-mode`。
  3. **`CodeMakerCluster.create_from_registry()`（新 classmethod）**：从 `AgentsRegistry` 直接创建集群。自动调用 `build_worker_configs()` 将 registry profile 转为 `WorkerConfig`，绑定 `_registry` 和 `_skill_mode` 到集群实例。
  4. **`_inject_skills()` 自动注入**：`CodeMakerCluster` 新增 `_inject_skills()` 方法，在 `run_parallel`/`run_chain`/`run_single` 提交任务前自动调用。根据 worker_id 反查 registry agent 配置，将 skill catalog（或 full SKILL.md）注入到 prompt 前。`_retry_failed` 和 `run_parallel_reduce` 内部的 `run_single` 传 `_skip_skill_inject=True` 避免重复注入。
  5. **`set_registry()` / `_resolve_agent_id()`**：允许对已有集群（`create`/`connect` 模式）事后绑定 registry 以启用 skill 注入。
  6. **`_add_connect_args` 重构**：`run-parallel`/`run-chain`/`run-parallel-reduce` 的参数组改为 `--config | --registry | --port` 三选一互斥组。`--registry` 使用 `agents_registry.json` 构建 workers。新增 `--registry-port`、`--skill-mode`、`--agent-ids` 参数。
  7. **`_create_cluster_from_args()` 统一创建逻辑**：`--registry` 走 `create_from_registry`，`--config` 走 `create`，`--port` 走 `connect`。
  8. **Session-gated 标记为 legacy**：`list-agents`/`run-agent` 仍可用，但 `__main__.py` 注释及文档中标注为 legacy。`show-registry` + `dispatch` 是推荐流程。
  9. **`GUIDE_FOR_CODEMAKER.md`（新/重写）**：面向 AI Agent 的使用指南，详述两步流程、返回格式、可选参数、错误处理、advanced 用法。
  10. **`.codemaker/skills/multi-agent-tcp/SKILL.md`（更新）**：新增 Prerequisite（`init_skill_list`）、Two-Step Workflow（`show-registry` → `dispatch`）、Key Rules、result format。标注 legacy 命令。
  11. **`__init__.py`**：导出 `show_registry_response`，版本升至 `0.5.0`。
- **涉及**：`cluster.py`、`registry.py`、`__main__.py`、`__init__.py`、`GUIDE_FOR_CODEMAKER.md`（新）、`.codemaker/skills/multi-agent-tcp/SKILL.md`、`.cursor/skills/multi-agent-tcp/SKILL.md`

- **日期**：2026-04-17（v0.4.1：Registry UI — Tkinter 可视化管理 agents_registry.json）
- **摘要**：
  1. **`registry_ui.py`（新）**：Tkinter 桌面应用（~890 行），可视化管理 `agents_registry.json`。
     - **主窗口**：Catppuccin Mocha 深色主题（`#1e1e2e` 背景）；顶栏 Undo/Title/Save 按钮；Canvas + Scrollbar 可滚动卡片网格（鼠标滚轮、响应式列数重排）。
     - **Agent 卡片**：显示 agent_id（粗体）、display_name、model（去前缀短名）、skills 数、enabled 状态（绿/红圆点）；右上角 `✕` 删除按钮（带确认）；双击进入编辑对话框。
     - **"+" 添加卡片**：点击打开新建 agent 对话框。
     - **编辑对话框**（`AgentDetailDialog`，modal Toplevel）：agent_id / display_name / model / cwd（含 Browse 文件夹选择） / timeout_sec / enabled / skills 七个字段。
     - **Model 下拉框**（ttk.Combobox）：启动时通过 `codemaker models` 子进程实时获取可用模型列表（缓存），合并 registry 中已用模型；Combobox `postcommand` 每次下拉时从缓存刷新。
     - **Skill 多选弹窗**（`SkillPickerPopup`）：从 `skill_list/manifest.json` 加载；每项显示 skill 名（粗体）+ 描述（小字灰色）；复选框选中/取消。
     - **状态管理**：`_saved_state` / `_current_state` 深拷贝比对；Undo 回滚至上次保存；Save 写 JSON；关闭窗口时未保存提示。
     - **性能优化**：Configure 事件 `after(30ms)` 防抖避免级联；hover 预收集扁平控件列表 + 指针边界检查避免子控件边界抖动；model 下拉仅读缓存不阻塞 UI 线程。
  2. **`__main__.py`**：新增 `registry-ui` 子命令（`python -m multi_agent_tcp registry-ui`）。
  3. **版本**：未改动 `__init__.py` 版本号（仍为 `0.4.0`）。
- **涉及**：`registry_ui.py`（新）、`__main__.py`、`SKILL.md`

- **日期**：2026-04-17（v0.4.0：Agents 配置表 + Skill 合并体系 + Session-gated dispatch）
- **摘要**：
  1. **Agents 配置表**：新增 `agents_registry.json`（用户可编辑的 agent 配置表，含 model/skills/cwd/timeout_sec/enabled）+ `registry.py`（`AgentsRegistry` 加载/查询类、`AgentProfile`/`SkillInfo`/`AgentSession` 数据类）。Cursor/CodeMaker 拉起 agents 时只能从此表中选取。
  2. **Skill 合并体系**：新增 `init_skill_list.py`，将 `.codemaker/skills`（12 个）和 `.cursor/skills`（17 个）合并去重到 `skill_list/`（25 个，重复以 `.codemaker` 为准），生成 `manifest.json` 索引。
  3. **Catalog 按需读取**：`build_skill_catalog()` 生成轻量目录表（~50 chars/skill，仅 name + description + file path），替代 `build_skill_preamble_full()` 的全量注入（~6K chars/skill）。Agent 通过 `read` 工具按需读取 SKILL.md。`inject_skills_into_prompt(mode="catalog"|"full")` 支持两种模式。
  4. **Session-gated dispatch**：CLI 新增 `list-agents`（生成 5 位随机 session_id + 可用 agents 快照）和 `run-agent --session-id --agent-id --prompt`（校验 session → 拉起 agent）。三道校验：session 存在性、1 小时 TTL 过期、agent_id 白名单。Session 文件持久化在 `sessions/` 目录。
  5. **`__init__.py`**：导出 `AgentsRegistry`、`AgentProfile`、`AgentSession`、`SkillInfo`，版本升至 `0.4.0`。
  6. **`.gitignore`**：新增 `sessions/`、`skill_list/`。
  7. **`test_skill_injection.py`**：Skill 注入验证测试脚本（支持 `--mode catalog|full`）。
- **涉及**：`registry.py`（新）、`init_skill_list.py`（新）、`agents_registry.json`（新）、`test_skill_injection.py`（新）、`__main__.py`、`__init__.py`、`.gitignore`、`SKILL.md`

- **日期**：2026-04-17（v0.3.0：结构化结果 + fan-out→reduce + LLM 精简序列化）
- **摘要**：
  1. **P0-1 结构化结果传递**：新增 `WorkerResult` dataclass（worker/status/answer/raw_stdout/stderr/elapsed_sec）、`ParallelResult` 类（succeeded/failed/all/ok/summary/raw 属性）。`run_parallel()` 返回 `ParallelResult` 取代原始 dict。`run_chain()` 的 `inject_prev` 改为注入结构化 context dict（`{worker, status, answer}`）。
  2. **P0-2 fan-out→reduce**：新增 `run_parallel_reduce()` 方法（`run_parallel` + `run_single` 语法糖）、`ReduceResult` dataclass（parallel + reduce + answer + ok）。CLI 新增 `run-parallel-reduce` 子命令。
  3. **`to_dict()` / `to_raw_dict()` 双序列化**：`to_dict()` 只输出 `status` + `answer`（LLM 友好，过滤 raw_stdout/stderr/worker/elapsed_sec 四个噪音字段）；`to_raw_dict()` 保留完整字段供调试。三个类（WorkerResult/ParallelResult/ReduceResult）均实现。
  4. **Broker 消息泄漏修复**：`broker.py` 的 `_handle_client` 中 `gather_reply` 消息在 `_on_gather_reply` 后缺少 `continue`，导致同时作为普通 `message` 转发到 orchestrator 队列，污染 `run_chain` 的 `wait_for_message`。已修复。
  5. **CLI/Demo 更新**：`__main__.py` 新增 `run-parallel-reduce` 命令、`--raw-output` 参数；`demo_gclient_three_search.py` 改用 `to_raw_dict()` 写调试文件；`HOWTO.txt` 更新 API 示例。
  6. **版本**：`__init__.py` 升至 `0.3.0`，导出 `ParallelResult`、`ReduceResult`、`WorkerResult`。
- **涉及**：`cluster.py`、`broker.py`、`__init__.py`、`__main__.py`、`demo_gclient_three_search.py`、`examples/HOWTO.txt`、`SKILL.md`

- **日期**：2026-04-17（失败重试 + Broker 并发安全 + 心跳修复）
- **摘要**：
  1. **`cluster.py` 失败重试**：新增 `is_retryable_error()`（检测 `database is locked` 等可重试 stderr 模式）、`_retry_failed()` 方法（串行重试避免锁冲突）。`run_parallel()` 新增 `max_retries`（默认 0）/ `retry_delay_sec`（默认 5.0）参数。`is_retryable_error` 加入 `__init__.py` 导出。
  2. **`broker.py` 心跳驱逐修复**：`_run_batch_gather` 从 `await`（阻塞 handler 循环、导致 orchestrator 无法回 pong 被 75s 驱逐）改为 `asyncio.create_task()`（非阻塞）。拆分为外壳 `_run_batch_gather`（异常兜底 + `_pop_gather` 清理）+ `_run_batch_gather_inner`（原逻辑）。新增 `_on_gather_task_done` done callback 立即 `log.error` 未捕获异常。
  3. **`broker.py` 并发写安全**：新增 `_write_locks: Dict[StreamWriter, Lock]` per-connection 写锁、`_safe_write_frame()` 封装。所有 broker 内 `write_frame` 调用替换为 `_safe_write_frame`，防止 handler 与 gather task 并发写同一 writer 时帧交错。连接关闭时清理写锁。
  4. **`__main__.py` CLI**：`run-parallel` 新增 `--max-retries`（默认 2）/ `--retry-delay-sec`（默认 5.0）。
  5. **`demo_gclient_three_search.py`**：新增 `--max-retries` / `--retry-delay-sec` CLI 参数，传入 `run_parallel()`。
- **涉及**：`cluster.py`、`broker.py`、`__init__.py`、`__main__.py`、`demo_gclient_three_search.py`、`SKILL.md`

- **日期**：2026-04-16（仅文档/skill 同步——确认与代码一致）
- **摘要**：全量比对 `cluster.py`、`__main__.py`、`__init__.py`、`demo_three_codemakers.py`、`demo_gclient_three_search.py`、`examples/HOWTO.txt` 及全部 12 个 examples/ 配置文件，确认 SKILL.md 各节（架构表、CodeMakerCluster API 签名、CLI 速查、batch_gather 协议、demo 描述）与实际代码完全一致。无需修订。
- **涉及**：无代码变更；仅本文件归档记录新增。

- **日期**：2026-04-16（CodeMakerCluster API + Demo 落地 + 框架定调）
- **摘要**：
  1. **`cluster.py` 新增**：`WorkerConfig` dataclass + `CodeMakerCluster` 类（`create`/`connect` 两种工厂、`run_parallel`/`run_chain`/`run_single` 任务方法、`stop`/`close` 生命周期、async context manager）。结果解析 `extract_final_text`/`summarize_gather_result` 从 demo 提取为公共函数。
  2. **`__main__.py` 新增 CLI**：`cluster start`（常驻集群）、`run-parallel`（并行）、`run-chain`（串行链），支持 `--config cluster.json`（一次性）或 `--port`（连已有集群）。
  3. **`__init__.py`**：导出 `CodeMakerCluster`、`WorkerConfig`，版本升至 0.2.0。
  4. **Demo 重写**：`demo_three_codemakers.py`（~70 行）和 `demo_gclient_three_search.py`（~120 行）改用 `CodeMakerCluster`，代码量分别从 214/311 行大幅缩减。
  5. **示例配置**：新增 `examples/cluster.json`、`examples/tasks_parallel.json`、`examples/tasks_chain.json`。
  6. **HOWTO.txt**：新增 "Quick Start with CodeMakerCluster" 章节置顶。
  7. **SKILL.md 定调**：框架定位改为 "CodeMaker CLI 多实例编排框架"。
- **涉及**：`cluster.py`（新）、`__main__.py`、`__init__.py`、`demo_three_codemakers.py`、`demo_gclient_three_search.py`、`examples/cluster.json`（新）、`examples/tasks_parallel.json`（新）、`examples/tasks_chain.json`（新）、`examples/HOWTO.txt`、`SKILL.md`

- **日期**：2026-04-16（CodeMaker CLI 合规排查 + 文件名修正）  
- **摘要**：  
  1. **模型前缀校验**：`_parse_codemaker_cfg` 中对 `model` 不以 `netease-codemaker/` 开头时 `log.warning`（不阻断，兼容自定义 AIGW）。  
  2. **permission 配置检查**：新增 `_check_permission_config`，首次 `codemaker_run` 时读 `cwd` 下 `codemaker.json` 的 `permission` 字段，非 `"allow"` 则 warning 提示可能因权限审批挂起。每个 `cwd` 只告警一次（`_permission_warned` set）。  
  3. **`prompt_via_file='never'` + 非 ASCII 告警**：`codemaker_run` 中检测到 prompt 含非 ASCII 但被强制走 argv 时 warning，建议改用 `'auto'`。  
  4. **文件名拼写修正**：`codemaker_cil.md` → `codemaker_cli.md`，全部 7 处引用已更新。  
- **涉及**：`codemaker_bridge.py`、`codemaker_cli.md`（重命名）、`SKILL.md`、demo 脚本、`HOWTO.txt`

- **日期**：2026-04-16（端口冲突 / 进程残留 / 心跳探活 / 日志落盘）  
- **摘要**：日志落盘 `log_setup.py`；端口冲突检测；`_proc_utils.py` 进程树清理；请求-应答式心跳；gather 断连感知。

- **日期**：2026-04-16（batch_gather + 可观测性 + 输出过滤）  
- **摘要**：batch_gather 协议、GatherState、gather_reply/gather_result；gclient 并行搜索 demo；结构化日志前缀；NDJSON 文本提取。

- **日期**：2026-04-16（orchestrate + 初版）  
- **摘要**：orchestrate 配方 CLI；初版 broker/agent/codemaker-worker。

---

## 变更记录（历史）

| 日期 | 摘要 |
|------|------|
| 2026-04-30 | **项目定位转向：peer-to-peer agent CLI 协作（纯文档/skill 同步，未改 .py 代码）**：取消"Cursor / CodeMaker 是上游 orchestrator"叙事；SKILL（Cursor + CodeMaker 两份）/ ROADMAP / README / HOWTO 全文重写；删除 `GUIDE_FOR_CODEMAKER.md` → 新建 `GUIDE_FOR_AGENTS.md`（面向任意 agent CLI / 脚本调用方）；ROADMAP 撤销旧"模型抽象层不做"条目改为"做最薄的 CLI Adapter"；脑暴文档新增 §10「对等通信原语 vs 编排原语」；CLI 命令名 / 配置 schema / 协议 100% 兼容。 |
| 2026-04-17 | **v0.5.1：异步 dispatch + 文件轮询**：`dispatch --async`（detached 后台进程 + job 跟踪）；`dispatch-status --wait N`（CLI 备选）；`_is_process_alive` 跨平台进程检测；result 嵌入状态文件；**推荐 LLM 用 `read` 工具轮询 `status_file`**（无审批/超时/中断）；`GUIDE_FOR_CODEMAKER.md` Section 4b 重写。 |
| 2026-04-17 | **v0.5.0：show-registry / dispatch 两步 LLM 流程**：`show-registry` 只读查询 + `dispatch` 一站式并行（registry → skill 注入 → 执行 → 结果）；`create_from_registry()` + `_inject_skills()` 自动注入；`_add_connect_args` 支持 `--registry`；`GUIDE_FOR_CODEMAKER.md`；session-gated 标记 legacy；v0.5.0。 |
| 2026-04-17 | **v0.4.1：Registry UI**：`registry_ui.py` Tkinter 桌面应用（深色主题、卡片网格、model 实时下拉 `codemaker models`、skill 多选弹窗、undo/save 状态管理、Configure 防抖 + hover 优化）；CLI `registry-ui` 子命令。 |
| 2026-04-17 | **v0.4.0：Agents 配置表 + Skill 合并体系 + Session-gated dispatch**：`agents_registry.json` + `AgentsRegistry`/`AgentProfile`/`AgentSession`/`SkillInfo`；`init_skill_list.py` 合并 `.codemaker/skills` + `.cursor/skills` → `skill_list/`（25 个 skill，`.codemaker` 优先）；catalog 按需读取替代全量注入；`list-agents`/`run-agent` CLI（5 位 session_id + TTL + 白名单校验）；v0.4.0。 |
| 2026-04-17 | **v0.3.0：结构化结果 + fan-out→reduce + LLM 精简序列化**：`WorkerResult`/`ParallelResult`/`ReduceResult` 类型；`run_parallel` 返回 `ParallelResult`；`run_parallel_reduce` fan-out→reduce；`to_dict()`（LLM 精简）/`to_raw_dict()`（调试完整）双序列化；chain 结构化 context 注入；broker gather_reply 消息泄漏修复；CLI `run-parallel-reduce`/`--raw-output`；v0.3.0。 |
| 2026-04-17 | **失败重试 + Broker 并发安全 + 心跳修复**：`is_retryable_error` + `_retry_failed` + `run_parallel(max_retries)` 串行重试；broker gather 改 `create_task` 非阻塞 + 异常兜底；per-connection `_safe_write_frame` 写锁；CLI/demo 新增 `--max-retries`/`--retry-delay-sec`。 |
| 2026-04-16 | **CodeMakerCluster API + Demo 落地 + 框架定调**：`cluster.py`（WorkerConfig + CodeMakerCluster）、CLI `cluster start`/`run-parallel`/`run-chain`、demo 重写、示例配置、`__init__` 导出 v0.2.0。 |
| 2026-04-16 | CodeMaker CLI 合规排查：模型前缀校验、permission 检查、never+非 ASCII 告警；文件名修正。 |
| 2026-04-16 | 日志落盘；端口冲突检测；进程树清理；请求-应答式心跳；gather 断连感知。 |
| 2026-04-16 | batch_gather 并行聚合协议；gclient 并行搜索 demo；结构化日志前缀；NDJSON 文本提取。 |
| 2026-04-16 | orchestrate 配方 CLI；初版 broker/agent/codemaker-worker。 |
