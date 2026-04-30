# 节点运行时与图编译方向任务

## 目标

把当前 cluster / broker 编排能力，逐步抬升为面向节点图的执行运行时与编译目标。

## 近期任务

1. 抽象节点分类：
   - Agent 节点
   - 处理节点
   - 路由节点
   - I/O 节点
2. 设计 Agent 节点的字段模型，与 `WorkerConfig` / registry schema 对齐。
3. 统一端口数据容器，采用 `MultiModalEnvelope` 作为长期方向。
4. 明确图编译到现有原语的映射：
   - 单节点 → `run_single`
   - fan-out → `run_parallel`
   - 线性链 → `run_chain`
   - fan-out + reduce → `run_parallel_reduce`
5. 评估未来 DAG 执行入口与条件路由的最小实现边界。

## 依赖知识

- [`../knowledge_base/multi_cli_workflow.md`](../knowledge_base/multi_cli_workflow.md)
- [`../knowledge_base/core_architecture.md`](../knowledge_base/core_architecture.md)
- [`../knowledge_base/cluster_api.md`](../knowledge_base/cluster_api.md)
