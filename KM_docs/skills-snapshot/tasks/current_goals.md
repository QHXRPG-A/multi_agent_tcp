# 当前短期目标总览

本文件提炼当前 `multi_agent_tcp` skill 相关的近期工程目标，来源主要包括：

- `KM_docs/multi-cli-node-workflow-brainstorm.md`
- `KM_docs/vendor-ryvencore-qt-node-appearance.md`
- `KM_docs/ryvencore-vs-ue5-blueprint-gaps-2-4-8.md`

## 当前主线

### 1. 多 CLI agent 接入基线

目标：把当前围绕 CodeMaker 的执行桥接，逐步演化为可扩展的多 CLI adapter 体系。

近期关注：
- 抽出 `CLIAdapter` 薄抽象
- 保持 `CodeMakerAdapter` 完整兼容现有行为
- 为 Claude Code / Codex 保留最小适配位点
- 明确哪些能力属于 adapter，哪些能力仍归各 CLI 自己管理

详见：[`multi_cli_adapter_tasks.md`](multi_cli_adapter_tasks.md)

### 2. 节点运行时与图编译方向

目标：把 `run_single` / `run_parallel` / `run_chain` / `run_parallel_reduce` 上升为节点图的编译目标，而不是最终用户只通过 Python API 手写编排。

近期关注：
- 节点分类
- Agent 节点字段模型
- 端口与 `MultiModalEnvelope`
- 图编译到 cluster / broker 原语的映射

详见：[`node_runtime_tasks.md`](node_runtime_tasks.md)

### 3. vendored Ryven / UI / 蓝图方向

目标：为未来可视化节点编辑器与蓝图体验增强建立可持续演进的基础。

近期关注：
- 理清 `ryvencore_qt` 视觉层结构
- 识别节点主题与外观改造落点
- 沉淀对标 UE5 蓝图的高优先级改进项

详见：[`vendor_ryven_tasks.md`](vendor_ryven_tasks.md)

## 分层规则

- 属于长期稳定知识：回写到 `knowledge_base/`
- 属于近期推进清单：保留在 `tasks/`
- 属于阶段性历史回顾：追加到 `archive/`
