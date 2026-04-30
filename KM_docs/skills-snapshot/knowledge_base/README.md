# multi_agent_tcp 技能知识库索引

本目录用于沉淀 `multi_agent_tcp` skill 的模块化知识文档。

约定：
- 每个模块单独成文，只记录当前有效知识，不承担历史变更流水。
- 历史变更统一记录在上级 `archive/` 目录下的各个 `*_archive.md` 中。
- 短期目标与待推进事项统一记录在上级 `tasks/` 目录，不混入知识库正文。
- 各知识文档之间允许直接交叉引用。
- `SKILL.md` 只保留高层入口、关键规则与知识索引，不再承载大段模块细节。

当前模块：
- `core_architecture.md`：主架构、核心组件、端口与协议入口
- `cluster_api.md`：`CodeMakerCluster` API、生命周期与结果类型
- `registry_and_skills.md`：`agents_registry.json`、skill 合并、注入策略与 registry 相关工作流
- `dispatch_workflows.md`：`show-registry` / `dispatch` / session-gated workflow / async dispatch
- `cli_reference.md`：CLI 速查与常用命令
- `runtime_notes.md`：编码、日志、进程树、心跳、重试与 `codemaker run` 易错点
- `multi_cli_workflow.md`：多 CLI 接入、节点化工作流、`CLIAdapter` 与 `MultiModalEnvelope` 方向
- `vendor_ryven_ui.md`：vendored `ryvencore_qt` / `Ryven` 的节点外观、主题与视觉层知识
- `blueprint_gap_notes.md`：对标 UE5 蓝图时的类型系统、编辑效率与信息密度改进方向
