# multi-agent-tcp Codex skill

本目录是当前本机生效的 Codex skill：`C:\Users\a\.codex\skills\multi-agent-tcp\`。

## 目的

- 为 GuLiCode desktop、GraphRuntimeControlPlane、GraphRuntime、AgentNode 队列、workspace/events 和 CLIWorkerBackend adapter 提供本地工作记忆。
- 保留旧 CodeMakerCluster / TCP / Ryven 资料，但只作为兼容和历史背景。
- 让后续更新 skill 时有稳定的知识库、任务目录和归档目录。

## 当前主线

- GuLiCode desktop / top Agent 发起 start plan。
- `GraphRuntimeControlPlane` 负责组织读取、开始校验、运行控制、消息批次、join、结束归档等非 UI 控制面。
- `GraphRuntime` 负责 AgentNode queue、tick dispatch、outgoing batch、fan-in/join、workspace/event/final status。
- `CLIWorkerBackend` 负责 Codex / CodeMaker / 其它 CLI 的后端适配。

## 维护规则

- 新内容优先写入 `knowledge_base/` 或 `tasks/`，长期变更再归档到 `archive/`。
- 写新文档时不要恢复旧的“Cursor/CodeMaker TCP 编排是中心”的表述。
- `CodeMakerCluster` 只作为旧 API 兼容名使用；新文档优先写 `CLIWorkerBackend`。
- Ryven 是可视化编辑器候选和历史原型；除非用户明确要求 Ryven/editor，不作为当前产品优先级。

## 当前包含内容

- `SKILL.md`
- `knowledge_base/`
- `tasks/`
- `archive/`
