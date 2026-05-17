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

Common repository root:

```text
F:\src\Package\Script\Python\multi_agent_tcp
```

Historical paths such as `D:\agents\multi_agent_tcp` or `F:\src\ryven_demo` may appear in archives. Do not use them as current defaults unless the user's machine actually has that path.

## Fast Handoff - 2026-05-17 Blueprint UI Runtime Status Projection

The Blueprint UI status projection layer has landed. GuLiCode now couples the
blueprint side panel to the runtime/control-plane lifecycle without starting
real CLI workers.

Completed in the current workspace:

1. `createBlueprintStartPlan(draft)` derives a deterministic start plan from
   the saved blueprint graph. It covers all AgentNode descriptions, walks start
   terminals through `exec` edges and RouteNodes to find initial AgentNodes,
   emits tasks only for those start nodes, and adds
   `{ allow_parallel: true, source: "blueprint-ui-derived" }`.
2. `desktop_blueprint_service.py` adds `blueprint.listRuns(projectDir?,
   blueprintId?)`, appends `explanation =
   runtime.explain_status(graph=graph)` to `blueprint.status`, and keeps
   `executionMode` guarded at status-only depth. `live` is explicitly rejected.
3. Electron main/IPC/preload/platform boundaries now expose
   `listBlueprintRuns`.
4. The blueprint panel Start action saves the project `BlueprintDocument`
   first, starts `default` with the derived plan, stores `runId`, polls
   `blueprint.status` / `blueprint.recentEvents(runId, 50)` every 2 seconds,
   and stops automatic polling for terminal or paused states.
5. The Runtime side panel projects Overview, Agents, Queues, Events, and
   Workspace directly from `status_snapshot` and `explain_status`.
6. Complete/Pause/Cancel controls call `blueprint.end` and immediately refresh.
7. The renderer remains a thin client: no local scheduler, queue advancement,
   fan-in, workspace/archive semantics, top-agent governance, tick loop, or
   worker lifecycle was added.

Files to start from:

- `desktop_blueprint_service.py`
- `test_desktop_blueprint_service.py`
- `GuLiCode/packages/app/src/pages/session/blueprint-model.ts`
- `GuLiCode/packages/app/src/pages/session/blueprint-model.test.ts`
- `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.tsx`
- `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.test.ts`
- `GuLiCode/packages/app/src/context/platform.tsx`
- `GuLiCode/packages/desktop-electron/src/main/blueprint-runtime.ts`
- `GuLiCode/packages/desktop-electron/src/main/blueprint-runtime.test.ts`
- `GuLiCode/packages/desktop-electron/src/main/ipc-blueprint-runtime.test.ts`
- `GuLiCode/packages/desktop-electron/src/main/ipc.ts`
- `GuLiCode/packages/desktop-electron/src/preload/index.ts`
- `GuLiCode/packages/desktop-electron/src/preload/types.ts`

Highest next priority: manual smoke this status projection in the packaged
desktop UI, then enter live execution depth only after the projection is stable.

- Verify Start saves before start, retains `runId`, and projects status/events
  in the Runtime panel.
- Verify Complete/Pause/Cancel and manual Refresh against terminal runs.
- Keep top-agent/operator audit surfaces such as utterances out of ordinary
  Agent message context.
- Second phase: add service-owned automatic tick loop, real
  `CLIWorkerBackend` startup, `executionMode=live`, and live worker execution.

Latest verification observed:

```powershell
cd D:\agent\multi_agent_tcp
pytest -q test_desktop_blueprint_service.py test_graph_control.py
python -m py_compile desktop_blueprint_service.py __main__.py __init__.py

cd D:\agent\multi_agent_tcp\GuLiCode\packages\app
bun test --preload ./happydom.ts ./src/pages/session/blueprint-model.test.ts ./src/pages/session/blueprint-side-panel.test.ts
bun run build

cd D:\agent\multi_agent_tcp\GuLiCode\packages\desktop-electron
bun test ./src/main/blueprint-runtime.test.ts ./src/main/ipc-blueprint-runtime.test.ts ./src/main/blueprint-catalog.test.ts
bun run build
```

Observed result: Python `17 passed`; app `18 pass`; Electron `9 pass`; both
Bun builds passed with existing Vite warnings only.

## Fast Handoff - 2026-05-16 Blueprint Runtime Middle Layer v1

Superseded for UI/runtime status coupling by the 2026-05-17 handoff above.
Keep this section as the historical service-middle-layer baseline.

The Blueprint Runtime middle layer v1 has landed. The Python desktop
blueprint service now owns live run registration and lifecycle polling for
saved project blueprint documents.

Completed in the current workspace:

1. `desktop_blueprint_service.py` now has a service-owned in-memory run
   registry guarded by `threading.RLock`.
2. Run ids use `run-<12 hex>`. Each registry entry keeps project dir,
   blueprint id, `BlueprintDocument`, `GraphDefinition`, `GraphRuntime`,
   `GraphRuntimeControlPlane`, and created/updated timestamps.
3. `blueprint.start` now loads the saved project blueprint JSON, converts
   `document.graph` through `graph_definition_from_dict(...)`, calls
   `validate_runnable()`, requires a complete `TopAgentStartPlan`, and calls
   control-plane `run.start`.
4. `DesktopBlueprintNoopBackend` is used for v1. It records worker configs in
   `ensure_worker()` but does not start broker/CLI workers; `run_single()`
   raises a clear non-execution error if reached.
5. `blueprint.status` returns `GraphRuntime.status_snapshot(graph=graph)`.
6. `blueprint.recentEvents` returns a bounded recent event window; default
   limit is 20 and accepted values are clamped to `0..200`.
7. `blueprint.end` supports `complete`, `cancel`, `fail`, and `pause`.
   Terminal runs remain queryable, and repeated end calls return
   `alreadyEnded: true` without calling `GraphRuntime.end_run()` again.
8. Service errors now support optional `details` and include runtime-facing
   codes such as `RUN_NOT_FOUND`, `INVALID_BLUEPRINT_GRAPH`,
   `BAD_START_PLAN`, `START_PLAN_INVALID`, and `UNSUPPORTED_RUN_ACTION`.
9. Python and Electron tests cover the real service lifecycle:
   save -> start -> status -> recentEvents -> end.

Files to start from:

- `desktop_blueprint_service.py`
- `test_desktop_blueprint_service.py`
- `GuLiCode/packages/desktop-electron/src/main/blueprint-runtime.ts`
- `GuLiCode/packages/desktop-electron/src/main/blueprint-runtime.test.ts`
- `GuLiCode/packages/desktop-electron/src/main/ipc-blueprint-runtime.test.ts`
- `GuLiCode/packages/desktop-electron/src/main/ipc.ts`
- `GuLiCode/packages/desktop-electron/src/preload/index.ts`
- `GuLiCode/packages/desktop-electron/src/preload/types.ts`
- `GuLiCode/packages/app/src/context/platform.tsx`
- `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.tsx`

Historical next priority, now completed by the 2026-05-17 handoff: runtime
status projection in GuLiCode UI.

- Add a start action UX that saves the project blueprint before calling
  `blueprint.start`.
- Display returned runtime/control-plane projections for runs, agents, queues,
  outgoing batches, joins, jobs, workspace changes, artifacts, reports, and
  recent events.
- Keep renderer behavior thin. Do not move scheduler, fan-in, queue,
  workspace/archive, or top-agent semantics into the UI.
- Keep top-agent/operator audit surfaces such as utterances out of ordinary
  Agent message context.
- Add automatic tick/live CLI execution only after this status projection
  layer is stable.

Latest verification observed:

```powershell
cd D:\agent\multi_agent_tcp
pytest -q test_desktop_blueprint_service.py test_graph_control.py
python -m py_compile desktop_blueprint_service.py __main__.py __init__.py

cd D:\agent\multi_agent_tcp\GuLiCode\packages\desktop-electron
bun test ./src/main/blueprint-runtime.test.ts ./src/main/ipc-blueprint-runtime.test.ts
```

Observed result: `17 passed` and `5 pass`.

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

### 3. `knowledge_base/`

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

### 4. `tasks/`

Short-term work. Prefer current files in this order:

- [`tasks/current_goals.md`](tasks/current_goals.md): current active priorities.
- [`tasks/guli_desktop_ui_tasks.md`](tasks/guli_desktop_ui_tasks.md): Guli desktop UI productization and blueprint embedding tasks.
- [`tasks/multi_agent_communication_tasks.md`](tasks/multi_agent_communication_tasks.md): GuLiCode top Agent, runtime control, message staging, joins, and framework-owned communication.
- [`tasks/node_runtime_tasks.md`](tasks/node_runtime_tasks.md): GraphRuntime / graph scheduling implementation tasks.
- [`tasks/multi_cli_adapter_tasks.md`](tasks/multi_cli_adapter_tasks.md): CLI backend adapter work, secondary to runtime/control-plane work.

### 5. `archive/`

Historical change records only. Do not use archive content as current behavior unless a current knowledge document points to it.

- [`archive/guli_desktop_ui_archive.md`](archive/guli_desktop_ui_archive.md)
- [`archive/blueprint_integration_archive.md`](archive/blueprint_integration_archive.md)
- [`archive/blueprint_api_bridge_2026-05-16.md`](archive/blueprint_api_bridge_2026-05-16.md)
- [`archive/blueprint_runtime_middle_layer_2026-05-16.md`](archive/blueprint_runtime_middle_layer_2026-05-16.md)
- [`archive/blueprint_ui_runtime_status_projection_2026-05-17.md`](archive/blueprint_ui_runtime_status_projection_2026-05-17.md)
- [`archive/gulicode_runtime_baseline_archive.md`](archive/gulicode_runtime_baseline_archive.md)
- [`archive/agents_architecture_archive.md`](archive/agents_architecture_archive.md)
- [`archive/ring_runtime_closure_archive.md`](archive/ring_runtime_closure_archive.md)
- [`archive/ring_session_runtime_archive.md`](archive/ring_session_runtime_archive.md)

## Query Map

- GuLiCode desktop startup, one-click launcher, packaged bring-up, taskbar icon, and direct Electron fallback: read `knowledge_base/gulicode_desktop.md`.
- Guli productization, desktop UI ownership, branding, icon replacement, empty-state wording, blueprint entry placement, and blueprint workbench embedding: read `knowledge_base/guli_desktop_ui.md`, then `tasks/guli_desktop_ui_tasks.md`.
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
