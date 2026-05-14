# Guli desktop UI tasks

## Current positioning

The current UI workstream is:

```text
Guli productization
  -> blueprint embedded in GuLiCode desktop
  -> runtime-backed desktop workbench
```

Do not treat the old Ryven/editor line as the current UI target.

## Already landed

- [DONE] Added a blueprint entry button to the session header.
- [DONE] Added i18n copy for the blueprint placeholder entry.
- [DONE] Replaced the new-session center mark with `GULI`.
- [DONE] Replaced desktop icon assets for `dev` / `beta` / `prod`.
- [DONE] Brought up one-click packaged startup through `start-gulicode-desktop.cmd --packaged`.
- [DONE] Fixed packaged main-window bring-up failures caused by off-screen saved state and icon-load crashes.
- [DONE] Stabilized packaged output to `dist/packaged-launch/current`.
- [DONE] Patched the final packaged `exe` icon through `rcedit`.
- [DONE] Wired the blueprint entry to open a GuLiCode-owned right-side panel.
- [DONE] Added the first blueprint empty canvas with grid background, close button, and i18n copy.
- [DONE] Reused the existing session resize handle so the session/blueprint divider can be dragged.
- [DONE] Replaced the placeholder canvas with blueprint workbench v1:
  persisted local draft, seed graph, node/edge rendering, selection, pan/zoom,
  node dragging, add Agent, connect mode, delete, reset/fit view, inspector
  editing, and runtime graph draft conversion.
- [DONE] Advanced the blueprint workbench to the runtime-aligned node and
  interaction pass:
  `route_nodes`, full Agent config fields, port-aware edges, node ports,
  add-node dropdown/drop-to-canvas, right-click canvas pan, node context menu,
  double-click inspector, keyboard delete, inspector collapse, and 24px grid
  snapping.
- [DONE] Added per-field inspector tip buttons. Clicking `?` shows what the
  field is and what it is used for.
- [DONE] Applied the current dark/technology/minimal visual pass: darker
  inspector surface, light inspector text and question buttons, node colors
  that separate from the canvas, corrected select option colors, and readable
  `nonblocking` / `非阻塞` labels.
- [DONE] Moved blueprint-wide user configuration into the top-left common
  config panel: `project_workdir`, `skill_dir`, and `rule_dir`.
- [DONE] Removed framework-managed fields from the Agent inspector UI:
  editable `cwd`, `read_scope`, `write_scope`, `artifact_scope`,
  `workspace_id`, `workspace_root`, `command`, and raw `skill_selection`.
- [DONE] Converted skills and rule paths to multi-select dropdowns backed by
  the configured skill/rule directories.
- [DONE] Converted CLI kind and model to dropdowns; model choices refresh
  through Electron IPC for `codemaker` and `codex`.
- [DONE] Added desktop catalog/model IPC and tests for skill scanning, rule
  scanning, and CLI model parsing.
- [DONE] Kept `adapter_options` as an advanced JSON escape hatch with clearer
  copy for low-level CLI adapter options.
- [DONE] Documented the Windows NSIS packaging/icon workaround for
  `winCodeSign` symlink failures and stale exe icons.
- [DONE] Ran the Windows NSIS workaround successfully on 2026-05-14 and
  produced the installer, blockmap, and unpacked exe from
  `GuLiCode/packages/desktop-electron/dist`.

## In progress

### 1. Blueprint entry embedding

- [DONE] Put the blueprint entry in the desktop chrome.
- [DONE] Wired the click action to a right-side panel in the existing session workbench.
- [DONE] First landing decision: blueprint starts as a right-side panel, not a separate route or revived legacy editor shell.
- [DONE] Added drag resizing on the session/blueprint split using the same `ResizeHandle` and `layout.session.width()` behavior as review.
- [DONE] Replaced the placeholder empty canvas with a real local blueprint graph surface.
- [DONE] Added wheel zoom, right-click pan, node creation, edge creation, selection, deletion, and inspector controls.
- [DONE] Removed the toolbar `Connect` and delete actions from the current
  blueprint workbench; connection creation now comes from node output ports,
  and deletion is handled through context menu, inspector edge action, or
  keyboard shortcuts.
- [DONE] Added the `Add node` dropdown with Agent, Route sequence, Route
  parallel, Route parallel_reduce, Start, and End entries. Click adds at the
  viewport center; dragging an item onto the canvas adds at the snapped drop
  point.
- [DONE] Added visible input/output ports: Start output only, End input only,
  Agent/Route input and output.
- [DONE] Split selection from inspection: left-click selects only, double-click
  or right-click `Edit` opens the inspector, and the inspector collapses when
  there is no valid target.
- [DONE] Added right-click node context menu with `Edit` and `Delete`.
- [DONE] Added `Backspace` / `Delete` deletion for selected nodes or edges,
  guarded so focused input/textarea/select/contenteditable fields do not delete
  canvas items.
- [DONE] Added 24px grid snapping for node drag, center-add, and drop-add
  coordinates. Viewport panning remains unsnapped.
- [DONE] Added inspector `?` tip buttons to Agent, Route, Terminal, and Edge
  fields, backed by localized copy.
- [DONE] Updated the blueprint surface toward dark, technology-oriented,
  minimal styling with higher node/canvas contrast.
- [DONE] Added the blueprint common config panel and moved project workdir,
  skill directory, and rule directory out of the Agent inspector.
- [DONE] Limited the Agent inspector to per-Agent execution/capability fields
  while keeping hidden schema compatibility fields for runtime export.
- [DONE] Added skill/rule multi-select controls with Electron catalog lookup
  and static fallbacks for web/test environments.
- [DONE] Added CLI/model dropdown behavior. `cli_kind` supports `codemaker`
  and `codex`; changing it refreshes model choices and the runtime export
  generates the command string.
- [TODO] Manual visual smoke pass in the packaged app for inspector colors,
  select menu readability, `非阻塞` visibility, common config placement,
  skill/rule dropdowns, model loading/failure state, and tip popovers.
- [TODO] Define durable blueprint state ownership beyond local draft state: project JSON, workspace records, and runtime-backed run state.
- [TODO] Add command palette or shortcut entry for opening the blueprint panel if it becomes a repeated workflow.

### 2. Guli productization

- [DONE] Replaced the empty-state mark with `GULI`.
- [DONE] Replaced desktop icon resources.
- [TODO] Audit remaining user-visible `OpenCode` wording across desktop-facing surfaces.
- [TODO] Decide the visible brand split between `GULI` and `GuLiCode` for headers, titles, onboarding, and packaging.

### 3. Runtime-backed UI

- [DONE] Shape local `RuntimeGraphDraft` output as
  `{ terminal_nodes, agent_nodes, route_nodes, edges }`, including
  `output_port` / `input_port`, so later runtime binding can consume a Python
  `GraphDefinition`-compatible payload.
- [DONE] Add local `BlueprintRouteNode` editing for `sequence`, `parallel`,
  and `parallel_reduce`.
- [DONE] Export blueprint common `project_workdir` into each runtime
  AgentNode `cwd` while allowing the framework to rewrite the actual process
  cwd to a private checkout later.
- [DONE] Preserve hidden AgentNode compatibility fields while removing them
  from user-editable inspector controls.
- [DONE] Add the first Electron/preload blueprint catalog boundary for
  directories, skills, rules, and CLI model lists.
- [TODO] Define the first live UI contract between the blueprint panel and `GraphRuntimeControlPlane`.
- [TODO] Extend the Electron/preload boundary from catalog/model lookup into
  runtime-owned graph persistence and run requests through Python/control-plane
  APIs.
- [TODO] Show run status, agent status, outgoing-batch status, join status, workspace changes, artifacts, and reports in GuLiCode.
- [TODO] Keep these views as projections of runtime/control-plane state rather than renderer-owned execution logic.
- [TODO] Add top-agent/operator audit views such as utterance history without exposing them as ordinary-Agent message context.

### 4. Desktop shell hardening

- [DONE] Off-screen saved window state is clamped back into a visible display.
- [DONE] Packaged icon failures no longer abort main-window creation.
- [DONE] Verified the local Windows NSIS workaround can package successfully
  without fixing system symlink permissions:
  temporary `electron-builder.local.config.ts`, `win.signAndEditExecutable=false`,
  cached `rcedit` in `afterPack`, `CSC_IDENTITY_AUTO_DISCOVERY=false`, and
  cleanup after packaging.
- [TODO] Add a simple repeatable smoke helper for packaged bring-up and icon verification.
- [TODO] Keep provider/model setup guidance out of repo files and inside runtime/user configuration only.
- [TODO] Make the full NSIS workaround one-command repeatable instead of
  hand-created temporary config.
- [TODO] If packaging fails with access denied on
  `dist/win-unpacked/d3dcompiler_47.dll`, close/kill old `GuLiCode Dev.exe`
  processes launched from `dist/win-unpacked` and rerun packaging.
- [TODO] In a Windows session with Developer Mode/elevated symlink privileges, retry direct `bun run package:win` and compare with the workaround output.

## Immediate next-session checklist

1. Confirm the current local blueprint model:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\app
bun test --preload ./happydom.ts ./src/pages/session/blueprint-model.test.ts ./src/pages/session/blueprint-side-panel.test.ts
bun run build
```

If touching catalog/model IPC, also run:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\desktop-electron
bun test ./src/main/blueprint-catalog.test.ts
```

2. Smoke the panel manually:

- open the blueprint panel from the session header
- right-click drag the canvas
- right-click a node and use `Edit` / `Delete`
- left-click a node and confirm the inspector stays closed
- double-click a node and confirm the inspector opens
- add all six node kinds from the dropdown
- drag a menu item onto the canvas and confirm grid snapping
- drag output port to input port and confirm an edge appears
- delete selected nodes/edges using `Backspace` and `Delete`
- edit the top-left common config panel and verify project workdir, skill dir,
  and rule dir persist
- verify the Agent inspector does not render editable command, cwd, workspace
  id/root, read/write/artifact scope, or raw skill_selection controls
- select multiple skills/rules and verify `toRuntimeGraphDraft` keeps
  `skills`, compatible `skill_selection`, and `rule_paths`
- switch CLI type and verify the model dropdown refreshes or shows failure
  while keeping the current model value
- click inspector `?` buttons and confirm the popover explains "what" and
  "usage"
- verify the inspector header, field labels, and question buttons are light on
  the dark surface
- verify select controls/options remain readable, especially `非阻塞`
- verify node fills/borders are visually distinct from the dark canvas

3. Then start runtime integration. The existing Electron/preload catalog
boundary should be extended into graph persistence and runtime status/start/end
APIs, not a renderer-side scheduler.

## File ownership reminders

- `GuLiCode/packages/app`: blueprint entrypoints, routes, workbench layout, desktop content surfaces
- `GuLiCode/packages/ui`: shared iconography and reusable UI building blocks
- `GuLiCode/packages/desktop-electron`: Electron shell, packaged identity, icon/taskbar behavior, startup hardening
- `GuLiCode/scripts/dev-desktop.ts`: one-click startup and packaged-smoke behavior

## Acceptance direction

This task line is in a good first state when:

1. A user can launch GuLiCode from one command.
2. The desktop shell visibly looks like Guli rather than Electron/OpenCode leftovers.
3. The blueprint entry opens a GuLiCode-owned surface.
4. That surface reads runtime/control-plane state rather than reimplementing scheduler rules.
5. Taskbar/window identity remains stable across repeated packaged launches.

Current status: items 1, 2, 3, and 5 have a working baseline. Item 4 is the next real blueprint development milestone.
Blueprint workbench local-draft editing is complete enough for the runtime
binding pass: it has RouteNode, port edges, configurable AgentNode fields,
terminal nodes, add/drop interactions, context menu deletion, inspector
separation, grid snapping, common config, catalog-backed skill/rule dropdowns,
and CLI/model dropdowns. Runtime binding, durable project persistence, and
status projection are the next UI milestones.
