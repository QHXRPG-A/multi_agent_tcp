# multi_agent_tcp 迭代路线图

> **设计哲学：薄通信总线，智能交给每一个 agent CLI。**
>
> 本框架不造智能体。所有的 agent CLI（CodeMaker / Claude Code / Codex / 自研）都是**对等节点**，分别拥有自己的 LLM 推理、tool calling、规划能力。框架只做一件事：**让这些 agent CLI 之间能可靠、高效地相互通信、相互协作**。

## 项目定位

```
┌────────────────────────────────────────────────────────────────────┐
│  Agent CLI A   Agent CLI B   Agent CLI C   ...   Python 脚本/CI    │
│  (CodeMaker)   (Claude Code) (Codex)             (任意发起方)       │
│       ▲              ▲              ▲                  ▲           │
│       │              │              │                  │           │
│       └──────────────┴──── TCP ─────┴──────────────────┘           │
│                              │                                     │
│                              ▼                                     │
│                          ┌────────┐                                │
│                          │ Broker │   寻址 / 邮箱 / 心跳 / 会话    │
│                          └────────┘   断连感知 / batch_gather       │
│                                                                    │
│  职责边界：                                                         │
│  ✓ 多 agent 进程生命周期管理（broker + agent 启停）                 │
│  ✓ 消息路由（unicast / broadcast / batch_gather）                  │
│  ✓ 并行 fan-out + 结果聚合                                          │
│  ✓ 串行 chain + 上下文传递                                          │
│  ✓ 超时、重试、断连感知等可靠性保障                                  │
│  ✓ 结构化结果提取与传递（让 agent 之间更容易协作）                  │
│  ✓ Skill / 能力声明（registry + skill catalog 注入）                │
│                                                                    │
│  不做：                                                             │
│  ✗ LLM 推理循环（每个 agent CLI 已有）                              │
│  ✗ Tool / Function calling 注册与执行（每个 agent CLI 已有）        │
│  ✗ 任务规划与分解、结果质量判断、动态任务分配                        │
│    （由发起方 agent CLI 自己决定，框架不替它决策）                  │
│  ✗ 对话历史 / 长期记忆（CodeMaker / Claude / Codex 自带 session）   │
│  ✗ 可视化 UI（结构化数据落盘即可，UI 是独立项目）                   │
└────────────────────────────────────────────────────────────────────┘
```

**核心拓扑特征**：所有节点对等。任意 agent CLI 既能作为接收方接受任务，也能作为发起方主动调 `dispatch` / `run_parallel` 给其它 agent 派子任务（典型路径：agent A 在自己的 prompt 处理中通过 bash 工具触发 dispatch）。Broker 不是"控制中心"，而是**对等节点之间的邮箱+寻址+会话**基础设施。

**核心推论**：框架的每一个新特性都应该问——"这是在帮助 agent CLI 之间更好地协作，还是在替代它们的能力？"只做前者。

> **历史背景**：早期版本（≤ v0.5.x）以"Cursor / CodeMaker 作为上游决策者"为主叙事，并在"不做清单"中明确"不做模型抽象层（绑定 CodeMaker CLI 是优势）"。2026-04-30 起项目**全面转向"agent CLI 对等协作"**：上游/下游概念退场；"不做模型抽象层"被撤销并改为"做最薄的 CLI Adapter"。详见 `KM_docs/multi-cli-node-workflow-brainstorm.md` 与 `.cursor/skills/multi-agent-tcp/ARCHIVE.md` 顶部归档条目。

---

## 当前能力（v0.5.x）

| 能力 | 状态 | 说明 |
|------|------|------|
| 多 agent 进程管理 | ✅ | broker + N agent，启停、进程树清理 |
| 对等并行分发 | ✅ | `run_parallel` → `ParallelResult`；任意发起方都能用 |
| fan-out → reduce | ✅ | `run_parallel_reduce` → `ReduceResult` |
| 串行链 | ✅ | `run_chain` + 结构化 context 注入 |
| 单任务 unicast | ✅ | `run_single` |
| 结构化结果 | ✅ | `WorkerResult` / `ParallelResult` / `ReduceResult`；`to_dict()`（精简）/ `to_raw_dict()`（调试完整） |
| 技术级重试 | ✅ | `database is locked` 等可重试错误串行重试 |
| 超时控制 | ✅ | 进程级 + gather 级 |
| 心跳探活 | ✅ | ping/pong + 驱逐 |
| 断连感知 | ✅ | gather 中 target 断连即报错 |
| 并发写安全 | ✅ | per-connection 写锁 |
| 日志落盘 | ✅ | rotating file + 结构化前缀 |
| Discovery（最小） | ✅ | `show-registry` 只读列表 |
| Skill 注入 | ✅ | catalog 模式（CodeMaker / OpenCode 体系） |
| 异步 dispatch | ✅ | `--async` + `read` 工具轮询 status_file |

---

## 迭代计划

### ~~P0：结构化结果传递~~ ✅ Done (v0.3.0)

> 已实现。`WorkerResult` dataclass + `ParallelResult` 类 + `run_parallel` 返回 `ParallelResult` + `run_chain` 结构化 context 注入。
>
> 额外改进：`to_dict()`（精简：仅 status + answer）/ `to_raw_dict()`（调试完整：含 raw_stdout/stderr/elapsed_sec），过滤发起方不需要的噪音字段。

---

### ~~P0：fan-out → reduce 模式~~ ✅ Done (v0.3.0)

> 已实现。`run_parallel_reduce()` 方法 + `ReduceResult` dataclass + CLI `run-parallel-reduce` 命令。

---

### P0：CLI Adapter 抽象（多 CLI 接入的前提）

> **目标**：把当前硬绑 CodeMaker 的 [`codemaker_bridge.py`](codemaker_bridge.py) 重构为 `CLIAdapter` 抽象 + `CodeMakerAdapter` 第一实现，平行支持 Claude Code、Codex 等其它 agent CLI。
>
> **状态**：脑暴已落地（详见 [`KM_docs/multi-cli-node-workflow-brainstorm.md`](KM_docs/multi-cli-node-workflow-brainstorm.md) §3）；尚未实现。

**改进方向**：

1. **抽出 `CLIAdapter` 抽象**：`build_argv` / `prompt_passing`（argv vs file vs stdin）/ `parse_output`（NDJSON / plain / 自定义 JSON）/ `materialize_attachments` / `health_check` / `model_prefix_rules`。
2. **`WorkerConfig` / `agents_registry.json` 增加 `cli_kind`**（向后兼容，缺省 `codemaker`）；`registry_ui.py` 下拉同步。
3. **第一阶段实现**：`CodeMakerAdapter`（重构 `codemaker_bridge.py`，行为零变化），保证当前所有用户用例不破坏。
4. **第二阶段实现**：`ClaudeCodeAdapter` / `CodexAdapter`，各跑一次 spike 后落地（`KM_docs/multi-cli-node-workflow-brainstorm.md` §3.3 表中所有 `TODO: spike`）。
5. **输出归一化**：所有 adapter 统一回 `WorkerResult{worker, status, answer, attachments, raw_stdout, stderr, elapsed_sec}`。

**不做**：不做 LLM 推理抽象层；不做模型路由（这是发起方 agent 的活）。Adapter **只适配进程 IO**，不替代任何 CLI 内部的 LLM 推理。

---

### P1：任务级重试（语义级）

> **目标**：区分"技术失败"和"任务未完成"，分别处理。

**现状**：`is_retryable_error` 只检测 `database is locked` 等进程级错误。

**改进方向**：

1. **用户自定义判定函数**

   ```python
   result = await cluster.run_parallel(
       tasks,
       should_retry=lambda worker_id, reply: "没有找到" in reply.answer,
       max_retries=2,
   )
   ```

2. **prompt 改写重试**

   ```python
   result = await cluster.run_parallel(
       tasks,
       should_retry=my_check,
       retry_rewrite=lambda worker_id, body, prev_reply: {
           **body,
           "prompt": body["prompt"] + f"\n\n上次尝试未成功，原因：{prev_reply.answer}\n请换一种方式搜索。"
       },
       max_retries=2,
   )
   ```

**不做**：不做自动判断"任务是否完成"（那需要 LLM 推理，交给发起方 agent 自决）。框架只提供 hook 点。

---

### P1：执行追踪（Tracing）

> **目标**：让发起方 agent 和人类能看清"谁做了什么、花了多久、结果如何"。

**现状**：日志散落在各进程的 rotating file 里，没有统一视图。

**改进方向**：

1. **结构化 trace 记录**：每次 `run_parallel` / `run_chain` / `run_single` 生成一条 trace

   ```python
   {
       "trace_id": "parallel-a1b2c3",
       "type": "parallel",
       "started_at": "2026-04-17T10:30:00Z",
       "tasks": [
           {"worker": "cm1", "status": "success", "elapsed_sec": 12.3},
           {"worker": "cm2", "status": "error", "elapsed_sec": 5.1, "error": "timeout"},
       ],
       "total_elapsed_sec": 12.3,
   }
   ```

2. **trace 落盘**：写入 `logs/traces/` 目录下 NDJSON 文件，一行一条 trace

3. **`cluster.traces`** 属性：内存中保留最近 N 条 trace，方便发起方 agent 回顾

**不做**：不做可视化 UI、不接第三方 tracing 平台（LangSmith 等）。只做结构化数据落盘。需要可视化时，数据格式已经在那里，外部工具自己读。

---

### P2：对等通信原语扩展

> **目标**：把当前以"发起方 → N 接收方"为主的 batch_gather/chain，扩成更对称的 peer-to-peer 协作原语。

**改进方向**（仅方向，未实现）：

1. **Discovery 升级（capability addressing）**：
   - `show-registry` 当前是最小发现；增加 capability filter：`--filter-skill messiah-ui-dev` / `--filter-cli-kind claude_code` / `--filter-tag refactoring`。
   - `agents_registry.json` 的 `agent` 增加 `tags` / `capabilities` 字段。

2. **多轮 conversation**：
   - 当前 `run_chain` 是线性单方向流水（A → B → C 各一次）。
   - 引入 `conversation_id`：A 发任务给 B，B 反问 A，A 再回，B 完成——多轮往返。
   - 与 P1 的 trace 共享同一 `conversation_id`。

3. **Per-agent permission**：
   - 每个 agent 在 registry 中可声明 `accept_from: ["agent-1", "agent-2"]` 或 `accept_task_kind: ["search", "review"]`，broker 在路由前做准入检查。

4. **Agent-to-agent inline call 模式**：
   - 文档化"agent CLI 在自己的 prompt 处理中通过 bash 工具触发 `dispatch` 给其它对等 agent"这一**自然实现路径**（已被 `.codemaker/skills/multi-agent-tcp/SKILL.md` 五步流程使用）。
   - 框架侧不需要新代码，只需要在 GUIDE_FOR_AGENTS / SKILL 中明确合法性与最佳实践。

---

### P2：DAG / 条件路由

> **目标**：支持比 parallel 和 chain 更复杂的拓扑，但保持薄框架——**条件判断逻辑由用户函数提供，不由框架内置 LLM**。

**现状**：只有 `run_parallel`（fan-out）和 `run_chain`（线性），无法表达"根据结果走不同分支"。

**改进方向**：

```python
from multi_agent_tcp import DAG, Node

dag = DAG()

# 定义节点
search = dag.add("search", worker="cm1", prompt="搜索所有 UIWindow 子类")
check  = dag.add("check",  worker="cm2", prompt="验证搜索结果的准确性")
deep   = dag.add("deep",   worker="cm3", prompt="对不准确的结果深入分析")
done   = dag.add("done",   worker="cm1", prompt="生成最终报告：{context}")

# 定义边
dag.edge(search, check)

# 条件路由：用户提供判断函数
dag.edge(check, deep,  when=lambda result: "不准确" in result.answer)
dag.edge(check, done,  when=lambda result: "不准确" not in result.answer)
dag.edge(deep,  done)

result = await cluster.run_dag(dag)
```

**设计要点**：

- `when` 是用户写的普通 Python 函数，不是 LLM 推理——**框架不做决策**
- 如果发起方 agent 想用 LLM 判断，它自己在 `when` 里调 LLM 就好（典型路径：`when` 内 subprocess 触发另一次 dispatch）
- 支持 fan-out（一个节点多条出边）、fan-in（多条入边汇聚）、条件跳过
- DAG 必须无环（框架校验），避免无限循环；如果需要循环重试，用 P1 的 `should_retry`

**不做**：不做图的可视化渲染、不做自动拓扑推断。

---

### P2：单元测试与集成测试

> **目标**：可维护性。

**现状**：仅 `smoke_local.py` 手动测试。

**改进方向**：

1. **单元测试**（不需要真实 CodeMaker CLI）
   - `protocol.py`：帧编解码
   - `cluster.py`：`extract_final_text`、`summarize_gather_result`、`is_retryable_error`
   - `WorkerConfig.to_agent_json` 序列化

2. **集成测试**（用 echo agent 代替 CodeMaker CLI）
   - broker 启动 → echo agent 注册 → `batch_gather` → 验证聚合结果
   - `run_parallel` / `run_chain` 端到端
   - 超时、断连、重试场景

3. **测试基础设施**
   - `conftest.py`：自动启停 broker + echo agents 的 fixture
   - 随机端口避免冲突

---

### P3：多模态消息

> **目标**：消息总线能承载文本之外的图像、音频、二进制 blob，让 agent 之间能传图、传文件、传音频片段。
>
> **状态**：脑暴见 [`KM_docs/multi-cli-node-workflow-brainstorm.md`](KM_docs/multi-cli-node-workflow-brainstorm.md) §5；尚未实现。

**改进方向**（仅方向）：

1. **`MultiModalEnvelope`** 信封：`{kind, mime, encoding: inline|fileref|blobref, value, meta}`，节点端口与 worker 消息共用一个容器。
2. **协议扩展**：保持 [`protocol.py`](protocol.py) 4-byte length + JSON 不变；新增 `blob_put` / `blob_get` 帧（base64 + blob store）。
3. **CLI Adapter 适配**：每个 adapter 在调 CLI 前 `materialize_attachments` 落地为对应 CLI 能消费的形式（文件路径 / inline base64 / @file 引用）。
4. **数据面策略**：text 与小图 inline；大图 / 音频走 blob_id。

---

### P3：Worker 能力声明（与 P2 Discovery 升级合并）

> **目标**：让发起方 agent 知道每个对端 agent 擅长什么，辅助它做任务分配决策。

**现状**：`WorkerConfig` 只有 `agent_id`、`cwd`、`model` 等运行时参数；registry 里有 `skills` 但没有更结构化的标签。

**改进方向**：

```python
WorkerConfig(
    agent_id="cm1",
    cwd=Path("F:/src"),
    cli_kind="codemaker",                # P0 已加
    tags=["search", "python"],           # 新增
    description="擅长 Python 代码搜索和分析",  # 新增
)
```

`cluster.describe_workers()` 返回所有 worker 的能力描述，发起方 agent 可以用它来决定把任务分给谁。

**不做**：不做自动任务分配（框架不决策）。只提供信息，让发起方 agent 决定。

---

### P3：节点化工作流（headless）

> **目标**：把"agent 调用 + 消息处理"建模成 DAG；用户能往图里加"消息格式化、字段抽取、模板填充、image 处理"等节点，而不止"调一个 CLI"。
>
> **状态**：脑暴见 [`KM_docs/multi-cli-node-workflow-brainstorm.md`](KM_docs/multi-cli-node-workflow-brainstorm.md) §4 / §6；尚未实现。

**与 P2 DAG 的关系**：P2 DAG 是 Python API；P3 节点化工作流是更高一层的"节点定义 + 端口契约 + 编译器"，编译目标就是 P2 DAG（再向下编译到 `run_parallel` / `run_chain` / `run_single`）。

**MVP 5 步**详见脑暴文档 §8，本 ROADMAP 不重复。

---

## 不做清单（明确的边界）

以下能力**不在本框架范围内**，原因是它们属于每个 agent CLI 自己的职责或不在框架定位内：

| 能力 | 归属 | 原因 |
|------|------|------|
| 多轮 ReAct / tool-call loop | 每个 agent CLI（CodeMaker / Claude / Codex） | CLI 内部已实现 |
| Tool 注册与执行 | 每个 agent CLI | CLI 自带文件读写、代码执行等工具 |
| 任务规划与分解 | 发起方 agent CLI | 发起方看全局，决定拆成几个子任务 |
| 结果质量判断 | 发起方 agent CLI | 需要语义理解，是 LLM 的活 |
| 动态任务分配 | 发起方 agent CLI | "这个任务给谁做"是决策，不是路由 |
| 对话历史 / 长期记忆 | 每个 agent CLI | CodeMaker / Claude / Codex 自带 session |
| LLM 推理抽象 | 不做 | 推理由各 CLI 完成，框架不重新实现 |
| 可视化 UI | 不做 | 结构化数据落盘即可，UI 是独立项目（vendored Ryven 仅作 P3 节点工作流的可视化候选） |

> **历史变更**：旧 ROADMAP 在本表中曾列"模型抽象层 / 不做（绑定 CodeMaker CLI 是优势）"。该条目自 2026-04-30 起**已撤销**，并改为 P0 的"做最薄的 CLI Adapter"——重点是**适配进程 IO**，不是适配模型推理。

---

## 版本规划

| 版本 | 里程碑 | 核心交付 |
|------|--------|----------|
| ~~**v0.3**~~ | ~~结构化结果~~ | ✅ `WorkerResult`/`ParallelResult`/`ReduceResult`；`run_parallel` 返回值增强；chain 结构化 context；`run_parallel_reduce`；`to_dict`/`to_raw_dict` 双序列化 |
| ~~**v0.5**~~ | ~~`show-registry` + `dispatch` + 异步~~ | ✅ 通用两步流程；async dispatch；status_file 轮询 |
| **v0.6** | CLI Adapter 抽象 | 把 `codemaker_bridge.py` 重构为 `CodeMakerAdapter`；`WorkerConfig.cli_kind` 字段；行为零变化 |
| **v0.7** | 多 CLI 落地 | `ClaudeCodeAdapter` / `CodexAdapter`（spike 之后） |
| **v0.8** | 语义重试 + Tracing | `should_retry` / `retry_rewrite` 回调（P1）；trace 落盘 |
| **v0.9** | 对等原语扩展 | Discovery capability filter；多轮 conversation；per-agent permission |
| **v1.0** | DAG + 测试稳定化 | `DAG` + `run_dag`、条件路由；完整测试覆盖；API 稳定化 |
| **v1.x+** | 多模态 + 节点工作流 | `MultiModalEnvelope`、blob store、headless 节点运行时 |

---

## 设计原则检查表

每次新增特性时对照：

- [ ] **这是通信/编排基础设施，还是在做 LLM 推理？** → 只做前者
- [ ] **这让 agent CLI 之间更容易协作了吗？** → 优先做
- [ ] **这让一个 agent 更容易调起另一个 agent 了吗？** → 优先做
- [ ] **去掉这个特性，发起方 agent 能否通过多调一次 `run_single` 自己实现？** → 如果是高频模式则内置，否则不做
- [ ] **零外部依赖？** → 保持纯标准库
- [ ] **是否破坏 peer-to-peer 对称性？**（例如：是否给某些 agent 引入特权？） → 默认拒绝；除非有明确理由
