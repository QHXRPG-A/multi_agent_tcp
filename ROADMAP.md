# multi_agent_tcp 迭代路线图

> **设计哲学：薄框架，智能交给两端的大模型。**
>
> 框架不造智能体。上游的 Cursor/CodeMaker 是决策者（orchestrator），下游的 CodeMaker CLI 是执行者（agent）。
> 框架只做一件事：**让两端的大模型能可靠、高效地协作**。

## 架构定位

```
┌────────────────────────────────────────────────────────────┐
│  Cursor / 调用方  (上游大模型 — 决策与编排)                    │
│  "看结果 → 判断 → 决定下一步发什么任务给谁"                     │
└──────────────────────┬─────────────────────────────────────┘
                       │  Python API / CLI
┌──────────────────────▼─────────────────────────────────────┐
│  multi_agent_tcp  (本框架 — 薄传输与编排原语)                  │
│                                                            │
│  职责边界：                                                  │
│  ✓ 进程生命周期管理（broker + worker 启停）                    │
│  ✓ 消息路由（unicast / broadcast / batch_gather）            │
│  ✓ 并行 fan-out + 结果聚合                                  │
│  ✓ 串行 chain + 上下文传递                                   │
│  ✓ 超时、重试、断连感知等可靠性保障                              │
│  ✓ 结构化结果提取与传递（让两端大模型更容易协作）                  │
│                                                            │
│  不做：                                                     │
│  ✗ LLM 推理循环（CLI 已有）                                  │
│  ✗ Tool/Function calling 注册与执行（CLI 已有）               │
│  ✗ 自主决策（交给上游 Cursor）                                │
│  ✗ 模型抽象层（绑定 CodeMaker CLI 是优势不是限制）              │
└──────────────────────┬─────────────────────────────────────┘
                       │  TCP (broker)
┌──────────────────────▼─────────────────────────────────────┐
│  CodeMaker CLI × N  (下游大模型 — 执行)                      │
│  每个 CLI 实例自带：多轮 tool-call loop、文件读写、代码执行      │
│  框架不需要重复造这些能力                                      │
└────────────────────────────────────────────────────────────┘
```

**核心推论**：框架的每一个新特性都应该问——"这是在帮助两端大模型更好地协作，还是在替代它们的能力？"只做前者。

---

## 当前能力（v0.3.0）

| 能力 | 状态 | 说明 |
|------|------|------|
| 进程管理 | ✅ | broker + N worker，启停、进程树清理 |
| 并行分发 | ✅ | `run_parallel` → `ParallelResult` |
| fan-out → reduce | ✅ | `run_parallel_reduce` → `ReduceResult` |
| 串行链 | ✅ | `run_chain` + 结构化 context 注入 |
| 单任务 | ✅ | `run_single` |
| 结构化结果 | ✅ | `WorkerResult` / `ParallelResult` / `ReduceResult`；`to_dict()`（LLM 精简）/ `to_raw_dict()`（调试完整） |
| 技术级重试 | ✅ | `database is locked` 等可重试错误串行重试 |
| 超时控制 | ✅ | 进程级 + gather 级 |
| 心跳探活 | ✅ | ping/pong + 驱逐 |
| 断连感知 | ✅ | gather 中 target 断连即报错 |
| 并发写安全 | ✅ | per-connection 写锁 |
| 日志落盘 | ✅ | rotating file + 结构化前缀 |

---

## 迭代计划

### ~~P0：结构化结果传递~~ ✅ Done (v0.3.0)

> 已实现。`WorkerResult` dataclass + `ParallelResult` 类 + `run_parallel` 返回 `ParallelResult` + `run_chain` 结构化 context 注入。
>
> 额外改进：`to_dict()`（LLM 精简：仅 status + answer）/ `to_raw_dict()`（调试完整：含 raw_stdout/stderr/elapsed_sec），过滤上游大模型不需要的噪音字段。

---

### ~~P0：fan-out → reduce 模式~~ ✅ Done (v0.3.0)

> 已实现。`run_parallel_reduce()` 方法 + `ReduceResult` dataclass + CLI `run-parallel-reduce` 命令。

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

**不做**：不做自动判断"任务是否完成"（那需要 LLM 推理，交给上游 Cursor 决定）。框架只提供 hook 点。

---

### P1：执行追踪（Tracing）

> **目标**：让上游大模型和人类能看清"谁做了什么、花了多久、结果如何"。

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

3. **`cluster.traces`** 属性：内存中保留最近 N 条 trace，方便上游大模型回顾

**不做**：不做可视化 UI、不接第三方 tracing 平台（LangSmith 等）。只做结构化数据落盘。需要可视化时，数据格式已经在那里，外部工具自己读。

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
- 如果上游大模型（Cursor）想用 LLM 判断，它自己在 `when` 里调 LLM 就好
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

### P3：Worker 能力声明（可选）

> **目标**：让上游大模型知道每个 worker 擅长什么，辅助它做任务分配决策。

**现状**：`WorkerConfig` 只有 `agent_id`、`cwd`、`model` 等运行时参数。上游大模型不知道 cm1 和 cm2 有什么区别（除了 cwd 不同）。

**改进方向**：

```python
WorkerConfig(
    agent_id="cm1",
    cwd=Path("F:/src"),
    tags=["search", "python"],                        # 可选标签
    description="擅长 Python 代码搜索和分析",             # 可选描述
)
```

`cluster.describe_workers()` 返回所有 worker 的能力描述，上游大模型可以用它来决定把任务分给谁。

**不做**：不做自动任务分配（框架不决策）。只提供信息，让上游大模型决定。

---

## 不做清单（明确的边界）

以下能力**不在本框架范围内**，原因是它们属于两端大模型的职责：

| 能力 | 归属 | 原因 |
|------|------|------|
| 多轮 ReAct / tool-call loop | CodeMaker CLI（下游） | CLI 内部已实现 |
| Tool 注册与执行 | CodeMaker CLI（下游） | CLI 自带文件读写、代码执行等工具 |
| 任务规划与分解 | Cursor（上游） | 上游大模型看全局，决定拆成几个子任务 |
| 结果质量判断 | Cursor（上游） | 需要语义理解，是 LLM 的活 |
| 动态任务分配 | Cursor（上游） | "这个任务给谁做"是决策，不是路由 |
| 对话历史 / 长期记忆 | Cursor（上游） | Cursor 自带会话上下文 |
| 模型抽象层 | 不做 | 绑定 CodeMaker CLI 是明确选择 |
| 可视化 UI | 不做 | 结构化数据落盘即可，UI 是独立项目 |

---

## 版本规划

| 版本 | 里程碑 | 核心交付 |
|------|--------|----------|
| ~~**v0.3**~~ | ~~结构化结果~~ | ✅ `WorkerResult`/`ParallelResult`/`ReduceResult`；`run_parallel` 返回值增强；chain 结构化 context；`run_parallel_reduce`；`to_dict`/`to_raw_dict` 双序列化 |
| **v0.4** | 语义重试 | `should_retry` / `retry_rewrite` 回调（P1 任务级重试） |
| **v0.5** | 可观测 | 结构化 trace 落盘、`cluster.traces` |
| **v0.6** | DAG | `DAG` + `run_dag`、条件路由 |
| **v1.0** | 稳定 | 完整测试覆盖、API 稳定化 |

---

## 设计原则检查表

每次新增特性时对照：

- [ ] **这是传输/编排基础设施，还是在做 LLM 推理？** → 只做前者
- [ ] **这让上游大模型更容易拿到结构化信息了吗？** → 优先做
- [ ] **这让下游 CLI 更容易被调度了吗？** → 优先做
- [ ] **去掉这个特性，用户能否通过多调一次 `run_single` 自己实现？** → 如果是高频模式则内置，否则不做
- [ ] **零外部依赖？** → 保持纯标准库
