# CodeMakerCluster API

参见 [`core_architecture.md`](core_architecture.md) 了解整体定位。

## 创建集群

```python
from multi_agent_tcp import CodeMakerCluster, WorkerConfig, AgentsRegistry
from pathlib import Path

reg = AgentsRegistry.load()
cluster = await CodeMakerCluster.create_from_registry(
    reg,
    agent_ids=["agent-1", "agent-2"],
    skill_mode="catalog",
    port=9140,
)

cluster = await CodeMakerCluster.create(
    workers=[
        WorkerConfig("cm1", cwd=Path("F:/src")),
        WorkerConfig("cm2", cwd=Path("F:/src")),
    ],
    port=9140,
)
cluster.set_registry(reg, skill_mode="catalog")

cluster = await CodeMakerCluster.connect(port=9140)
```

## 提交任务

```python
par = await cluster.run_parallel([
    ("cm1", {"prompt": "Task A"}),
    ("cm2", {"prompt": "Task B"}),
])

par = await cluster.run_parallel(
    [("cm1", {"prompt": "A"}), ("cm2", {"prompt": "B"}), ("cm3", {"prompt": "C"})],
    max_retries=2,
    retry_delay_sec=5.0,
)

rr = await cluster.run_parallel_reduce(
    tasks=[("cm1", {"prompt": "A"}), ("cm2", {"prompt": "B"})],
    reduce_worker="cm1",
    reduce_prompt="Merge:\n{results}",
)

results = await cluster.run_chain([
    ("cm1", {"prompt": "Step1"}),
    ("cm2", {"prompt": "Step2, continue..."}),
])

reply = await cluster.run_single("cm1", {"prompt": "One task"})
```

## 结果类型

- `WorkerResult`
- `ParallelResult`
- `ReduceResult`

常用能力：
- `to_dict()`：LLM 友好的精简结果
- `to_raw_dict()`：调试用完整结果
- `extract_final_text`：最终文本提取
- `is_retryable_error`：可重试错误识别

## 生命周期

```python
async with await CodeMakerCluster.create(workers=...) as cluster:
    ...

await cluster.stop()
await cluster.close()
```

## 从 JSON 加载

```python
import json
from pathlib import Path

data = json.loads(Path("cluster.json").read_text())
workers = CodeMakerCluster.workers_from_json(data)
host, port = CodeMakerCluster.host_port_from_json(data)
```

## 相关知识

- 主架构：[`core_architecture.md`](core_architecture.md)
- Registry 与 skill：[`registry_and_skills.md`](registry_and_skills.md)
- 运行时细节：[`runtime_notes.md`](runtime_notes.md)
