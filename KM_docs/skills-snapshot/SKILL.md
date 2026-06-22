---
name: multi-agent-tcp
description: >-
 Work on the current multi_agent_tcp direction: gulicode-bp Codex plugin
 productization, Blueprint web workbench, GraphRuntimeControlPlane, GraphRuntime
 scheduling, plugin-controlled start plans, AgentNode queues, workspace state, events,
 and CLIWorkerBackend adapters. Use for the gulicode-bp plugin, blueprint
 workbench/debug startup, runtime start/status/end, agent dispatch,
 workspace/archive flow, per-agent private workspaces, MCP workspace tools, and
 GuLiCode desktop compatibility work.
---
# multi_agent_tcp Project Skill

Use this skill when working on the `multi_agent_tcp` repository, especially the
`gulicode-bp` Codex plugin, Blueprint web workbench, POPO-triggered Blueprint
execution, blueprint runtime, plugin-controlled start plans, multi-agent
communication, workspace isolation, MCP workspace tools, and CLI worker
adapters. Temporarily treat GuLiCode desktop, mobile, console, and hosted/server
surfaces as out of scope unless the user explicitly asks for them.

This file is intentionally short so Codex can discover the skill reliably.
Detailed context lives in the files listed below. Load only the relevant files
for the current task.

## Most Important Local Command

When the user asks to reinstall, refresh, reload, or restart the installed
`gulicode-bp` plugin after Python/runtime/framework changes, prefer this
one-step command from the repo root:

```powershell
F:\src\Package\Script\Python\multi_agent_tcp\restart-gulicode-bp-plugin.cmd -Install -SkipWebBuild -SyncFrameworkAssets -NoOpen -ProjectDir F:\src\Package\Script\Python\multi_agent_tcp
```

This command reinstalls/refreshes the personal plugin package, refreshes the
plugin runtime Python package, syncs framework assets, and restarts the plugin
service. If startup is slow or a previous run returned a health-check false
negative, add a wider health window:

```powershell
F:\src\Package\Script\Python\multi_agent_tcp\restart-gulicode-bp-plugin.cmd -Install -SkipWebBuild -SyncFrameworkAssets -NoOpen -ProjectDir F:\src\Package\Script\Python\multi_agent_tcp -HealthTimeoutSeconds 90
```

Use `-SkipWebBuild` only when
`F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\app\dist\index.html`
exists and `dist\assets\` is present. If the dist is missing or stale, rerun
without `-SkipWebBuild`; the installer can run `bun install` and build the app.
Never accept the fallback `plugins\gulicode-bp\web\index.html` page as the
Workbench.

If the one-step restart command returns exit code `1`, do not treat that as a
failure by itself, but only ignore it after checking that the installed plugin
service, POPO callback service, and MCP status are running and the Workbench
URL passes these checks:

- `<origin>/config.js` has `projectDir` equal to the requested project,
  normally `F:\src\Package\Script\Python\multi_agent_tcp`.
- The Workbench HTML is the built GuLiCode app, not the fallback page with
  `<main class="shell">`.
- `POST <origin>/api/blueprint` with the config token and
  `blueprint.list(projectDir)` returns the expected Blueprint list.

If the log says `command not found: vite`, `GuLiCode app dist is missing`, or
`fallback web UI`, that exit code `1` is a real install/build failure: install
or build the GuLiCode app first, then rerun the restart.

The script writes restart logs under:

```text
F:\src\Package\Script\Python\multi_agent_tcp\logs\restart-gulicode-bp-plugin-*.log
```

After it finishes, verify the useful health endpoints first:

```text
http://127.0.0.1:8787/api/health
http://127.0.0.1:3100/health
```

After a successful reinstall/restart, open or query the installed plugin
Workbench through `start_blueprint_workbench` or the installed script:

```powershell
C:\Users\qiuhaoxuan\plugins\gulicode-bp\.runtime\venv\Scripts\python.exe C:\Users\qiuhaoxuan\plugins\gulicode-bp\scripts\start_workbench.py --project-dir <project-dir> --blueprint-id <blueprint-id> --ready-file <ready-json>
```

For this machine's main Blueprint project, use
`F:\src\Package\Script\Python\multi_agent_tcp` as `<project-dir>`. Do not give
a Workbench URL whose decoded route or `config.js` points at a temporary Codex
worktree such as `C:\Users\qiuhaoxuan\.codex\worktrees\...` unless the user
explicitly asked to debug that worktree.

When the user asked for one-click reinstall/restart and did not ask for logs or
diagnostics, the final response should default to only the plugin Workbench URL
as a Markdown link. Do not include POPO callback URLs, health URLs, process
details, or restart-log summaries unless the restart failed or the user asks for
those details.

## Current Center

The active product direction is:

```text
gulicode-bp Codex plugin
  -> local Blueprint web workbench
  -> POPO callback and Blueprint session message entry
  -> GraphRuntimeControlPlane
  -> GraphRuntime
  -> AgentNode queues, outgoing batches, joins, workspace state, events
  -> CLIWorkerBackend
  -> AgentTCPClient / Broker / CLIAdapter / worker process
```

Interpretation rules:

- Treat `gulicode-bp` as the default user-facing development/debug entrypoint.
- Treat the Blueprint web workbench as a plugin-served surface backed by the
  existing GuLiCode app build and Python runtime service.
- Focus current implementation on the plugin and POPO invocation chain.
- Do not include `/mobile`, `/console`, GuLiCode desktop/Electron, or hosted
  server product work in the default scope. Use those paths only when the user
  explicitly asks for that surface.
- Treat `GraphRuntimeControlPlane` and `GraphRuntime` as the framework-owned
  execution center.
- Treat Codex desktop control as two explicit actions: set the saved start
  AgentNode, then execute a caller-provided plan against that saved start node.
- Treat low-level TCP workers as a backend adapter path, not the product
  architecture center.
- Prefer `CLIWorkerBackend` in new writing. Mention `CodeMakerCluster` only as a
  backward-compatible alias for the old cluster facade.
- Keep Codex-first adapter work as the default for live blueprint smoke,
  streaming, and MCP workspace-tool validation.
- Do not revive the retired Ryven/editor UI line unless the user explicitly asks
  for it.

Current common local root:

```text
F:\src\Package\Script\Python\multi_agent_tcp
```

Historical paths such as `D:\agents\multi_agent_tcp` may appear in archive
notes. Do not use them as current defaults unless they exist on this machine.

## Start Here

Read these first based on the task:

- Project architecture and ownership:
  `knowledge_base/core_architecture.md`
- GuLiCode desktop startup, packaging, and shell/runtime layering for explicit
  desktop work:
  `knowledge_base/gulicode_desktop.md`
- GuLiCode app UI, plugin-served blueprint workbench, mobile/console debug
  surfaces, and renderer conventions:
  `knowledge_base/guli_desktop_ui.md`
- Runtime control-plane CLI/RPC flows:
  `knowledge_base/dispatch_workflows.md`
- Plugin start-plan governance and multi-agent communication design:
  `多agents通信设计.md`
- Registry, skill selection, and skill injection:
  `knowledge_base/registry_and_skills.md`
- CLI adapter/backend history and constraints:
  `knowledge_base/multi_cli_workflow.md`
- Environment setup and machine-specific diagnostics:
  `environment_setup.md`
- Current active priorities:
  `tasks/current_goals.md`
- Historical plugin-first debug startup workflow:
  `knowledge_base/debug_start.md`

## Recent Handoff

For the latest persistent POPO start-Agent session, Codex app-server thread
reuse, in-flight `turn/steer` injection, callback timeout silence, and restart
orphan worker cleanup from 2026-06-18:

- Runtime/backend POPO-bound saved start full Agents now use a
  `codex_app_server` backend by default, keep one Codex thread for the active
  POPO `sessionKey`, inject transcript history only on activation/re-activation,
  steer in-flight POPO messages into the active Codex turn when possible, and
  fall back to the existing Agent queue when steer is rejected:
  `archive/runtime-backend/blueprint_popo_persistent_codex_session_steer_cleanup_2026-06-18.md`
- The POPO callback no longer sends `蓝图运行仍在处理中` for a still-running
  persistent run, and `restart-gulicode-bp-plugin.ps1` now kills plugin-owned
  `multi_agent_tcp_cluster` broker/agent process trees so child
  `codex app-server --listen stdio://` processes cannot survive restart as
  orphans:
  `archive/runtime-backend/blueprint_popo_persistent_codex_session_steer_cleanup_2026-06-18.md`

Use this file when the user reports:

- POPO messages within 10 minutes do not reach the same Agent/Codex thread.
- later active-run POPO messages repeat `[Recent BlueprintSession Messages]`.
- a busy Agent ignores or fails to receive an in-flight POPO steer message.
- POPO users receive the framework status text `蓝图运行仍在处理中`.
- plugin restart leaves `multi_agent_tcp_cluster` or `codex app-server`
  processes behind.

For the latest POPO file-only attachment delay, fileId download, and POPO
file-send token refresh from 2026-06-17:

- Runtime/backend POPO callback now downloads `fileInfo.fileId` attachments to
  absolute local paths, caches non-image file-only messages until the user's
  next ordinary text message, accumulates multiple files in order, keeps images
  immediate, clears pending files on `/new` and `/stop`, and fixes
  `blueprint_send_popo_file` / `file_sender.send(path)` upload failures by
  sending `Open-Access-Token` to `uploadUrl` and retrying once after token
  expiry:
  `archive/runtime-backend/blueprint_popo_file_attachment_delay_token_refresh_2026-06-17.md`

Use this file when the user reports:

- a POPO file-only message reaches the Agent before the next text message.
- a POPO file attachment is unresolved or lacks an absolute path.
- a POPO callback has `fileInfo.fileId` but no direct file URL.
- multiple uploaded POPO files should be delivered with one later text message.
- `/new`, `/stop`, `/help`, or `/excel-log` consumes pending files incorrectly.
- `blueprint_send_popo_file` or `file_sender.send(path)` fails with
  `access token expired` while the local file exists.

For the latest one-click reinstall/restart script hardening, Workbench
`ProjectDir` binding, fallback web UI refusal, and exit-code-1 diagnosis from
2026-06-17:

- Installer/runtime script changes ensure `--skip-web-build` cannot silently
  install the fallback Workbench, missing `vite` triggers `bun install`, restart
  scripts pass and verify the target `ProjectDir`, and one-click restart should
  default to the main project Workbench URL:
  `archive/runtime-backend/gulicode_bp_reinstall_workbench_guardrail_2026-06-17.md`

Use this file when the user reports:

- a Workbench URL points at `C:\Users\qiuhaoxuan\.codex\worktrees\...` instead
  of `F:\src\Package\Script\Python\multi_agent_tcp`.
- reinstall/restart returns exit code `1` and the cause may be a real build
  failure.
- logs mention `command not found: vite`, missing GuLiCode app dist, or
  `fallback web UI`.
- the installed Workbench shows the simple fallback page instead of the built
  GuLiCode app.

For the latest Blueprint slot termination hardening, POPO concurrent session
write fix, framework-forwarded start-Agent POPO replies, and POPO `/new`
confirmation behavior from 2026-06-10:

- Runtime/backend `blueprint.slots.terminate` structure-level forced cleanup,
  `session.json` unique temp writes and Windows retry, ordinary start-Agent
  replies forwarded to POPO with `messageId` transcript fields, and `/new`
  returning `已开启新会话`:
  `archive/runtime-backend/blueprint_slot_termination_popo_direct_reply_new_session_2026-06-10.md`

Use this file when the user reports:

- `终止运行槽` only killed one instance or left queued/running sessions behind.
- POPO callback fails with `[WinError 5] 拒绝访问` while replacing
  `session.json`.
- POPO receives no final reply even though Workbench shows an ordinary start
  Agent reply.
- POPO `/new` clears the session but appears stuck because there is no
  confirmation.

For the latest Blueprint session-slot lifecycle, framework-managed session
termination, POPO callback resilience, and Agent panel transcript timeline work
from 2026-06-10:

- Runtime/backend structure-level slot summaries, per-pool max three active
  sessions, queued sessions, removal of Agent-visible
  `blueprint_terminate_session`, framework idle auto termination, POPO callback
  local-route fallback, `agent_info()` service-lock fix, and POPO reply
  auto-task-status behavior:
  `archive/runtime-backend/blueprint_session_slots_framework_auto_popo_resilience_2026-06-10.md`
- Workbench current-session vs Blueprint-slot status card, active/queued
  session counts, session terminate / slot terminate actions,
  transcript-backed Agent panel timeline, maintenance-event filtering, and
  stream text null-guard crash fix:
  `archive/frontend/blueprint_session_slot_panel_timeline_2026-06-10.md`

Use those files when the user reports:

- A POPO message was sent but did not enter the Blueprint session transcript.
- `/popo/callback` returns 500 because callback config lookup timed out.
- The main runtime or callback config query is unresponsive while the Agent
  information panel is open.
- An Agent can see or call `blueprint_terminate_session`, or a run slot is
  completed by an Agent instead of by UI/framework policy.
- The runtime panel confuses session count, live run instance count, and
  structure-level Blueprint slot status.
- The Agent panel shows task-status/summary/session-maintenance text as a
  normal Agent reply.

For readable POPO session keys from 2026-06-09:

- Runtime/backend service-side receiver ownership via saved `popoReplyTo`,
  POPO send helper, transcript `agent_reply` / `popo_reply_sent` events,
  readable `bps_popo_<user>_<hash>` session keys, and legacy `bps_<hash>`
  migration:
  `archive/runtime-backend/blueprint_popo_reply_tool_readable_sessions_2026-06-09.md`
- Workbench session dropdown `sessionDisplayName` support, session-key-first
  display, and POPO user-readable second-line label:
  `archive/frontend/blueprint_popo_readable_session_list_2026-06-09.md`

Use those files when the user reports:

- A POPO-started Agent can see the message but its ordinary final reply is not
  forwarded to the POPO user.
- POPO reply target selection is wrong for private or group conversations.
- The session list shows only opaque `bps_<hash>` ids instead of including the
  POPO user such as `qiuhaoxuan`.
- Existing old POPO sessions do not migrate to readable `bps_popo_...` keys.

For the latest POPO callback service global robot route configuration and
Workbench control drawer work from 2026-06-09:

- Runtime/backend plugin-level POPO callback robot allowlist
  `popo_robot_routes.json`, internal list/save/delete/toggle commands,
  `blueprint.popo.callbackConfig`, legacy `/popo/callback` unique-enabled auto
  resolution, multi-enabled conflict behavior, and MCP public/internal
  credential boundary:
  `archive/runtime-backend/blueprint_popo_global_callback_routes_2026-06-09.md`
- Workbench Blueprint Control drawer, POPO Callback Service panel, service
  status/callback URL display, robot enable checkbox and credential editor, and
  collaboration panel relocation into the drawer:
  `archive/frontend/blueprint_popo_global_callback_service_drawer_2026-06-09.md`

Use those files when the user reports:

- `/popo/callback/<robot_app_key>` accepts or rejects the wrong robot.
- Legacy `/popo/callback` should auto resolve one enabled robot or reject
  multiple enabled robots.
- `blueprint.popo.robots` or related Workbench API calls return
  `UNKNOWN_COMMAND`.
- The Blueprint Control drawer or POPO Callback Service panel is missing from
  the Workbench.
- A packaged plugin still uses old POPO callback credentials after rebuild or
  restart.
- Public Codex MCP exposes or can mutate POPO callback robot credentials.

For the latest POPO Blueprint session identity, start-Agent ownership, idle
termination, and agent-level POPO Inspector work from 2026-06-09:

- Runtime/backend direct Workbench session key `main+<blueprintId>`, POPO
  session-key separation, agent-level `popo_entry` validation, `/new` session
  clear behavior, POPO idle termination checks, start-Agent-only
  `blueprint_terminate_session` MCP tool, plugin rebuild/restart, and smoke
  results:
  `archive/runtime-backend/blueprint_popo_session_identity_termination_2026-06-09.md`
- Workbench full-Agent `popo_entry` model, legacy runtime POPO migration,
  Inspector disabled-state reasons, saved-start-only POPO editability, previous
  start-Agent POPO clearing, POPO Blueprint indicator, i18n, frontend tests, and
  page smoke:
  `archive/frontend/blueprint_agent_level_popo_entry_ui_2026-06-09.md`

Use those files when the user reports:

- Direct Blueprint run-slot messages still create `bps_...` sessions instead of
  using `main+<blueprintId>`.
- POPO forwarding appears editable on the wrong full Agent, multiple full
  Agents can enable POPO, or the disabled reason is unclear.
- A POPO-enabled full Agent is not forced to be the saved start Agent.
- A POPO Blueprint is missing its visual indicator.
- `/new` does not clear the expected Blueprint session history.
- POPO Blueprint sessions do not ask the start full Agent whether to terminate
  when all Agents, ScriptNodes, and resident-service calls are idle.
- `blueprint_terminate_session` is missing for the POPO start Agent or is
  exposed to the wrong Agent.

For the latest Blueprint sessions, run slots, POPO entry, Codex start-agent
setting, and MCP boundary work from 2026-06-05:

- Runtime/backend session storage, run-slot assignment, POPO singleton-service
  routing, Codex desktop `setStartAgent` / `executePlan`, run-scoped monitor
  tools, public/internal MCP boundaries, Workbench internal slot bridge fix, and
  automated test results:
  `archive/runtime-backend/blueprint_sessions_slots_popo_mcp_2026-06-05.md`
- Workbench sessions dropdown, Blueprint run-slot panel, single AgentNode start
  selector, POPO entry inspector fields, monitor-tools toggle, platform bridge
  methods, browser smoke, and UI test results:
  `archive/frontend/blueprint_sessions_slots_popo_entry_ui_2026-06-05.md`

Use those files when the user reports:

- Blueprint sessions are unclear, missing from the toolbar, not scrolling, or
  cannot be deleted correctly
- "Blueprint run slot" start/message UI returns `UNKNOWN_COMMAND` or does not
  show POPO entry errors
- `runtime.start_node_id` is not saved, the start node selector is empty, or a
  plan starts from a node other than the saved AgentNode
- POPO robot app key/config binding, session routing, or slot load balancing is
  behaving unexpectedly
- Codex desktop should set the start Agent separately from executing a specified
  plan
- public MCP tools should expose `blueprint_set_start_agent` /
  `blueprint_execute_plan` but not `blueprint.slots.*`
- full AgentNode Blueprint monitor tools need run-scoped status/events/diff
  access without cross-run mutation

For the latest `table_queue_service` ScriptNode help/schema pattern and
table-occupation resident service work from 2026-06-08:

- `table_queue_service` as the reference design for ScriptNodes that expose
  multiple operations through `action` + `arguments`, targeted `help`/`schema`
  behavior, script-only resident service gating, valid table name validation,
  and `refresh_valid_tables` running SVN update before scanning `.xlsx` files:
  `archive/runtime-backend/blueprint_table_queue_script_help_pattern_2026-06-08.md`

Use that file when the user reports:

- a future ScriptNode needs an Agent-facing help/schema contract
- an Agent is unsure what structure to pass to a ScriptNode
- a ScriptNode multiplexes operations through `action` + `arguments`
- `table_queue_service` action formats, unknown-action behavior, or schema
  output size need clarification
- table occupation requests should reject unknown `.xlsx` names
- `refresh_valid_tables` should update SVN before reading table names

For the latest Blueprint resident service and Script Function Node boundary
notes, plus a real AgentNode `xltool` resident-service write smoke from
2026-06-08:

- Script Function Node project scope, resident service global plugin runtime
  scope, service `description` ownership, synchronous
  `blueprint_service_call` return behavior, `xltool` service shape, live Excel
  write smoke result, and known service-result/Windows archive follow-ups:
  `archive/runtime-backend/blueprint_resident_services_script_nodes_xltool_smoke_2026-06-08.md`

Use that file when the user reports:

- an AgentNode cannot discover or call a resident service
- resident service `description` text is unclear or stale
- `blueprint_service_call` timing/result behavior is ambiguous
- Script Function Nodes and resident services are being conflated
- `xltool` resident-service Excel writes need a known-good smoke reference
- a successful Blueprint run is marked failed during Windows archive/close

For the latest Blueprint resident services panel pagination/search/collapse
work from 2026-06-05:

- Resident services panel local search, fixed five-item pagination, header
  collapse/expand, dedicated refresh action, no-match empty-state fix, i18n, and
  browser smoke:
  `archive/frontend/blueprint_resident_services_panel_search_pagination_collapse_2026-06-05.md`

Use that file when the user reports:

- the resident services panel should show only five services per page
- resident service search, no-match copy, or page clamping behaves incorrectly
- the resident services panel header should collapse/expand instead of looking
  like a close button
- pagination buttons or localized resident service labels are missing
- a packaged Workbench still shows the old resident services panel after plugin
  rebuild/restart

For the latest Blueprint Prompt editor and popout chrome polish from
2026-06-03:

- Prompt node compact canvas editing, double-click draggable/resizable editor
  dialog, custom resize handle, Escape close behavior, hidden redundant
  Blueprint popout title bar, and browser smoke:
  `archive/frontend/blueprint_prompt_editor_popout_chrome_2026-06-03.md`

Use that file when the user reports:

- Prompt node double-click editing should open a separate text dialog
- the Prompt editor dialog cannot be dragged by its title bar
- the Prompt editor dialog cannot be resized from the bottom-right handle
- dragging/resizing Prompt dialogs behaves incorrectly after canvas pan/zoom
- `/blueprint-window/...` still shows the redundant top title bar, dock button,
  or close button above the real Blueprint toolbar

For the latest Blueprint Prompt node and Agent port expansion work from
2026-06-02:

- Prompt node model/UI, editable prompt text, once/always trigger controls,
  fixed Agent `prompt: str` input, expandable Agent port rows, and frontend
  smoke:
  `archive/frontend/blueprint_prompt_node_agent_ports_ui_2026-06-02.md`
- Python `PromptNode`, `GraphDefinition.prompt_nodes`, fixed Agent prompt-port
  validation, once/always prompt injection, no-op dispatch behavior, and runtime
  tests:
  `archive/runtime-backend/blueprint_prompt_node_runtime_2026-06-02.md`

Use those files when the user reports:

- Prompt nodes are missing from node search, do not expand into a textarea, or
  do not save trigger mode.
- Agent/Worker Agent nodes should show fixed port rows like Script nodes, the
  `prompt: str` triangle pin is missing, or the old add/remove prompt menu
  appears.
- `PromptNode(out)` cannot connect to `Agent(prompt)`, creates an exec edge
  instead of a data edge, or non-Prompt sources can target Agent `prompt`.
- Prompt text does not inject with legacy `run_prompt`, once/always behavior is
  wrong, or no-op dispatches consume once prompts.

For the latest `gulicode-bp` MCP direct-control start and live close-loop work
from 2026-06-02:

- Workbench planning inbox removal, Codex MCP direct start plan
  create/validate/start flow, live-start nonblocking return with
  `startPending`, terminal manifest persistence, Windows long-path workspace
  copy fixes, installed runtime wheel refresh, and direct smoke results:
  `archive/runtime-backend/gulicode_bp_mcp_direct_start_live_close_loop_2026-06-02.md`

Use that file when the user reports:

- Workbench still exposes planning-request UI or task text for plan generation
- `blueprint_start` hangs, times out, or creates a run but does not return
- MCP/UI status disagree after a live start
- cancelled runs leave `run_manifest.status=running`
- long Windows paths under `.bun` / `node_modules` break run workspace snapshot
- packaged plugin runtime still runs stale Python after source changes

For the latest Workbench external-run synchronization work from 2026-06-02:

- Planning button/task textarea removal in the runtime panel, direct-run UI
  retention, periodic `listBlueprintRuns` sync, active-run preference, and the
  Ctrl+R workaround fix for already-open Workbench tabs:
  `archive/frontend/blueprint_workbench_external_run_sync_2026-06-02.md`

Use that file when the user reports:

- Codex MCP starts a Blueprint run but the already-open Workbench still shows an
  old `CANCELLED` run
- pressing Ctrl+R makes the correct running run appear
- Workbench should observe external MCP starts without a browser refresh

For the latest `gulicode-bp` plugin singleton service and reload work from
2026-06-02:

- Codex-plugin-only singleton service boundary, stateless stdio MCP proxies,
  `service.lock` / `service.json` / `service.log.jsonl`, Workbench attach
  wrapper, owner takeover, planning-request reassignment, duplicate active-run
  guard, canonical personal-plugin `.runtime` state, Windows venv launcher
  cleanup, and final clean reload process inventory:
  `archive/runtime-backend/gulicode_bp_plugin_singleton_service_2026-06-02.md`

Use that file when the user reports:

- duplicate `gulicode_bp_mcp.py --service`, Workbench, live-run registry, or
  plugin-managed Collaboration Server ownership
- uncertainty about which plugin processes must be unique versus allowed
  Codex-side bootstrap/proxy access processes
- stale `service.json`, `service.lock`, or singleton health after killing or
  reloading the plugin
- planning requests moving between Codex threads or owner takeover behavior
- duplicate active blueprint starts for the same `projectDir + blueprintId`

For the latest `gulicode-bp` MCP transport, bootstrap lock, and status logging
work from 2026-06-02:

- Transport/bootstrap/Workbench lifecycle boundaries, dead-PID bootstrap lock
  cleanup, bootstrap/MCP logs, `mcp_status.json` heartbeat diagnostics, Codex
  stdio reconnect boundary after `Transport closed`, and plugin manifest
  default prompt limit:
  `archive/runtime-backend/gulicode_bp_mcp_transport_bootstrap_logging_2026-06-02.md`

Use that file when the user reports:

- `gulicode-bp` MCP tools are visible but calls return `Transport closed`
- Workbench is open but MCP tools cannot be called
- MCP startup appears stuck behind `bootstrap.lock`
- `mcp_status.json` says `running` while the MCP process is gone or stale
- the user asks what transport, bootstrap, or Workbench means
- Codex warns that `interface.defaultPrompt` has too many prompts

For the latest `gulicode-bp` first-run bootstrap and packaging work from
2026-06-01:

- New-user standalone install path, `.runtime/venv` first-run bootstrap,
  bootstrap MCP entrypoint, Windows re-entry behavior, release package layout,
  fixed `package-gulicode-bp-plugin.cmd` packaging command, release smoke, and
  release-versus-trunk semantics:
  `archive/runtime-backend/gulicode_bp_first_run_bootstrap_packaging_2026-06-01.md`

Use that file when the user reports:

- a new Codex user cannot run `gulicode-bp` without local `multi_agent_tcp`
  source
- `.runtime/venv` is missing, stale, locked, or not loading from plugin-owned
  site-packages
- `.mcp.json` still points at repo-local Python, `PYTHONPATH`, or
  `GULICODE_BP_REPO_ROOT`
- release packages include `.runtime`, lack `runtime/wheels`, or need package
  shape verification
- the user asks what `release` versus trunk/source means
- the user says `鎵撳寘`, `鎻掍欢鎵撳寘`, or `package`

For the latest `gulicode-bp` standalone runtime and Codex fan-out smoke work
from 2026-06-01:

- Plugin-owned runtime venv install/cache sync, installer repair behavior,
  MCP event-loop `asyncio.run()` fix, queued outgoing-target reminders,
  reminder race guards, `fanout-worker-smoke`, and Codex live fan-out smoke:
  `archive/runtime-backend/gulicode_bp_standalone_codex_fanout_runtime_2026-06-01.md`

Use that file when the user reports:

- installed `gulicode-bp` still depends on local repo source or stale Codex
  cache `.mcp.json`
- `blueprint_start` fails inside MCP with `asyncio.run() cannot be called from
  a running event loop`
- fan-out runs leave `remaining_targets` stuck or reminders create duplicate
  batches
- a side-browser workbench URL shows `ERR_CONNECTION_REFUSED` after runtime
  restart
- live worker smoke should use Codex rather than CodeMaker

For the latest `gulicode-bp` plugin direct-control and start-plan work from
2026-06-01:

- Plugin CRUD MCP/API, deterministic `blueprint.plan.create`,
  `blueprint.plan.validate`, confirmed `blueprint_start`, Top Agent wording
  removal, two-step workbench run UI, and the current P0 standalone-distribution
  boundary:
  `archive/runtime-backend/gulicode_bp_plugin_direct_control_start_plan_2026-06-01.md`

Use that file when the user reports:

- installing `gulicode-bp` without a local `multi_agent_tcp` checkout does not
  work
- Blueprint CRUD, plan creation/validation, or confirmed start should be driven
  directly by plugin MCP tools
- the UI still exposes Top Agent planning language or skips the generate-plan
  confirmation step

For the latest Agent and Script Function Node interaction work from
2026-05-31:

- Agent -> Script multi-input fan-out, Script multi-output -> Agent fan-in,
  true sibling edges, hub rendering, and group hover/select/delete:
  `archive/frontend/blueprint_agent_script_fan_edges_2026-05-31.md`
- Ordinary-Agent `blueprint_script_call` MCP tool, batch `script_calls` state,
  idle reminders, script execution events, and automatic downstream Agent
  delivery:
  `archive/runtime-backend/blueprint_script_call_mcp_runtime_2026-05-31.md`
- GuLiCode desktop debug loopback issue where stale `127.0.0.1:5173` blocked
  renderer health while `[::1]:5173` worked:
  `archive/runtime-backend/gulicode_desktop_debug_loopback_renderer_2026-05-31.md`

Use those files when the user reports:

- Agent -> Script or Script -> Agent connections should fan across all script
  ports, delete as a group, or render with a hub.
- Agents are not calling Script Function Nodes, `required_script_calls` is
  missing, `blueprint_script_call` is unavailable, or downstream Script output
  is not automatically delivered to Agents.
- `agent.dispatch` incorrectly bypasses a Script Function Node path.
- GuLiCode desktop appears to have an Electron process and bridge but the
  window is blank or the debug launcher reports desktop failure while
  `[::1]:5173` is healthy.

For the latest built-in Blueprint Branch/Tick common node work from 2026-05-31:

- Branch/Tick node search, common node graph model, port type validation,
  Inspector edge validation, Tick-only direct-run allowance, and Branch pin
  labels/triangle input:
  `archive/frontend/blueprint_common_nodes_branch_tick_ui_type_ports_2026-05-31.md`
- Python `CommonNode`, `common_nodes` graph parsing, backend port type
  validation, `agent.dispatch` to Branch, Branch strict-bool routing, Tick
  scheduling/backpressure, and common-node status:
  `archive/runtime-backend/blueprint_common_nodes_branch_tick_runtime_2026-05-31.md`

Use those files when the user reports:

- Branch/Tick nodes are missing from node search or serialize incorrectly
- Branch pins should show `condition: bool`, `true: message`, or
  `false: message`
- invalid `tick -> bool` or other typed-port connections are accepted
- canvas drag connection and Inspector edge edits disagree
- Tick-only start-plan generation incorrectly requires a selected start node
- `common_nodes` JSON fails to load, Branch dispatch does not route, or Tick
  cadence/backpressure/status looks wrong

For the latest Blueprint Script Function Node work from 2026-05-31:

- Right-click node search, Script Function Node creation dialog, IDE selector,
  compile button, dynamic script ports, and Python-style node visual:
  `archive/frontend/blueprint_script_function_node_ui_ide_compile_2026-05-31.md`
- Python `@blueprint_node` discovery/execution, `.multi_agent_workspace/scripts`
  management, desktop bridge commands, editor discovery/opening, and runtime
  Agent -> Script -> Agent flow:
  `archive/runtime-backend/blueprint_script_function_node_runtime_bridge_2026-05-31.md`

Use those files when the user reports:

- right-click node search or the Script Function Node `+` flow is wrong
- the toolbar Script editor selector, "system default" fallback, or script
  double-click open behavior is wrong
- the Blueprint Compile button does not refresh script signatures/ports
- Script Function Node visual shape, collapse/expand, or port rendering is
  wrong
- `blueprint.scriptNodes` / `blueprint.createScriptNode` fails, script catalog
  scanning imports user code, or Agent -> Script -> Agent dispatch fails

For the latest full CLI Agent / Worker Agent split from 2026-05-30:

- Full CLI `Agent` node UI, access-policy inspector, i18n, and opaque
  light-green visual treatment:
  `archive/frontend/blueprint_full_agent_node_ui_2026-05-30.md`
- Full `Agent` runtime launch semantics, message-only MCP scope, and real
  Codex end-to-end smoke:
  `archive/runtime-backend/blueprint_full_agent_runtime_real_codex_smoke_2026-05-30.md`

Use those files when the user reports:

- the add-node menu, inspector, or visible name for `Agent` / `Worker Agent` is
  wrong
- full `Agent` nodes are not opaque light green
- a full `Agent` unexpectedly gets private workspace or workspace MCP tools
- `worker_agent` can bypass sandbox or dangerous access policy
- real Codex full-Agent dispatch through `agent_dispatch` needs to be checked

For the latest Blueprint Agent model/runtime cleanup from 2026-05-29:

- Test Agent merge into normal Agent UI, global Agent panel JSON test-log
  switch, Agent `简介` / `提示词` split, and frontend tests:
  `archive/frontend/blueprint_agent_prompt_log_cleanup_2026-05-29.md`
- Hidden Windows worker/adapter launches and per-run `run_prompt` runtime
  injection:
  `archive/runtime-backend/blueprint_hidden_console_run_prompt_2026-05-29.md`

Use those files when the user reports:

- Test Agent nodes or yellow test styling still appear in the Blueprint UI
- Agent panel test JSON snapshots are missing, unexpectedly produced, or need
  the global switch behavior checked
- Agent inspector `简介` / `提示词` behavior is unclear
- Blueprint startup opens visible terminal windows
- `run_prompt` is injected repeatedly or not injected on first dispatch

For the latest Collaboration Server `/mobile` desktop-bridge work from
2026-05-29:

- Account-level desktop bridge, mobile chat, composer mode sync, structured
  segments, and tick/scroll fixes:
  `archive/future-server/collaboration_server_desktop_bridge_mobile_chat_2026-05-29.md`

Use that file when the user reports:

- mobile chat send reaches desktop but does not appear on `/mobile`
- `/mobile` mode selector is missing desktop agents or `蓝图规划`
- reasoning/tool disclosures close, resize, or jump scroll during tick refresh
- desktop session mirror or `desktop.session.submit` behavior is unclear

For the latest blueprint multi-document and direct-run work from 2026-05-30:

- Project blueprint dropdown, new blueprint dialog, current blueprint id
  binding, and direct live run button:
  `archive/frontend/blueprint_multi_document_direct_run_2026-05-30.md`

Use that file when the user reports:

- the Blueprint toolbar dropdown, project blueprint switching, or new blueprint
  creation is wrong
- runtime `Confirm run` should start live only after a generated start plan
- start-plan generation does not require or respect selected start nodes
- plugin start-plan generation starts the wrong blueprint document

For earlier blueprint panel work from 2026-05-25:

- Progress overlay and staged-plan sync:
  `archive/frontend/blueprint_flow_progress_overlay_plan_sync_2026-05-25.md`
- Runtime visual flow and pending filter:
  `archive/frontend/blueprint_runtime_visual_flow_pending_filter_2026-05-25.md`

Use those files when the user reports:

- blueprint submit progress is missing or stuck
- the start-plan preview card does not appear
- the blueprint panel overlay/mask behavior is wrong
- runtime node glow, edge flow, or pending task filtering looks wrong

## Archive Structure

Archive records are split by ownership:

- `archive/frontend/`: GuLiCode renderer/app UI, blueprint side panel, session
  composer planning UX, CSS/i18n, popout windows, and UI tests.
- `archive/runtime-backend/`: GraphRuntime, GraphRuntimeControlPlane, Blueprint
  MCP runtime, DesktopBlueprintService, AgentTCP, CLIWorkerBackend, queues,
  workspaces, and local desktop service behavior.
- `archive/future-server/`: reserved for future hosted/server-side product work.

Archives are historical records. Prefer current `knowledge_base/` and `tasks/`
files for implementation decisions unless an archive is explicitly called out.

## Query Map

- Local environment setup, Python/Bun/Codex paths, PowerShell script policy,
  localhost MCP `502` / `503`, proxy, `NO_PROXY`, and repo `skill_list`:
  read `environment_setup.md`.
- GuLiCode desktop startup, packaged bring-up, taskbar icon, and direct
  Electron fallback: read `knowledge_base/gulicode_desktop.md`; use it only
  for explicit desktop-shell work.
- When the user says `调试启动`: read `knowledge_base/debug_start.md`, then
  start the `gulicode-bp` plugin workbench, the Collaboration Server, the app
  dev server, the mock mobile `/mobile` client, and the `/console` server
  console. Do not start the GuLiCode Electron desktop unless explicitly asked.
- Desktop UI ownership, branding, icon replacement, empty-state wording,
  blueprint entry placement, and blueprint workbench embedding:
  read `knowledge_base/guli_desktop_ui.md`, then
  `tasks/guli_desktop_ui_tasks.md`.
- Agent information panel interactions, task status display, automatic run
  summary, long-press progress, Markdown reply rendering, context menu,
  move/resize behavior, Test Agent JSON snapshots, and clean desktop debug:
  read `archive/frontend/blueprint_agent_task_panel_auto_top_summary_2026-05-22.md`
  plus the relevant `archive/frontend/agent_info_panel_*` files.
- GuLiCode plugin control, organization view, start plan, and status
  explanation: read `多agents通信设计.md`, then
  `tasks/multi_agent_communication_tasks.md`.
- Runtime start/status/end, organization, message batch, agent dispatch,
  join-create, and join-contribute: read `knowledge_base/dispatch_workflows.md`.
- Current architecture or component ownership:
  read `knowledge_base/core_architecture.md`.
- `GraphDefinition.agent_cycle_groups()` and cycle/loop handling:
  read `knowledge_base/ring_structure_solution.md`, then
  `knowledge_base/core_architecture.md`.
- Legacy `CodeMakerCluster`, `run_parallel`, `run_chain`, broker, and TCP worker
  path: read `knowledge_base/cluster_api.md`.
- Workspace API, changesets, archive, private checkout, conflict flow, and MCP
  workspace tools: read `knowledge_base/core_architecture.md` and
  `tasks/multi_agent_communication_tasks.md`.
- Multi CLI adapters, Codex/CodeMaker process adapters, and `CLIAdapter`:
  read `knowledge_base/multi_cli_workflow.md`.

## Working Rules

- Prefer repo-local patterns and existing tests.
- For frontend work, keep GuLiCode UI restrained, dense, and consistent with the
  current app. Avoid unrelated redesigns.
- For runtime work, keep the control-plane API as the product boundary and keep
  CLI workers as replaceable adapters.
- For ordinary agents, preserve private workspace isolation. Project mutations
  should flow through the framework workspace/MCP path, not direct writes to the
  shared project root.
- For ScriptNodes that expose multiple operations, use the `table_queue_service`
  `help`/`schema` contract as the reference: targeted help returns one schema,
  empty help returns all schemas, unknown actions return allowed actions plus a
  hint, and business calls return only business results.
- When changing skill knowledge, keep this `SKILL.md` short and move detail to
  `knowledge_base/`, `tasks/`, or `archive/`.
- When copying into `KM_docs/skills-snapshot`, mirror the current installed
  skill tree.

## Repository Link

- GitHub: https://github.com/QHXRPG-A/multi_agent_tcp
- Current common local root: `F:\src\Package\Script\Python\multi_agent_tcp`
