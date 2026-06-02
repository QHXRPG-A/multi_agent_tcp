# 多 CLI Adapter 方向任务

> 当前定位：本文件是后端 CLI 适配层任务，不是 GuLiCode / GraphRuntime 的产品主线。新设计应使用 `CLIWorkerBackend` / `CLIAdapter` 术语；`Codex` 只是一个兼容 adapter，不能重新成为架构中心。

## 目标

围绕 GuLiCode 桌面 app 和 GraphRuntime 需要的 worker backend，建立多 CLI agent 接入基线。

适配层职责：

- 把 Codex、Codex、未来 Claude 等 CLI 包装成 runtime 可调用的 backend。
- 承接 `AgentNode` 的 prompt、context、workspace contract、attachments、timeout、cancel 和结果解析。
- 对上保持稳定的 `CLIWorkerBackend` / `CLIAdapter` 边界，不让具体 CLI 细节渗透到 GraphRuntime 调度语义中。

非目标：

- 不把 `CLIWorkerBackend` 重新定义为当前主架构。
- 不用 adapter 任务替代 GuLiCode top-Agent、control plane、message batch、join、workspace/events 主线。
- 不把 registry-ui 的旧 Codex 字段作为新 UI 的默认信息架构。

## 近期任务

Current adapter priority override - 2026-05-18:

- Highest related blocker status: desktop blueprint `live` now launches workers
  from the `GraphRuntime` materialized private Agent context, including private
  checkout cwd, private `CODEX_HOME`, `framework-agent-runtime`, `AGENTS.md`,
  MCP tool context, direct-read project/shared roots, backend Workspace API
  env, and authorized skill/rule materialization.
- Codex is the active implementation path for live Agent output streaming.
- Prioritize `cli_kind=codex`, `CodexAdapter`, `codex exec --json`, and Codex
  JSONL normalization into `AgentStreamEvent`.
- Do not spend new effort on Codex streaming or Codex model UX in this
  project phase unless the user explicitly re-opens that track.
- Keep Codex as a compatibility/fallback adapter behind `CLIWorkerBackend`.

## 2026-05-20 Status Update - Agent Prompt Surface Simplification

Completed:

1. Ordinary Codex Agent prompt-facing context no longer exposes
   `workspace_api` or CLI command recipes. The generated framework skill now
   teaches MCP tools plus direct read-only project/shared paths.
2. `workspace_api.py` remains as an internal/test/debug CLI over
   `WorkspaceRPCServer`, but it is no longer part of the ordinary Agent mental
   model.
3. `prompt_execution_context` intentionally keeps direct-read roots:
   `project_context`, `project_code_root`, `checkout_path`, and
   `shared_workspace`, while omitting bearer/RPC tokens, private Codex home,
   real skill source paths, and CLI command strings.
4. The active Codex path remains MCP-first:
   `workspace_checkout/status/diff/submit/sync/publish/publish_file`,
   `agent_dispatch`, `agent_context`, and `join_contribute`.

Current adapter guidance:

- Treat CLI framework commands as backend/debug compatibility, not Agent UI.
- Keep Codex streaming and Agent information panel continuity as the active
  adapter quality focus.
- Do not reintroduce Codex streaming work unless explicitly requested.

## 2026-05-19 Status Update - Codex MCP Transport Hardening

Completed:

1. The opt-in real Codex MCP smoke now passes through the full
   `DesktopBlueprintService` live path: planner uses `framework_ordinary`
   Workspace write/submit/publish and dispatch tools, reviewer reads the shared
   report directly from `shared_workspace.reports`, and both worker replies
   complete in `GraphRuntime`.
2. Codex stderr live-stream forwarding is capped. Full stderr is still written
   to diagnostics, but noisy plugin/sandbox output no longer floods the broker
   stream channel.
3. Codex stdout/stderr fields are compacted before being returned over the TCP
   worker reply. `final_text`, return code, timeout metadata, and diagnostics
   paths remain available, while the large raw payload stays on disk.
4. Windows real-smoke projects default to
   `%LOCALAPPDATA%\multi_agent_tcp\real_codex_mcp` to avoid pytest temporary
   directory ACL issues. Use `MULTI_AGENT_TCP_REAL_CODEX_MCP_ROOT` to override
   and `MULTI_AGENT_TCP_KEEP_REAL_CODEX_MCP=1` to keep a successful smoke
   project for inspection.

Current validation:

```powershell
$env:MULTI_AGENT_TCP_RUN_REAL_CODEX_MCP = "1"
python -m pytest -q test_desktop_blueprint_service.py::test_real_codex_live_blueprint_uses_mcp_for_workspace_and_dispatch_flow -vv
# 1 passed, 2 warnings in 135.84s

python -m pytest -q test_agent_runtime.py -k "not real_codex_cli"
# 77 passed, 3 deselected
```

## 2026-05-19 Status Update - Desktop Private Context + Config Boundary

Completed:

1. Desktop blueprint live mode now constructs `GraphRuntime` with
   `enforce_private_agent_context=True` and lets `GraphRuntime.ensure_agent()`
   materialize the private worker context before `CLIWorkerBackend` sees a
   worker config.
2. Desktop skill selection for live runs is backed by
   `DesktopBlueprintSkillCatalog`, sourced from common `skill_dir`, and copied
   into each private `CODEX_HOME` only through authorized skill materialization.
3. Rule files selected in the UI are stored as filenames relative to common
   `rule_dir`, then resolved and materialized during desktop start. This keeps
   user-machine absolute rule paths out of Agent node config.
4. Blueprint start now requires absolute common config paths and rejects
   missing required fields in both renderer and desktop service.

Remaining:

1. Manual desktop live smoke with Codex Agent nodes and user-provided common
   config paths.

1. 将已落地的 Codex / Codex adapter 收敛到 `CLIWorkerBackend` 边界：
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

1. 已新增 `adapters.py`，包含 `AgentMessage`、`AdapterResult`、`CLIAdapter`、`CodexAdapter` 与 `adapter_from_agent_config`。
2. `CodexAdapter` 已把现有 `codex_bridge.codex_run` 包在 adapter 边界后，保持 Codex 现有 per-message `codex run` 行为兼容。
3. `WorkerConfig`、`AgentProfile`、registry 加载与 `AgentNode.to_worker_config()` 已包含 `cli_kind`、`adapter_options`、`extra_env`。
4. `body_to_agent_message()` 已统一 prompt、context、attachments 的基础消息解析。
5. `test_agent_runtime.py` 已覆盖 adapter 消息解析、`WorkerConfig` 扩展字段序列化、`CodexAdapter` 复用实例边界。
6. 已新增 `codex_bridge.py`，封装 `codex exec` 的非交互执行、stdin prompt、`--json`、`--output-last-message`、`--cd`、`--model`、`--image`、超时杀进程树和 JSONL / last-message 提取。
7. 已新增 `CodexAdapter`，`adapter_from_agent_config()` 支持 `cli_kind=codex` 与 `mode=codex-worker`。
8. `__main__.py agent --mode` 已支持 `codex-worker`，统一复用 `_agent_loop_adapter()`。
9. `WorkerConfig(cli_kind="codex", model=...)` 会生成 `codex` worker config，并把 model 映射到 `codex exec --model`。
10. `cluster._parse_worker_result()` 已支持 `body.codex.final_text` / `last_message`，保持 `WorkerResult`、`ParallelResult`、`ReduceResult` 上层视图统一。
11. `AgentSkillView` 已新增 `codex_execution_context()` 与 `codex_adapter_options()`，可把授权 skill catalog 与 agent 独立目录上下文注入 Codex prompt/context。
12. 已补测试覆盖 CodexAdapter 复用边界、codex-worker mode 分派、Codex model 映射、Codex JSONL final text 提取、SkillSpace 到 Codex adapter options 的授权暴露。

部分完成：

1. `CLIAdapter` 目前具备 `start()`、`send_message()`、`health_check()`、`close()`；具体 CLI 的配置校验、prompt 传递、附件处理和输出解析仍分散在 `codex_bridge.py` / `codex_bridge.py`。
2. Codex adapter 已能执行真实 `codex exec`，但仍是 per-message 子进程模式；worker 级 adapter 长生命周期不等于 Codex CLI 内部会话持久化。
3. `AgentSkillView` 已可注入 Codex prompt/context，但自动临时 `CODEX_HOME` 强隔离还没有和 workspace manager / run lifecycle 完整联动。
4. `registry_ui.py` 仍主要面向 Codex model 候选和通用 agent 字段，尚未按 `cli_kind` 渲染差异化字段。
5. Claude adapter spike 仍处于待确认状态：本机未发现 `claude` CLI，不预设调用方式或输出格式。

未完成 / 下一步：

1. 将 CodexAdapter 的临时 `CODEX_HOME` 强隔离自动绑定到 agent 独立目录或 run workspace，并明确 auth / config / session 文件策略。
2. 增加 `cli_kind=codex` 的 registry / cluster 示例与端到端 smoke，覆盖真实 broker + worker + run_single。
3. 继续确认 Claude CLI 的安装路径、非交互入口、stdin / file prompt、结构化输出、cwd/env、附件与取消语义。
4. 把 adapter 配置校验收敛为明确接口，避免所有校验都散落在具体 bridge 中。
5. 评估是否需要 Codex session resume / persistent semantics，而不是仅每条消息 `codex exec`。
6. 让 `registry_ui.py` 按 `cli_kind` 渲染不同字段与 model 候选。
7. 设计非 Codex adapter 的最小测试替身，用于验证 `cli_kind` 分派和 registry-ui 字段差异。

## 依赖知识

- [`../knowledge_base/multi_cli_workflow.md`](../knowledge_base/multi_cli_workflow.md)
- [`../knowledge_base/registry_and_skills.md`](../knowledge_base/registry_and_skills.md)
- [`../knowledge_base/runtime_notes.md`](../knowledge_base/runtime_notes.md)

---

## 2026-05-15 Status Update - Real Codex Framework Flow

The Codex AgentNode private-context baseline is now landed and verified through
a real framework run. This changes the status of the older "temporary
`CODEX_HOME` isolation" and "real broker + worker + run_single smoke" items:
they are no longer first-enablement work.

Completed:

1. Real `cli_kind="codex"` framework-flow integration:
   - real `CLIWorkerBackend.create(...)`;
   - real broker and worker subprocesses;
   - real `GraphRuntime(enforce_private_agent_context=True)`;
   - real `WorkspaceRPCServer`;
   - real `codex exec`;
   - no fake Codex and no `RUN_REAL_CODEX` gate.
2. Private Codex home lifecycle:
   - private `CODEX_HOME` is bound to the agent private run directory;
   - only Codex runtime state files are seeded from the user home:
     `config.toml`, `auth.json`, `models_cache.json`;
   - framework and authorized business skills are re-materialized into the
     private home;
   - user skills, sessions, logs, and plugin caches are not treated as
     authorized business context.
3. Project-reference workspace flow:
   - Codex checks out `src/framework_probe.txt` from project into private
     checkout;
   - edits only the private checkout;
   - runs `workspace_api status` and `diff`;
   - submits a changeset accepted into the project directory;
   - publishes a report into `shared/reports`;
   - `runtime.end_run(..., archive=True)` preserves the shared report and
     changeset record while excluding private scratch.
4. Command/API-level supervision:
   - `WorkspaceRPCServer` records `workspace_api_call` manifest entries for
     checkout/status/diff/submit/publish and other Workspace API commands;
   - the real Codex test asserts Codex JSONL `command_execution` entries for
     checkout/status/diff/submit/publish;
   - the real Codex test guards framework `submit` so the project file must
     still be the original base content immediately before submit applies the
     accepted changeset. This verifies the observed project mutation comes from
     Workspace API submit rather than a direct project-directory write.
5. Direct-write negative coverage:
   - `test_real_codex_cli_framework_blocks_direct_project_and_shared_writes`
     launches real Codex in the framework private context;
   - the prompt intentionally exposes the physical project file and temporary
     shared report path and asks Codex to write them directly without
     `workspace_api`;
   - the direct writes are denied by Codex `workspace-write`, the private
     checkout remains writable, the project file stays at its base content, no
     shared report appears, and no Workspace API audit call is recorded.
6. Blocked-write recovery coverage:
   - `test_real_codex_cli_framework_recovers_from_blocked_direct_write`
     launches real Codex in the same private AgentNode path;
   - the prompt intentionally attempts a direct project write first, catches
     the sandbox denial, and then continues in the same turn through
     checkout/status/diff/submit/publish;
   - the submit guard verifies the project file is still base content until
     Workspace API submit applies the accepted changeset.
7. Worker failure propagation:
   - GraphRuntime now treats explicit worker replies with `body.ok == false`
     as current message/job failure instead of ordinary agent utterances;
   - blocking AgentNode messages raise, record `framework.message.failed`, keep
     `last_error`, and return the AgentInstance to `idle` so it remains
     reusable for retry/continuation;
   - nonblocking AgentNode jobs emit `TaskFailed`;
   - sandbox-denied direct filesystem writes do not necessarily fail the task
     if Codex catches the denial, recovers through Workspace API/private
     checkout, and exits successfully.
8. Windows checkout refresh hardening:
   - checkout refresh no longer deletes the checkout directory itself when it
     may be the current working directory;
   - this fixes `WinError 32` when `workspace_api checkout --path ...` is run
     from inside the private checkout.

Remaining adapter work:

1. Harden the private Codex home policy further if Codex adds new required
   runtime state files.
2. Add registry/UI examples for `cli_kind=codex` around this real baseline.
3. Decide whether Codex session resume/persistent semantics are needed beyond
   current per-message `codex exec`.
4. Keep Claude and other CLI adapters as separate future probes; do not infer
   their sandbox/auth/session behavior from Codex.
