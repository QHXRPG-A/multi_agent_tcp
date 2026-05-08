# 多 CLI Adapter 方向任务

> 当前定位：本文件是后端 CLI 适配层任务，不是 GuLiCode / GraphRuntime 的产品主线。新设计应使用 `CLIWorkerBackend` / `CLIAdapter` 术语；`CodeMaker` 只是一个兼容 adapter，不能重新成为架构中心。

## 目标

围绕 GuLiCode 桌面 app 和 GraphRuntime 需要的 worker backend，建立多 CLI agent 接入基线。

适配层职责：

- 把 Codex、CodeMaker、未来 Claude 等 CLI 包装成 runtime 可调用的 backend。
- 承接 `AgentNode` 的 prompt、context、workspace contract、attachments、timeout、cancel 和结果解析。
- 对上保持稳定的 `CLIWorkerBackend` / `CLIAdapter` 边界，不让具体 CLI 细节渗透到 GraphRuntime 调度语义中。

非目标：

- 不把 `CodeMakerCluster` 重新定义为当前主架构。
- 不用 adapter 任务替代 GuLiCode top-Agent、control plane、message batch、join、workspace/events 主线。
- 不把 registry-ui 的旧 CodeMaker 字段作为新 UI 的默认信息架构。

## 近期任务

1. 将已落地的 Codex / CodeMaker adapter 收敛到 `CLIWorkerBackend` 边界：
   - prompt contract
   - execution context
   - workspace API / VCS checkout contract
   - structured result extraction
   - timeout / cancel / cleanup
2. 继续硬化已落地的 `CodexAdapter`：
   - `codex exec`
   - stdin prompt
   - `--model`
   - `--cd`
   - `--json` 或 `--output-last-message`
   - 图片附件 `--image`
   - 超时与取消
3. 完善 `cli_kind=codex` / `mode=codex-worker` 的生产配置路径：
   - registry 示例
   - cluster JSON 示例
   - registry-ui 字段差异化
4. 继续完善 SkillSpace / AgentSkillView 与 CodexAdapter 的隔离：
   - 只暴露授权 skills
   - agent 不接触真实 skill 空间路径
   - 将临时 `CODEX_HOME` 自动绑定到 agent 独立目录或 run workspace
5. 设计 AgentNode prompt contract：
   - 用户设置的 agent prompt
   - 上游传入上下文
   - 框架接口文档
   - 授权 skills catalog
   - 输出格式要求
6. 继续确认 Claude CLI 的非交互入口、输出格式、cwd/env、附件与取消语义。
7. 评估 `registry_ui.py` 后续如何按 `cli_kind` 渲染不同字段与 model 候选，但不要把旧 registry-ui 作为 GuLiCode UI 主线。

## 当前代码对照状态（2026-05-03）

已完成：

1. 已新增 `adapters.py`，包含 `AgentMessage`、`AdapterResult`、`CLIAdapter`、`CodeMakerAdapter` 与 `adapter_from_agent_config`。
2. `CodeMakerAdapter` 已把现有 `codemaker_bridge.codemaker_run` 包在 adapter 边界后，保持 CodeMaker 现有 per-message `codemaker run` 行为兼容。
3. `WorkerConfig`、`AgentProfile`、registry 加载与 `AgentNode.to_worker_config()` 已包含 `cli_kind`、`adapter_options`、`extra_env`。
4. `body_to_agent_message()` 已统一 prompt、context、attachments 的基础消息解析。
5. `test_agent_runtime.py` 已覆盖 adapter 消息解析、`WorkerConfig` 扩展字段序列化、`CodeMakerAdapter` 复用实例边界。
6. 已新增 `codex_bridge.py`，封装 `codex exec` 的非交互执行、stdin prompt、`--json`、`--output-last-message`、`--cd`、`--model`、`--image`、超时杀进程树和 JSONL / last-message 提取。
7. 已新增 `CodexAdapter`，`adapter_from_agent_config()` 支持 `cli_kind=codex` 与 `mode=codex-worker`。
8. `__main__.py agent --mode` 已支持 `codex-worker`，统一复用 `_agent_loop_adapter()`。
9. `WorkerConfig(cli_kind="codex", model=...)` 会生成 `codex` worker config，并把 model 映射到 `codex exec --model`。
10. `cluster._parse_worker_result()` 已支持 `body.codex.final_text` / `last_message`，保持 `WorkerResult`、`ParallelResult`、`ReduceResult` 上层视图统一。
11. `AgentSkillView` 已新增 `codex_execution_context()` 与 `codex_adapter_options()`，可把授权 skill catalog 与 agent 独立目录上下文注入 Codex prompt/context。
12. 已补测试覆盖 CodexAdapter 复用边界、codex-worker mode 分派、Codex model 映射、Codex JSONL final text 提取、SkillSpace 到 Codex adapter options 的授权暴露。

部分完成：

1. `CLIAdapter` 目前具备 `start()`、`send_message()`、`health_check()`、`close()`；具体 CLI 的配置校验、prompt 传递、附件处理和输出解析仍分散在 `codemaker_bridge.py` / `codex_bridge.py`。
2. Codex adapter 已能执行真实 `codex exec`，但仍是 per-message 子进程模式；worker 级 adapter 长生命周期不等于 Codex CLI 内部会话持久化。
3. `AgentSkillView` 已可注入 Codex prompt/context，但自动临时 `CODEX_HOME` 强隔离还没有和 workspace manager / run lifecycle 完整联动。
4. `registry_ui.py` 仍主要面向 CodeMaker model 候选和通用 agent 字段，尚未按 `cli_kind` 渲染差异化字段。
5. Claude adapter spike 仍处于待确认状态：本机未发现 `claude` CLI，不预设调用方式或输出格式。

未完成 / 下一步：

1. 将 CodexAdapter 的临时 `CODEX_HOME` 强隔离自动绑定到 agent 独立目录或 run workspace，并明确 auth / config / session 文件策略。
2. 增加 `cli_kind=codex` 的 registry / cluster 示例与端到端 smoke，覆盖真实 broker + worker + run_single。
3. 继续确认 Claude CLI 的安装路径、非交互入口、stdin / file prompt、结构化输出、cwd/env、附件与取消语义。
4. 把 adapter 配置校验收敛为明确接口，避免所有校验都散落在具体 bridge 中。
5. 评估是否需要 Codex session resume / persistent semantics，而不是仅每条消息 `codex exec`。
6. 让 `registry_ui.py` 按 `cli_kind` 渲染不同字段与 model 候选。
7. 设计非 CodeMaker adapter 的最小测试替身，用于验证 `cli_kind` 分派和 registry-ui 字段差异。

## 依赖知识

- [`../knowledge_base/multi_cli_workflow.md`](../knowledge_base/multi_cli_workflow.md)
- [`../knowledge_base/registry_and_skills.md`](../knowledge_base/registry_and_skills.md)
- [`../knowledge_base/runtime_notes.md`](../knowledge_base/runtime_notes.md)
