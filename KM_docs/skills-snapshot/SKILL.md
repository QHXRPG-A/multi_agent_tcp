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
7. Known remaining backend risk: the combined run with
   `test_workspace_manager.py` still fails
   `test_agent_checkout_dulwich_merge_accepts_non_overlapping_same_file_changes`
   because a non-overlapping same-file checkout submit returns `conflict`.

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
```

Detailed archive:

- [`archive/blueprint_common_config_paths_2026-05-19.md`](archive/blueprint_common_config_paths_2026-05-19.md)

## Fast Handoff - 2026-05-18 Blueprint Agent Panel + Debug Baseline

When the next task is GuLiCode blueprint UI or desktop debug startup, start
from this state:

1. The Agent information panel no longer opens by hover. It opens by left
   mouse long-press on Agent nodes with an `800ms` circular progress ring, or
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
- [`archive/agent_info_panel_live_runtime_2026-05-18.md`](archive/agent_info_panel_live_runtime_2026-05-18.md)
- [`archive/agent_info_panel_interaction_2026-05-18.md`](archive/agent_info_panel_interaction_2026-05-18.md)
- [`archive/agent_info_panel_test_node_json_2026-05-18.md`](archive/agent_info_panel_test_node_json_2026-05-18.md)
- [`archive/gulicode_runtime_baseline_archive.md`](archive/gulicode_runtime_baseline_archive.md)
- [`archive/agents_architecture_archive.md`](archive/agents_architecture_archive.md)
- [`archive/ring_runtime_closure_archive.md`](archive/ring_runtime_closure_archive.md)
- [`archive/ring_session_runtime_archive.md`](archive/ring_session_runtime_archive.md)

## Query Map

- GuLiCode desktop startup, one-click launcher, packaged bring-up, taskbar icon, and direct Electron fallback: read `knowledge_base/gulicode_desktop.md`.
- Guli productization, desktop UI ownership, branding, icon replacement, empty-state wording, blueprint entry placement, and blueprint workbench embedding: read `knowledge_base/guli_desktop_ui.md`, then `tasks/guli_desktop_ui_tasks.md`.
- Blueprint Agent information panel interactions, long-press progress, context-menu entry, move/resize behavior, Test Agent JSON snapshots, user-message capture, and clean desktop debug baseline: read `archive/agent_info_panel_interaction_2026-05-18.md`, then `archive/agent_info_panel_test_node_json_2026-05-18.md`, then `tasks/current_goals.md`.
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
