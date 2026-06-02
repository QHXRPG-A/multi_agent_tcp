# Guli desktop UI archive

This archive records desktop/UI productization rounds for `multi_agent_tcp/GuLiCode`.

## 2026-05-14 - Blueprint config boundary, catalog IPC, and model dropdowns

### Summary

This pass adjusted the blueprint inspector configuration boundary so users edit
only project-level common config and per-Agent execution/capability choices.
Private workspaces, temporary shared workspaces, generated commands, and
workspace/scope policy remain framework-owned concepts.

Implemented state:

1. Added a top-left "blueprint common config" panel on the canvas for:
   - `project_workdir`
   - `skill_dir`
   - `rule_dir`
2. Defaulted `skill_dir` to
   `F:\src\Package\Script\Python\multi_agent_tcp\skill_list`.
3. Defaulted `project_workdir` to the opened project directory.
4. Removed editable Agent inspector controls for framework-managed fields:
   `cwd`, `read_scope`, `write_scope`, `artifact_scope`, `workspace_id`,
   `workspace_root`, `command`, and raw `skill_selection`.
5. Kept those internal fields in the `BlueprintAgentNode` model for
   compatibility with existing runtime/schema code.
6. Updated runtime draft export so common `project_workdir` is written into
   AgentNode `cwd`, while the actual launch cwd can still be rewritten by the
   framework to a private checkout.
7. Generated `command` during export from `cli_kind`:
   - `codex -> codex`
   - `codex -> codex`
8. Converted `skills` to a multi-select dropdown populated from `skill_dir`.
   Selected skills export both as `skills` and
   `skill_selection: { mode: "selected", skill_hashes: [...] }`; no selection
   exports `skill_selection: { mode: "none" }`.
9. Converted `rule_paths` to a multi-select dropdown populated from `rule_dir`.
   Empty rule directory is valid and simply shows no options.
10. Converted `cli_kind` to a dropdown with initial options `codex` and
    `codex`.
11. Converted `model` to a dropdown that refreshes when CLI kind changes:
    - `codex` calls `codex models codex` and parses
      non-empty output lines.
    - `codex` calls `codex debug models` and parses JSON `models[].slug`.
    - failures preserve the current/fallback model and expose loading/failure
      state in the UI.
12. Kept `adapter_options` as the advanced JSON field. Its intended meaning is
    "low-level fallback parameters passed directly to the selected CLI
    adapter", such as Codex sandbox/config/extra_args or Codex base_args.
13. Added Electron main/preload IPC for blueprint directory, skill, rule, and
    model catalog lookup.
14. Added web/test fallback behavior when Electron APIs are absent.

### Affected repository files

- `GuLiCode/packages/app/src/pages/session/blueprint-model.ts`
- `GuLiCode/packages/app/src/pages/session/blueprint-model.test.ts`
- `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.tsx`
- `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.test.ts`
- `GuLiCode/packages/app/src/context/platform.tsx`
- `GuLiCode/packages/app/src/i18n/en.ts`
- `GuLiCode/packages/app/src/i18n/zh.ts`
- `GuLiCode/packages/app/src/i18n/zht.ts`
- `GuLiCode/packages/desktop-electron/src/main/blueprint-catalog.ts`
- `GuLiCode/packages/desktop-electron/src/main/blueprint-catalog.test.ts`
- `GuLiCode/packages/desktop-electron/src/main/ipc.ts`
- `GuLiCode/packages/desktop-electron/src/preload/index.ts`
- `GuLiCode/packages/desktop-electron/src/preload/types.ts`

### Validation

Relevant tests passed:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\app
bun test --preload ./happydom.ts ./src/pages/session/blueprint-model.test.ts ./src/pages/session/blueprint-side-panel.test.ts
# 11 pass

cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\desktop-electron
bun test ./src/main/blueprint-catalog.test.ts
# 4 pass
```

### Known follow-up state

- Manual packaged-app smoke should verify the common config panel, skill/rule
  dropdowns, CLI/model loading/failure state, and hidden framework-managed
  fields in the Agent inspector.
- The Electron/preload boundary currently covers catalog/model lookup only.
  The next implementation step is graph persistence and
  `GraphRuntimeControlPlane` start/status/end through the runtime/Python
  boundary.
- Durable project JSON/workspace persistence is still undecided.
- Full runtime status projection for runs, agents, outgoing batches, joins,
  workspace changes, artifacts, reports, and top-agent explanations remains the
  next product milestone.

## 2026-05-14 - Blueprint inspector tips, dark visual pass, and NSIS package workaround

### Summary

This pass refined the runtime-aligned blueprint panel after the node/port
interaction work. The user-facing focus was inspector explanation, dark visual
consistency, and producing a Windows installer despite the local symlink
permission issue.

Implemented UI state:

1. Added per-field inspector `?` tip buttons.
2. Tip popovers explain both what the field is and what it is used for.
3. Added localized tip copy for Agent, Route, Terminal, and Edge fields.
4. Moved the inspector toward a dark surface with light text, light labels,
   and visible question buttons.
5. Adjusted node colors so nodes are visually separated from the dark canvas
   background while keeping the dark/technology/minimal direction.
6. Corrected native select text/option colors for the dark inspector.
7. Restored visibility for `nonblocking` / `非阻塞` in the execution mode
   select.
8. Kept the existing runtime-aligned local draft boundary; no renderer-side
   scheduling logic was added.

### Packaging result

The normal full Windows package path can still hit electron-builder
`winCodeSign-2.6.0.7z` symlink extraction failures in a non-elevated Windows
session. For this pass, packaging used the local workaround directly:

1. Created a temporary `electron-builder.local.config.ts`.
2. Imported the base `electron-builder.config`.
3. Set `win.signAndEditExecutable = false`.
4. Added an `afterPack` hook using cached `rcedit-x64.exe` to apply
   `resources/icons/icon.ico`.
5. Set `CSC_IDENTITY_AUTO_DISCOVERY=false`.
6. Set `ELECTRON_BUILDER_RCEDIT_PATH` to the newest cached winCodeSign
   directory containing both `rcedit-x64.exe` and `rcedit-ia32.exe`.
7. Ran `bunx electron-builder --win --config electron-builder.local.config.ts`.
8. Deleted the temporary config after packaging.

One first run failed before packaging because old `GuLiCode Dev.exe` instances
were still running from `dist/win-unpacked` and locked
`d3dcompiler_47.dll`. After killing only those output-directory processes, the
same workaround package command succeeded.

Successful outputs:

```text
GuLiCode/packages/desktop-electron/dist/opencode-electron-win-x64.exe
  -> 149.29 MB, 2026-05-14 18:13:35
GuLiCode/packages/desktop-electron/dist/opencode-electron-win-x64.exe.blockmap
  -> 0.16 MB, 2026-05-14 18:13:37
GuLiCode/packages/desktop-electron/dist/win-unpacked/GuLiCode Dev.exe
  -> 212.66 MB, 2026-05-14 18:13:03
```

### Validation

Before packaging, these checks passed:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\app
bun test --preload ./happydom.ts ./src/pages/session/blueprint-model.test.ts
bun run build

cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\desktop-electron
bun run build
```

Full package command that succeeded:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\desktop-electron
$env:CSC_IDENTITY_AUTO_DISCOVERY = 'false'
$env:ELECTRON_BUILDER_RCEDIT_PATH = '<cached winCodeSign rcedit dir>'
bunx electron-builder --win --config electron-builder.local.config.ts
```

### Affected repository files

- `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.tsx`
- `GuLiCode/packages/app/src/i18n/en.ts`
- `GuLiCode/packages/app/src/i18n/zh.ts`
- `GuLiCode/packages/app/src/i18n/zht.ts`

### Known follow-up state

- Manual packaged-app visual smoke is still useful for the inspector: tip
  popovers, dark labels, native select popups, `非阻塞` visibility, and
  node/canvas contrast.
- The NSIS workaround is proven but still manual. Next cleanup should make it
  one-command repeatable or document an approved symlink-permission route.
- If a future package run fails removing `dist/win-unpacked/d3dcompiler_47.dll`,
  look for old `GuLiCode Dev.exe` processes under `dist/win-unpacked` before
  changing app code.
- The next product milestone remains runtime binding through
  Electron/preload/Python and `GraphRuntimeControlPlane`, not more local
  renderer scheduling.

## 2026-05-14 - Runtime-aligned blueprint node and interaction pass

### Summary

This pass continued from the local Solid blueprint panel and did not introduce
a separate graph editor dependency. The panel still uses HTML nodes plus SVG
edges, but the draft model and interactions are now much closer to the Python
runtime graph shape.

Implemented state:

1. Extended `BlueprintDraft.graph` with `route_nodes`.
2. Added runtime-compatible `BlueprintRouteNode` fields:
   `node_id`, `route_kind`, `targets`, `reduce_target`, and `reduce_prompt`.
3. Expanded `BlueprintAgentNode` editing fields:
   `agent_id`, `prompt`, `execution_mode`, `cli_kind`, `model`, `cwd`,
   `skills`, `skill_selection`, `rule_paths`, `timeout_sec`,
   `prompt_via_file`, `command`, `adapter_options`, `extra_env`, `external`,
   `workspace_id`, `workspace_root`, `read_scope`, `write_scope`, and
   `artifact_scope`.
4. Updated runtime draft conversion to emit:

```ts
{
  terminal_nodes,
  agent_nodes,
  route_nodes,
  edges: [{ from, to, edge_type, output_port?, input_port? }],
}
```

5. Added route node creation for `sequence`, `parallel`, and
   `parallel_reduce`.
6. Added port-aware `GraphEdge` state. The default connection remains
   `exec` from `out` to `in`.
7. Rendered node ports:
   - Start: output only
   - End: input only
   - Agent: input and output
   - Route: input and output
8. Removed the old toolbar `Connect` and toolbar delete actions from the
   current panel. Connections are now created by dragging from output ports to
   input ports.
9. Replaced `+ Agent` with an `Add node` dropdown containing Agent, Route
   sequence, Route parallel, Route parallel_reduce, Start, and End. Clicking
   adds at the viewport center; dragging a dropdown item onto the canvas adds
   at the drop position.
10. Moved canvas panning to right-click drag. Left-click blank canvas no
    longer pans.
11. Split selection from inspection. Left-clicking a node selects it only;
    double-clicking a node or choosing right-click `Edit` opens the inspector.
12. Added a node context menu with `Edit` and `Delete`.
13. Added `Backspace` / `Delete` deletion for selected nodes or edges, guarded
    so focused `input`, `textarea`, `select`, or contenteditable fields do not
    delete canvas items.
14. Cascaded edge deletion for all node kinds, including terminal and route
    nodes. The inspector closes when its target disappears.
15. Added `GRID_SIZE = 24` snapping for node drag, center-add, and drop-add
    coordinates. Viewport panning remains unsnapped.
16. Inspector JSON fields (`adapter_options`, `extra_env`,
    `skill_selection`) keep the previous parsed value and show invalid state
    while text contains invalid JSON.

### Affected repository files

- `GuLiCode/packages/app/src/pages/session/blueprint-model.ts`
- `GuLiCode/packages/app/src/pages/session/blueprint-model.test.ts`
- `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.tsx`
- `GuLiCode/packages/app/src/components/session/session-header.tsx`
- `GuLiCode/packages/app/src/context/layout.tsx`
- `GuLiCode/packages/app/src/pages/session.tsx`
- `GuLiCode/packages/app/src/pages/session/session-side-panel.tsx`
- `GuLiCode/packages/app/src/i18n/en.ts`
- `GuLiCode/packages/app/src/i18n/zh.ts`
- `GuLiCode/packages/app/src/i18n/zht.ts`

### Validation expectations

Run these before building on the pass:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\app
bun test --preload ./happydom.ts ./src/pages/session/blueprint-model.test.ts
bun run build
```

Manual smoke checklist:

- open the blueprint panel from the session header
- right-click drag the canvas
- right-click a node and use `Edit` / `Delete`
- left-click a node and verify the inspector does not open
- double-click a node and verify the inspector opens
- add all six node kinds from the dropdown
- drag a dropdown item onto the canvas and verify grid snapping
- drag output port to input port and verify an edge appears
- delete selected nodes/edges with `Backspace` and `Delete`
- verify inspector collapse after deleting the inspected node/edge

### Known follow-up state

- The current panel remains local draft UI. It does not start or schedule a
  runtime graph from the renderer.
- The next implementation step is an Electron/preload/Python boundary for
  graph persistence plus `GraphRuntimeControlPlane` start/status/end.
- Durable blueprint ownership still needs a decision: local draft migration,
  project JSON, workspace records, or another runtime-owned store.
- Live runtime projections still need UI: run status, agent status, outgoing
  batches, joins, workspace changes, artifacts, reports, and top-agent
  explanations.
- Frontend browser smoke should still be performed after the next build.

## 2026-05-14 - Blueprint workbench v1 and Windows package icon workaround

### Summary

1. Replaced the empty right-side blueprint grid with a first interactive graph
   workbench inside `packages/app`.
2. Added a UI-only `BlueprintDraft` model with:
   - `graph.agent_nodes`
   - `graph.terminal_nodes`
   - `graph.edges`
   - `layout.nodes`
   - `layout.viewport`
   - `selection`
3. Seeded new drafts with `start -> planner -> coder -> review -> summary -> end`.
4. Persisted drafts through `Persist.workspace(projectDir, "blueprint-draft.v1")`.
5. Implemented HTML node rendering plus SVG edges, wheel zoom, blank-canvas
   pan, node drag, click selection, fit view, and reset view.
6. Added toolbar actions for add Agent node, connect mode, delete selection,
   and reset draft. Connect mode creates default `exec` edges and rejects
   duplicate edges.
7. Added inspector editing for Agent `agent_id`, `prompt`, `execution_mode`,
   scope fields, and edge `edge_type`.
8. Kept `start` and `end` terminal nodes non-deletable and cascaded edge
   deletion when a node is removed.
9. Added `toRuntimeGraphDraft(draft)` as a pure conversion boundary returning
   `{ terminal_nodes, agent_nodes, edges }`; runtime execution is not called
   from the renderer in this round.
10. Produced a Windows NSIS package using the local `winCodeSign` workaround
    and corrected the unpacked `GuLiCode Dev.exe` icon with cached `rcedit`.

### Affected repository files

- `GuLiCode/packages/app/src/pages/session/blueprint-model.ts`
- `GuLiCode/packages/app/src/pages/session/blueprint-model.test.ts`
- `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.tsx`
- `GuLiCode/packages/app/src/i18n/en.ts`
- `GuLiCode/packages/app/src/i18n/zh.ts`
- `GuLiCode/packages/app/src/i18n/zht.ts`

### Validation

Blueprint model:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\app
bun test --preload ./happydom.ts ./src/pages/session/blueprint-model.test.ts
bun run build
```

Result:

- blueprint model tests passed for default draft, add node, add/dedupe edge,
  delete-node cascade, and runtime graph conversion
- app production build passed
- `bun run typecheck` remains blocked by existing
  `src/custom-elements.d.ts` content (`../../ui/src/custom-elements.d.ts`)

Desktop packaging:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\desktop-electron
bun run build
```

Result:

- desktop-electron build passed
- direct `bun run package:win` can fail in this Windows session because
  electron-builder's `winCodeSign-2.6.0.7z` extraction attempts to create
  symlinks for bundled Darwin libraries
- successful workaround used a temporary `electron-builder.local.config.ts`
  that imported the base config, set `win.signAndEditExecutable = false`, and
  ran cached `rcedit-x64.exe --set-icon resources/icons/icon.ico` in `afterPack`
- the temporary config was deleted after packaging
- output artifacts:

```text
GuLiCode/packages/desktop-electron/dist/opencode-electron-win-x64.exe
GuLiCode/packages/desktop-electron/dist/opencode-electron-win-x64.exe.blockmap
GuLiCode/packages/desktop-electron/dist/win-unpacked/GuLiCode Dev.exe
```

### Known follow-up state

- Bind the local draft workbench to `GraphRuntimeControlPlane` and
  `GraphRuntime` through a proper Electron/preload/Python boundary.
- Decide durable project JSON/workspace persistence and migration beyond the
  local `blueprint-draft.v1` draft.
- Add runtime status projection for runs, agents, outgoing batches, joins,
  workspace changes, artifacts, reports, and top-agent explanations.
- Make the Windows NSIS/rcedit workaround repeatable, or verify direct
  `bun run package:win` from a Windows session with symlink privileges.

## 2026-05-14 - Blueprint right-side panel and resizable split baseline

### Summary

1. Changed the session-header blueprint button from placeholder toast behavior to a real toggle.
2. Added a GuLiCode-owned right-side blueprint panel inside the existing session workbench.
3. Landed the first blueprint surface as an empty grid canvas with:
   - header and blueprint icon
   - close button
   - localized empty-state title and description
4. Reused the existing side-panel layout model so opening blueprint shrinks the session pane like review does.
5. Added drag resizing to the session/blueprint divider by rendering the existing `ResizeHandle` when either review or blueprint is open.
6. Regenerated the packaged Windows desktop smoke output after the resize change.

### Affected repository files

- `GuLiCode/packages/app/src/components/session/session-header.tsx`
- `GuLiCode/packages/app/src/context/layout.tsx`
- `GuLiCode/packages/app/src/i18n/en.ts`
- `GuLiCode/packages/app/src/i18n/zh.ts`
- `GuLiCode/packages/app/src/i18n/zht.ts`
- `GuLiCode/packages/app/src/pages/session.tsx`
- `GuLiCode/packages/app/src/pages/session/session-side-panel.tsx`
- `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.tsx`

### Product/UI result

Clicking the blueprint entry in the session header now opens the right-side blueprint system. The first version is intentionally minimal: an empty canvas that establishes the workbench surface before graph editing and runtime binding are added.

The session/blueprint divider now uses the same resizable split behavior as existing side panels:

```text
Session pane width -> layout.session.width()
Resize handle     -> packages/ui/src/components/resize-handle.tsx
Blueprint panel   -> packages/app/src/pages/session/blueprint-side-panel.tsx
```

The blueprint panel currently shares the right-side main panel slot with review. If both review and blueprint states are open, blueprint is displayed first; closing blueprint reveals the existing review/file context instead of discarding it.

### Validation

Commands and observations from this round:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\app
bun run build
```

Result:

- Vite production build passed.
- `git diff --check` passed for the edited session file.
- `bun run typecheck` remains blocked by existing `src/custom-elements.d.ts` content (`../../ui/src/custom-elements.d.ts`) and was not caused by this blueprint work.

Packaged smoke:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode
bun run desktop -- --packaged
```

Result:

- Packaged command returned successfully.
- Current runnable exe:

```text
F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\desktop-electron\dist\packaged-launch\current\win-unpacked\GuLiCode Dev.exe
```

- After the resizable divider change, observed exe timestamp was `2026/5/14 11:21:49`.

### Known follow-up state

- `GuLiCode/bun.lock` was already dirty and unrelated to this UI work; do not revert it blindly.
- NSIS installer output with `bun run package:win` failed in the normal Windows session because electron-builder's `winCodeSign` extraction attempted to create symlinks and Windows denied that privilege. The unpacked runnable exe is available.
- Browser visual automation was not completed because the required in-app browser Node REPL control surface was not exposed in the session; validation relied on app build and packaged smoke.

### Next handoff

The next developer should start from the right-side panel, not by adding a separate legacy visual-editor route. The immediate blueprint UI work is:

1. Add a graph canvas implementation inside `packages/app`.
2. Define blueprint draft persistence and workspace/project ownership.
3. Add node/edge creation, pan/zoom, selection, deletion, and save/load behavior.
4. Bind run/status surfaces to `GraphRuntimeControlPlane` without moving graph scheduling semantics into the renderer.

## 2026-05-13 - Guli desktop productization baseline and blueprint entry embedding

### Summary

1. Re-centered the active UI line around **Guli productization + blueprint embedded in the GuLiCode desktop app**.
2. Added the first blueprint entry surface in the session header as a placeholder button with i18n copy.
3. Replaced the new-session center mark with `GULI`.
4. Reworked the packaged desktop startup path so `start-gulicode-desktop.cmd --packaged` can build and launch a stable unpacked desktop app.
5. Fixed packaged bring-up blockers:
   - missing `git` in the Bun shell path during prebuild
   - renderer asset race conditions
   - off-screen saved window state
   - icon-load failure aborting main-window creation
6. Replaced desktop icon resources and added a post-package `rcedit` patch so the final `GuLiCode Dev.exe` carries the GuLiCode icon.
7. Stabilized packaged output to a fixed path:

```text
GuLiCode/packages/desktop-electron/dist/packaged-launch/current/win-unpacked/GuLiCode Dev.exe
```

### Affected repository files

- `GuLiCode/packages/app/src/components/session/session-header.tsx`
- `GuLiCode/packages/app/src/components/session/session-new-view.tsx`
- `GuLiCode/packages/app/src/i18n/en.ts`
- `GuLiCode/packages/app/src/i18n/zh.ts`
- `GuLiCode/packages/app/src/i18n/zht.ts`
- `GuLiCode/packages/ui/src/components/icon.tsx`
- `GuLiCode/packages/desktop-electron/icons/dev/*`
- `GuLiCode/packages/desktop-electron/icons/beta/*`
- `GuLiCode/packages/desktop-electron/icons/prod/*`
- `GuLiCode/packages/desktop-electron/src/main/index.ts`
- `GuLiCode/packages/desktop-electron/src/main/windows.ts`
- `GuLiCode/packages/desktop-electron/electron-builder.config.ts`
- `GuLiCode/packages/script/src/index.ts`
- `GuLiCode/scripts/dev-desktop.ts`

### Desktop bring-up result

The validated one-click packaged command for this round is:

```powershell
F:\src\Package\Script\Python\multi_agent_tcp\start-gulicode-desktop.cmd --packaged
```

Observed effective result:

- packaged output is produced under `dist/packaged-launch/current`
- Electron main log reaches `main window created`
- the visible desktop window title is `GuLiCode`
- the packaged `exe` resource icon is the GuLiCode icon rather than the stale Electron-style icon

### Product/UI result

The first desktop productization surfaces now look like this:

- blueprint is visible as a top-level desktop action
- the new-session center surface reads `GULI`
- desktop icon assets are aligned across dev/beta/prod channels

This is still a baseline, not the finished blueprint workbench.

### What remains intentionally unfinished

- The blueprint button open logic is not wired yet.
- The dedicated blueprint route/panel/workbench layout is not built yet.
- Runtime-backed status surfaces for runs, agents, joins, workspace changes, artifacts, and reports are still ahead.
- Some Windows taskbar pins may still need repinning if they were created from older timestamped build paths before the output path was stabilized.

### Documentation cleanup result

This same round also retired the old Ryven/editor UI line from the active skill snapshot and replaced it with:

- `knowledge_base/guli_desktop_ui.md`
- `tasks/guli_desktop_ui_tasks.md`
- `archive/guli_desktop_ui_archive.md`
