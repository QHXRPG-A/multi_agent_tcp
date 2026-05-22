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

## Fast Handoff - 2026-05-22 Agent Task Panel + Auto Top Summary

When the next task is Agent information panel status display, task completion
visibility, run summary readiness, or automatic Top Agent summary behavior,
start from this state:

1. Agent lifecycle state and Agent task status are intentionally separate.
   `idle` means the AgentNode is available for another framework message;
   `task_status=completed|blocked|needs_input|failed` means the current run
   task has reached a terminal outcome.
2. The Agent information panel top metric strip now displays both `状态` and
   `任务状态`. The detail expander also shows task message id and task summary
   when available.
3. `AgentInfoPanel` resolves task status first from the latest
   `agent.task_status` stream event, then from status/runtime fields.
4. `RunReadyForTopAgentSummary` / `run.ready_for_top_agent_summary` remains a
   backend readiness signal. The backend does not create a separate bottom Top
   Agent worker.
5. GuLiCode desktop/current chat session is the Top Agent. The frontend now
   bridges summary readiness into that main `blueprintPlanning` composer path.
6. On `ready_for_top_agent_summary === true`, `BlueprintSidePanel`
   automatically submits a Top Agent summary request containing run id,
   generation, and per-AgentNode task statuses.
7. The automatic request tells Top Agent to use
   `framework_control_runtime_status`,
   `framework_control_top_agent_explain_status`, and
   `framework_control_top_agent_utterances`; it also says not to stage a new
   plan or start a new run.
8. Automatic requests are deduplicated by `runId + summary generation`.
9. If the main composer is busy or already has draft/context content, the
   auto-submit uses `silentBlocked` and retries later instead of showing repeat
   toasts.
10. Blueprint popout forwarding and Electron preload types carry
    `silentBlocked` so popout-submitted automatic requests behave the same as
    sidebar requests.
11. The runtime ready banner now says a Top Agent summary is being requested,
    not merely that a summary is possible.

Latest relevant verification:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\app
bun test --preload ./happydom.ts ./src/pages/session/blueprint-side-panel.test.ts ./src/pages/session/blueprint-planning-session.test.ts
bun run typecheck

cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\desktop-electron
bun run typecheck
bun test ./src/main/ipc-blueprint-runtime.test.ts

cd F:\src\Package\Script\Python\multi_agent_tcp
git diff --check -- GuLiCode/packages/app/src/pages/session/blueprint-side-panel.tsx GuLiCode/packages/app/src/pages/session.tsx GuLiCode/packages/app/src/context/platform.tsx GuLiCode/packages/app/src/pages/session/session-side-panel.tsx GuLiCode/packages/desktop-electron/src/preload/types.ts GuLiCode/packages/app/src/i18n/en.ts GuLiCode/packages/app/src/i18n/zh.ts GuLiCode/packages/app/src/i18n/zht.ts GuLiCode/packages/app/src/pages/session/blueprint-side-panel.test.ts GuLiCode/packages/app/src/pages/session/blueprint-planning-session.test.ts
```

Observed result: app source tests passed with 13 passed and 342 assertions;
app typecheck passed; desktop Electron typecheck passed; desktop IPC tests
passed with 2 passed and 25 assertions; `git diff --check` reported only CRLF
conversion warnings.

Current follow-ups:

1. Manual smoke a fresh live fan-out run and confirm the Top Agent summary
   request appears in the main desktop session without clicking runtime
   `完成`.
2. Verify the silent retry path by keeping text in the main composer until
   summary readiness, clearing it, and confirming the auto-summary request is
   later submitted.
3. Decide whether a completed Top Agent summary should optionally auto-end the
   run through `runtime_end("complete")`; current behavior only requests the
   summary and leaves final closure deliberate.

Detailed archive:

- [`archive/blueprint_agent_task_panel_auto_top_summary_2026-05-22.md`](archive/blueprint_agent_task_panel_auto_top_summary_2026-05-22.md)

## Fast Handoff - 2026-05-22 Runtime Completion, Demux, And Workspace Panels

When the next task is concurrent agent replies, runtime workspace status,
AgentNode task completion, idle summary prompts, start-node coverage, or the
runtime workspace/events side panel, start from this state:

1. `AgentTCPClient.wait_for_message(expect_from=...)` now demuxes through a
   private inbox. Concurrent worker replies can arrive out of order without one
   waiter consuming another sender's final reply.
2. `agent.stream` events remain non-final and are only consumed by the waiter
   for the matching sender. `incoming()` also uses the same inbox.
3. Live `GraphRuntime` workspace snapshots hydrate from the active run
   workspace (`archive_run` first, `private_context_run` fallback) and enumerate
   actual reports, artifacts, accepted changesets, directories, and absolute
   paths.
4. `DesktopBlueprintService` binds live runtime status/final report projection
   to the same archive run workspace used by the run.
5. The runtime workspace metrics are interactive: left click opens a canvas
   floating content panel; right click opens the category directory in
   Explorer; item right click reveals the item path.
6. Electron/platform now includes `revealPathInFileManager(path)` backed by
   `shell.showItemInFolder(path)`.
7. The runtime events panel has a height slider and compact event rows.
8. Agent info tool groups label and color tool categories separately for MCP,
   command/shell execution, and Codex/internal activity.
9. Ordinary MCP includes `agent_task_status`, scoped to the current ordinary
   token and active message/batch context.
10. Each AgentNode tracks `has_received_flow`, `idle_since`, current
   `task_status`, summary prompt state, and summary data. New message flow
   resets terminal status back to `working`.
11. After flowed-to agents sit idle for 30 seconds without a terminal task
   status, the framework queues one `framework_summary_request` asking the
   agent to summarize its own current task.
12. Ring agents use the same completion semantics, with the extra requirement
   that their circulation-count dict must be empty or all zero before the idle
   prompt timer can qualify.
13. Start validation computes source SCC groups from the Agent exec graph.
   Each source group requires exactly one selected start node; isolated agents
   are their own groups and source rings allow any one member.
14. When all expected AgentNodes have received flow and are terminal, with no
   visible pending runtime work or conflicts, `GraphRuntime` emits
   `RunReadyForTopAgentSummary` and stream
   `run.ready_for_top_agent_summary`.

Latest relevant verification:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp
python -m py_compile graph_runtime.py graph_control.py blueprint_mcp_runtime.py agent_launch_context.py desktop_blueprint_service.py test_agent_runtime.py test_desktop_blueprint_service.py
pytest -q test_agent_runtime.py -k "not real_codex"
pytest -q test_desktop_blueprint_service.py
git diff --check

cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\app
bun test --preload ./happydom.ts ./src/pages/session/blueprint-side-panel.test.ts ./src/i18n/parity.test.ts
bun run typecheck
```

Observed result: py_compile passed; runtime tests passed with 90 passed and 3
deselected; desktop service tests passed with 34 passed, 1 skipped, and 2
warnings; app tests passed with 13 passed; app typecheck passed; `git diff
--check` reported only CRLF conversion warnings. A combined full pytest command
timed out after five minutes and hit a Windows terminal flush `OSError`, so the
runtime and desktop suites were verified separately.

Current follow-ups:

1. Manual desktop smoke a fan-out blueprint through task-status completion and
   top-agent summary-ready emission.
2. Manual ring smoke: verify circulation counts hit zero before the idle
   summary prompt can fire.
3. Re-test command execution failures that show
   `CreateProcessWithLogonW failed: 1326` with known-good Windows credentials
   or without the alternate-logon path.
4. Decide whether runtime event panel height should persist per session.

Detailed archive:

- [`archive/blueprint_runtime_completion_demux_workspace_2026-05-22.md`](archive/blueprint_runtime_completion_demux_workspace_2026-05-22.md)

## Fast Handoff - 2026-05-21 Blueprint Popout Window + Endpoint Visibility

When the next task is blueprint window behavior, sidebar docking, Electron
window lifecycle, or canvas endpoint visibility, start from this state:

1. Blueprint "drag out" is a real independent Electron `BrowserWindow`, not an
   in-app fixed overlay. The old `data-blueprint-floating-panel` path in
   `session.tsx` is removed.
2. Embedded sidebar blueprint title-bar dragging calls
   `platform.openBlueprintWindow(projectDir, sessionId, rect)` after the
   threshold and marks the session blueprint panel as `floating` so the right
   side panel no longer occupies layout width.
3. The popout renderer uses the normal app provider stack without the visual
   app shell through `AppInterface visualShell={false}` and the dedicated
   route `/:dir/blueprint-window/:id?`.
4. Electron `windows.ts` owns popout lifecycle with `blueprintWindowContexts`.
   Popouts are de-duplicated by `projectDir + sessionId`; drag-out focuses an
   existing matching popout.
5. The popout keeps the "dock back to sidebar" button. Docking sends
   `blueprint-window-dock-request` to the main renderer, focuses the main
   window, and closes the popout without also emitting the normal close event.
6. Closing the popout sends `blueprint-window-closed`; the main session clears
   the blueprint floating/open state.
7. Popout runtime task submit is forwarded to the main session through
   `blueprint-window-submit-planning`, then the main chat blueprint-planning
   handoff accepts or rejects it.
8. Node port visibility is edge-directed: no incoming edge hides the input
   port by default, and no outgoing edge hides the output port by default.
   Hover, selected state, and active connection drag reveal the necessary
   ports for editing.
9. Use the Electron dev server that was relaunched after this pass:
   renderer `http://localhost:5173/`, sidecar `http://127.0.0.1:9484`,
   desktop log `GuLiCode/logs/gulicode-desktop-direct.log`.

Latest relevant verification:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\app
bun test --preload ./happydom.ts ./src/pages/session/blueprint-side-panel.test.ts ./src/i18n/parity.test.ts
bun run typecheck

cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\desktop-electron
bun test ./src/main/ipc-blueprint-runtime.test.ts
bun run typecheck

cd F:\src\Package\Script\Python\multi_agent_tcp
git diff --check
```

Observed result: app tests passed, desktop IPC tests passed, both typechecks
passed, and `git diff --check` reported only CRLF conversion warnings.

Current follow-ups:

1. Manual desktop smoke: drag blueprint out, move independent OS window, dock
   back to sidebar, and close the popout.
2. Manual popout runtime smoke: submit a runtime task from the popout and
   verify it is accepted by the main chat `blueprintPlanning` flow.
3. Manual node port smoke: isolated nodes hide ports by default, while
   hover/selection/connection drag still makes ports usable.

Detailed archive:

- [`archive/blueprint_popout_window_ports_2026-05-21.md`](archive/blueprint_popout_window_ports_2026-05-21.md)

## Fast Handoff - 2026-05-21 Blueprint Runtime Task Entry

When the next task is GuLiCode blueprint Runtime panel entry behavior, manual
start UX, start-node selection, terminal node compatibility, or draggable
runtime panels, start from this state:

1. New desktop blueprints no longer create or expose product-facing start/end
   terminal nodes. Legacy `terminal_nodes` are still accepted on import, but
   are hidden from the canvas/inspector and filtered from runtime/export paths.
2. Add Node contains Agent and Route choices only. Do not reintroduce Start/End
   as normal product UI choices unless the product direction changes.
3. Runtime/start graph conversion no longer relies on terminal traversal.
   `createBlueprintStartPlan` requires explicit `startNodes`; when none are
   provided it emits empty `start_nodes` and lets backend start-plan validation
   return the expected error.
4. `blueprint.validate`, `blueprint.start`, and
   `blueprint.planning.ensureContext` use desktop graph DAG/reference
   validation instead of terminal-based `validate_runnable()`. The stricter
   `TopAgentStartPlan` validation still requires non-empty unique AgentNode
   `start_nodes` and tasks covering all start nodes.
5. The Runtime panel has a top task-planning block: multi-select AgentNode
   start selector, large task textarea, and Submit button. Empty start
   selection means Top Agent chooses during planning; empty task blocks submit.
6. Manual runtime submit does not directly call `startBlueprintRun`. It sends a
   real user-side message to the main chat, switches the composer into
   `blueprintPlanning`, and runs the existing planning submit override.
7. The toolbar Start button and runtime header start icon now focus the task
   planning block instead of bypassing the task requirement.
8. The main chat handoff is one-shot and refuses to overwrite an existing main
   composer draft/context; the user must clear or send the draft first.
9. The automatic "confirm project workdir" prompt is once per app lifetime.
   Manual directory selection and conflict dialogs are unaffected.
10. Runtime top-level panels are reorderable by the thick handle above each
    panel. During drag, the original panel becomes a dashed placeholder and a
    detached dashed ghost follows the pointer until drop.

Latest relevant verification:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\app
bun test --preload ./happydom.ts ./src/pages/session/blueprint-model.test.ts ./src/pages/session/blueprint-side-panel.test.ts ./src/pages/session/blueprint-planning-session.test.ts ./src/components/prompt-input/submit.test.ts ./src/i18n/parity.test.ts
bun run typecheck

cd F:\src\Package\Script\Python\multi_agent_tcp
python -m pytest -q test_desktop_blueprint_service.py
python -m py_compile desktop_blueprint_service.py graph_runtime.py graph_control.py test_desktop_blueprint_service.py
```

Drag refinement follow-up verification:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\app
bun run typecheck
bun test --preload ./happydom.ts ./src/pages/session/blueprint-side-panel.test.ts ./src/i18n/parity.test.ts
```

Current follow-ups:

1. Manual desktop smoke the full task-panel path:
   submit task -> main chat user message -> `blueprintPlanning` mode ->
   staged plan -> approve -> live run.
2. Visual smoke the narrow Runtime panel layout, including start-node
   multi-select, textarea, long action buttons, panel drag ghost, and dashed
   placeholder.
3. Decide whether runtime panel order should persist beyond the current panel
   session.

Detailed archive:

- [`archive/blueprint_runtime_task_entry_panel_reorder_2026-05-21.md`](archive/blueprint_runtime_task_entry_panel_reorder_2026-05-21.md)

## Fast Handoff - 2026-05-21 Desktop Blueprint Planning Mode

When the next task is GuLiCode desktop blueprint planning mode, Top Agent
status/explain behavior, or `framework_control` MCP registration from the
desktop composer, start from this state:

1. Product decision: GuLiCode desktop/current chat session is the Top Agent
   role. Do not start a separate bottom Top Agent worker, private Top Agent
   `CODEX_HOME`, or Top Agent CLI session.
2. The composer agent dropdown has a virtual "blueprint planning" mode. Only
   this mode provisions planning context/MCP and attaches the framework system
   prompt. Build/Plan/ordinary agents stay normal chat.
3. Backend planning entry is `DesktopBlueprintPlanningSession`, keyed by
   `projectDir + blueprintId + desktopSessionId`. It loads the current graph
   and creates a no-op runtime/control plane for organization, validation,
   question, and staged-plan storage.
4. Planning MCP exposes only the desktop planning subset:
   organization/status/explain/utterances, `runtime_validate_start`,
   `top_agent_request_user_input`, and `top_agent_stage_start_plan`. It must
   not expose `runtime_start`, `top_agent_ask`, or
   `top_agent_start_session`.
5. App-facing API is `blueprint.planning.*`; approve is app-mediated through
   existing `startBlueprintRun(..., "live")`, followed by
   `markBlueprintPlanningPlanStarted`.
6. Dynamic MCP registration must trust `mcp.add`'s returned status. Do not use
   `mcp.status()` as the connection oracle for runtime-injected
   `framework_control`, because status only enumerates persistent MCP config.
7. Known fixed bugs in this pass: wrong `sessionDirectory` passed to
   `ensureContext`, stale `runs/active/planning-*` workspace collisions after
   debug restart, Solid store clone failure on approve/start, and false
   `framework_control not connected` after dynamic MCP add.
8. P0 status-source mismatch is fixed. Planning MCP status/explain/utterance
   calls now select the active live `DesktopBlueprintRun` when one is linked
   or discoverable for the same `projectDir + blueprintId`; otherwise they
   fall back to the planning context no-op runtime.
9. Live runs now write compact diagnostics under
   `shared/logs/blueprint-diagnostics/{snapshot.json,events.jsonl}`. Use
   `statusSource.selected` to tell whether Top Agent was grounded in
   `active_live_run` or `planning_context`; `mismatch=true` is expected when
   the no-op planning runtime differs from the active live run.
10. Next follow-ups: smoke the Runtime task-panel submit path with an existing
    planning context, consider throttling duplicate mismatch diagnostics during
    polling, and optionally expose the diagnostics path in debug UI.

Latest relevant verification:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp
pytest -q test_desktop_blueprint_service.py::test_blueprint_service_desktop_planning_context_plan_flow -q
python -m py_compile desktop_blueprint_service.py blueprint_mcp_runtime.py test_desktop_blueprint_service.py
python -m pytest -q test_desktop_blueprint_service.py

cd GuLiCode\packages\app
bun test --preload ./happydom.ts ./src/pages/session/blueprint-planning-session.test.ts ./src/components/prompt-input/submit.test.ts
bun run typecheck

cd ..\desktop-electron
bun test ./src/main/blueprint-runtime.test.ts ./src/main/ipc-blueprint-runtime.test.ts
bun run typecheck
```

Detailed archive:

- [`archive/blueprint_runtime_task_entry_panel_reorder_2026-05-21.md`](archive/blueprint_runtime_task_entry_panel_reorder_2026-05-21.md)
- [`archive/blueprint_planning_mode_no_bottom_top_agent_2026-05-21.md`](archive/blueprint_planning_mode_no_bottom_top_agent_2026-05-21.md)
- [`archive/blueprint_planning_status_source_diagnostics_2026-05-21.md`](archive/blueprint_planning_status_source_diagnostics_2026-05-21.md)

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
   grid snapping, expanded Agent/Route/Edge inspector fields, legacy terminal
   import compatibility, per-field inspector tip buttons, and the current
   dark/technology/minimal visual pass. Inspector labels, "?" buttons, select options, and
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
- [`archive/blueprint_agent_task_panel_auto_top_summary_2026-05-22.md`](archive/blueprint_agent_task_panel_auto_top_summary_2026-05-22.md)
- [`archive/blueprint_runtime_completion_demux_workspace_2026-05-22.md`](archive/blueprint_runtime_completion_demux_workspace_2026-05-22.md)
- [`archive/blueprint_popout_window_ports_2026-05-21.md`](archive/blueprint_popout_window_ports_2026-05-21.md)
- [`archive/blueprint_runtime_task_entry_panel_reorder_2026-05-21.md`](archive/blueprint_runtime_task_entry_panel_reorder_2026-05-21.md)
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
- Blueprint Agent information panel interactions, task status display, automatic Top Agent summary, long-press progress, Markdown reply rendering, context-menu entry, move/resize behavior, Test Agent JSON snapshots, user-message capture, and clean desktop debug baseline: read `archive/blueprint_agent_task_panel_auto_top_summary_2026-05-22.md`, then `archive/agent_info_panel_markdown_longpress_2026-05-20.md`, then `archive/agent_info_panel_interaction_2026-05-18.md`, then `archive/agent_info_panel_test_node_json_2026-05-18.md`, then `tasks/current_goals.md`.
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
