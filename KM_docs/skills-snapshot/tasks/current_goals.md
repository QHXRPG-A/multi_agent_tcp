# Current Short-Term Goals

Last cleaned: 2026-05-14

## Current Main Line

The active project direction is:

```text
Guli productization
  -> blueprint embedded in GuLiCode desktop
  -> GraphRuntimeControlPlane
  -> GraphRuntime
  -> AgentNode queues, outgoing batches, joins, workspace/events
  -> CLIWorkerBackend adapters
```

Primary design source:

- [`../多agents通信设计.md`](../多agents通信设计.md)
- [`guli_desktop_ui_tasks.md`](guli_desktop_ui_tasks.md)
- [`multi_agent_communication_tasks.md`](multi_agent_communication_tasks.md)
- [`../knowledge_base/gulicode_desktop.md`](../knowledge_base/gulicode_desktop.md)
- [`../knowledge_base/guli_desktop_ui.md`](../knowledge_base/guli_desktop_ui.md)
- [`../knowledge_base/core_architecture.md`](../knowledge_base/core_architecture.md)

## Recently Completed Baseline

This round has already established the first usable desktop/UI baseline:

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
  configuration fields, terminal node kinds, route node kinds, and port-aware
  `GraphEdge` fields with default `out -> in` exec edges.
- Every canvas node now renders at least one connection port: Start has output,
  End has input, and Agent/Route nodes have both input and output.
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
  `project_workdir`, `skill_dir`, and `rule_dir`; default `skill_dir` is
  `F:\src\Package\Script\Python\multi_agent_tcp\skill_list`, and
  `project_workdir` defaults to the opened project directory.
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
  and refreshes model candidates by running `codemaker models netease-codemaker`
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

## Immediate Handoff For The Next Agent

Start from these source files:

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
- `GuLiCode/packages/app/src/pages/session.tsx`
- `GuLiCode/packages/app/src/pages/session/session-side-panel.tsx`
- `GuLiCode/packages/app/src/components/session/session-header.tsx`
- `GuLiCode/packages/app/src/context/layout.tsx`
- `GuLiCode/packages/app/src/i18n/en.ts`
- `GuLiCode/packages/app/src/i18n/zh.ts`
- `GuLiCode/packages/app/src/i18n/zht.ts`

Before changing behavior, run:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\app
bun test --preload ./happydom.ts ./src/pages/session/blueprint-model.test.ts ./src/pages/session/blueprint-side-panel.test.ts
bun run build
```

If touching Electron catalog/model IPC or packaged desktop identity, also run:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\desktop-electron
bun test ./src/main/blueprint-catalog.test.ts
bun run build
```

Known local limitation: `bun run typecheck` in `packages/app` is still blocked
by existing `src/custom-elements.d.ts` content (`../../ui/src/custom-elements.d.ts`).

## Active Priorities

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
   - Verify the right-side blueprint panel opens with the seed graph
     `start -> planner -> coder -> review -> summary -> end`.
   - Drag the session/blueprint divider and verify both panes resize like the review side panel.
   - Zoom with the mouse wheel.
   - Pan the canvas with right-click drag; left-click drag on blank canvas should not pan.
   - Left-click a node to select it without opening the inspector.
   - Double-click a node, or use the right-click node menu `Edit`, to open the inspector.
   - Use the `Add node` dropdown to create Agent, Route sequence, Route parallel,
     Route parallel_reduce, Start, and End nodes.
   - Drag an add-node menu item onto the canvas and verify the dropped position
     snaps to the 24px grid.
   - Drag from an output port to an input port and verify a port-aware `exec`
     edge appears.
   - Delete nodes and edges through right-click menu / inspector action /
     `Backspace` / `Delete`, and verify connected edges are removed with their node.
   - Verify the inspector collapses when no inspected target remains.
   - Edit Agent, Route, Terminal, and Edge inspector fields; JSON fields should
     show an invalid state while preserving the previous parsed value.
   - Verify the top-left common config panel controls project workdir, skill
     dir, and rule dir.
   - Verify the Agent inspector does not show editable command, cwd,
     workspace id/root, read/write/artifact scope, or raw skill_selection
     fields.
   - Verify skill and rule multi-select dropdowns reflect the selected
     directories and preserve selected values across save/reopen.
   - Switch CLI kind between `codemaker` and `codex`; verify the model dropdown
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

Continue maintaining Codex/CodeMaker adapters and `CLIWorkerBackend`, but do not let adapter mechanics drive product architecture.

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
-> bun run typecheck is still blocked by existing src/custom-elements.d.ts content (`../../ui/src/custom-elements.d.ts`)
-> bun test --preload ./happydom.ts ./src/pages/session/blueprint-model.test.ts ./src/pages/session/blueprint-side-panel.test.ts passes for the blueprint draft model and inspector-source boundary, including route_nodes, port-aware edges, config export, generated command, skill_selection compatibility, hidden framework-managed controls, delete cascade, runtime conversion, and grid snapping

F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\desktop-electron\dist\packaged-launch\current\win-unpacked\GuLiCode Dev.exe
-> regenerated after the blueprint divider change

F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\desktop-electron
-> bun test ./src/main/blueprint-catalog.test.ts passes for codemaker/codex model parsing and skill/rule directory scanning
-> bun run build passes
-> default bun run package:win can still fail in a normal Windows session on winCodeSign symlink extraction
-> successful local installer workaround: temporary electron-builder.local.config.ts, win.signAndEditExecutable=false, afterPack rcedit icon patch, CSC_IDENTITY_AUTO_DISCOVERY=false, ELECTRON_BUILDER_RCEDIT_PATH=<cached winCodeSign rcedit dir>, bunx electron-builder --win --config electron-builder.local.config.ts
-> if old dist/win-unpacked/GuLiCode Dev.exe processes are still running, builder can fail removing d3dcompiler_47.dll; close/kill those old output-dir instances and rerun
-> produced dist/opencode-electron-win-x64.exe, dist/opencode-electron-win-x64.exe.blockmap, and dist/win-unpacked/GuLiCode Dev.exe with the corrected icon
-> 2026-05-14 successful artifact timestamps: installer 18:13:35, blockmap 18:13:37, win-unpacked exe 18:13:03
```
