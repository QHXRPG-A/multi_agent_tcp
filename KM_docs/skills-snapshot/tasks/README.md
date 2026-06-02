# 短期任务目录

本目录用于记录 `multi_agent_tcp` skill 相关的近期目标、任务拆解与阶段性推进事项。

约定：
- 这里只记录“最近要推进什么”，不承担长期知识沉淀。
- 稳定方法、长期结构性知识应回写到 `knowledge_base/`。
- 历史变更与阶段性回顾应写入 `archive/`。
- 每个任务文档可引用 `knowledge_base/` 与 `KM_docs/` 中的来源材料。

当前优先级：

1. `current_goals.md`：当前短期目标总览，优先读。
2. `guli_desktop_ui_tasks.md`：Guli 桌面端 UI 产品化、蓝图入口嵌入、品牌与图标一致性、桌面壳层硬化。
3. `multi_agent_communication_tasks.md`：GuLiCode 顶层 Agent、GraphRuntimeControlPlane、GraphRuntime 调度权、消息批次、fan-in/join、workspace/events 主线。
4. `node_runtime_tasks.md`：节点运行时和图调度任务。只按 GraphRuntime / control plane 主线理解。
5. `multi_cli_adapter_tasks.md`：CLIWorkerBackend / Codex / Codex adapter 任务。它是后端适配层，不是产品主架构。

维护规则：

- 新增任务先落到 `current_goals.md` 或 `guli_desktop_ui_tasks.md` / `multi_agent_communication_tasks.md`，再按需要拆到其它文件。
- 写新任务时使用 `GuLiCode`、`Guli`、`GraphRuntimeControlPlane`、`GraphRuntime`、`CLIWorkerBackend` 等当前术语。
- `CLIWorkerBackend`、`show-registry/dispatch` 只作为兼容或历史内容出现。
- 旧 Ryven/editor UI 轨道已不在当前短期任务列表中；若要重启，必须由用户显式提出。
