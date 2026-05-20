---
name: multi-agent-tcp
description: >-
 Work on the current multi_agent_tcp direction: GuLiCode desktop productization,
 blueprint runtime embedding, GraphRuntimeControlPlane, GraphRuntime scheduling,
 top-agent orchestration, AgentNode queues, workspace state, events, and
 CLIWorkerBackend adapters. Use for GuLiCode desktop, blueprint entry embedding,
 runtime start/status/end, agent dispatch, workspace/archive flow, and legacy
 TCP/CodeMaker backend compatibility.
---
# multi_agent_tcp - GuLiCode desktop and blueprint skill

## Current Position

The current project center is **Guli productization + blueprint embedded in the GuLiCode desktop app**.

The main architecture line is:

```text
GuLiCode desktop / UI / top Agent
  -> blueprint entry and workbench surfaces
  -> GraphRuntimeControlPlane
  -> GraphRuntime
  -> AgentNode queues, outgoing batches, joins, workspace state, events
  -> CLIWorkerBackend
  -> AgentTCPClient / Broker / CLIAdapter / worker process
```

Rules of interpretation:

- Treat `GraphRuntimeControlPlane` and `GraphRuntime` as the framework-owned execution center.
- Treat GuLiCode desktop as the user-facing product center.
- Treat blueprint capability as embedded inside GuLiCode desktop, not as a separate Ryven-led product surface.
- Treat low-level TCP workers as a backend adapter path, not the product architecture center.
- Treat `CodeMakerCluster` as a backward-compatible alias for the old cluster facade. New writing should prefer `CLIWorkerBackend`.
- Treat the old Ryven/editor UI line as retired from this active skill snapshot. Only revisit it if the user explicitly revives that track.
- Current adapter priority is Codex-first. For Agent information panel streaming
  and live blueprint smoke, focus on `cli_kind=codex`, `CodexAdapter`, and the
  Codex JSONL -> `AgentStreamEvent` path. Do not spend new effort on CodeMaker
  streaming unless the user explicitly re-opens that track; treat CodeMaker as
  compatibility/fallback.

Common repository root:

```text
F:\src\Package\Script\Python\multi_agent_tcp
```

Historical paths such as `D:\agents\multi_agent_tcp` or `F:\src\ryven_demo` may appear in archives. Do not use them as current defaults unless the user's machine actually has that path.

## Fast Handoff - 2026-05-20 Agent Info Panel Stream UI

When the next task is Agent information panel transcript quality, status
display, streaming behavior, tool-call rendering, or Test Agent panel smoke,
start from this state:

1. Agent information panels default to the tall shape `420 x 620`. The old
   width/height preset selector is removed.
2. Agent information panels open by left mouse long-press on Agent nodes after
   `500ms`, or through the Agent node context menu. Moving the pointer by `8px`
   or more cancels the pending long-press open.
3. The compact top status strip always shows four cards: status, queue,
   messages, and busy count.
4. The status detail expander lives in that top strip. It is the only place
   where "运行状态" and "JSON 位置" appear; those details are not rendered in the
   chat body or composer.
5. Panel-sent user messages are inserted into the transcript immediately for
   all Agents. Runtime/user-message lifecycle status is then synced from
   runtime events and stream events. Test Agent JSON persistence still only
   runs for Test Agent nodes.
6. The transcript projects `AgentStreamEvent` into structured display rows:
   user messages, Agent replies, collapsible reasoning summaries, collapsible
   tool calls, and queue errors. Raw status/scheduler ticks stay hidden.
7. Agent reply rows (`tone === "reply"`) render through the existing
   `@opencode-ai/ui/markdown` `Markdown` component. Non-reply rows, reasoning,
   errors, tool calls, and tool-call second-level expanded content remain
   plain text / `<pre>`.
8. Agent reply Markdown uses compact dark-panel styling. Fenced code blocks
   render as real code blocks, and panel-local `pre` / Shiki `.shiki`
   backgrounds are forced dark so code fences do not appear as white blocks.
9. Consecutive tool calls are grouped by default when no visible user/Agent
   reply, reasoning, error, or other content interrupts them. Hidden status
   ticks do not break the group. A multi-tool segment renders as
   `工具调用组 · N 个工具` and can be expanded to inspect individual tools.
10. Event collapsibles are controlled by `agentPanelEventOpen`, keyed by stable
   display event ids, so stream/status ticks do not auto-collapse rows the user
   opened.

Latest relevant verification:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\app
bun test --preload ./happydom.ts ./src/pages/session/blueprint-side-panel.test.ts
bun run typecheck
```

Detailed archive:

- [`archive/agent_info_panel_stream_ui_2026-05-20.md`](archive/agent_info_panel_stream_ui_2026-05-20.md)
- [`archive/agent_info_panel_markdown_longpress_2026-05-20.md`](archive/agent_info_panel_markdown_longpress_2026-05-20.md)

## Fast Handoff - 2026-05-20 Blueprint Project Workdir + Agent Surface

When the next task is blueprint project workdir switching, Agent tool
surface, direct project/shared reads, or MCP/CLI exposure cleanup, start from
this state:

1. The blueprint project workdir is the authoritative session/workspace root
   selection. The blueprint panel confirms the current project directory on
   entry, offers a folder picker, and relocates/reloads the blueprint when the
   directory changes.
2. Backend relocation command is `blueprint.relocateProjectWorkdir`: unchanged
   paths return `changed: false`; changed paths write
   `.multi_agent_workspace/blueprints/default.json` under the target project;
   existing target blueprints return a conflict for overwrite/load/cancel UI.
3. Runtime/start/stop loading disables the blueprint common config entry. The
   common-config `project_workdir` field is read-only; only the folder picker
   can initiate relocation.
4. Ordinary Agents directly read `project_context`, `project_code_root`, and
   the current run `shared_workspace` physical paths. Code edits still happen
   only in the private checkout and must submit through MCP.
5. Ordinary MCP tool surface is intentionally small:
   `workspace_checkout`, `workspace_status`, `workspace_diff`,
   `workspace_submit`, `workspace_sync`, `workspace_publish`,
   `workspace_publish_file`, `agent_dispatch`, `agent_context`, and
   `join_contribute`.
6. Workspace read/list/archive tools were removed from ordinary/control MCP,
   `workspace_api.py`, and `WorkspaceRPCServer` Agent-facing surfaces. Internal
   manager read/archive methods remain for framework reports/status/archive.
7. CLI framework APIs remain in full internal `execution_context` and backend
   env for tests/debugging, but ordinary Agent `prompt_execution_context` no
   longer includes `workspace_api`, `submit_command`, or CLI command recipes.
8. Codex launch safety rejects `danger-full-access` and rejects `--add-dir`
   entries overlapping `project_context`, `project_code_root`, or the run
   `shared_workspace.root`.
9. For manual debugging, avoid using `C:\` as the project workdir. Use a normal
   writable project directory such as `D:\agents_work_test`; setting only an
   Agent cwd is not enough because Workspace authority follows the blueprint
   project workdir/session root.

Latest relevant verification:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp
python -m py_compile blueprint_mcp_runtime.py agent_launch_context.py workspace_api.py workspace_rpc.py codex_bridge.py test_workspace_api.py test_agent_runtime.py test_desktop_blueprint_service.py
pytest -q test_workspace_api.py test_agent_runtime.py test_desktop_blueprint_service.py
# Observed related full pass: 127 passed, 1 skipped, 2 warnings.

cd GuLiCode\packages\app
bun run typecheck
bun test --preload ./happydom.ts ./src/pages/session/blueprint-side-panel.test.ts

cd ..\desktop-electron
bun test ./src/main/blueprint-runtime.test.ts ./src/main/ipc-blueprint-runtime.test.ts
bun run typecheck
```

Detailed archive:

- [`archive/blueprint_project_workdir_agent_surface_2026-05-20.md`](archive/blueprint_project_workdir_agent_surface_2026-05-20.md)

## Fast Handoff - 2026-05-19 Full MCP Control + Real Codex Smoke

When the next task is MCP integration, live Agent tool discovery, or the
original Agent timeout after panel messages, start from this state:

1. Run-scoped MCP runtime is implemented in `blueprint_mcp_runtime.py`: one
   ASGI/uvicorn server per live blueprint run, with `/ordinary/mcp` and
   `/control/mcp` FastMCP mounts.
2. `DesktopBlueprintRun.mcp` owns the handle. Live start order is
   WorkspaceRPCServer -> GraphRuntime/ControlPlane -> MCP handle -> private
   Codex context -> `control.start_run()`.
3. Private `CODEX_HOME/config.toml` gets `framework_ordinary` or
   `framework_control` using `url` + `bearer_token_env_var`,
   `enabled_tools`, and per-tool `approval_mode = "approve"`; bearer tokens
   are injected only through env vars.
4. Ordinary MCP exposes execution-scoped tools only: Workspace checkout/status/
   diff/submit/sync/publish/publish_file, `agent_dispatch`, scoped
   `agent_context`, and scoped `join_contribute`. Ordinary Agents read
   project_context/project_code_root and the run temporary shared workspace
   directly through injected read-only filesystem paths.
5. Control MCP exposes top-agent/control-plane tools: organization read,
   top-agent context/ask/status/utterances, run validate/start/status/end,
   message batch/stage, control-side agent dispatch, join create/contribute,
   and utterance/status inspection. It no longer exposes Workspace read/list/
   archive tools.
6. Permission gates are server-enforced: `ask`, `start`, `status`, `end`,
   `utterances`, and debug-only `fixture`. Ordinary Agents cannot call global
   lifecycle/message-batch/utterance tools; Top Agent cannot call Workspace
   write/submit/publish tools.
7. Framework skill/rule injection remains required. The framework skill is
   MCP-first; CLI framework APIs stay available for internal/debug paths but
   are not exposed in ordinary Agent prompt-facing context.
8. Active ordinary Agent message context is refreshed from
   `GraphRuntime.agent_message_context_callback`; `agent_dispatch` uses token
   scope context and does not scan journals.
9. Path validation for `workspace_publish_file` is done in MCP before
   Workspace RPC and blocks traversal, drive-relative paths, arbitrary absolute
   paths, and symlink/junction escape.
10. MCP `runtime_end` now prefers the `DesktopBlueprintService` live-run close
    callback and closes MCP tokens; it falls back to `GraphRuntime.end_run()`
    only when no desktop close callback is available.
11. Real `codex exec` launched through the full `DesktopBlueprintService` live
    path completes the ordinary MCP flow:
    checkout/status/diff/submit/publish/publish_file/agent_dispatch all
    produce `framework_mcp_tool_call` audit entries.
12. Real-smoke hardening is in place: the Windows project root defaults to
    `%LOCALAPPDATA%\multi_agent_tcp\real_codex_mcp`, live stderr streaming is
    capped, and Codex stdout/stderr are compacted for TCP transport while full
    diagnostics remain on disk.

Latest relevant verification:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp
python -m pip install -e .
python -m py_compile __init__.py blueprint_mcp_runtime.py agent_launch_context.py graph_runtime.py graph_control.py workspace_rpc.py desktop_blueprint_service.py test_desktop_blueprint_service.py test_agent_runtime.py test_workspace_api.py test_workspace_manager.py codex_bridge.py
pytest -q test_desktop_blueprint_service.py test_agent_runtime.py test_workspace_api.py test_workspace_manager.py
# Latest full related result: 146 passed, 1 skipped, 2 warnings.
pytest -q test_desktop_blueprint_service.py::test_live_blueprint_mcp_workspace_dispatch_flow_with_agent_backend -vv
$env:MULTI_AGENT_TCP_RUN_REAL_CODEX_MCP = "1"
pytest -q test_desktop_blueprint_service.py::test_real_codex_live_blueprint_uses_mcp_for_workspace_and_dispatch_flow -vv
# Latest focused real Codex result: 1 passed, 2 warnings in 135.84s.
```

Detailed archive:

- [`archive/blueprint_full_mcp_control_real_smoke_2026-05-19.md`](archive/blueprint_full_mcp_control_real_smoke_2026-05-19.md)
- [`archive/blueprint_run_mcp_runtime_2026-05-19.md`](archive/blueprint_run_mcp_runtime_2026-05-19.md)

## Fast Handoff - 2026-05-19 Blueprint Header Status + IPC Restart

When the next task is GuLiCode blueprint header status, persistence errors, or
desktop IPC mismatch debugging, start from this state:

1. The blueprint header persistence area is now expandable. Loading/saving
   remain compact one-line states; errors open a popover with the full message.
2. This was added after the header showed a truncated
   `blueprint-configure-runtime` IPC error. The expanded message confirmed a
   main/preload mismatch:
   `No handler registered for 'blueprint-configure-runtime'`.
3. The source already has the handler in
   `GuLiCode/packages/desktop-electron/src/main/ipc.ts`. If the error appears
   again after IPC/preload edits, restart the whole Electron main process;
   reloading only the renderer is not enough.
4. The latest clean restart reached renderer `http://localhost:5173/` and
   sidecar `http://127.0.0.1:5337`, with logs at
   `GuLiCode/logs/gulicode-desktop-restart-20260519-122112.log` and matching
   `.err.log`.

Latest relevant verification:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\app
bun test --preload ./happydom.ts ./src/pages/session/blueprint-side-panel.test.ts
bun test --preload ./happydom.ts ./src/i18n/parity.test.ts
bun run typecheck
bun run build
```

Detailed archive:

- [`archive/blueprint_header_status_debug_restart_2026-05-19.md`](archive/blueprint_header_status_debug_restart_2026-05-19.md)

## Fast Handoff - 2026-05-19 Blueprint Python Detection + Config UX

When the next task is GuLiCode blueprint startup, Python interpreter setup, or
common config UI, start from this state:

1. `python_path` is now part of blueprint common config. It is required before
   start, validated as an absolute path, and checked in both renderer and
   desktop service start paths.
2. The common config panel includes a `Python interpreter` field with a file
   picker and a visible Detect button. Detect validates the current input first,
   then falls back through the runtime detection order.
3. Runtime Python resolution order is:
   configured `python_path`, `GULICODE_PYTHON`, `python`, `python3`, Windows
   `py -3`, then project/package `.venv`.
4. Detection runs Python with `-c "import sys; print(sys.executable)"` and only
   writes a verified absolute `sys.executable` back into the UI.
5. The renderer also auto-detects Python during common-config backfill and just
   before blueprint start. If detection fails, the field stays red and the
   config-required dialog remains the blocking path.
6. The common config panel lives next to Add Node in the toolbar, opens and
   collapses by click, scrolls vertically, and is widened to `360px`.
7. Electron IPC/preload/platform now includes `blueprint-detect-python` and
   `blueprint-configure-runtime`. Restart any already running debug Electron
   window after this change because main/preload IPC changed.
8. Adjacent local path cleanup is included: `dev-desktop.ts` uses
   electron-builder cache env vars / `LOCALAPPDATA` first, and examples no
   longer use local `F:/src` paths.

Latest relevant verification:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\app
bun test --preload ./happydom.ts ./src/pages/session/blueprint-model.test.ts ./src/pages/session/blueprint-side-panel.test.ts ./src/i18n/parity.test.ts
bun run typecheck
bun run build

cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\desktop-electron
bun test ./src/main/blueprint-runtime.test.ts ./src/main/ipc-blueprint-runtime.test.ts
bun run typecheck
bun run build

cd F:\src\Package\Script\Python\multi_agent_tcp
pytest -q test_desktop_blueprint_service.py
python -m py_compile desktop_blueprint_service.py cluster.py
```

Detailed archive:

- [`archive/blueprint_python_detection_config_2026-05-19.md`](archive/blueprint_python_detection_config_2026-05-19.md)

## Fast Handoff - 2026-05-19 Blueprint Common Config + Private Runtime

When the next task is GuLiCode blueprint startup, local path handling, or
desktop live runtime smoke, start from this state:

1. Do not reintroduce hard-coded user-machine absolute paths in code defaults.
   The blueprint common config panel owns local-only paths:
   `project_workdir`, `skill_dir`, and `rule_dir`.
2. `project_workdir` is always required before start and must be an absolute
   path. `skill_dir` is required only when Agents use skills. `rule_dir` is
   required only when Agents have rule files. Any non-empty optional path must
   also be absolute.
3. The common config panel fields now have `?` help buttons using the same
   popover interaction as the inspector. Startup failure shows a blocking
   config-required dialog with a single confirm action.
4. Rule catalog values are now filenames relative to the configured `rule_dir`,
   so Agent `rule_paths` no longer store user-machine absolute paths from the
   selector. The desktop service resolves them from common `rule_dir` at start.
5. The desktop service also validates common config during `blueprint.start`,
   so IPC/direct service calls cannot bypass the renderer guard.
6. Desktop live mode uses the framework-managed private Agent context:
   `GraphRuntime(enforce_private_agent_context=True)`, private checkout cwd,
   private `CODEX_HOME`, `framework-agent-runtime`, `AGENTS.md`, Workspace API
   env/prompt context, and authorized skill/rule materialization.
7. The previous backend risk is closed: non-overlapping same-file checkout
   submits are accepted even when Dulwich is unavailable or reports a false
   conflict, while real same-region conflicts still return structured
   `conflict` results.

Latest relevant verification:

```powershell
cd GuLiCode\packages\app
bun test --preload ./happydom.ts ./src/pages/session/blueprint-model.test.ts ./src/pages/session/blueprint-side-panel.test.ts ./src/i18n/parity.test.ts
bun run typecheck
bun run build

cd ..\desktop-electron
bun test ./src/main/blueprint-catalog.test.ts ./src/main/ipc-blueprint-runtime.test.ts ./src/main/blueprint-runtime.test.ts
bun run typecheck
bun run build

cd ..\..\..
pytest -q test_desktop_blueprint_service.py
pytest -q test_workspace_manager.py
pytest -q test_desktop_blueprint_service.py test_workspace_manager.py
```

Detailed archive:

- [`archive/blueprint_common_config_paths_2026-05-19.md`](archive/blueprint_common_config_paths_2026-05-19.md)

## Fast Handoff - 2026-05-18 Blueprint Agent Panel + Debug Baseline

When the next task is GuLiCode blueprint UI or desktop debug startup, start
from this state:

1. The Agent information panel no longer opens by hover. It opens by left
   mouse long-press on Agent nodes with a `500ms` circular progress ring, or
   through the Agent node right-click menu item `信息面板` / `Info panel`.
2. Long-press cancels when pointer movement reaches `8px`; `pointercancel`,
   canvas click, port interactions, and connection drag clear pending
   long-press state.
3. Agent information panels are movable and resizable. Drag the title area to
   move; drag the bottom-right handle to resize. Default size is `374 x 410`,
   minimum size is `320 x 300`. Opening still tries to place the panel in view,
   but drag updates are no longer clamped, so panels can be moved partly out of
   the canvas. Panel body text is selectable and the body scrolls with wheel.
4. Existing panel behavior remains: close, pin, multiple pinned panels,
   non-pinned outside-click close, stream transcript, `default/top` sends, and
   read-only static display when no live run exists.
5. The Add Node menu includes a Test Agent preset for Agent information panel
   smoke/debug work. The special test-only right-click `Start test` action was
   removed; test nodes now use the normal blueprint runtime start path.
6. Test Agent panels persist a realtime JSON v2 snapshot and show its path in
   the panel. Use the single fixed file
   `%APPDATA%\ai.opencode.desktop.dev\logs\agent-info-panel-tests\agent-panel-test.json`.
   Desktop startup and `blueprint-start` clear the directory; later panel
   persists overwrite the same file and remove obsolete timestamped snapshots.
   The v2 payload keeps only `agentReplies`, `userMessages`, and
   `frameworkMessages`; it does not write raw `node`, `panel`, `runtime`, or
   `streamEvents` objects.
7. Panel-sent user messages are recorded in `payload.userMessages` with
   `runtimeMessageId`, lifecycle status (`queued`, `sent`, `dispatching`,
   `running`, `succeeded`, `failed`), timestamps, and error text when present.
   `sent` only means IPC queue acceptance; final success/failure comes from
   stream events or recent runtime events.
8. Test Codex nodes set/backfill `skip_git_repo_check: true` to avoid the
   `C:\` trusted-directory smoke failure. Runtime run-list status is merged from
   `status.run`, so snapshots do not report stale `running` after cancel, fail,
   or complete.
9. The latest desktop debug start used `GuLiCode/logs/gulicode-desktop-direct.log`;
   it reached `server ready` with renderer `http://localhost:5173/` and sidecar
   `http://127.0.0.1:9766`.
10. The code-level debug cleanup in this pass covers `blueprint-list-models`
   Windows spawn/`EPERM` handling, DnD cleanup warnings, stale PTY WebSocket
   errors, and Solid SVG computation warnings.
11. Current stream priority is Codex-first. If Agent output still appears
   non-streaming, first verify the blueprint uses `cli_kind=codex`, then inspect
   WebSocket lifetime/cursor handling and Codex JSONL event mapping. Do not
   chase CodeMaker streaming for this project phase unless explicitly asked.
12. Highest next priority: desktop blueprint `live` runs are currently starting
    ordinary and Test Agents as raw CLI workers before `GraphRuntime` can
    materialize the framework-managed private context. Fix the desktop live
    startup path so it uses `GraphRuntime(enforce_private_agent_context=True)`,
    private checkout/CODEX_HOME, `framework-agent-runtime`, `AGENTS.md`,
    Workspace API context, and authorized skill/rule materialization before
    doing more Agent panel polish.

Latest relevant verification:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\app
bun test --preload ./happydom.ts ./src/pages/session/blueprint-model.test.ts ./src/pages/session/blueprint-side-panel.test.ts
bun run typecheck
bun run build

cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\desktop-electron
bun test ./src/main/ipc-blueprint-runtime.test.ts
bun run typecheck
bun run build
```

Detailed archive:

- [`archive/agent_info_panel_interaction_2026-05-18.md`](archive/agent_info_panel_interaction_2026-05-18.md)
- [`archive/agent_info_panel_test_node_json_2026-05-18.md`](archive/agent_info_panel_test_node_json_2026-05-18.md)
- [`archive/agent_info_panel_stream_private_context_2026-05-18.md`](archive/agent_info_panel_stream_private_context_2026-05-18.md)

## Fast Handoff - 2026-05-15 Real Codex Framework Flow Baseline

When the next task touches Codex AgentNode private context, Workspace API,
or framework-owned checkout/submit/archive behavior, start from this state:

1. The real Codex framework-flow baseline is now covered by
   `test_agent_runtime.py::test_real_codex_cli_framework_private_checkout_submit_and_archive_flow`.
   It uses real `CLIWorkerBackend.create(...)`, broker/worker subprocesses,
   `GraphRuntime(enforce_private_agent_context=True)`, `WorkspaceRPCServer`,
   and real `codex exec`; there is no fake Codex and no `RUN_REAL_CODEX`
   environment gate. If `codex` is absent, it skips like the existing smoke
   tests.
2. The framework path now seeds private `CODEX_HOME` with only Codex runtime
   state files (`config.toml`, `auth.json`, `models_cache.json`) while
   re-materializing authorized framework/business skills into the private
   home. Do not go back to an empty private `config.toml`; real `codex exec`
   can fail before tool execution when auth/provider config is missing.
3. `workspace_api checkout --path ...` is expected to work when launched from
   inside the agent private checkout. `workspace_manager._copy_project_tree`
   and checkout refresh paths preserve the checkout directory itself and clear
   contents, avoiding Windows cwd deletion failures (`WinError 32`).
4. `WorkspaceRPCServer` now records each Workspace API request as a
   `workspace_api_call` manifest entry with `workspace_event =
   "WorkspaceAPICalled"`. The real Codex baseline also asserts Codex JSONL
   `command_execution` entries for checkout/status/diff/submit/publish and
   guards that the project file is still unchanged immediately before
   framework `submit`; this closes the old gap where a direct project write
   could look like a valid accepted changeset after the fact.
5. Direct-write negative coverage exists in
   `test_real_codex_cli_framework_blocks_direct_project_and_shared_writes`.
   It exposes the physical project file and temporary shared report path to
   real Codex and asks for direct shell writes without `workspace_api`; the
   writes are blocked by the Codex `workspace-write` sandbox, while a private
   checkout write still succeeds.
6. Blocked-write recovery coverage exists in
   `test_real_codex_cli_framework_recovers_from_blocked_direct_write`. It asks
   real Codex to try a direct project write, observes the sandbox block, and
   then complete the same turn through checkout/status/diff/submit/publish.
   The submit-time guard verifies the project file is still base content until
   Workspace API submit applies the accepted changeset.
7. Broker and worker subprocesses receive the package parent on `PYTHONPATH`,
   so spawned `python -m multi_agent_tcp.workspace_api ...` commands work when
   tests or runtime start from the package directory.
8. Codex timeout diagnostics now preserve JSONL events, partial stdout/stderr,
   elapsed time, and last-message/final-text extraction, which is important
   when real CLI behavior changes.
9. Worker replies with `body.ok == false` now fail the current GraphRuntime
   message/job, not the reusable agent binding. Blocking AgentNode messages
   raise, record `framework.message.failed`, leave `last_error`, and return
   the AgentInstance to `idle` so a later message can retry or continue.
   Nonblocking jobs emit `TaskFailed`. This covers Codex/model stream failures
   such as `stream disconnected before response.completed`. A sandbox-denied
   shell write is different: if Codex catches the denial, recovers through
   Workspace API, and exits with `ok == true`, the task continues.
10. On Windows, the real integration test overrides Codex to
   `windows.sandbox="unelevated"` to avoid the elevated sandbox helper
   intermittently hanging or failing under multiple tool launches.

Latest relevant verification:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp
pytest -q test_agent_runtime.py::test_real_codex_cli_framework_private_checkout_submit_and_archive_flow -vv
pytest -q test_agent_runtime.py::test_real_codex_cli_framework_blocks_direct_project_and_shared_writes -vv
pytest -q test_agent_runtime.py::test_real_codex_cli_framework_recovers_from_blocked_direct_write -vv
pytest -q test_workspace_api.py::test_workspace_api_rpc_checkout_submit test_agent_runtime.py::test_real_codex_cli_framework_private_checkout_submit_and_archive_flow -vv
pytest -q test_agent_runtime.py::test_graph_runtime_keeps_agent_idle_after_worker_ok_false test_agent_runtime.py::test_nonblocking_agent_job_fails_on_worker_ok_false -vv
pytest -q test_agent_runtime.py::test_initialize_private_codex_home_seeds_runtime_state_only test_agent_runtime.py::test_graph_runtime_private_context_materializes_codex_skill_and_rules test_workspace_manager.py::test_checkout_refresh_works_when_process_cwd_is_checkout_dir test_workspace_manager.py::test_checkout_refresh_preserves_framework_agents_md test_workspace_manager.py::test_project_reference_checkout_fetches_specific_paths_and_submits_to_project -vv
python -m py_compile agent_launch_context.py workspace_manager.py cluster.py codex_bridge.py workspace_rpc.py graph_runtime.py test_agent_runtime.py test_workspace_api.py test_workspace_manager.py
```

Real Codex tests depend on the external Codex/model stream. If a combined run
fails with `stream disconnected before response.completed`, rerun the single
target before treating it as a framework regression.

## Fast Handoff - 2026-05-14 Blueprint UI + Config Boundary

When the next task is blueprint UI or GuLiCode desktop bring-up, start here:

1. Read `tasks/current_goals.md` first, then `tasks/guli_desktop_ui_tasks.md`.
2. For current UI behavior, inspect:
   - `GuLiCode/packages/app/src/pages/session/blueprint-model.ts`
   - `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.tsx`
   - `GuLiCode/packages/app/src/pages/session/blueprint-model.test.ts`
   - `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.test.ts`
   - `GuLiCode/packages/app/src/context/platform.tsx`
   - `GuLiCode/packages/desktop-electron/src/main/blueprint-catalog.ts`
   - `GuLiCode/packages/desktop-electron/src/main/blueprint-catalog.test.ts`
   - `GuLiCode/packages/desktop-electron/src/main/ipc.ts`
   - `GuLiCode/packages/desktop-electron/src/preload/index.ts`
   - `GuLiCode/packages/desktop-electron/src/preload/types.ts`
3. The local draft workbench is already runtime-shaped enough to emit
   `{ terminal_nodes, agent_nodes, route_nodes, edges }`. It has route nodes,
   port-aware edges, add-node dropdown/drop-to-canvas, node ports, right-click
   canvas pan, node context menu, double-click inspector, keyboard deletion,
   grid snapping, expanded Agent/Route/Terminal/Edge inspector fields,
   per-field inspector tip buttons, and the current dark/technology/minimal
   visual pass. Inspector labels, "?" buttons, select options, and
   `nonblocking` / `非阻塞` text are expected to stay legible on the dark
   panel background.
4. The blueprint config boundary has been adjusted:
   - The top-left canvas panel is the user-facing "blueprint common config".
     It owns `project_workdir`, `skill_dir`, and `rule_dir`.
   - Default `skill_dir` is
     `F:\src\Package\Script\Python\multi_agent_tcp\skill_list`.
   - `project_workdir` defaults to the currently opened project directory and
     is written into each AgentNode `cwd` only during runtime draft export.
   - The Agent inspector no longer exposes framework-managed fields:
     `cwd`, `read_scope`, `write_scope`, `artifact_scope`, `workspace_id`,
     `workspace_root`, editable `command`, or raw `skill_selection`.
   - `command` is framework-generated from `cli_kind`
     (`codemaker -> codemaker`, `codex -> codex`).
   - `skills` and `rule_paths` are multi-select dropdowns fed by the selected
     skill/rule directories. Selected skills are exported both as `skills` and
     as `skill_selection: { mode: "selected", skill_hashes: [...] }`; no
     selected skill exports `skill_selection: { mode: "none" }`.
   - `cli_kind` is a dropdown for `codemaker` / `codex`. Switching CLI refreshes
     model choices through Electron IPC: `codemaker models netease-codemaker`
     line output or `codex debug models` JSON `models[].slug`.
   - `adapter_options` stays as an advanced JSON escape hatch for low-level
     CLI adapter arguments, such as Codex sandbox/config/extra_args or
     CodeMaker base_args. Normal users usually leave it empty.
5. Do not reintroduce the old toolbar "connect" button or the old toolbar
   delete button. Connections are made by dragging from output ports to input
   ports. Deletion is node context menu, selected edge inspector action, or
   `Backspace` / `Delete`.
6. The next real milestone is not more renderer scheduling logic. Extend the
   current Electron/preload boundary beyond catalog/model lookup into
   blueprint persistence and `GraphRuntimeControlPlane` / `GraphRuntime`
   start/status/end, then project runtime status back into the panel.

Quick verification commands:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\app
bun test --preload ./happydom.ts ./src/pages/session/blueprint-model.test.ts ./src/pages/session/blueprint-side-panel.test.ts
bun run build

cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\desktop-electron
bun test ./src/main/blueprint-catalog.test.ts
bun run build
```

## GuLiCode Packaging Fast Path

Read this before packaging on Windows.

1. For the normal unpacked smoke path, prefer:

```powershell
F:\src\Package\Script\Python\multi_agent_tcp\start-gulicode-desktop.cmd --packaged
```

2. For the full desktop package flow:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\desktop-electron
bun run build
bun run package:win
```

3. If `bun run package:win` fails while extracting `winCodeSign-2.6.0.7z`
   because Windows denies symlink creation for the bundled `darwin/10.12`
   libraries, do not chase app code. Use the documented local workaround:
   create a temporary `electron-builder.local.config.ts` that imports the base
   config, sets `win.signAndEditExecutable = false`, and runs cached `rcedit`
   in `afterPack` to apply `resources/icons/icon.ico` to the final exe.

```powershell
$rceditDir = (Get-ChildItem $env:LOCALAPPDATA\electron-builder\Cache\winCodeSign -Directory |
  Where-Object {
    (Test-Path (Join-Path $_.FullName 'rcedit-x64.exe')) -and
    (Test-Path (Join-Path $_.FullName 'rcedit-ia32.exe'))
  } | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName

$env:CSC_IDENTITY_AUTO_DISCOVERY = 'false'
$env:ELECTRON_BUILDER_RCEDIT_PATH = $rceditDir
bunx electron-builder --win --config electron-builder.local.config.ts
```

4. If packaging fails while clearing `dist/win-unpacked` with an access-denied
   error on `d3dcompiler_47.dll`, close or kill old `GuLiCode Dev.exe`
   processes that are running from `dist/win-unpacked`, then rerun the same
   workaround command.

5. Delete the temporary local config after packaging. Expected outputs are:

```text
GuLiCode/packages/desktop-electron/dist/opencode-electron-win-x64.exe
GuLiCode/packages/desktop-electron/dist/opencode-electron-win-x64.exe.blockmap
GuLiCode/packages/desktop-electron/dist/win-unpacked/GuLiCode Dev.exe
```

If the unpacked exe icon looks wrong, patch it directly with cached `rcedit`
and rebuild the installer with the `afterPack` hook. See
`knowledge_base/gulicode_desktop.md` and `knowledge_base/guli_desktop_ui.md`
for the full packaging/icon notes.

## GuLiCode Debug Startup Fast Path

Use this when the user asks to launch the desktop app with visible runtime
errors, or after packaging/dev startup reports noisy or unclear output. Keep
`DEBUG` unset unless explicitly investigating Vite/Babel internals; `DEBUG=*`
will flood the terminal with transformer traversal logs.

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\desktop-electron
$env:ELECTRON_ENABLE_LOGGING = '1'
$env:ELECTRON_ENABLE_STACK_DUMPING = '1'
Remove-Item Env:\DEBUG -ErrorAction SilentlyContinue
bun run dev
```

If a previous debug window used `DEBUG=*`, close that old PowerShell window
before starting this cleaner session so logs and dev ports do not mix.

## Document Layout

### 1. `SKILL.md`

This file is only the high-level navigation and maintenance policy. Do not put long module details here.

### 2. `多agents通信设计.md`

Primary design document for top-agent governance and multi-agent communication.

Read first when the user asks about:

- GuLiCode as global coordinator / top Agent
- multi-agent communication
- ordinary Agent message dispatch
- start/status/end runtime interfaces
- required outgoing targets
- fan-out and fan-in
- join aggregation
- top-agent rule / skill / profile

### 3. `environment_setup.md`

Current local environment setup and diagnostics for this machine.

Read first when the user asks about:

- dependency setup or environment repair
- Python/Bun/Codex executable paths and versions
- PowerShell script policy or generated `multi-agent-tcp.exe` launch issues
- system proxy / `NO_PROXY` bypass for localhost MCP `502` / `503` failures
- repo-local `skill_list` initialization

### 4. `knowledge_base/`

Stable current knowledge. Prefer these files for implementation decisions:

- [`knowledge_base/core_architecture.md`](knowledge_base/core_architecture.md): current architecture centered on GuLiCode, `GraphRuntimeControlPlane`, `GraphRuntime`, workspace/events, and CLI backend adapters.
- [`knowledge_base/gulicode_desktop.md`](knowledge_base/gulicode_desktop.md): desktop shell source structure, one-click startup, packaged launch, Electron/Tauri path choice, and shell/runtime layering.
- [`knowledge_base/guli_desktop_ui.md`](knowledge_base/guli_desktop_ui.md): Guli productization, desktop UI ownership, blueprint entry embedding, branding, icon pipeline, and workbench integration rules.
- [`knowledge_base/dispatch_workflows.md`](knowledge_base/dispatch_workflows.md): runtime control-plane CLI/RPC workflows, legacy dispatch notes, and thin-client boundaries.
- [`knowledge_base/ring_structure_solution.md`](knowledge_base/ring_structure_solution.md): current cycle-structure closure: cycles are observable SCC groups only; runtime uses normal dispatch and join semantics.
- [`knowledge_base/cluster_api.md`](knowledge_base/cluster_api.md): legacy `CodeMakerCluster` compatibility and preferred `CLIWorkerBackend` terminology.
- [`knowledge_base/registry_and_skills.md`](knowledge_base/registry_and_skills.md): registry, skill selection, and catalog injection.
- [`knowledge_base/runtime_notes.md`](knowledge_base/runtime_notes.md): encoding, logs, process cleanup, retry, and CLI runtime pitfalls.
- [`knowledge_base/multi_cli_workflow.md`](knowledge_base/multi_cli_workflow.md): CLI adapter/backend history and still-relevant adapter constraints.

### 5. `tasks/`

Short-term work. Prefer current files in this order:

- [`tasks/current_goals.md`](tasks/current_goals.md): current active priorities.
- [`tasks/guli_desktop_ui_tasks.md`](tasks/guli_desktop_ui_tasks.md): Guli desktop UI productization and blueprint embedding tasks.
- [`tasks/multi_agent_communication_tasks.md`](tasks/multi_agent_communication_tasks.md): GuLiCode top Agent, runtime control, message staging, joins, and framework-owned communication.
- [`tasks/node_runtime_tasks.md`](tasks/node_runtime_tasks.md): GraphRuntime / graph scheduling implementation tasks.
- [`tasks/multi_cli_adapter_tasks.md`](tasks/multi_cli_adapter_tasks.md): CLI backend adapter work, secondary to runtime/control-plane work.

### 6. `archive/`

Historical change records only. Do not use archive content as current behavior unless a current knowledge document points to it.

- [`archive/guli_desktop_ui_archive.md`](archive/guli_desktop_ui_archive.md)
- [`archive/blueprint_integration_archive.md`](archive/blueprint_integration_archive.md)
- [`archive/blueprint_full_mcp_control_real_smoke_2026-05-19.md`](archive/blueprint_full_mcp_control_real_smoke_2026-05-19.md)
- [`archive/blueprint_run_mcp_runtime_2026-05-19.md`](archive/blueprint_run_mcp_runtime_2026-05-19.md)
- [`archive/agent_info_panel_live_runtime_2026-05-18.md`](archive/agent_info_panel_live_runtime_2026-05-18.md)
- [`archive/agent_info_panel_interaction_2026-05-18.md`](archive/agent_info_panel_interaction_2026-05-18.md)
- [`archive/agent_info_panel_markdown_longpress_2026-05-20.md`](archive/agent_info_panel_markdown_longpress_2026-05-20.md)
- [`archive/agent_info_panel_test_node_json_2026-05-18.md`](archive/agent_info_panel_test_node_json_2026-05-18.md)
- [`archive/blueprint_header_status_debug_restart_2026-05-19.md`](archive/blueprint_header_status_debug_restart_2026-05-19.md)
- [`archive/gulicode_runtime_baseline_archive.md`](archive/gulicode_runtime_baseline_archive.md)
- [`archive/agents_architecture_archive.md`](archive/agents_architecture_archive.md)
- [`archive/ring_runtime_closure_archive.md`](archive/ring_runtime_closure_archive.md)
- [`archive/ring_session_runtime_archive.md`](archive/ring_session_runtime_archive.md)

## Query Map

- Local environment setup, dependency repair, Python interpreter detection,
  PowerShell/Codex command quirks, localhost MCP `502` / `503` failures, system
  proxy, `NO_PROXY`, and repo `skill_list`: read `environment_setup.md`.
- GuLiCode desktop startup, one-click launcher, packaged bring-up, taskbar icon, and direct Electron fallback: read `knowledge_base/gulicode_desktop.md`.
- Guli productization, desktop UI ownership, branding, icon replacement, empty-state wording, blueprint entry placement, and blueprint workbench embedding: read `knowledge_base/guli_desktop_ui.md`, then `tasks/guli_desktop_ui_tasks.md`.
- Blueprint Agent information panel interactions, long-press progress, Markdown reply rendering, context-menu entry, move/resize behavior, Test Agent JSON snapshots, user-message capture, and clean desktop debug baseline: read `archive/agent_info_panel_markdown_longpress_2026-05-20.md`, then `archive/agent_info_panel_interaction_2026-05-18.md`, then `archive/agent_info_panel_test_node_json_2026-05-18.md`, then `tasks/current_goals.md`.
- GuLiCode top Agent, organization view, top-agent profile, start plan, status explanation: read `多agents通信设计.md`, then `tasks/multi_agent_communication_tasks.md`.
- Runtime start/status/end, organization, message batch, agent dispatch, join-create/join-contribute: read `knowledge_base/dispatch_workflows.md`.
- Current architecture or component ownership: read `knowledge_base/core_architecture.md`.
- `GraphDefinition.agent_cycle_groups()` (exec-edge SCCs, agent-only groups, cycles through `RouteNode`): read `knowledge_base/core_architecture.md` (section *GraphDefinition: agent cycle groups*).
- Cycle / 环状结构 handling: read `knowledge_base/ring_structure_solution.md`, then `knowledge_base/core_architecture.md` and `knowledge_base/dispatch_workflows.md`. Cycle detection is observability only, not a scheduling entry point.
- Legacy `CodeMakerCluster`, `run_parallel`, `run_chain`, broker/TCP worker path: read `knowledge_base/cluster_api.md`.
- Registry, skills, per-agent skill selection: read `knowledge_base/registry_and_skills.md`.
- Workspace API, changesets, archive, private checkout, conflict flow: read `knowledge_base/core_architecture.md` and `tasks/multi_agent_communication_tasks.md`.
- Multi CLI adapters, Codex/CodeMaker process adapters, `CLIAdapter`: read `knowledge_base/multi_cli_workflow.md`, but keep the `CLIWorkerBackend` adapter boundary in mind.

## Maintenance Rules

- Current effective knowledge belongs in `knowledge_base/`.
- Short-term priorities and checklists belong in `tasks/`.
- Historical migration notes belong in `archive/`.
- Do not restore old "Cursor/CodeMaker TCP orchestration" framing as the skill center.
- Do not restore the retired Ryven/editor UI line as the current product priority unless the user explicitly asks for it.
- When documenting backend execution, prefer `CLIWorkerBackend`; mention `CodeMakerCluster` only as a compatibility alias.
- When documenting user-facing orchestration, prefer GuLiCode desktop, blueprint embedding, top Agent, and framework-owned runtime APIs.
- When startup notes disagree, prefer `start-gulicode-desktop.cmd`, `start-gulicode-desktop.sh`, `bun run desktop`, and `GuLiCode/scripts/dev-desktop.ts` over older raw `bun --cwd packages/desktop-electron dev` notes.
- When copying into `KM_docs/skills-snapshot`, mirror the current skill tree so removed legacy UI docs also disappear from the snapshot.

## Repository Link

- GitHub: <https://github.com/QHXRPG-A/multi_agent_tcp>
- Current common local root: `F:\src\Package\Script\Python\multi_agent_tcp`
