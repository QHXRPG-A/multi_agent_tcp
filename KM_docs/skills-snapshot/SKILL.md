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
`gulicode-bp` Codex plugin, Blueprint web workbench, blueprint runtime,
plugin-controlled start plans, multi-agent communication, workspace isolation, MCP
workspace tools, GuLiCode mobile/console debug surfaces, and CLI worker
adapters.

This file is intentionally short so Codex can discover the skill reliably.
Detailed context lives in the files listed below. Load only the relevant files
for the current task.

## Current Center

The active product direction is:

```text
gulicode-bp Codex plugin
  -> local Blueprint web workbench
  -> GuLiCode app dev surfaces: /mobile and /console
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
- Keep `/mobile` and `/console` in the default debug stack through the app dev
  server.
- Treat GuLiCode desktop/Electron as a secondary compatibility target. Start it
  only when the user asks for desktop shell, IPC, packaging, taskbar, or
  desktop-window behavior.
- Treat `GraphRuntimeControlPlane` and `GraphRuntime` as the framework-owned
  execution center.
- Treat start plan generation and validation as a `gulicode-bp` plugin
  responsibility: create/validate a plan first, show it for confirmation, then
  call `blueprint_start` with the confirmed plan.
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
- Plugin-first debug start workflow for Blueprint workbench + Collaboration
  Server + mock mobile + server console:
  `knowledge_base/debug_start.md`

## Recent Handoff

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
- When changing skill knowledge, keep this `SKILL.md` short and move detail to
  `knowledge_base/`, `tasks/`, or `archive/`.
- When copying into `KM_docs/skills-snapshot`, mirror the current installed
  skill tree.

## Repository Link

- GitHub: https://github.com/QHXRPG-A/multi_agent_tcp
- Current common local root: `F:\src\Package\Script\Python\multi_agent_tcp`
