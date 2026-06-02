# Current Short-Term Goals

Last cleaned: 2026-06-01

## Current Main Line

The active project direction is:

```text
gulicode-bp Codex plugin
  -> local Blueprint web workbench
  -> GuLiCode app dev surfaces: /mobile and /console
  -> DesktopBlueprintService / GraphRuntimeControlPlane
  -> GraphRuntime
  -> AgentNode queues, outgoing batches, joins, workspace/events
  -> CLIWorkerBackend adapters
```

Primary design source:

- [`../多agents通信设计.md`](../多agents通信设计.md)
- [`multi_agent_communication_tasks.md`](multi_agent_communication_tasks.md)
- [`../knowledge_base/debug_start.md`](../knowledge_base/debug_start.md)
- [`../knowledge_base/guli_desktop_ui.md`](../knowledge_base/guli_desktop_ui.md)
- [`../knowledge_base/gulicode_desktop.md`](../knowledge_base/gulicode_desktop.md) for explicit desktop work
- [`../knowledge_base/core_architecture.md`](../knowledge_base/core_architecture.md)

Default debug startup is plugin-first: `start-gulicode-debug.cmd` starts the
`gulicode-bp` workbench, Collaboration Server, `/mobile`, and `/console`, and
skips the GuLiCode Electron desktop shell. Use `start-gulicode-desktop.cmd`
only for explicit desktop-shell, IPC, packaging, taskbar, or windowing tasks.

## Highest Priority

P0: make `gulicode-bp` installable and usable without a local
`multi_agent_tcp` source checkout.

Current implementation direction:

- The plugin installer builds the `multi-agent-tcp` runtime wheel and installs
  it into a plugin-owned `.runtime/venv`.
- Installed `.mcp.json` points at the plugin-owned Python and no longer carries
  repo `PYTHONPATH` / `GULICODE_BP_REPO_ROOT`.
- `GULICODE_BP_REPO_ROOT` is reserved for explicit repository development
  mode; standalone acceptance can set `GULICODE_BP_DISABLE_REPO_FALLBACK=1`.
- Script Function Node templates import the generated project-local
  `gulicode_blueprint.py` shim so editor jumps stay out of runtime source.

Target:

- Keep `plugins/gulicode-bp` as the product entrypoint.
- Package or install the Python runtime needed by the plugin into a
  plugin-owned location.
- Do not require end users to clone `F:\src\Package\Script\Python\multi_agent_tcp`.
- Prefer a plugin-private venv or wheel-based runtime install over copying
  loose repo source into the plugin forever.
- Make `.mcp.json` point at the plugin-owned Python/runtime path.
- Keep script-node authoring pointed at the local `gulicode_blueprint.py` shim.
- Keep source-of-truth development in this repo, then build/install a
  self-contained plugin artifact.

Acceptance:

- On a machine without the repo checkout, installing `gulicode-bp` can run
  `start_blueprint_workbench`, `blueprint_list`, `blueprint_create`,
  `blueprint_plan_create`, `blueprint_plan_validate`, and `blueprint_start`
  for a normal project.
- The installer reports clear repair steps if Python, wheel install, Codex CLI,
  or required runtime dependencies are missing.
- Existing repo-bound developer workflow remains available for local
  development and debugging.

## Recently Completed Baseline

Historical desktop/UI baseline retained for compatibility:

- One-click packaged startup now uses `start-gulicode-desktop.cmd --packaged`.
- Packaged output is stabilized at `GuLiCode/packages/desktop-electron/dist/packaged-launch/current/win-unpacked/GuLiCode Dev.exe`.
- Packaged startup now waits for renderer assets, tolerates `electron-builder` partial Windows sign-tool noise, and patches the final `exe` icon with `rcedit`.
- Packaged main-window bring-up is hardened against off-screen saved window state and icon-load failures inside the Electron main process.
- Desktop icon assets have been replaced for `dev` / `beta` / `prod`.
- The new-session empty state now shows `GULI`.
- The session header blueprint entry now opens a GuLiCode-owned right-side blueprint panel.
- The blueprint panel now contains a runtime-aligned local graph workbench:
  default seed graph, persisted `BlueprintDraft`, HTML nodes plus SVG edges,
  selection, node drag, right-click canvas pan, wheel zoom, add-node dropdown,
  drag/drop node creation, port-to-port connection, context-menu deletion,
  keyboard deletion, reset/fit view, and inspector editing.
- The local graph model now includes `route_nodes`, full `AgentNode`
  configuration fields, legacy terminal-node compatibility, route node kinds,
  and port-aware `GraphEdge` fields with default `out -> in` exec edges.
- Agent/Route canvas nodes render input/output connection ports. Start/End
  terminal ports are now legacy import compatibility only, not current product
  UI.
- Inspector fields now include per-field `?` tip buttons describing what each
  setting is and what it is used for.
- The blueprint panel has passed the current dark, technology-oriented,
  minimal visual pass. Nodes are intentionally more distinct from the canvas
  background, and the inspector uses a dark surface with light labels,
  visible question buttons, corrected select option colors, and legible
  `nonblocking` / `非阻塞` labels.
- `toRuntimeGraphDraft(draft)` now preserves the shape needed for later
  `{ terminal_nodes, agent_nodes, route_nodes, edges }` runtime conversion
  without invoking runtime execution from the renderer.
- The blueprint common config panel now owns user-visible
  `project_workdir`, `skill_dir`, and `rule_dir`. User-machine local paths are
  no longer hard-coded in code defaults; `skill_dir` and `rule_dir` start empty
  and must be set by the user when the blueprint needs them.
- The Agent inspector now hides framework-managed execution fields:
  `cwd`, `read_scope`, `write_scope`, `artifact_scope`, `workspace_id`,
  `workspace_root`, editable `command`, and raw `skill_selection`.
- Runtime draft export still preserves backend compatibility: common
  `project_workdir` is written to AgentNode `cwd`, `command` is generated from
  `cli_kind`, selected skills are mirrored into both `skills` and
  `skill_selection`, and empty skill selection writes `{ mode: "none" }`.
- Skill and rule fields are multi-select dropdowns backed by the common
  directories. Rule directories can be empty without error.
- CLI kind and model are dropdowns. Electron IPC now lists skill/rule catalogs
  and refreshes model candidates by running `codex models codex`
  or parsing `codex debug models` JSON.
- `adapter_options` remains visible only as an advanced JSON field for
  low-level CLI adapter fallback parameters.
- The latest packaged smoke output was regenerated at `GuLiCode/packages/desktop-electron/dist/packaged-launch/current/win-unpacked/GuLiCode Dev.exe` on 2026-05-14 after the resizable blueprint divider change.
- Full Windows installer packaging has a documented local workaround for
  electron-builder `winCodeSign` symlink extraction failures: temporary local
  config, `win.signAndEditExecutable = false`, and `afterPack` `rcedit`
  icon patching.
- The full Windows NSIS workaround was run successfully on 2026-05-14 and
  produced `dist/opencode-electron-win-x64.exe`,
  `dist/opencode-electron-win-x64.exe.blockmap`, and
  `dist/win-unpacked/GuLiCode Dev.exe`. If `d3dcompiler_47.dll` cannot be
  removed, terminate old `GuLiCode Dev.exe` processes launched from
  `dist/win-unpacked` and rerun the workaround.
- 2026-05-18 live runtime pass is complete enough for first UI smoke:
  `blueprint.start` supports `status/live`, live mode starts
  `CLIWorkerBackend` + `GraphRuntimeControlPlane` + `GraphRuntime` tick loop,
  and the desktop service owns backend/tick/WebSocket cleanup.
- Agent stream is now a unified `AgentStreamEvent` model. `HTTP/IPC` remains
  the control plane for start/status/end/agentInfo/queue/token, while WebSocket
  is the event plane for Agent status, queue updates, message parts, public
  reasoning summaries, tool calls, final message completion, and errors.
- GuLiCode blueprint canvas now has an Agent information panel opened by
  left mouse long-press with a circular progress ring, or through the Agent
  node right-click `信息面板` context menu. Hover opening is retired.
- Agent information panels support close, pin, multiple pinned panels,
  non-pinned outside-click close, stream transcript, `default/top` message
  sends, read-only static display when no live run exists, title-bar drag move,
  and bottom-right handle resize with canvas clamping.
- The Agent panel close bug was fixed by replacing the Solid store `panels`
  object with `reconcile(panels)` rather than shallow-merging filtered objects.
- The 2026-05-18 desktop debug cleanup fixed noisy code-level errors around
  `blueprint-list-models` Windows `spawn EPERM`, Solid DnD nonexistent
  droppable/draggable cleanup, stale PTY WebSocket teardown, and blueprint SVG
  render computations.
- Clean debug startup is documented after packaging instructions:
  run Electron dev with `ELECTRON_ENABLE_LOGGING=1`,
  `ELECTRON_ENABLE_STACK_DUMPING=1`, and no `DEBUG=*`.
- Test Agent panel JSON has been reduced to the v2 message-only debug shape:
  fixed `agent-panel-test.json`, payload arrays `agentReplies`,
  `userMessages`, and `frameworkMessages`, no raw `node`, `panel`, `runtime`,
  or `streamEvents` objects.
- Agent information panel status events now project into structured UI instead
  of raw JSON. Visible transcript events hide `status`, `message.started`,
  `queue.updated`, `tool.started`, `tool.completed`, stderr deltas, reasoning
  deltas, and Codex internal log lines; user-facing `part.delta` /
  `message.completed` content is grouped as `Agent 回复`.
- Agent information panels can be dragged outside the visible canvas after
  opening, body content is selectable/copyable, and wheel scrolling is handled
  inside the panel body.
- Latest Windows package after the panel cleanup was rebuilt at
  `GuLiCode/packages/desktop-electron/dist/opencode-electron-win-x64.exe` on
  2026-05-18.
- The desktop blueprint live runtime now starts through the framework-managed
  private Agent context: `GraphRuntime(enforce_private_agent_context=True)`,
  private checkout cwd, private `CODEX_HOME`, `framework-agent-runtime`,
  `AGENTS.md`, Workspace API prompt/context, and authorized skill/rule
  materialization.
- Blueprint start is now guarded by common config validation in both renderer
  and desktop service. `project_workdir` is always required and absolute;
  `skill_dir` is required when skills are used; `rule_dir` is required when
  rule files are selected; any non-empty optional path must be absolute.
- Rule catalog selections now store filenames relative to configured `rule_dir`
  instead of user-machine absolute paths. The desktop service resolves them
  from common config during start.
- Backend workspace merge regression is fixed: non-overlapping same-file
  checkout submits are accepted even when Dulwich is unavailable or reports a
  false conflict, and the combined
  `test_desktop_blueprint_service.py test_workspace_manager.py` run passes.
- Blueprint runtime manual entry is now task-planning-first: the Runtime panel
  asks for optional start AgentNodes plus a required task, then submits the
  task as a real main-chat user message in `blueprintPlanning` mode instead of
  directly starting the runtime.
- New product-facing blueprints no longer create or show start/end terminal
  nodes. Legacy terminal nodes are still readable, but canvas, inspector,
  export, and runtime graph conversion filter them out.
- Desktop graph validation no longer requires terminal start/end nodes for
  `blueprint.validate`, `blueprint.start`, or planning context creation.
  Final `TopAgentStartPlan` validation still requires non-empty AgentNode
  `start_nodes` and matching tasks.
- The automatic project-workdir confirmation dialog is now shown only once per
  app lifetime. Manual directory selection and relocation conflict dialogs are
  unchanged.
- Runtime top-level panels are reorderable by dragging the thick handle above
  a panel. The original panel becomes a dashed placeholder and a detached
  dashed ghost follows the mouse until drop.
- Blueprint drag-out now opens a real independent Electron `BrowserWindow`,
  not an in-app fixed overlay. The popout route renders only the blueprint
  panel through the shared provider stack, keeps the "dock back to sidebar"
  button, and sends dock/close/planning-submit events back to the main session.
- Blueprint node ports are hidden by default unless their direction has an
  edge: no incoming edge hides the left/input port, and no outgoing edge hides
  the right/output port. Hover, selection, and active connection dragging still
  reveal ports for graph editing.

## Immediate Handoff For The Next Agent

Start from these source files:

- `plugins/gulicode-bp/mcp/gulicode_bp_mcp.py`
- `plugins/gulicode-bp/scripts/install_personal_plugin.py`
- `plugins/gulicode-bp/scripts/start_workbench.py`
- `plugins/gulicode-bp/skills/blueprint/SKILL.md`
- `start-gulicode-debug.ps1`
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
- `GuLiCode/packages/desktop-electron/src/main/blueprint-runtime.ts`
- `GuLiCode/packages/desktop-electron/src/main/blueprint-runtime.test.ts`
- `GuLiCode/packages/desktop-electron/src/main/ipc-blueprint-runtime.test.ts`
- `GuLiCode/packages/desktop-electron/src/main/windows.ts`
- `GuLiCode/packages/desktop-electron/src/renderer/index.tsx`
- `GuLiCode/packages/app/src/pages/session.tsx`
- `GuLiCode/packages/app/src/pages/session/session-side-panel.tsx`
- `GuLiCode/packages/app/src/pages/session/blueprint-window.tsx`
- `GuLiCode/packages/app/src/pages/session/composer/session-composer-region.tsx`
- `GuLiCode/packages/app/src/components/session/session-header.tsx`
- `GuLiCode/packages/app/src/components/prompt-input.tsx`
- `GuLiCode/packages/app/src/components/prompt-input/submit.ts`
- `GuLiCode/packages/app/src/context/layout.tsx`
- `GuLiCode/packages/app/src/i18n/en.ts`
- `GuLiCode/packages/app/src/i18n/zh.ts`
- `GuLiCode/packages/app/src/i18n/zht.ts`
- `desktop_blueprint_service.py`
- `agent_launch_context.py`
- `graph_runtime.py`
- `cluster.py`
- `test_desktop_blueprint_service.py`

Before changing behavior, run:

```powershell
cd GuLiCode\packages\app
bun test --preload ./happydom.ts ./src/pages/session/blueprint-model.test.ts ./src/pages/session/blueprint-side-panel.test.ts ./src/pages/session/blueprint-planning-session.test.ts ./src/components/prompt-input/submit.test.ts ./src/i18n/parity.test.ts
bun run typecheck
```

If touching Electron catalog/model IPC, runtime IPC, or packaged desktop
identity, also run:

```powershell
cd GuLiCode\packages\desktop-electron
bun test ./src/main/blueprint-catalog.test.ts ./src/main/blueprint-runtime.test.ts ./src/main/ipc-blueprint-runtime.test.ts
bun run build
```

For explicit desktop-shell debugging with visible Electron errors:

```powershell
cd GuLiCode\packages\desktop-electron
$env:ELECTRON_ENABLE_LOGGING = '1'
$env:ELECTRON_ENABLE_STACK_DUMPING = '1'
Remove-Item Env:\DEBUG -ErrorAction SilentlyContinue
bun run dev
```

Do not use `DEBUG=*` by default; it floods the terminal with Babel/Vite
internal traversal logs.

## Active Priorities

Highest priority as of 2026-06-01:

1. Standalone `gulicode-bp` distribution.
   - Make the installed plugin usable without a local `multi_agent_tcp`
     checkout.
   - Package or install `DesktopBlueprintService`, `GraphRuntime`, and runtime
     dependencies into a plugin-owned location.
   - Rewrite `.mcp.json` / installer output to point at the plugin-owned
     Python/runtime path.
   - Smoke a no-repo install path: start workbench, list/create blueprint,
     create/validate start plan, start/status/end live run.

2. Plugin-first Blueprint debug loop.
   - Use the debug startup workflow to start the `gulicode-bp` workbench,
     Collaboration Server, mock mobile `/mobile`, and `/console` together.
   - Do not start the GuLiCode Electron desktop shell unless the task is
     explicitly about desktop-shell, IPC, packaging, taskbar, or windowing
     behavior.
   - Exercise the plugin workbench path end to end: open current project
     blueprint -> validate -> start/status/events/diff -> stop/end.
   - Keep `/mobile` and `/console` available in the same debug loop for
     collaboration and runtime observability.
   - Exercise the account-level bridge loop where relevant: mobile chat submit
     -> Collaboration Server -> active runtime/session bridge -> session
     snapshot -> mobile chat refresh.
   - Exercise blueprint start from mobile where relevant: mobile goal ->
     plugin start-plan create/validate -> pending confirmation -> live run
     start.
   - Verify mobile agent message send, run cancel, diff approve audit-only,
     real rollback, viewer/logged-out read-only fallback, CSRF failures,
     runtime failure propagation, audit logs, client logs, and payload
     scrubbing.
   - Verify mobile chat UX remains stable while `/api/mobile/tick` refreshes:
     structured Markdown, reasoning/tool disclosure state, disclosure width,
     and scroll position.
   - Capture any routing/auth/runtime-binding gaps as integration blockers
     before adding more features.

Latest detailed archive:

- [`../archive/runtime-backend/gulicode_bp_plugin_direct_control_start_plan_2026-06-01.md`](../archive/runtime-backend/gulicode_bp_plugin_direct_control_start_plan_2026-06-01.md)
- [`../archive/future-server/collaboration_server_desktop_bridge_mobile_chat_2026-05-29.md`](../archive/future-server/collaboration_server_desktop_bridge_mobile_chat_2026-05-29.md)
- [`../archive/future-server/collaboration_server_mobile_write_loop_2026-05-28.md`](../archive/future-server/collaboration_server_mobile_write_loop_2026-05-28.md)

2026-05-29 completed: account-level desktop bridge + mobile chat:

The Collaboration Server now supports account-level mobile-to-desktop control:
multiple mobile sessions may connect to one account while only one active
desktop session is allowed. Desktop registers a loopback bridge; mobile chat and
blueprint-planning writes go through the server and are forwarded to the active
desktop bridge. Desktop session snapshots mirror session summaries, current
messages, structured segments, and PromptInput composer modes. `/mobile`
renders the desktop current conversation, sends with desktop-equivalent
`promptMode/agentName`, supports `build` / `plan` / `蓝图规划`, and preserves
reasoning/tool disclosure state, width, and scroll position across ticks.

Validation from the pass:

- `python -m pytest -q test_collaboration_server.py` passed: 18 passed.
- `cd GuLiCode/packages/app && bun test --preload ./happydom.ts ./src/mobile ./src/components/collaboration-auth.test.ts ./src/pages/session/blueprint-planning-session.test.ts` passed.
- `cd GuLiCode/packages/app && bun run typecheck` passed.
- `cd GuLiCode/packages/desktop-electron && bun run typecheck` passed.
- Live smoke confirmed `/mobile` message send, desktop reply snapshot, structured
  segment rendering, disclosure persistence, stable expanded width, and stable
  scrollTop across ticks.

2026-05-28 completed: mobile mock + Collaboration Server phase 1:

The first FastAPI Collaboration Server and `/mobile` read-only loop are now
implemented at code/test level. The server is a gateway only: auth/session,
admin management, project membership, runtime binding, safe projection,
event journal/replay/SSE, runtime bridge reads, audit records, and disabled
phase-2 write gates. The `/mobile` surface keeps its existing three-tab mock UI
while loading same-origin `/api` data with mock fallback.

The same pass added observability: structured rotating server logs,
runtime bridge and SSE/event logs, mobile ring-buffer logs, default mobile
log upload to `POST /api/client-logs`, sqlite `client_logs`, and
admin-only `GET /api/admin/logs/client`. This is operational monitoring, not
server-owned runtime scheduling.

Validated commands:

- `pytest -q test_collaboration_server.py test_desktop_blueprint_service.py`
  passed: 46 passed, 1 skipped.
- `cd GuLiCode/packages/app && bun test --preload ./happydom.ts ./src/mobile ./src/pwa.ts`
  passed: 9 passed.
- `cd GuLiCode/packages/app && bun run typecheck` passed.
- `git diff --check` passed with only existing CRLF warnings.

Immediate next Collaboration Server tasks:

1. Add retention/pruning for sqlite operational logs:
   `client_logs` default 30 days, audit logs retained longer or manually
   pruned, startup prune plus periodic 24h prune.
2. Add admin/system diagnostics for log health and runtime bridge availability
   without exposing bridge tokens, cookies, local paths, or raw runtime payloads.
3. Run a manual same-origin smoke with a real desktop runtime binding:
   login, project list, latest run, status, events, diff, reports/artifacts,
   mobile fallback after bridge outage, and admin client-log query.
4. Keep phase-2 write endpoints gated until the product decision for mobile
   send/approval/run-control permissions is explicit.

Historical implementation checklist from the completed pass:

1. Preserve the current mobile mock UI while replacing data sources.
   - Continue from the implemented `/mobile` mock-first SolidJS entry in
     `GuLiCode/packages/app`.
   - Keep the current three-tab product shape: `Top Agent`, `蓝图`, and `待定`.
   - Avoid frontend redesign, navigation changes, new approval controls, node
     editing, runtime start/stop buttons, or message-send UX unless the user
     explicitly asks.
   - Replace `mobileMockData` incrementally behind the existing components with
     Collaboration Server responses.
   - Keep the Agent sheet, structure map, run status, and Diff presentation
     visually aligned with the current mock.
   - Preserve the PWA rule that `/auth/*`, `/api/*`, `/runs/*`, and `/stream`
     stay `NetworkOnly`; cache only app shell and static assets.

2. Build the service/API boundary in parallel with the mock frontend.
   - Treat `docs/gulicode_collaboration_server_design.md` as the current API
     and implementation boundary.
   - Implement the Python Collaboration Server path the mobile mock will call;
     the PWA must never talk directly to Python Runtime, Workspace RPC, MCP
     bearer endpoints, private checkouts, or service tokens.
   - Prioritize read-only/mobile-safe endpoints first: auth/session, project
     list, run list/detail/status, Agent snapshot, Diff summary, reports,
     artifacts, event history, and SSE stream.
   - Keep run creation, mobile message send, approvals, and run control behind
     explicit capability gates after the read-only loop works.
   - Keep GraphRuntimeControlPlane/Python Runtime access server-side behind a
     service-token bridge with explicit audit records.
   - Make event streaming cursor-based and idempotent so the mobile client can
     reconnect after backgrounding or network loss.

3. Validate frontend/server together, not as separate tracks.
   - Add backend tests for auth, token/path scrubbing, runtime bridge
     forwarding, event replay, and report/artifact exposure.
   - Add mobile tests that keep the current mock UI stable while the data
     source switches from local mock data to API fixtures/live server data.
   - Current source focus:
     `GuLiCode/packages/app/src/mobile/*`,
     `GuLiCode/packages/app/src/pwa.ts`,
     `GuLiCode/packages/app/src/entry.tsx`,
     `GuLiCode/packages/app/vite.config.ts`,
     `GuLiCode/packages/app/e2e/mobile.spec.ts`,
     `docs/gulicode_collaboration_server_design.md`,
     and the future `collaboration_*` Python service files.

Detailed context:

- [`../archive/future-server/collaboration_server_phase1_mobile_observability_2026-05-28.md`](../archive/future-server/collaboration_server_phase1_mobile_observability_2026-05-28.md)
- `docs/gulicode_collaboration_server_design.md`
- Repo-local mock archive: `archive/frontend/mock/`
- Installed-skill historical first pass:
  [`../archive/frontend/gulicode_mobile_pwa_mock_first_pass_2026-05-27.md`](../archive/frontend/gulicode_mobile_pwa_mock_first_pass_2026-05-27.md)

2026-05-26 Blueprint runtime and Diff stabilization:

Current state:

1. Run-scoped Blueprint Diff is implemented end to end: backend reads archived
   `changesets/<id>/{changeset.json,patch.diff,submit_result.json}`, desktop
   bridge exposes `blueprint.runDiff` / `blueprint.changesetDiff`, and the
   blueprint panel renders the run-scoped overlay inside the canvas area.
2. The native right global Review/FileTree diff now receives blueprint accepted
   diffs through a direct parent callback plus the existing
   `workspace.diff.changed` fallback event. This avoids lost first-sync events
   and works for non-git project-reference sessions by merging blueprint diffs
   into the `turn` review mode.
3. Completed live smoke evidence:
   - `run-3811f7b6a44f`: 3 accepted changesets / 3 files.
   - `run-739420ebbb3d`: 4 total changesets, 3 accepted, 1 rejected,
     `acceptedDiffs` has 3 files.
   - `run-bda914213882`: 3 accepted changesets / 3 files.
4. Blueprint startup slowness root cause is fixed in workspace checkout:
   `workspace_manager._relative_files()` no longer uses `root.rglob("*")`.
   It uses top-down `os.walk` pruning so excluded directories such as
   `.multi_agent_workspace`, `.git`, and `node_modules` are never descended
   into. On `D:\agents_work_test`, full-scope copy measured `0.015s`, 4 files,
   and did not enter `.multi_agent_workspace`.
5. The frontend no longer auto-submits a completed-run Top Agent summary
   prompt. Reloading with Ctrl+R should not create a new "思考中" turn. The
   `ready_for_top_agent_summary` backend flag remains only as a terminal
   readiness signal for automatic run completion/final result calculation.
6. Existing blockers fixed during smoke remain in force: archived run Diff
   lookup reopens active/archived/failed run paths; `workspace_publish`
   cross-Agent same-path writes require `expected_version`; default AgentNode
   `write_scope` is project-wide `["**"]`, with legacy
   `["shared/reports/**"]` migrated to that default.

High-priority remaining checks:

1. Restart the `gulicode-bp` workbench/blueprint service before retesting
   startup speed; existing Python service processes still have old code loaded.
2. Manual UI smoke for native global diff sync:
   - Start a new live blueprint run in `D:\agents_work_test`.
   - Verify the blueprint Diff overlay and right native Review/FileTree diff
     show accepted diffs during runtime and after completion/archive.
   - Verify rejected/conflict changesets stay visible in Blueprint Diff status
     UI but do not enter native accepted diff rendering.
3. Ctrl+R smoke after a completed run:
   - Reload the Electron renderer.
   - Verify the completed run is restored without auto-submitting a Top Agent
     summary prompt and without creating a new left-chat "思考中" turn.
4. Test multiple Agents sequentially modifying the same project file and
   verify Blueprint Diff display:
   - Run 3 Agents in sequential/blocking order.
   - All Agents must use `workspace_checkout` / `workspace_submit`; do not use
     `workspace_publish` as the main result.
   - Target one file such as `docs/blueprint_diff_shared_test.md`.
   - Agent 1 creates the file; Agent 2 syncs/reads current content and appends
     the second section; Agent 3 syncs/reads current content and appends the
     third section.
   - Expected result: Blueprint Diff shows 3 changesets for one file, and each
     `查看` detail shows the correct incremental diff.
5. Test `workspace_submit` conflict and Blueprint Diff status display:
   - Run 3 Agents in `parallel_all`.
   - All Agents must use `workspace_checkout` / `workspace_submit`; do not use
     `workspace_publish` as the main result.
   - All Agents edit the same first line of a file such as
     `docs/blueprint_diff_conflict_test.md` with different content.
   - Expected result: Blueprint Diff shows accepted/conflict/rejected status
     distribution correctly, and conflicted changesets do not enter
     `acceptedDiffs`.

Detailed archive:

- [`../archive/runtime-backend/blueprint_run_diff_workspace_scope_2026-05-26.md`](../archive/runtime-backend/blueprint_run_diff_workspace_scope_2026-05-26.md)
- [`../archive/runtime-backend/blueprint_checkout_prune_startup_2026-05-26.md`](../archive/runtime-backend/blueprint_checkout_prune_startup_2026-05-26.md)
- [`../archive/frontend/blueprint_diff_native_sync_no_auto_summary_2026-05-26.md`](../archive/frontend/blueprint_diff_native_sync_no_auto_summary_2026-05-26.md)

2026-05-21 Blueprint independent window and endpoint visibility update:

Closed in this pass:

1. Blueprint title-bar drag-out now opens an independent Electron
   `BrowserWindow`; the previous in-app fixed overlay has been removed.
2. Popout windows are keyed by `projectDir + sessionId` and focus existing
   matching windows instead of creating duplicates.
3. Popout renderer initialization uses `getBlueprintWindowContext()` and a
   dedicated `/:dir/blueprint-window/:id?` route.
4. `AppInterface visualShell={false}` lets the popout reuse providers without
   rendering the normal desktop app shell.
5. The popout keeps the "dock back to sidebar" action. Docking focuses the main
   window, reopens the embedded side panel, and closes the popout.
6. Closing the popout clears the main session blueprint floating/open state.
7. Runtime task submit from the popout forwards to the main session
   `blueprintPlanning` handoff and returns an accepted/rejected response.
8. Node input/output ports now default to edge-directed visibility with
   hover/selection/connection-drag edit fallbacks.

Detailed archive:

- [`../archive/blueprint_popout_window_ports_2026-05-21.md`](../archive/blueprint_popout_window_ports_2026-05-21.md)

Immediate next checks:

1. Manual desktop smoke: drag blueprint out, move the independent OS window,
   dock it back, and close it.
2. Manual popout runtime smoke: submit a task from the popout and verify the
   main chat blueprint-planning flow receives it.
3. Manual endpoint smoke: isolated nodes hide ports by default, hover/selection
   reveals them, and connection dragging still creates edges.

2026-05-21 Blueprint runtime task entry and panel reorder:

Closed in this pass:

1. New blueprint documents no longer seed start/end terminal nodes; legacy
   `terminal_nodes` remain import-compatible but are hidden and filtered from
   runtime/export surfaces.
2. Add Node no longer offers Start/End. Runtime/export graph conversion keeps
   AgentNode/RouteNode execution structure only.
3. `createBlueprintStartPlan` now requires explicit `startNodes`; missing
   start nodes intentionally produces an empty `start_nodes` plan for backend
   validation to reject.
4. Desktop service validation for `blueprint.validate`, `blueprint.start`, and
   planning context creation moved from terminal `validate_runnable()` to
   DAG/reference/AgentNode validation.
5. The Runtime panel now has a top task-planning area with AgentNode
   multi-select, large task textarea, and gated submit.
6. Manual task submit goes through the main chat: it switches to
   `blueprintPlanning`, sends a real user message, and relies on the existing
   Top Agent planning flow to stage or reject the live run.
7. Top toolbar Start and Runtime header Start now focus the task-planning area
   instead of directly starting the blueprint.
8. Runtime action controls were changed into long rows with large action text
   and smaller explanatory copy.
9. Runtime top-level panels can be reordered by dragging their thick handle;
   the original panel becomes a placeholder and a detached ghost follows the
   pointer.
10. The automatic project-workdir confirmation prompt now fires only once per
    app lifetime.

Immediate follow-up queue:

1. Manual smoke the full intended path in the running desktop app: task panel
   submit -> main chat user message -> automatic `blueprintPlanning` mode ->
   staged plan -> approve -> live run.
2. Visual smoke the narrow Runtime panel layout, especially the multi-select,
   selected start nodes, textarea, submit button, long action buttons, drag
   ghost, and placeholder.
3. Decide whether runtime panel order should persist between panel sessions or
   remain local to the current session.

Detailed archive:

- [`../archive/blueprint_runtime_task_entry_panel_reorder_2026-05-21.md`](../archive/blueprint_runtime_task_entry_panel_reorder_2026-05-21.md)

2026-05-21 Desktop blueprint planning mode:

Closed in this pass:

1. Product direction changed: the GuLiCode desktop app/current chat session is
   the Top Agent role. Do not start a separate bottom Top Agent worker,
   private Top Agent `CODEX_HOME`, or user-runnable Top Agent CLI session.
2. The composer dropdown now has a virtual "blueprint planning" mode. Only
   that mode provisions planning context/MCP and attaches the framework system
   prompt. Build/Plan/ordinary agents remain normal chat.
3. Backend planning context is `DesktopBlueprintPlanningSession`, keyed by
   `projectDir + blueprintId + desktopSessionId`; it uses a no-op
   runtime/control plane for graph organization, plan validation, questions,
   and staged plans.
4. Planning MCP exposes the desktop planning subset and filters
   `runtime_start`, `top_agent_ask`, and `top_agent_start_session`.
5. Approve remains app-mediated through `startBlueprintRun(..., "live")`,
   followed by `markBlueprintPlanningPlanStarted`.
6. Fixed current debug blockers: wrong project directory passed to
   `ensureContext`, stale `runs/active/planning-*` workspace collision,
   Solid store clone failure on approve/start, and dynamic MCP false
   `not connected` caused by using `mcp.status()` after runtime `mcp.add`.

P0 closed in this pass:

1. Planning-mode status source mismatch is fixed. Planning MCP
   `runtime_status`, `runtime_explain_status`, `top_agent_explain_status`,
   `top_agent_utterances`, and `runtime_top_agent_utterances` now select the
   active live `DesktopBlueprintRun` when one is linked or discoverable for the
   same `projectDir + blueprintId`.
2. If no active live run exists, planning status falls back to the planning
   context no-op runtime.
3. MCP responses keep the existing shape and add `status_source`,
   `source_run_id`, and `planning_session_id`.
4. `blueprint.planning.status` now returns `statusSource` alongside the old
   `runtimeStatus` and `activeRun` fields.
5. Live runs create run-scoped diagnostics at
   `shared/logs/blueprint-diagnostics/{snapshot.json,events.jsonl}`.
6. Manual evidence from `D:\agents_work_test` showed the planning no-op runtime
   stayed `created` with no agents, while `active_live_run` reported
   `running` and `test-agent=idle`; the Top Agent status tools selected
   `active_live_run` and answered consistently with the Runtime panel.

Immediate follow-up queue:

1. Manual smoke the new Runtime task panel while a planning context exists;
   direct side-panel Start has been retired in favor of task submit through
   main-chat `blueprintPlanning`.
2. Consider throttling repeated `planning_status_source_mismatch` diagnostics
   during polling.
3. Optionally expose diagnostics paths from run summaries in a developer/debug
   UI affordance.

Detailed archive:

- [`../archive/blueprint_runtime_task_entry_panel_reorder_2026-05-21.md`](../archive/blueprint_runtime_task_entry_panel_reorder_2026-05-21.md)
- [`../archive/blueprint_planning_mode_no_bottom_top_agent_2026-05-21.md`](../archive/blueprint_planning_mode_no_bottom_top_agent_2026-05-21.md)
- [`../archive/blueprint_planning_status_source_diagnostics_2026-05-21.md`](../archive/blueprint_planning_status_source_diagnostics_2026-05-21.md)

2026-05-20 Agent information panel stream UI update:

Closed in this pass:

1. Agent information panels now default to tall mode (`420 x 620`) and no
   longer expose the old width/height preset selector.
2. The top status strip defaults to the four compact fields: status, queue,
   messages, and busy count.
3. "运行状态" and "JSON 位置" are available only from the top status detail
   expander, not from the chat body or composer.
4. Panel-sent user messages are recorded and displayed immediately for every
   Agent. Runtime lifecycle sync remains event-driven; Test Agent JSON writes
   are still limited to Test Agent nodes.
5. Transcript projection now has explicit tones for user messages, Agent
   replies, reasoning summaries, tool calls, queue errors, and generic visible
   events.
6. Reasoning and tool entries are collapsible. Their open state is controlled
   by `agentPanelEventOpen`, keyed by display event id, so stream/status ticks
   do not collapse content the user opened.
7. Consecutive tool calls are grouped by default when no visible user/Agent
   reply, reasoning, error, or other content interrupts them. Hidden status
   ticks do not break the group. The grouped row renders as
   `工具调用组 · N 个工具` and expands to the individual tool details.

Detailed archive:

- [`../archive/agent_info_panel_stream_ui_2026-05-20.md`](../archive/agent_info_panel_stream_ui_2026-05-20.md)

2026-05-20 Blueprint project workdir + Agent surface update:

Closed in this pass:

1. Blueprint project workdir now drives the real session/workspace root:
   entering the blueprint panel prompts the user to confirm/select the project
   directory, and a changed directory relocates the current blueprint document
   to `<target>/.multi_agent_workspace/blueprints/default.json` before opening
   the target session.
2. Runtime/start/stop loading disables the blueprint common config entry; the
   common-config `project_workdir` field is read-only and can only be changed
   through the folder picker plus backend relocation flow.
3. Ordinary Agents now read `project_context` / `project_code_root` and the
   current run `shared_workspace` directly from injected read-only filesystem
   paths.
4. Ordinary/control MCP no longer exposes `workspace_read`, `workspace_list`,
   `workspace_list_archives`, or `workspace_extract_archive`.
5. `workspace_api.py` and `WorkspaceRPCServer` no longer expose Agent-facing
   `read`, `list`, `list-archives`, or `extract-archive`; internal manager
   read/archive methods remain available for framework status, reports,
   archive, and tests.
6. Ordinary Agent prompt-facing context no longer includes `workspace_api`,
   `submit_command`, or CLI command recipes. CLI/RPC stays in full internal
   `execution_context` for framework internals, tests, and debugging.
7. Codex launch safety now protects `project_context`, `project_code_root`, and
   the run `shared_workspace.root` from `--add-dir` writable escapes, and still
   rejects `danger-full-access`.

Current ordinary Agent-facing model:

```text
read project/shared directly
edit code only in private checkout
submit code through MCP
publish reports/artifacts through MCP
communicate through agent_dispatch / join_contribute
```

Detailed archive:

- [`../archive/blueprint_project_workdir_agent_surface_2026-05-20.md`](../archive/blueprint_project_workdir_agent_surface_2026-05-20.md)

Immediate next checks:

1. Manual GuLiCode desktop smoke with a user-selected project workdir and the
   relocation conflict branches.
2. Full MCP live run under a normal project directory such as
   `D:\agents_work_test`, not `C:\`.
3. Agent panel follow-up-send smoke after the status/idle and message-context
   changes: confirm late replies are still streamed and recorded.

2026-05-19 MCP full-control acceptance update:

MCP is accepted as the full run-scoped tool protocol for live blueprint Agents.
The layer now covers the public `GraphRuntimeControlPlane` control surface with
separate ordinary-Agent and top-agent/control tool boundaries. Ordinary Agents
receive only scoped execution tools; Top Agent receives orchestration,
observation, lifecycle, message, join, utterance, and status tools.

The original ordinary-agent adoption blocker was Codex CLI non-interactive MCP
approval: JSONL showed `mcp_tool_call` followed by
`user cancelled MCP tool call` before requests reached the framework MCP
server. Private `CODEX_HOME/config.toml` now writes `enabled_tools` and
per-tool `approval_mode = "approve"` for the run-scoped framework MCP server.

Closed in this pass:

1. Runtime dependencies are declared and install through
   `python -m pip install -e .`: `mcp`, `uvicorn`, `starlette`, and `httpx`.
2. The run-scoped ordinary/control MCP servers start through the full live
   framework path and expose the intended ordinary/control public tool sets.
3. MCP tool calls are audited as `framework_mcp_tool_call` with safe argument
   summaries, while Workspace RPC still audits `workspace_api_call`.
4. Private `CODEX_HOME` MCP config is materialized with token env vars, and
   prompt-facing context exposes direct-read project/shared roots while still
   excluding bearer tokens, RPC tokens, raw Codex home paths, and real
   skill-space source paths.
5. Deterministic live MCP client tests cover checkout/status/diff/submit,
   publish/publish_file, direct shared report reads, `agent_dispatch`, runtime
   control caveats, and message journal flow.
6. Skill/rule injection remains part of the private Agent context:
   `framework-agent-runtime`, selected business skill/rule, and checkout/base
   `AGENTS.md` are materialized.
7. Real Codex MCP smoke now passes through the full framework backend live
   flow; no fallback `python -m multi_agent_tcp.workspace_api` shell command is
   used in that acceptance path.
8. Control MCP parity is implemented for organization/top-agent context,
   run validate/start/status/end, message batch/stage, control-side
   `agent_dispatch`, join create/contribute, top-agent utterances, and
   status inspection. Workspace read/list/archive tools are intentionally not
   exposed to Agents.
9. `runtime_end` now prefers the `DesktopBlueprintService` live close callback,
   which tears down the backend path and closes MCP tokens.
10. Real-smoke transport hardening is complete: live stderr stream noise is
    capped and Codex stdout/stderr are compacted over TCP while full
    diagnostics remain available on disk.

Accepted real-Codex evidence:

1. `MULTI_AGENT_TCP_RUN_REAL_CODEX_MCP=1 pytest -q test_desktop_blueprint_service.py::test_real_codex_live_blueprint_uses_mcp_for_workspace_and_dispatch_flow -vv`
   passed on 2026-05-19: `1 passed, 2 warnings in 135.84s`.
2. Codex JSONL and runtime `agent_stream_events` showed real MCP tool invocation
   rather than fallback `python -m multi_agent_tcp.workspace_api` CLI commands.
3. `run.shared/manifest.json` contained `framework_mcp_tool_call` entries for
   `workspace_checkout`, `workspace_status`, `workspace_diff`,
   `workspace_submit`, `workspace_publish`, `workspace_publish_file`,
   and `agent_dispatch`, plus corresponding `workspace_api_call` entries where
   Workspace RPC is used. The downstream reviewer reads the shared report file
   directly from `shared_workspace.reports`.
4. The project file remained at base content before submit and contained the
   test marker exactly once after accepted `workspace_submit`.
5. Final/report text proved framework skill, selected business skill, and
   selected business rule were injected.
6. Planner/reviewer flow proved cross-Agent information still moves through
   `agent_dispatch`, the message journal, queues/ticks, and shared references;
   natural language replies remain private utterances unless explicitly
   dispatched.

Remaining queue after MCP full-control acceptance:

1. Reproduce the original Agent timeout/panel-message scenario with MCP
   enabled; verify active message context refresh, Codex JSONL completion, and
   WebSocket stream continuity after follow-up sends.
2. Keep or extend the real direct-write boundary smoke in the MCP-enabled
   private context, especially project/shared write denial versus private
   checkout write allowance.
3. Add negative HTTP/MCP coverage for missing bearer token and
   `Mcp-Session-Id` reuse across ordinary/control endpoints.
4. Add UI-facing top-agent/operator surfaces for MCP control status and
   utterance audit without exposing those tools to ordinary Agents.

2026-05-19 priority update:

The desktop blueprint `live` private-context startup blocker and the
`DulwichWorkspaceManager` non-overlapping same-file merge regression are closed
at code and unit-test level. The remaining first task is a manual GuLiCode
desktop smoke pass using user-provided common config paths.

Secondary 2026-05-18 Codex/UI priority context:

Codex-first update: for this project phase, do not spend new work on
Codex streaming. Prioritize `cli_kind=codex` live runs, `CodexAdapter`
JSONL streaming, WebSocket stability, and Agent information panel transcript
quality. Codex stays compatibility/fallback unless the user explicitly
re-opens that track.

1. Manually smoke the live blueprint path in GuLiCode desktop: start live run,
   tick loop, runtime panel updates, Agent panel long-press progress,
   right-click `信息面板`, move/resize, close/pin, WebSocket transcript, and
   `default/top` queue sends.
2. Decide durable blueprint persistence ownership: local draft, project JSON,
   workspace records, and migration from `Persist.workspace(projectDir,
   "blueprint-draft.v1")`.
3. Continue keeping renderer logic as runtime/control-plane projection only;
   do not move GraphRuntime scheduling semantics into the UI.
4. Stabilize Agent output streaming on the Codex path before investigating any
   Codex adapter streaming work.
5. Harden Windows packaging into a repeatable helper and keep clean debug
   startup as the default troubleshooting path.

Superseded 2026-05-14 priority list kept for historical context:

1. Bind the blueprint draft UI to `GraphRuntimeControlPlane` and `GraphRuntime` without moving scheduler semantics into the renderer.
2. Decide durable blueprint persistence ownership: local draft, project JSON, workspace records, and migration from `Persist.workspace(projectDir, "blueprint-draft.v1")`.
3. Extend the existing Electron/preload catalog bridge into the Python/runtime bridge needed for graph load/save and runtime start/status/end.
4. Project runtime/control-plane status into GuLiCode UI: runs, agents, outgoing batches, joins, workspace changes, artifacts, reports, and top-agent explanations.
5. Frontend smoke the current blueprint interaction and config pass: common config panel, skill/rule multi-selects, CLI/model dropdown refresh, right-click canvas pan, right-click node menu, double-click inspector, add-node click/drop, port drag connection, grid snapping, inspector collapse, and keyboard delete.
6. Frontend visual-smoke the current blueprint style pass: dark inspector
   surface, light labels, tip buttons, select menu colors, `非阻塞`
   visibility, and node/background contrast.
7. Harden Windows packaging: turn the successful NSIS/rcedit workaround into
   a repeatable script or doc-backed helper, verify installer plus unpacked
   exe icons, avoid temporary config drift, and kill only old packaged
   `GuLiCode Dev.exe` instances when the output directory is locked.
8. Continue brand unification across desktop window title, taskbar identity, packaged icons, empty states, and any remaining user-visible `OpenCode` wording.
9. Expose top-agent/operator audit surfaces only in top-level UI views, not as ordinary-Agent message context.
10. Keep workspace/archive behavior aligned with framework-owned changeset, conflict, report, artifact, and reference records.
11. Keep Tauri secondary on this machine; Electron remains the default bring-up and verification path.

## 2026-05-14 Testing Focus

1. Desktop packaged smoke:
   - Run `F:\src\Package\Script\Python\multi_agent_tcp\start-gulicode-desktop.cmd --packaged`.
   - Verify the produced app launches from `dist/packaged-launch/current/win-unpacked/GuLiCode Dev.exe`.
   - Verify Electron main log reaches `main window created`.

2. Icon and branding smoke:
   - Verify the packaged `exe` carries the GuLiCode icon.
   - Verify `dist/win-unpacked/GuLiCode Dev.exe` carries the GuLiCode icon
     after the `rcedit` patch, not the stale Electron icon.
   - Verify the generated NSIS installer is rebuilt after the icon patch.
   - Verify the new-session center surface still says `GULI`.
   - Verify the session header blueprint button renders and toggles the blueprint panel.

3. Blueprint embedding smoke:
   - Click the blueprint entry in the session header.
   - Verify the right-side blueprint panel opens with an Agent/Route seed
     graph; Start/End terminals should not appear in new product-facing
     blueprints.
   - Drag the session/blueprint divider and verify both panes resize like the review side panel.
   - Zoom with the mouse wheel.
   - Pan the canvas with right-click drag; left-click drag on blank canvas should not pan.
   - Left-click a node to select it without opening the inspector.
   - Double-click a node, or use the right-click node menu `Edit`, to open the inspector.
   - Use the `Add node` dropdown to create Agent, Route sequence, Route parallel,
     and Route parallel_reduce nodes. Start/End should not appear in current
     product-facing Add Node UI.
   - Drag an add-node menu item onto the canvas and verify the dropped position
     snaps to the 24px grid.
   - Drag from an output port to an input port and verify a port-aware `exec`
     edge appears.
   - Delete nodes and edges through right-click menu / inspector action /
     `Backspace` / `Delete`, and verify connected edges are removed with their node.
   - Verify the inspector collapses when no inspected target remains.
   - Edit Agent, Route, and Edge inspector fields; JSON fields should show an
     invalid state while preserving the previous parsed value.
   - Verify the top-left common config panel controls project workdir, skill
     dir, and rule dir.
   - Verify the Agent inspector does not show editable command, cwd,
     workspace id/root, read/write/artifact scope, or raw skill_selection
     fields.
   - Verify skill and rule multi-select dropdowns reflect the selected
     directories and preserve selected values across save/reopen.
   - Switch CLI kind between `codex` and `codex`; verify the model dropdown
     enters loading state, keeps the current value on failure, and refreshes
     choices when the CLI command succeeds.
   - Click each inspector `?` tip button class in the current section and
     verify the popover explains both what the field is and what it is used for.
   - Verify inspector labels, the header text, and question buttons remain
     light-colored on the dark inspector surface.
   - Verify select controls and native option popups remain readable in the
     dark theme, especially the `nonblocking` / `非阻塞` option.
   - Verify node fills and borders remain visually separated from the canvas
     background while keeping the dark/technology/minimal direction.
   - Close and reopen the panel, then refresh and verify the local draft
     persists.
   - Close the blueprint panel and verify the previous session/review/file-tree layout remains usable.

4. Runtime/UI contract smoke:
   - Keep the rule that renderer surfaces consume runtime/control-plane state instead of rebuilding graph scheduling locally.
   - Keep durable Agent outputs flowing through framework APIs: `agent.dispatch`, Workspace API, `join.contribute`, and later structured task APIs.

## Deferred / Secondary Tracks

### CLI backend adapters

Continue maintaining Codex/Codex adapters and `CLIWorkerBackend`, but do not let adapter mechanics drive product architecture.

See [`multi_cli_adapter_tasks.md`](multi_cli_adapter_tasks.md).

### Legacy Ryven/editor line

The old Ryven/editor UI line was removed from the active skill snapshot on 2026-05-13. Recover it from git history or old archives only if the user explicitly asks to restart that track.

## Validation Snapshot

Most recent desktop productization smoke observed during this round:

```text
F:\src\Package\Script\Python\multi_agent_tcp\start-gulicode-desktop.cmd --packaged
-> builds packaged desktop app
-> patches final exe icon
-> launches GuLiCode Dev from dist/packaged-launch/current/win-unpacked

C:\Users\qiuhaoxuan\AppData\Roaming\ai.opencode.desktop.dev\logs\main.log
-> creating main window
-> main window created

Additional 2026-05-14 checks:

F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\app
-> bun run build passes after blueprint panel and resizable divider work
-> bun run typecheck was blocked at that time by existing src/custom-elements.d.ts content (`../../ui/src/custom-elements.d.ts`); see 2026-05-18 checks for current passing state
-> bun test --preload ./happydom.ts ./src/pages/session/blueprint-model.test.ts ./src/pages/session/blueprint-side-panel.test.ts passes for the blueprint draft model and inspector-source boundary, including route_nodes, port-aware edges, config export, generated command, skill_selection compatibility, hidden framework-managed controls, delete cascade, runtime conversion, and grid snapping

F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\desktop-electron\dist\packaged-launch\current\win-unpacked\GuLiCode Dev.exe
-> regenerated after the blueprint divider change

F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\desktop-electron
-> bun test ./src/main/blueprint-catalog.test.ts passes for codex/codex model parsing and skill/rule directory scanning
-> bun run build passes
-> default bun run package:win can still fail in a normal Windows session on winCodeSign symlink extraction
-> successful local installer workaround: temporary electron-builder.local.config.ts, win.signAndEditExecutable=false, afterPack rcedit icon patch, CSC_IDENTITY_AUTO_DISCOVERY=false, ELECTRON_BUILDER_RCEDIT_PATH=<cached winCodeSign rcedit dir>, bunx electron-builder --win --config electron-builder.local.config.ts
-> if old dist/win-unpacked/GuLiCode Dev.exe processes are still running, builder can fail removing d3dcompiler_47.dll; close/kill those old output-dir instances and rerun
-> produced dist/opencode-electron-win-x64.exe, dist/opencode-electron-win-x64.exe.blockmap, and dist/win-unpacked/GuLiCode Dev.exe with the corrected icon
-> 2026-05-14 successful artifact timestamps: installer 18:13:35, blockmap 18:13:37, win-unpacked exe 18:13:03

Additional 2026-05-18 live runtime / Agent panel checks:

F:\src\Package\Script\Python\multi_agent_tcp
-> python -m py_compile desktop_blueprint_service.py graph_runtime.py client.py broker.py adapters.py codex_bridge.py cluster.py __main__.py test_desktop_blueprint_service.py passes
-> pytest -q test_desktop_blueprint_service.py test_multi_agent_tcp_cli.py passes with local multi-agent-tcp CLI shim
-> focused GraphRuntime queue/worker-failure tests pass

F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\app
-> bun test --preload ./happydom.ts ./src/pages/session/blueprint-model.test.ts ./src/pages/session/blueprint-side-panel.test.ts passes
-> bun run typecheck passes
-> bun run build passes

F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\desktop-electron
-> bun test ./src/main/blueprint-runtime.test.ts ./src/main/ipc-blueprint-runtime.test.ts passes
-> bun run typecheck passes
-> bun run build passes
-> packaging workaround produced dist/opencode-electron-win-x64.exe, dist/opencode-electron-win-x64.exe.blockmap, and dist/win-unpacked/GuLiCode Dev.exe

Additional 2026-05-18 Agent panel interaction / debug checks:

F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\app
-> bun test --preload ./happydom.ts ./src/pages/session/blueprint-side-panel.test.ts passes
-> bun test --preload ./happydom.ts ./src/i18n/parity.test.ts passes
-> bun run typecheck passes
-> bun run build passes

F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\desktop-electron\debug-logs\dev-20260518-151513.log
-> server ready
-> renderer dev server http://localhost:5173/
-> sidecar http://127.0.0.1:6168
-> no new Uncaught / EPERM / Cannot remove / agentHoverTimer errors observed
```
