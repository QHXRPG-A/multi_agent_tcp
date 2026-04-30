---
name: multi-agent-tcp
description: >
  Coordinate with peer agent CLIs (CodeMaker / Claude Code / Codex / scripts)
  through the multi_agent_tcp peer-to-peer agent communication bus. Any agent
  CLI can act as both initiator and receiver: hand off subtasks to other
  agents, run parallel code searches, fan-out + reduce workflows, serial
  pipelines (analyze -> design -> implement), mixed-model dispatch, or
  session-gated agent dispatch (list-agents -> run-agent).
  Trigger words: peer agent, agent collaboration, multi agent, parallel search,
  fan-out, reduce, run-parallel, run-chain, cluster, broker, agent dispatch,
  multi_agent_tcp, peer-to-peer, agent-to-agent, 对等 agent, 多agent, 并行搜索,
  分而治之, 流水线协作, agent 协作.
---

# multi_agent_tcp — Peer Agent Coordination

`multi_agent_tcp` is a **peer-to-peer agent CLI communication bus**. As a running agent CLI, you are one peer among many; you can both **receive** tasks from other peers and **initiate** task hand-offs to other agents (each with its own model and domain Skills) when it lets you finish faster.

> **核心理念：不空等。** 当你作为发起方把子任务派给其它对等 agent 后，**不要干等回复**，而是利用等待时间亲自完成一个子任务，做完后再轮询 agent 结果。这样总耗时 ≈ max(自留子任务, agent 子任务)，而非串行累加。

> **历史背景**：此前版本以"Cursor / CodeMaker 作为上游决策者"叙述本 skill；2026-04-30 起项目全面转向"agent CLI 之间的对等通信、管理、协作"。本 skill 的工作流没变（你仍然作为发起方调 `dispatch`），但概念上"主模型"和"agent"是**对等节点**——你可能正是别人的 agent，别人也可能是你的 agent。

## ⛔ Prohibited Actions

- **DO NOT** read or modify files inside `multi_agent_tcp/` directory
- **DO NOT** write your own `cluster.json`
- **DO NOT** use internal Python APIs directly
- **Only use the CLI commands** documented below

## Mandatory Workflow (5 steps, strictly in order)

> Every step must complete before the next one begins. Do not skip or reorder.
> **dispatch 是长时间运行命令（分钟级），必须使用 `--async` 异步模式，绝对不能用同步模式。**

```
1. run show-registry       → 获取 agents.json（立即完成）
2. read agents.json + 分析决策 → 拆分子任务：N-1 个给其它 agent，1 个留给自己
3. run dispatch --async    → 提交派给其它 agent 的子任务，立即拿到 status_file 路径
4. self-work               → 你（发起方）亲自执行自留子任务（与其它 agent 并行）
5. 延时轮询 status_file   → 自留任务完成后，轮询 agent 结果直到 status != "running"
```

### Step 1 — Query Available Peer Agents

```bash
python -m multi_agent_tcp show-registry -o .codemaker/tmp/agents.json
```

Read-only, no side effects. Output example:
```json
{
  "count": 3,
  "agents": [
    {
      "agent_id": "agent-1",
      "display_name": "助手 Alpha",
      "model": "netease-codemaker/kimi-k2.5",
      "skills": [{"name": "messiah-ui-dev", "description": "弥赛亚引擎游戏UI开发"}],
      "timeout_sec": 1800
    }
  ]
}
```

执行 show-registry 后，用 `read_file` 读取 agents.json。注意每个对等 agent 的：
- `agent_id` — 在 tasks.json 中使用
- `skills` — 它擅长什么领域
- `model` — 它用什么模型

### Step 2 — Analyze, Decide & Build Tasks（含自留任务拆分）

将用户任务拆分为 N 个子任务，其中 **N-1 个分配给其它对等 agent，1 个留给自己（你这个发起方）亲自执行**。

#### 任务拆分策略

**自留任务的选取原则**（按优先级）：
1. **需要与用户交互或确认的子任务** — 其它 agent 无法与用户对话，这类任务必须自留
2. **需要编辑文件的子任务** — 你有 edit_file 等工具，对端 agent 通常只能搜索和分析
3. **最需要深度推理的子任务** — 你通常是更强的模型，复杂推理任务优先自留
4. **依赖其他子任务结果的汇总任务** — 最终整合工作天然属于发起方

**分配给其它 agent 的任务特点**：
- 独立的信息搜集、代码搜索、模式分析
- 不需要文件编辑权限
- 可以自包含完成，不依赖其他子任务的中间结果

#### 示例：3 个子任务的拆分

用户需求：「分析项目中 UIWindow 的继承体系、SceneNode 的继承体系，然后汇总一份架构文档」

| 子任务 | 分配 | 原因 |
|--------|------|------|
| 搜索 UIWindow 继承体系 | → agent-1 | 独立搜索任务 |
| 搜索 SceneNode 继承体系 | → agent-3 | 独立搜索任务 |
| 汇总架构文档 + 写文件 | → **自留** | 需要整合结果 + 编辑文件 |

构造 tasks.json 时**只包含分配给其它 agent 的任务**（自留任务不写入）:
```json
[
  {"agent_id": "agent-1", "prompt": "在 gclient/gamesystem/ 中查找所有 UIWindow 子类，列出类名、文件路径、继承关系"},
  {"agent_id": "agent-3", "prompt": "在 Engine 中查找 SceneNode 继承体系，列出类名、文件路径、继承关系"}
]
```

> **心中记住自留任务**：在 Step 4 中亲自执行。如果自留任务简单（如纯汇总），也可以跳过 Step 4，在 Step 5 轮询完成后直接执行。

### Step 3 — Async Dispatch（提交派给其它 agent 的任务）

> ⚠️ **强制规则**：必须使用 `--async` 参数。不加 `--async` 的同步 dispatch 会阻塞数分钟，导致终端超时、对话中断。

```bash
python -m multi_agent_tcp dispatch --async --tasks-json '[{"agent_id":"agent-1","prompt":"..."},{"agent_id":"agent-3","prompt":"..."}]'
```

也可以先写文件再引用：
```bash
python -m multi_agent_tcp dispatch --async --tasks .codemaker/tmp/tasks.json
```

**立即返回**（不会阻塞）：
```json
{
  "job_id": "a1b2c3d4",
  "status": "running",
  "status_file": "F:/.../logs/dispatch_jobs/a1b2c3d4.json",
  "output_file": "F:/.../logs/dispatch_jobs/a1b2c3d4_result.json"
}
```

> 记下 `status_file` 路径，**不要立即轮询**，先去做自留任务（Step 4）。

### Step 4 — Self-Work（你亲自执行自留子任务）

> ⚠️ **核心步骤**：这是本 skill 区别于纯 fan-out 模式的关键。dispatch 后不要空等，立即开始做自留子任务。

在 Step 3 拿到 `status_file` 后，**立即开始执行自留子任务**。用你的全部工具能力（`grep_search`、`read_file`、`edit_file` 等）完成工作。

**执行原则**：
- 像正常编码一样完成自留任务，不需要考虑对端 agent 的进度
- 自留任务和对端 agent 的任务**天然并行**：你在用工具做事的同时，其它 agent 进程在后台运行
- 自留任务完成后，再进入 Step 5 轮询其它 agent 的结果

**时间利用示意**：
```
时间线 ──────────────────────────────────────────────►
peer agents:  [========= 后台并行执行各自子任务 =========]
你:           [==== 自留任务（搜索+分析+编辑）====][轮询][整合输出]
                                                    ▲
                                            此时 peer 大概率已完成
```

> 如果自留任务是纯汇总类（需要等其它 agent 结果才能做），可以跳过本步骤，直接进入 Step 5。

### Step 5 — Poll Until Done（延时轮询状态文件）

> ⚠️ **强制规则**：每次轮询必须先等待再读取，**禁止连续无间隔读取**。
> 连续无间隔 read 会产生 30+ 次无效轮询，严重浪费 token。

拿到 `status_file` 路径后，用**终端命令一步完成等待+读取**：

```cmd
timeout /t 30 /nobreak >nul && type <status_file 的完整路径>
```

一条命令同时完成延时和读取，终端返回后直接看到状态文件内容。

#### 轮询策略（强制遵守）

> 进入本步骤时，自留任务已完成（或被跳过），距离 dispatch 已经过去了一段时间。

1. **首次轮询**：判断自留任务耗时
   - 如果 Step 4 自留任务**实际执行了**（做了搜索、编辑等操作）→ 直接 `type <status_file>` 读取状态（不需要额外等待，因为做自留任务的时间已经是天然延时）
   - 如果 Step 4 被**跳过**（自留任务是汇总类）→ 执行 `timeout /t 30 /nobreak >nul && type <status_file>`（首次等 30 秒）
2. 如果 `"status": "running"` → 执行 `timeout /t 20 /nobreak >nul && type <status_file>`（后续每次等 20 秒），回到第 2 步
3. 如果 `"status": "completed"` → 从 `result` 字段读取完整结果，**任务完成**
4. 如果 `"status": "failed"` → 检查 `error`，可读 `log_file` 排查

> **等待间隔规则**：
> - 执行了 Step 4 后首次轮询：**0 秒**（直接读取，自留任务时间已充当延时）
> - 跳过 Step 4 后首次轮询：**30 秒**
> - 后续每次等待 **20 秒**
> - ⛔ **禁止连续 read_file 不加等待** — 这是最重要的规则，违反会浪费大量 token

> ⛔ **禁止用 `dispatch-status` 终端命令轮询**。
> ⛔ **禁止用 `read_file` 工具连续无间隔轮询**。

#### 轮询返回格式

用 `read_file` 读 `status_file` 得到（进行中）：
```json
{
  "status": "running",
  "job_id": "a1b2c3d4",
  "pid": 12345,
  "started_at": 1776414978.67,
  "output_file": "F:/.../logs/dispatch_jobs/a1b2c3d4_result.json"
}
```

用 `read_file` 读 `status_file` 得到（已完成 — result 已嵌入）：
```json
{
  "status": "completed",
  "job_id": "a1b2c3d4",
  "pid": 12345,
  "started_at": 1776414978.67,
  "completed_at": 1776415099.12,
  "output_file": "F:/.../logs/dispatch_jobs/a1b2c3d4_result.json",
  "result": {
    "ok": true,
    "dispatched_agents": ["agent-1", "agent-3"],
    "workers": {
      "agent-1": {"status": "success", "answer": "Found UIWindow subclasses: ..."},
      "agent-3": {"status": "success", "answer": "SceneNode hierarchy: ..."}
    },
    "summary": "Parallel result: 2/2 succeeded ..."
  }
}
```

用 `read_file` 读 `status_file` 得到（失败）：
```json
{
  "status": "failed",
  "job_id": "a1b2c3d4",
  "failed_at": 1776415008.55,
  "error": "Process (PID 12345) exited unexpectedly. Check log: ..."
}
```

### 完成后处理

从 `result.workers` 中提取每个对端 agent 的 `answer`，**与自留任务的结果合并整合**，输出给用户。

> 整合时注意：自留任务的结果你已经有了（Step 4 中产生），其它 agent 的结果从 `result.workers` 中获取，两部分合并成完整答案。

| status | meaning |
|--------|---------|
| `success` | Completed, `answer` has content |
| `error` | Execution error |
| `timeout` | Timed out |
| `empty` | Completed but no output |

## Optional Parameters (dispatch)

| Param | Default | Description |
|-------|---------|-------------|
| `--port` | 9140 | Broker port |
| `--timeout` | 1800 | Overall timeout (seconds) |
| `--max-retries` | 2 | Retries for transient errors |
| `--retry-delay-sec` | 5.0 | Delay between retries |
| `--skill-mode` | catalog | `catalog` (lightweight) or `full` (complete SKILL.md) |

## Prerequisite (one-time setup)

Before first use, merge skill files:
```bash
python -m multi_agent_tcp.init_skill_list
```
If `show-registry` returns `"(unknown)"` for skill descriptions, run this command.

## Key Rules

1. **Follow the 5-step workflow in order** — no skipping, no reordering（Step 4 可在自留任务为纯汇总时跳过）
2. **不空等原则** — dispatch 后必须优先执行自留子任务（Step 4），禁止 dispatch 后立即进入轮询空等。唯一例外：自留任务依赖其它 agent 结果（如纯汇总）
3. **任务拆分必须自留一个** — Step 2 拆分时，至少保留一个子任务给自己亲自执行，不要把所有任务都扔给对端 agent 然后干等
4. **必须使用 `--async` 模式** — 同步 dispatch 会导致终端超时和对话中断，这是已知问题，绝对禁止使用同步模式
5. **轮询必须加延时** — 使用 `timeout /t N /nobreak >nul && type <status_file>` 一步完成等待+读取。⛔ 禁止用 `read_file` 连续无间隔轮询（会产生 30+ 次无效读取浪费 token）。⛔ 禁止用 `dispatch-status` 终端命令轮询。执行了 Step 4 后首次轮询可直接读取（自留任务时间已充当延时）
6. **轮询不能偷懒** — 必须持续轮询直到 `status != "running"`，拿到最终结果后才能结束本轮回复
7. **Complete all steps in one conversation turn** — 不要在轮询中途结束回复让用户去取结果，用户期望你给出完整答案
8. **轮询时静默** — 在 Step 5 轮询期间，如果任务仍在运行（`status == "running"`），**只调用工具，不输出任何文字**给用户。不要说"还在跑"、"继续等待"之类的话。只有当任务最终完成（`completed` / `failed`）时，才向用户展示结果
9. **Never write cluster.json** — `dispatch` handles everything from registry
10. **Never read `multi_agent_tcp/` source files** — interact only through CLI
11. **Same agent = serial** — use different peer agents for true parallelism
12. **Windows**: Use `-o file.json` to write output; never pipe through `| Out-File`
13. **Temp files**: Write to `.codemaker/tmp/` directory
