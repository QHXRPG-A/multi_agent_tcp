# 多 CLI Adapter 方向任务

## 目标

围绕 `KM_docs/multi-cli-node-workflow-brainstorm.md` 中提出的方向，建立多 CLI agent 接入基线。

## 近期任务

1. 梳理 `codemaker_bridge.py` 中哪些逻辑是 CodeMaker 专属，哪些可提炼为 adapter 公共接口。
2. 明确 `CLIAdapter` 的最小方法集合：
   - 配置校验
   - argv / stdin / file prompt 传递
   - 附件物化
   - 输出解析
   - 健康检查
3. 设计 `WorkerConfig` / `agents_registry.json` 的扩展位：
   - `cli_kind`
   - `adapter_options`
   - `extra_env`
4. 为 Claude Code / Codex 列出 spike 清单，只记录“待确认事实”，不预设不存在的 CLI 约束。
5. 评估 `registry_ui.py` 后续如何按 `cli_kind` 渲染不同字段与 model 候选。

## 依赖知识

- [`../knowledge_base/multi_cli_workflow.md`](../knowledge_base/multi_cli_workflow.md)
- [`../knowledge_base/registry_and_skills.md`](../knowledge_base/registry_and_skills.md)
- [`../knowledge_base/runtime_notes.md`](../knowledge_base/runtime_notes.md)
