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
