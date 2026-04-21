# multi_agent_tcp — CodeMaker 使用指南

> **目标读者**：CodeMaker CLI（或 Cursor）中的 AI Agent。
> 本文档帮助你理解这个框架的目的，以及**你应该如何调用它来协调多个 CodeMaker CLI 实例**。

---

## 1. 这个框架是什么？

**一句话**：`multi_agent_tcp` 让你（一个 AI Agent）能够**同时指挥多个 CodeMaker CLI 实例**，并行分发任务、自动注入领域 Skills、聚合结构化结果。

### 为什么需要它？

你（单个 CodeMaker 实例）一次只能处理一个任务。当你需要：

- 在代码库的多个目录中**并行搜索**
- 把大任务**拆成 N 个子任务同时执行**
- 让不同 agent **利用各自的 Skills 领域知识**分别处理

就需要拉起多个 CodeMaker CLI 实例协作。这个框架为你提供了标准化的接口。

---

## 2. 你的使用流程（两步）

### 完整流程图

```
┌──────────────────────────────────────────────────────────────┐
│ Step 1: 查询可用 agents                                      │
│                                                              │
│   python -m multi_agent_tcp show-registry -o agents.json     │
│                                                              │
│   返回：agent-1 (UI专家, skills: messiah-ui-dev)             │
│         agent-2 (网络专家, skills: game-client-telnet)       │
│         agent-3 (引擎专家, skills: messiah-engine-structure) │
└──────────────────────┬───────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────┐
│ 你（LLM）分析：哪些 agent 适合处理当前任务？                  │
│                                                              │
│ 决策：用 agent-1 搜 UI 代码，用 agent-3 搜引擎代码            │
└──────────────────────┬───────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────┐
│ Step 2: 分发任务                                              │
│                                                              │
│   python -m multi_agent_tcp dispatch --tasks tasks.json      │
│                                                              │
│   tasks.json:                                                │
│   [                                                          │
│     {"agent_id": "agent-1", "prompt": "查找所有 UIWindow"},  │
│     {"agent_id": "agent-3", "prompt": "查找 SceneNode 体系"} │
│   ]                                                          │
│                                                              │
│   框架自动：                                                  │
│   ✅ 从 registry 读取 model/cwd/timeout                      │
│   ✅ 注入每个 agent 的 Skills 到 prompt                      │
│   ✅ 启动 broker + workers                                   │
│   ✅ 并行执行                                                │
│   ✅ 返回结构化结果                                           │
└──────────────────────────────────────────────────────────────┘
```

---

## 3. Step 1：查询可用 agents

### 命令

```bash
python -m multi_agent_tcp show-registry -o agents.json
```

### 返回格式

```json
{
  "count": 3,
  "message": "3 agent(s) available. Use `dispatch` with agent_id + prompt pairs to run tasks.",
  "agents": [
    {
      "agent_id": "agent-1",
      "display_name": "助手 Alpha",
      "model": "netease-codemaker/kimi-k2.5",
      "skills": [
        {"name": "excel-export-flow", "description": "导表流程"},
        {"name": "messiah-ui-dev", "description": "弥赛亚引擎游戏UI开发"}
      ],
      "cwd": "F:/src/Package/Script/Python",
      "timeout_sec": 1800
    },
    {
      "agent_id": "agent-2",
      "display_name": "助手 Beta",
      "model": "netease-codemaker/kimi-k2.5",
      "skills": [
        {"name": "game-client-telnet", "description": "游戏客户端 Telnet"},
        {"name": "query-logtail", "description": "Logtail 日志查询"}
      ],
      "cwd": "F:/src/Package/Script/Python",
      "timeout_sec": 1800
    },
    {
      "agent_id": "agent-3",
      "display_name": "助手 Gamma",
      "model": "netease-codemaker/kimi-k2.5",
      "skills": [
        {"name": "messiah-engine-structure", "description": "弥赛亚引擎目录结构"},
        {"name": "messiah-panpan-dev", "description": "盘盘系统开发"}
      ],
      "cwd": "F:/src/Package/Script/Python",
      "timeout_sec": 1800
    }
  ]
}
```

### 你拿到后应该做什么？

分析返回的 agents 列表：
- 看每个 agent 的 **skills** — 它擅长什么领域
- 看 **model** — 它用什么模型
- 决定当前任务需要哪些 agents
- 为每个选中的 agent 写一个 prompt

### 特点

- **只读**，不产生 session 文件，无副作用
- 每次调用都读最新的 `agents_registry.json`
- 不输出 `-o` 时直接打印到 stdout

---

## 4. Step 2：分发任务

### 命令

```bash
python -m multi_agent_tcp dispatch --tasks tasks.json -o result.json
```

### tasks.json 格式

```json
[
  {"agent_id": "agent-1", "prompt": "在 gclient/gamesystem/ 中查找所有 UIWindow 子类"},
  {"agent_id": "agent-3", "prompt": "在 Engine 中查找 SceneNode 的完整继承体系"}
]
```

**格式说明**：
- 数组中的每个对象包含 `agent_id` + `prompt`
- `agent_id` 必须是 `show-registry` 返回的合法 ID
- `prompt` 是发给该 agent 的任务指令
- 可以给同一个 agent 发多个任务（不同 prompt）
- 可以只使用部分 agents

### 也可以内联 JSON（无需文件）

```bash
python -m multi_agent_tcp dispatch \
    --tasks-json '[{"agent_id":"agent-1","prompt":"查找 UIWindow"},{"agent_id":"agent-2","prompt":"查找 RPC 接口"}]' \
    -o result.json
```

### dispatch 自动完成的事情

1. 加载 `agents_registry.json`
2. 验证所有 `agent_id` 存在且已启用
3. 按 registry 配置创建 workers（正确的 model / cwd / timeout）
4. **自动将每个 agent 的 Skills 注入到其 prompt 中**
5. 启动 broker + worker 进程
6. 并行执行所有任务
7. 收集结果，杀掉进程，返回结构化 JSON

### 返回格式

```json
{
  "ok": true,
  "dispatched_agents": ["agent-1", "agent-3"],
  "workers": {
    "agent-1": {
      "status": "success",
      "answer": "找到以下 UIWindow 子类：\n1. GameChooseWindow (gclient/gamesystem/uihall/...)..."
    },
    "agent-3": {
      "status": "success",
      "answer": "SceneNode 继承体系：\n- SceneNode (base)\n  - MeshSceneNode\n  - ..."
    }
  },
  "summary": "Parallel result: 2/2 succeeded\n[OK] agent-1: 找到以下...\n[OK] agent-3: SceneNode..."
}
```

### 可选参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--port` | 9140 | broker 端口 |
| `--timeout` | 1800 | 整体超时（秒） |
| `--max-retries` | 2 | 可重试错误的重试次数 |
| `--retry-delay-sec` | 5.0 | 重试间隔 |
| `--skill-mode` | catalog | `catalog`（轻量目录表）或 `full`（完整 SKILL.md） |
| `--raw-output` | 无 | 写完整调试输出到文件 |

---

## 4b. 长时间任务：异步 dispatch（推荐）

`dispatch` 可能需要几分钟才能完成（等待多个 agent 各自调用 LLM）。如果你的终端工具有超时限制，**务必使用 `--async` 模式**。

### 流程：dispatch --async → read 轮询状态文件

```
┌─────────────────────────────────────────────────────────────────┐
│ Step 2a: 发起异步 dispatch（终端命令，仅此一次）                    │
│                                                                 │
│   python -m multi_agent_tcp dispatch --async                    │
│       --tasks tasks.json                                        │
│                                                                 │
│   立即返回：                                                     │
│   {                                                             │
│     "job_id": "a1b2c3d4",                                      │
│     "status": "running",                                        │
│     "status_file": "F:/.../logs/dispatch_jobs/a1b2c3d4.json"   │
│   }                                                             │
└──────────────────────┬──────────────────────────────────────────┘
                       │
                       ▼  (等待 15-30 秒)
┌─────────────────────────────────────────────────────────────────┐
│ Step 2b: 用 read 工具读取 status_file（不需要终端命令！）          │
│                                                                 │
│   read("F:/.../logs/dispatch_jobs/a1b2c3d4.json")              │
│                                                                 │
│   如果 "status": "running" → 等 15-30 秒，再 read 一次          │
│   如果 "status": "completed" → result 字段包含完整结果           │
│   如果 "status": "failed"   → error 字段包含错误信息            │
└─────────────────────────────────────────────────────────────────┘
```

> **为什么用 `read` 而不是终端命令轮询？**
>
> | | 终端命令 `dispatch-status` | `read` 工具读文件 |
> |--|---------------------------|------------------|
> | **用户审批** | 需要（可能被 deny） | 不需要 |
> | **超时风险** | 有（命令可能被截断） | 无（瞬间返回） |
> | **轮次中断** | 空输出可能结束 turn | 总是有内容返回 |
> | **token 开销** | 较高（命令上下文） | 极低（纯文件内容） |

### 命令

```bash
# 发起（终端命令，仅此一次，立即返回）
python -m multi_agent_tcp dispatch --async --tasks tasks.json
```

### 异步返回格式

发起时立即得到：
```json
{
  "job_id": "a1b2c3d4",
  "status": "running",
  "pid": 12345,
  "message": "Use the `read` tool to poll status_file until status becomes 'completed' or 'failed'.",
  "status_file": "F:/.../logs/dispatch_jobs/a1b2c3d4.json",
  "output_file": "F:/.../logs/dispatch_jobs/a1b2c3d4_result.json"
}
```

用 `read` 工具读 `status_file` 得到（进行中）：
```json
{
  "status": "running",
  "job_id": "a1b2c3d4",
  "pid": 12345,
  "started_at": 1776414978.67,
  "output_file": "F:/.../logs/dispatch_jobs/a1b2c3d4_result.json"
}
```

用 `read` 工具读 `status_file` 得到（已完成 — result 已嵌入）：
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
    "workers": { ... },
    "summary": "Parallel result: 2/2 succeeded ..."
  }
}
```

用 `read` 工具读 `status_file` 得到（失败）：
```json
{
  "status": "failed",
  "job_id": "a1b2c3d4",
  "failed_at": 1776415008.55,
  "error": "Process (PID 12345) exited unexpectedly. Check log: ..."
}
```

### 推荐轮询策略

**策略 A（首选）：终端 sleep + type 轮询**（适用于终端命令自动审批的环境）

LLM 工具层没有 sleep 能力，但终端命令可以实现真正的等待。利用 Windows `timeout` 命令
先等待 20 秒，再读取状态文件，**一条命令同时完成延时和读取**：

```cmd
timeout /t 20 /nobreak >nul && type <status_file>
```

流程：
1. 发起 `dispatch --async`，拿到 `status_file` 路径
2. 执行 `timeout /t 20 /nobreak >nul && type <status_file>`
3. 如果 `"status": "running"` → 重复第 2 步
4. 如果 `"status": "completed"` → 从 `result` 字段读取完整结果，**完成**
5. 如果 `"status": "failed"` → 检查 `error`，可读 `log_file` 排查

> **优势**：实现了真正的 15-20 秒延时，避免密集无效轮询，节省 token。
> **前提**：用户需设置终端命令自动审批（auto-approve），否则每次 `timeout` 都需要手动确认。

**策略 B：read 工具直读**（适用于终端需手动审批的环境）

1. 发起 `dispatch --async`，拿到 `status_file` 路径
2. 用 `read` 工具读取 `status_file`
3. 如果 `"status": "running"` → **在两次 read 之间穿插其他有意义的工作**（分析上下文、准备后续步骤等），避免密集连续 read
4. 如果 `"status": "completed"` → 从 `result` 字段读取完整结果，**完成**
5. 如果 `"status": "failed"` → 检查 `error`，可读 `log_file` 排查

> ⚠️ **禁止密集连续 read**：不得在无间隔的情况下连续多次 read 同一个状态文件。
> 每次 read 之间至少应有其他工具调用或分析步骤，否则会浪费大量 token。

### 备选：dispatch-status 命令轮询

如果你的环境支持长时间终端阻塞，也可以用命令轮询：

```bash
python -m multi_agent_tcp dispatch-status --job-id <job_id> --wait 25
```

`--wait N` 阻塞最多 N 秒（每 3 秒检查一次），完成立即返回。
但**不推荐**，因为终端命令有审批和超时风险。

### 何时用 --async vs 同步

| 场景 | 推荐 |
|------|------|
| 你的终端工具有超时限制 | `--async` |
| 多 agent 并行任务（分钟级） | `--async` |
| 单 agent 快速任务（<30 秒） | 同步（不加 `--async`） |
| 脚本/CI 中自动化 | 同步（可控制超时） |

---

## 5. Skills 自动注入机制

每个 agent 在 `agents_registry.json` 中配置了 skills 列表。当你使用 `dispatch` 时，框架会自动在 prompt 前面注入 skill 信息。

**例如 agent-1 配置了 `messiah-ui-dev` skill，你发送的 prompt 是**：
```
查找所有 UIWindow 子类
```

**agent-1 实际收到的 prompt 是**：
```
# Your Registered Skills

You have the following skills available. **Before starting a task,
check if any skill is relevant. If so, read the SKILL.md file first,
then follow its instructions.**

| Skill | Description | SKILL.md Path |
|-------|-------------|---------------|
| `excel-export-flow` | 导表流程 | `F:/.../skill_list/excel-export-flow/SKILL.md` |
| `messiah-ui-dev` | 弥赛亚UI开发 | `F:/.../skill_list/messiah-ui-dev/SKILL.md` |

Total: 2 skill(s). Use the `read` tool to load the full SKILL.md when needed.

============================================================
# Task

查找所有 UIWindow 子类
```

这意味着 agent-1 会利用 `messiah-ui-dev` 中的领域知识来完成任务，而你不需要手动处理这一切。

---

## 6. 实际场景示例

### 场景 1：三 agent 并行搜索

```bash
# Step 1：查询
python -m multi_agent_tcp show-registry -o agents.json
# → 得知有 agent-1(UI) agent-2(网络) agent-3(引擎)

# Step 2：分发（你构造 tasks.json 后执行）
python -m multi_agent_tcp dispatch --tasks tasks.json -o result.json
```

`tasks.json`:
```json
[
  {"agent_id": "agent-1", "prompt": "查找所有 CSB 资源的引用路径"},
  {"agent_id": "agent-2", "prompt": "查找所有 telnet 命令注册位置"},
  {"agent_id": "agent-3", "prompt": "查找 SceneNode 的 C++ 继承体系"}
]
```

### 场景 2：只用一个 agent

```bash
python -m multi_agent_tcp dispatch \
    --tasks-json '[{"agent_id":"agent-1","prompt":"修复 UIListViewCycle 刷新时的闪烁问题"}]' \
    -o result.json
```

### 场景 3：同一 agent 多个任务

```json
[
  {"agent_id": "agent-1", "prompt": "在 gclient/gamesystem/ 中搜索 GameChooseWindow"},
  {"agent_id": "agent-1", "prompt": "在 gclient/gameplay/ 中搜索 GameLogicBlasting"}
]
```

> 注意：同一 agent 的多个任务会**串行执行**（一个 worker 进程一次只能处理一个任务）。如果需要真正并行，使用不同的 agent。

---

## 7. agents_registry.json 配置

这是所有 agent 信息的**单一配置源**：

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
    },
    "agent-2": {
      "display_name": "助手 Beta",
      "model": "netease-codemaker/kimi-k2.5",
      "cwd": "F:/src/Package/Script/Python",
      "skills": ["game-client-telnet", "query-logtail"],
      "timeout_sec": 1800,
      "enabled": true
    }
  }
}
```

| 字段 | 说明 |
|------|------|
| `agent_id`（key） | agent 唯一标识，`dispatch` 时使用 |
| `display_name` | 可读名称 |
| `model` | 使用的 LLM 模型，格式 `netease-codemaker/<模型名>` |
| `cwd` | CodeMaker CLI 的工作目录 |
| `skills` | 该 agent 擅长的领域知识（SKILL.md 列表） |
| `timeout_sec` | 单次任务超时 |
| `enabled` | 是否可用 |

可用 `python -m multi_agent_tcp registry-ui` 打开图形界面编辑。

---

## 8. 结果数据结构

### dispatch 返回的顶层

```json
{
  "ok": true,
  "dispatched_agents": ["agent-1", "agent-3"],
  "workers": { ... },
  "summary": "Parallel result: 2/2 succeeded ..."
}
```

| 字段 | 说明 |
|------|------|
| `ok` | bool：全部 agent 都成功？ |
| `dispatched_agents` | 本次使用的 agent ID 列表 |
| `workers` | 每个 agent 的结果（见下） |
| `summary` | 人类可读摘要 |

### 每个 worker 的结果

```json
{
  "status": "success",
  "answer": "找到以下类定义：..."
}
```

| status 值 | 含义 |
|-----------|------|
| `success` | 执行成功，`answer` 有内容 |
| `error` | 执行出错 |
| `timeout` | 超时 |
| `empty` | 执行成功但无输出 |

---

## 9. CLI 命令速查

```bash
# ========== 推荐的两步流程 ==========

# Step 1：查询可用 agents（只读，无副作用）
python -m multi_agent_tcp show-registry [-o agents.json]

# Step 2：分发任务（自动 registry + skills + 并行）
python -m multi_agent_tcp dispatch --tasks tasks.json [-o result.json]
python -m multi_agent_tcp dispatch --tasks-json '[...]' [-o result.json]

# Step 2（异步版，适合长时间任务 / 终端有超时限制）
python -m multi_agent_tcp dispatch --async --tasks tasks.json
# 然后用 read 工具读 status_file 轮询，不需要再跑终端命令

# ========== 其他命令 ==========

# GUI 编辑 agents_registry.json
python -m multi_agent_tcp registry-ui

# 合并 skills
python -m multi_agent_tcp.init_skill_list [--force]

# ========== 高级 / 旧接口（仍可用） ==========

# Session-gated 单 agent dispatch
python -m multi_agent_tcp list-agents [-o agents.json]
python -m multi_agent_tcp run-agent --session-id XXXXX --agent-id agent-1 --prompt "..."

# run-parallel + registry（底层接口）
python -m multi_agent_tcp run-parallel --registry --tasks tasks.json [-o result.json]
python -m multi_agent_tcp run-chain --registry --tasks tasks.json [-o result.json]
```

---

## 10. 注意事项

### 模型名称格式

所有模型必须以 `netease-codemaker/` 为前缀：
```
netease-codemaker/kimi-k2.5
netease-codemaker/claude-opus-4-6
netease-codemaker/gpt-5.2-codex-2026-01-14
```

### CodeMaker 权限

每个 agent 的 `cwd` 下需有 `codemaker.json`，且 `"permission": "allow"`。

### Windows 编码

- 子进程已自动设置 `PYTHONUTF8=1`
- 使用 `-o result.json` 直接写文件，**不要**用 PowerShell 管道 `| Out-File`

### 同一 agent 多任务

一个 worker 进程一次只能执行一个 `codemaker run`。如果 tasks.json 中给同一个 agent_id 发了多个任务，它们会由 batch_gather 协议在同一个 worker 上排队执行。要真正并行，必须使用不同的 agent_id。

---

## 11. 目录结构

```
multi_agent_tcp/
├── __init__.py             # 包导出（v0.5.0）
├── __main__.py             # CLI 入口（show-registry / dispatch / ...）
├── cluster.py              # CodeMakerCluster（create_from_registry 等）
├── registry.py             # AgentsRegistry + show_registry_response
├── agents_registry.json    # ★ 所有 agent 的配置源
├── broker.py               # TCP 消息中枢
├── client.py               # AgentTCPClient
├── protocol.py             # 帧协议
├── codemaker_bridge.py     # codemaker run 子进程桥接
├── init_skill_list.py      # Skill 合并脚本
├── registry_ui.py          # Tkinter GUI
├── log_setup.py            # 日志配置
├── _proc_utils.py          # 进程树清理
└── examples/
    ├── HOWTO.txt            # 详细用法文档
    └── *.json               # 示例配置
```

---

## 总结

```
你的操作            方式                                               说明
─────────           ──────────────────────────────                    ─────
查询可用 agents     终端: show-registry -o agents.json                 只读，返回所有 agent 的 id/model/skills
分发并行任务        终端: dispatch --tasks tasks.json -o result.json    同步，等到全部完成才返回
分发（异步）        终端: dispatch --async --tasks tasks.json           立即返回 job_id + status_file
轮询异步结果        read: 读取 status_file                              不需要终端命令，直到 completed/failed
```

**核心原则**：
1. **先查询再分发** — 先调 `show-registry` 知道有哪些 agent，再决定用谁
2. **不要自己写 cluster.json** — `dispatch` 自动从 `agents_registry.json` 读取一切
3. **tasks.json 格式简单** — `[{"agent_id": "...", "prompt": "..."}, ...]`
4. **长任务用 `--async`** — 发起后用 `read` 工具轮询 status_file，不走终端命令
