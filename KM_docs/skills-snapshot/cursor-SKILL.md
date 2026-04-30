# multi_agent_tcp — 多 agent CLI 之间的对等通信总线 + 多 agent 管理

> **框架核心目的**：在多个 **agent CLI**（CodeMaker / Claude Code / Codex / 自研）之间提供一个**对等通信总线**与**多 agent 生命周期/会话/能力管理层**。任何 agent CLI 都既可以作为消息**接收方**，也可以作为**发起方**通过 broker 给其它 agent 发任务、查能力、做协作。框架本身**不替代** agent 的 LLM 推理、tool calling、规划与决策——这些仍由各 CLI 自己完成。
>
> 历史背景：早期版本曾以"Cursor / CodeMaker 作为上游决策者拉起多 worker"为主叙事；自 2026-04-30 起项目**全面转向"agent CLI 之间对等协作"**，旧叙事不再使用。归档详见 [`ARCHIVE.md`](ARCHIVE.md) 顶部条目。

**定位**：进程级的 **agent-to-agent 通信总线**——所有 agent CLI（含外部 Python 脚本/CI）以**对等节点**身份接入同一 broker，通过 `agent_id` 寻址互发任务、聚合结果、串行流水。`CodeMakerCluster` Python 类是其中一种发起方实现，`show-registry` / `dispatch` 等 CLI 命令既能被外部脚本用，也能被另一个 agent CLI 在自己的 bash 工具里触发。

**代码根路径**：`f:\src\Package\Script\Python\multi_agent_tcp\`  
**用户文档**：`multi_agent_tcp/examples/HOWTO.txt`  
**面向 agent CLI 的接入指南**：`multi_agent_tcp/GUIDE_FOR_AGENTS.md`（取代旧 `GUIDE_FOR_CODEMAKER.md`）  
**CodeMaker CLI 笔记（仅本地）**：`multi_agent_tcp/codemaker_cli.md`（已 **gitignore**；当前 CodeMaker 是唯一已落地的 CLI Adapter，对照 CLI 时自备该文件）  
**GitHub（公开仓库）**：https://github.com/QHXRPG-A/multi_agent_tcp  

**Cursor skill 维护范围**：用户若说「只更新 Cursor skill」，**仅改** `.cursor/skills/multi-agent-tcp/SKILL.md`；`.codemaker/skills/multi-agent-tcp/SKILL.md` 为另一份拷贝（面向 agent CLI 自身消费，结构不同），需另行手动或脚本同步。

## 最近归档

完整历史（**最近归档**长条目 + **变更记录**简表）见同目录 **[`ARCHIVE.md`](ARCHIVE.md)**。权威归档日期以 `ARCHIVE.md` 内「最近归档」**第一条**为准。

## GitHub 与一键提交/更新

- **仓库**：https://github.com/QHXRPG-A/multi_agent_tcp  
- **本地根目录**：`multi_agent_tcp/`（内含 `.git/`）。在终端先 `cd` 到该目录再执行 git；不要在上级 `Python/` 目录误用 `git`（除非用户明确管理的是单仓大库）。

### 拉取更新（与远程 `main` 对齐）

```bash
cd /f/src/Package/Script/Python/multi_agent_tcp   # 按本机路径调整
git fetch origin
git pull origin main
```

若推送时提示 non-fast-forward，可先：`git pull --rebase origin main`，解决冲突后再 `git push origin main`。

### 一键提交并推送（单条命令）

提交前用 `git status` 确认变更范围；`git commit` 需非空暂存区，否则命令失败。

**Git Bash / MINGW64：**

```bash
cd /f/src/Package/Script/Python/multi_agent_tcp
git add -A
git status
git commit -m "chore: <一句话摘要>"
git push -u origin main
```

可合并为一行（慎用，摘要仍要可读）：

```bash
git add -A && git commit -m "chore: your message" && git push origin main
```

**PowerShell：**

```powershell
Set-Location "F:\src\Package\Script\Python\multi_agent_tcp"
git add -A; git status; git commit -m "chore: your message"; git push origin main
```

### 与 Cursor skill 的关系

- **https://github.com/QHXRPG-A/multi_agent_tcp** 跟踪的是目录 **`multi_agent_tcp/`** 内的文件（包代码、`README.md`、`GUIDE_FOR_AGENTS.md` 等），**不包含**工作区根下的 `.cursor/skills/`（除非用户日后把 skill 移入该子目录或改仓库结构）。
- **本文件**路径为 `.cursor/skills/multi-agent-tcp/SKILL.md`：随 **Cursor 工作区根** 的 git 管理；与 `multi_agent_tcp` 子目录的 `git push` **可能是两次提交**（父仓 vs 子仓）。用户说「只更新 Cursor」时，Agent **只改**本文件，**不**改 `.codemaker/skills/multi-agent-tcp/SKILL.md`。

## 架构（必读）

```
┌────────────────────────────────────────────────────────────────────┐
│  Agent CLI A   Agent CLI B   Agent CLI C   ...   Python 脚本/CI    │
│       ▲              ▲              ▲                  ▲           │
│       │              │              │                  │           │
│       └──────────────┴──── TCP ─────┴──────────────────┘           │
│                              │                                     │
│                              ▼                                     │
│                          ┌────────┐                                │
│                          │ Broker │   寻址 / 邮箱 / 心跳 / 会话    │
│                          └────────┘   断连感知 / batch_gather       │
└────────────────────────────────────────────────────────────────────┘
```

所有节点对等：任何节点可发 unicast、broadcast、batch_gather；broker 只做**通信基础设施**，不做决策。

| 组件 | 文件 | 职责 |
|------|------|------|
| **Cluster（发起方门面）** | `cluster.py` | `CodeMakerCluster`：发起方便捷类——管理 broker + N 个 worker 子进程生命周期；**`create_from_registry()`**（推荐，从 `AgentsRegistry` 创建集群 + 自动 skill 注入）/ `create()` / `connect()` 三种工厂；`_inject_skills()` 自动在 `run_parallel`/`run_chain`/`run_single` 前注入 skill catalog；`set_registry()` 事后绑定；`run_parallel`（→`ParallelResult`，含 `max_retries` 失败重试）/ `run_parallel_reduce`（→`ReduceResult`）/ `run_chain` / `run_single` 高层任务方法；`WorkerConfig` / `WorkerResult` / `ParallelResult` / `ReduceResult` 数据类型（`to_dict` 精简 / `to_raw_dict` 调试完整）；`is_retryable_error` 可重试错误检测；结果解析 `extract_final_text`。注：当前是发起方常用入口，未来增加 CLI Adapter 抽象后会与 broker 解耦得更彻底 |
| **Async Dispatch（异步作业）** | `__main__.py` 内 | `dispatch --async`（detached 后台进程）+ `dispatch-status`（CLI 轮询备选）；job 跟踪：`DISPATCH_JOBS_DIR`、`_write_job_status`/`_read_job_status`/`_check_job_once`/`_is_process_alive`；**推荐发起方用 `read` 工具直接读 `status_file` 轮询**（无审批/超时/中断）；完成时 result 嵌入状态文件 |
| **Registry（agent 配置表）** | `registry.py` | `AgentsRegistry`：加载 `agents_registry.json`；`AgentProfile` / `SkillInfo` / `AgentSession` 数据类型；`show_registry_response()` 只读查询（供 `show-registry` CLI）；`build_worker_configs()` 将 profile 转 `WorkerConfig`；skill catalog 按需读取（`build_skill_catalog` / `inject_skills_into_prompt`）；session-gated dispatch（`create_session` / `validate_session`，5 位随机 ID + 1h TTL） |
| **Registry UI** | `registry_ui.py` | Tkinter 桌面应用，可视化管理 `agents_registry.json`（卡片网格 + 编辑对话框 + model 实时下拉 + skill 多选弹窗）；CLI `registry-ui` 启动 |
| **Agents 配置** | `agents_registry.json` | 用户可编辑的 agent 注册表：每个 agent 含 `model` / `skills` / `cwd` / `timeout_sec` / `enabled`。任何发起方（外部脚本 / 另一个 agent CLI）拉起 agents 时**只能从此表中选取** |
| **Skill 合并** | `init_skill_list.py` | 将 `.codemaker/skills` + `.cursor/skills` 合并去重到 `skill_list/`（`.codemaker` 优先）；生成 `manifest.json` |
| **Broker** | `broker.py` | 单端口监听；对等通信总线核心；`register` / `send` / `broadcast` / `ping` / **`batch_gather`**（非阻塞 `create_task` + 异常兜底）；`GatherState` 管理并行聚合；`_safe_write_frame` per-connection 写锁；心跳探活；端口冲突检测；gather 断连感知 |
| **客户端** | `client.py` | `AgentTCPClient`：`connect`、`send_to`、`broadcast`、`incoming()`、`wait_for_message`、`batch_gather()`；`pump()` 独立 task 自动回 pong。任何 agent CLI / 脚本都可以用它接入 broker |
| **帧协议** | `protocol.py` | 4 字节大端长度 + UTF-8 JSON |
| **CodeMaker CLI Adapter** | `codemaker_bridge.py` | 子进程执行 `codemaker run`；超时时 `async_kill_process_tree`；运行时防御（模型前缀校验、permission 检查、never+非 ASCII 告警）。当前是**唯一已落地的 CLI Adapter**；未来 Claude Code / Codex / 自研 CLI 各自加 adapter（详见 `KM_docs/multi-cli-node-workflow-brainstorm.md`） |
| **编排 CLI（低层 recipe）** | `orchestrate.py` | 读 JSON 配方：send_to / broadcast / wait_for / batch_gather；适合预定义的固定步骤序列 |
| **Agent CLI 接入指南** | `GUIDE_FOR_AGENTS.md` | 面向**任意 agent CLI / 脚本调用方**的接入文档：两步流程（`show-registry` → `dispatch`）；异步 dispatch（`--async` + `read` 工具轮询 `status_file`）；返回格式、可选参数、错误处理。取代旧 `GUIDE_FOR_CODEMAKER.md` |
| **包 CLI** | `__main__.py` | 低层：`broker` / `agent` / `spawn`；**通用接入流程：`show-registry` / `dispatch`（含 `--async`）/ `dispatch-status`**——任意 agent CLI 或脚本均可调用；高层：`cluster start` / `run-parallel`（支持 `--registry`）/ `run-parallel-reduce` / `run-chain`；Legacy：`list-agents` / `run-agent`；GUI：`registry-ui` |
| **日志** | `log_setup.py` | `setup_logging(verbose, name)`：stderr + RotatingFileHandler |
| **进程工具** | `_proc_utils.py` | `kill_process_tree`（Windows `taskkill /T`）、`terminate_and_wait`、`async_kill_process_tree` |

**端口**：仅 **broker 进程 bind** 一个端口；各 agent CLI / 脚本作为 **TCP 客户端**接入该端口，多连接共存。

## 三种典型协作拓扑

| 拓扑 | 谁是发起方 | 适用场景 |
|------|------------|----------|
| **外部脚本 → broker → N 个 agent CLI** | Python 脚本 / CI / 工具 | 批跑、CI 任务、自动化扫描 |
| **agent CLI A → broker → agent CLI B/C/...** | 另一个 agent CLI（在 prompt 处理中通过 bash 工具触发 `dispatch`） | 一个 agent 自己拆任务，把子任务派给其它 agent 协作 |
| **agent CLI A ↔ broker ↔ agent CLI B** | 双方都可发起 | 双向流水（A 出方案 → B 评审 → A 修订） |

> 三种拓扑都用同一套底层协议（`send_to` / `batch_gather`）；区别只是**谁先开口**。

## CodeMakerCluster API（发起方便捷入口）

> 这是 Python 代码层的**发起方**便捷类。任何接入 broker 的 agent / 脚本都可以用它批量提交任务；底层仍是 `AgentTCPClient.batch_gather`。

### 创建集群

```python
from multi_agent_tcp import CodeMakerCluster, WorkerConfig, AgentsRegistry
from pathlib import Path

# 方式 1（推荐）：从 registry 创建，自动注入 Skills
reg = AgentsRegistry.load()
cluster = await CodeMakerCluster.create_from_registry(
    reg,
    agent_ids=["agent-1", "agent-2"],  # None = all enabled
    skill_mode="catalog",               # "catalog"(默认) 或 "full"
    port=9140,
)

# 方式 2：手动指定 workers（无自动 skill 注入）
cluster = await CodeMakerCluster.create(
    workers=[
        WorkerConfig("cm1", cwd=Path("F:/src")),
        WorkerConfig("cm2", cwd=Path("F:/src")),
    ],
    port=9140,
)
# 可事后绑定 registry 启用 skill 注入：
cluster.set_registry(reg, skill_mode="catalog")

# 方式 3：连接已运行的集群
cluster = await CodeMakerCluster.connect(port=9140)
```

### 提交任务

```python
# 并行（batch_gather）→ ParallelResult
par = await cluster.run_parallel([
    ("cm1", {"prompt": "Task A"}),
    ("cm2", {"prompt": "Task B"}),
])
for wr in par.succeeded:          # List[WorkerResult]
    print(wr.worker, wr.answer[:200])
print(par.ok)                     # True if all succeeded
print(par.to_dict())              # 精简 (status + answer)
print(par.to_raw_dict())          # 调试 (含 raw_stdout/stderr/elapsed)

# 并行 + 失败重试
par = await cluster.run_parallel(
    [("cm1", {"prompt": "A"}), ("cm2", {"prompt": "B"}), ("cm3", {"prompt": "C"})],
    max_retries=2,
    retry_delay_sec=5.0,
)

# fan-out → reduce → ReduceResult
rr = await cluster.run_parallel_reduce(
    tasks=[("cm1", {"prompt": "A"}), ("cm2", {"prompt": "B"})],
    reduce_worker="cm1",
    reduce_prompt="Merge:\n{results}",
)
print(rr.answer)                  # reduce worker's final answer
print(rr.parallel.succeeded)      # fan-out results

# 串行链（自动注入结构化 context dict）
results = await cluster.run_chain([
    ("cm1", {"prompt": "Step 1"}),
    ("cm2", {"prompt": "Step 2, continue..."}),
])
# 每步收到：body["context"] = {"worker": "cm1", "status": "success", "answer": "..."}

# 单任务
reply = await cluster.run_single("cm1", {"prompt": "One task"})
```

### 生命周期

```python
# async context manager（推荐）
async with await CodeMakerCluster.create(workers=...) as cluster:
    ...  # stop() 自动调用

# 手动
await cluster.stop()   # create() 模式：杀所有子进程
await cluster.close()  # connect() 模式：仅关闭 TCP 连接
```

### 从 JSON 配置加载

```python
import json
data = json.loads(Path("cluster.json").read_text())
workers = CodeMakerCluster.workers_from_json(data)
host, port = CodeMakerCluster.host_port_from_json(data)
```

## Agents 配置表 + Skill 体系

### agents_registry.json（用户编辑 / Registry UI）

可通过 `python -m multi_agent_tcp registry-ui` 打开图形界面编辑，也可直接编辑 JSON：

```json
{
  "skill_list_dir": "skill_list",
  "agents": {
    "agent-1": {
      "display_name": "助手 Alpha",
      "model": "netease-codemaker/kimi-k2.5",
      "cwd": "F:/src/Package/Script/Python",
      "skills": ["excel-export-flow", "messiah-ui-dev"],
      "timeout_sec": 1800,
      "enabled": true
    }
  }
}
```

### Skill 合并（init_skill_list.py）

```bash
python -m multi_agent_tcp.init_skill_list [--force]
```

将 `.codemaker/skills` 和 `.cursor/skills` 合并到 `skill_list/`：
- 重复 skill（同名目录）以 `.codemaker` 版本为准
- 生成 `skill_list/manifest.json`（name → description/source/file_count）
- `skill_list/` 已 gitignore，需时重跑即可

### Skill 注入策略（catalog 按需读取）

> 当前 catalog 注入语义为 **CodeMaker / OpenCode 体系下的"agent 自带 read 工具 + SKILL.md 触发约定"**。Claude Code / Codex 等其它 CLI 接入后需各自适配（见 `KM_docs/multi-cli-node-workflow-brainstorm.md` §7）。

**不把全部 SKILL.md 塞进 prompt**（~6K chars/skill，10 个 skill = 60K chars）。

改用轻量目录表（~50 chars/skill）+ agent 按需 `read`：

```python
reg = AgentsRegistry.load()
# catalog 模式（默认，推荐）：~500 chars 目录表
prompt = reg.inject_skills_into_prompt("agent-1", task, mode="catalog")
# full 模式（legacy）：嵌入完整 SKILL.md 内容
prompt = reg.inject_skills_into_prompt("agent-1", task, mode="full")
```

接收方 agent 收到的 catalog 示例：

```
| Skill | Description | SKILL.md Path |
|-------|-------------|---------------|
| `excel-export-flow` | 导表流程 | `F:/.../skill_list/excel-export-flow/SKILL.md` |
| `messiah-ui-dev` | 弥赛亚UI开发 | `F:/.../skill_list/messiah-ui-dev/SKILL.md` |

Total: 2 skill(s). Use the `read` tool to load the full SKILL.md when needed.
```

### show-registry / dispatch 通用接入流程

任意发起方（外部 Python 脚本 / CI / **另一个 agent CLI 通过 bash 工具触发**）协调多 agent 的标准两步：

1. **`show-registry`**（只读，无副作用）：返回所有 enabled agent 的 `agent_id` / `display_name` / `model` / `skills`（含 description）/ `cwd` / `timeout_sec`。发起方据此决策用哪些 agent。

```bash
python -m multi_agent_tcp show-registry [-o agents.json]
```

返回示例：
```json
{
  "count": 3,
  "message": "3 agent(s) available. Use `dispatch` with agent_id + prompt pairs to run tasks.",
  "agents": [
    {"agent_id": "agent-1", "display_name": "助手 Alpha", "model": "netease-codemaker/kimi-k2.5",
     "skills": [{"name": "messiah-ui-dev", "description": "弥赛亚引擎游戏UI开发"}],
     "cwd": "F:/src/Package/Script/Python", "timeout_sec": 1800}
  ]
}
```

2. **`dispatch`**（一站式并行执行）：接收 `[{"agent_id":"...","prompt":"..."}, ...]` 任务列表，自动加载 registry → 验证 agent_id → `create_from_registry` 创建集群 → 注入 Skills → 并行执行 → 返回结构化结果。

```bash
# 同步（阻塞直到完成，适合 <30 秒的快速任务）
python -m multi_agent_tcp dispatch --tasks tasks.json [-o result.json]
# 异步（立即返回 job_id + status_file，推荐用于分钟级任务）
python -m multi_agent_tcp dispatch --async --tasks tasks.json
```

| 参数 | 默认 | 说明 |
|------|------|------|
| `--port` | 9140 | broker 端口 |
| `--timeout` | 1800 | 整体超时（秒） |
| `--max-retries` | 2 | 可重试错误重试次数 |
| `--retry-delay-sec` | 5.0 | 重试间隔 |
| `--skill-mode` | catalog | `catalog`（轻量）或 `full`（嵌入完整 SKILL.md） |
| `--async` | — | 后台执行，立即返回 `job_id` + `status_file` |

返回结果含 `dispatched_agents` 字段标识实际分发的 agent。

**异步 dispatch 轮询**（`--async` 模式）：

发起方启动 `dispatch --async` 后用 **`read` 工具直接读 `status_file`** 轮询（不走终端命令），直到 `status` 变为 `completed`（result 嵌入状态文件）或 `failed`。read 工具无需用户审批、无超时风险、不会中断 LLM 轮次。备选：`dispatch-status --job-id <id> [--wait N]`（终端命令，不推荐——有审批/超时/中断风险）。

### Session-gated agent dispatch（legacy，仍可用）

> **注意**：推荐使用上方的 `show-registry` + `dispatch` 流程。Session-gated 方式仍可用于需要 session 校验的场景。

发起方拉起 agent 的 legacy 两步：

1. **`list-agents`**：读取 registry，生成 5 位随机 `session_id`，返回可用 agents 列表
2. **`run-agent --session-id XXXXX --agent-id agent-1 --prompt "..."`**：校验 session 后拉起

三道校验防止盲目拉取未配置 agent：

| 校验 | 失败场景 | 错误信息 |
|------|----------|----------|
| session 存在性 | 没调过 `list-agents` | `Session XXXXX not found` |
| TTL 过期 | session 超过 1 小时 | `Session expired` |
| agent 白名单 | agent_id 不在 session 快照中 | `Agent 'xxx' is not in session` |

Session 文件持久化在 `sessions/`（已 gitignore），过期自动清理。

```python
# Python API
reg = AgentsRegistry.load()
session = reg.create_session()           # 生成 session
print(session.session_id)                # "58248"
print(session.to_list_response())        # 发起方可消费的 JSON

AgentsRegistry.validate_session("58248", "agent-1")  # 校验
```

## CLI 速查

```text
# ---- show-registry / dispatch（任意发起方通用两步流程）----
python -m multi_agent_tcp show-registry [-o agents.json]
python -m multi_agent_tcp dispatch --tasks tasks.json [-o result.json] [--max-retries 2] [--skill-mode catalog]
python -m multi_agent_tcp dispatch --tasks-json '[{"agent_id":"agent-1","prompt":"..."}]' -o result.json
# 异步 dispatch（推荐用于分钟级任务，发起方用 read 工具轮询 status_file）
python -m multi_agent_tcp dispatch --async --tasks tasks.json
python -m multi_agent_tcp dispatch-status --job-id <job_id> [--wait 25]  # 备选终端轮询

# ---- Session-gated dispatch（legacy，仍可用）----
python -m multi_agent_tcp list-agents [-o result.json]
python -m multi_agent_tcp run-agent --session-id 58248 --agent-id agent-1 --prompt "任务描述"
python -m multi_agent_tcp run-agent --session-id 58248 --agent-id agent-1 --prompt-file task.md --skill-mode full

# ---- 高层（支持 --config / --registry / --port 三选一）----
python -m multi_agent_tcp cluster start --config multi_agent_tcp/examples/cluster.json
python -m multi_agent_tcp run-parallel --registry --tasks tasks.json -o result.json --skill-mode catalog
python -m multi_agent_tcp run-parallel --config multi_agent_tcp/examples/cluster.json --tasks multi_agent_tcp/examples/tasks_parallel.json -o result.json
python -m multi_agent_tcp run-parallel --port 9140 --tasks tasks.json
python -m multi_agent_tcp run-parallel --config cluster.json --tasks tasks.json --max-retries 2 --retry-delay-sec 5
python -m multi_agent_tcp run-parallel-reduce --registry --tasks tasks.json --reduce-worker agent-1 --reduce-prompt "Merge:\n{results}" -o result.json
python -m multi_agent_tcp run-chain   --registry --tasks tasks.json -o result.json

# ---- 低层（管道细粒度控制 / agent 直接接入）----
python -m multi_agent_tcp broker --config multi_agent_tcp/examples/broker.json
python -m multi_agent_tcp agent --config <agent.json> [--mode echo|listen|codemaker-worker]
python -m multi_agent_tcp spawn --config multi_agent_tcp/examples/spawn_three_codemaker.json
python -m multi_agent_tcp.orchestrate --recipe multi_agent_tcp/examples/recipe_chain.json

# ---- GUI（可视化管理 agents_registry.json）----
python -m multi_agent_tcp registry-ui
python -m multi_agent_tcp.registry_ui

# ---- Skill 合并 ----
python -m multi_agent_tcp.init_skill_list [--force]

# ---- 演示 / 测试 ----
python -m multi_agent_tcp.demo_three_codemakers [--port 9133]
python -m multi_agent_tcp.demo_gclient_three_search [--trace] [--port 9140] [--max-retries 2] [--retry-delay-sec 5]
python -m multi_agent_tcp.test_skill_injection [--agent-id agent-1] [--skill excel-export-flow] [--mode catalog|full]
```

## batch_gather 协议（对等通信总线核心）

> **关键定位**：batch_gather 是**对等通信原语**——任何接入 broker 的节点都能用它"一次给 N 个对等节点发不同消息、聚合所有回复"。它不预设"谁是上游谁是下游"，发起方与接收方角色对等。

一次 RPC 将不同消息并行发给多个 agent，broker 等到全部回复后聚合返回：

1. **发起方 → broker**：`{ "type": "batch_gather", "id": "<unique>", "timeout_sec": 300, "items": [{"to": "<agent_id>", "body": <json>}, ...] }`
2. **broker → 每个 target**：标准 `message` 帧 + `"gather": {"id": "...", "reply_to": "<initiator>"}`
3. **target → broker**：标准 `send` 帧 + `"gather_reply": "<same id>"`（echo / codemaker-worker 内置透传）
4. **broker → 发起方**：`{ "type": "gather_result", "id": "...", "ok": true|false, "replies": {...}, "errors": {...} }`

错误码：`pre_check_failed`（target 不在线）、`duplicate_gather_id`、`timeout`、`dispatch_failed`、`target_disconnected`。

**程序内**：`await client.batch_gather(gather_id, [(to, body), ...], timeout_sec=...)` → 返回 `gather_result` dict。`gather_result` 走专用 `_gather_futures`，不进入 `incoming()` / `_recv_queue`。

## 失败重试机制

`run_parallel()` 支持对可重试错误自动重试：

- **检测**：`is_retryable_error(reply)` 检查 `body.codemaker.stderr` 是否包含已知可重试模式（`"database is locked"`、`"resource temporarily unavailable"`）。
- **策略**：失败的 worker **逐个串行重试**（`run_single`），每次间隔 `retry_delay_sec`，避免再次并发锁冲突。
- **合并**：重试成功的结果替换回原始 `gather_result.replies`，最终重新评估 `ok` 状态。
- **参数**：`max_retries`（CLI 默认 2）、`retry_delay_sec`（CLI 默认 5.0）。API 层 `max_retries` 默认 0（不重试），需显式传入。
- **日志前缀**：`[retry]`。

## 编排配方（orchestrate）

低层替代方案，适合完全预定义的步骤序列：

- **前提**：broker 与目标 agents 已启动；本进程仅作 **TCP 客户端** 连 broker。  
- **命令**：`python -m multi_agent_tcp.orchestrate --recipe <path.json> [-o out.json] [-v]`  
- **步骤类型**：`send_to`、`broadcast`、`wait_for`、`batch_gather`。

## CodeMaker `codemaker run` 桥接（当前唯一 CLI Adapter，易错点）

> **定位提示**：`codemaker_bridge.py` 是当前框架内**唯一已落地的 CLI Adapter**。Claude Code、Codex、自研 CLI 的等价 adapter 是 ROADMAP 短期目标（详见 `KM_docs/multi-cli-node-workflow-brainstorm.md` §3）。

1. **必须有一条 message**：仅 `-f` 会报 `You must provide a message or a command`。  
2. **顺序**：`... [-m MODEL] <run_stub_message> -f <utf8文件>`（stub 在 `-f` **前**）。  
3. **勿在 `-f` 后再加长句 argv**：会被当成**文件路径**，报 `File not found: ...`。  
4. **中文/非 ASCII**：`prompt_via_file: auto`（默认）时写 UTF-8 临时文件，用 `-f` 传；`run_stub_message` 保持短 ASCII。  
5. 子进程环境带 `PYTHONUTF8=1`。临时文件在 `communicate` 结束后 `unlink` 清理。
6. **codemaker NDJSON stdout 解析**：`--format json` 输出 NDJSON。最终文本答案在 `{"type":"text", "part":{"text":"..."}}` 条目中。`extract_final_text()` / `summarize_gather_result()` 提取。
7. **模型前缀**：`-m` 参数必须为 `netease-codemaker/<model>`。
8. **permission 必须 `"allow"`**：`cwd` 下 `codemaker.json` 的 `permission` 不是 `"allow"` 时，非交互 `codemaker run` 可能挂起。
9. **`prompt_via_file='never'` + 非 ASCII**：Windows argv 编码可能损坏中文 prompt。

## 心跳探活协议

1. **Broker → agent**：每 30s 发 `{"type":"ping"}`。
2. **Agent → broker**：`pump()` 独立 task 立即回 `{"type":"pong"}`（codemaker 阻塞时也能秒回）。
3. **Broker 判定**：75s 无帧则驱逐。
4. **关键实现**：`_handle_client` 循环 **不会** 被 `_run_batch_gather` 阻塞（后者在 `create_task` 中执行），确保 handler 能持续读 pong 帧，避免发起方被误驱逐。

## 日志落盘

`log_setup.setup_logging(verbose, name)` → stderr + `multi_agent_tcp/logs/{name}_{ts}_{pid}.log`（20MB × 5）。`.gitignore` 已忽略 `logs/`。

## 进程树清理

`_proc_utils.py`：`kill_process_tree`（Windows `taskkill /T`）、`terminate_and_wait`、`async_kill_process_tree`。`CodeMakerCluster.stop()` 内部使用这些函数清理所有子进程。

## 结构化日志前缀

| 前缀 | 来源 | 含义 |
|------|------|------|
| `[orch]` | `client.py` / orchestrate | batch_gather 发送与接收（"orch" 是历史前缀名，含义现为"对等通信总线发起方"） |
| `[gather]` | `broker.py` | gather 生命周期 |
| `[heartbeat]` | `broker.py` | 心跳探活 |
| `[chain]` | `__main__.py` agent 循环 | codemaker-worker 收到消息 → codemaker_run → 回复 |
| `[retry]` | `cluster.py` | `run_parallel` 可重试失败的串行重试 |
| `[cil]` | `codemaker_bridge.py` | codemaker 子进程 spawn / EXIT / TIMEOUT |

## 路线图方向（仅文档承诺，详见 ROADMAP.md / KM_docs/multi-cli-node-workflow-brainstorm.md）

围绕"对等通信总线 + 多 agent 管理"持续演进：

- **CLI Adapter 抽象**：把 `codemaker_bridge.py` 重构为 `CodeMakerAdapter`，平行加 `ClaudeCodeAdapter` / `CodexAdapter`；`agents_registry.json` 增加 `cli_kind` 字段（向后兼容，缺省 codemaker）。
- **Discovery 升级**：`show-registry` 当前是最小发现机制；后续加 capability filter（按 skill / tag / cli_kind 寻址）。
- **多轮 conversation**：`run_chain` 已支持线性流水；后续加 `conversation_id` 让两个 agent 多轮往返。
- **Per-agent permission**：每个 agent 可声明"我接受谁发的任务、什么类型的任务"。
- **多模态消息**：当前协议只承载 JSON 文本；后续新增 `blob_put` / `blob_get` 帧（base64 + blob store）以支持图像/音频。
- **节点化工作流（headless）**：把"agent 调用 + 消息处理"建模成 DAG，节点编译到 `run_parallel` / `run_chain` / `run_single`。
  - **节点四类**（与 brainstorm §4.1 对齐）：
    - **Agent 节点**（重点）：节点系统里**唯一负责装载一个对等 agent CLI 的节点类型**——可视化编辑器里**用户拖出一个 Agent 节点 = 拉起一个 agent**。用户在节点检视面板上声明 `cli_kind`（codemaker / claude_code / codex / custom）/ `model` / `cwd` / `agent_id` / `skills` / `timeout_sec` / `adapter_options` / `extra_env`，并定义输入端口（`prompt` / `attachments` / `context`）与输出端口（`answer` / `attachments_out` / `status` / `raw`）。底层对应 `WorkerConfig` + `CLIAdapter`，与 `agents_registry.json` 共享 schema。完整字段表见 `KM_docs/multi-cli-node-workflow-brainstorm.md` §4.1.1。
    - **处理节点**（pure function）：纯函数式 message 转换，例 `Jinja2Render` / `JsonPathPick` / `MdStrip` / `ImageResize` / `JsonMerge`。
    - **路由节点**：控制流，例 `FanOut` / `FanIn` / `Switch`（对应 ROADMAP P2 条件路由的 `when=`）。
    - **I/O 节点**：与外部世界交互，例 `FileRead` / `FileWrite` / `HttpGet` / `McpCall` / `BlobPut` / `BlobGet`。
  - **可视化编辑器**：本框架不自研 UI；可视化阶段复用 vendored Ryven（MVP 第 ⑤ 步可选交付），节点定义复用 §4.1.1 / §4.2 schema，不重写编辑器。

## Windows 编码注意

- **不要**通过 PowerShell `| Out-File` 管道写中文 JSON。
- 使用 `Path.write_text(encoding="utf-8")` 或 CLI 的 `-o` 参数直写文件。

## 归档协议（维护本 skill）

当用户在本仓库、且上下文明确为 **multi_agent_tcp** 时说 **「归档」**（或「把 multi_agent_tcp 归档到 skill」等同义指令）时：

1. **读取** `.cursor/skills/multi-agent-tcp/SKILL.md` 与 **`ARCHIVE.md`**。  
2. **对照**当前 `multi_agent_tcp/` 下代码与 `examples/HOWTO.txt`、以及**本地** `codemaker_cli.md`（若存在）中与框架相关的实际行为，**修订 `SKILL.md` 正文各节**（架构、API、CLI、协议等）。  
3. 在 **`ARCHIVE.md`「最近归档」** 小节**顶部**插入一条新记录（含日期、摘要、涉及文件）。  
4. **权威归档日期**以 `ARCHIVE.md` 内「最近归档」**第一条**为准；若需同步简表，在 **`ARCHIVE.md`「变更记录」** 表顶追加一行。  
5. 若本轮无代码变更、仅同步文档到 skill，摘要中注明「仅文档/skill 同步」。

**不要**在未用户触发「归档」时，仅为小改动批量改写 `SKILL.md` / `ARCHIVE.md`。
