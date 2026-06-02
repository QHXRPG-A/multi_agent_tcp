# Guli app UI tasks

## Current positioning

The current UI workstream is:

```text
gulicode-bp plugin workbench
  -> GuLiCode app Blueprint routes/components
  -> /mobile and /console
  -> runtime-backed web workbench
```

Use Electron desktop tasks only when the user explicitly asks for desktop shell,
IPC, packaging, taskbar, or windowing work.

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
- [DONE] Added the first live blueprint runtime path through desktop Python
  service: `status/live` start modes, live `GraphRuntime` tick loop,
  `CLIWorkerBackend`, status/end cleanup, agentInfo, queueAgentMessage, and
  WebSocket stream token.
- [DONE] Added the Agent information panel on blueprint Agent nodes:
  left mouse long-press with circular progress, right-click `信息面板`,
  close, pin, multiple pinned panels, outside-click close for non-pinned
  panels, stream transcript, default/top send modes, read-only static display
  when no live run exists, drag-to-move, and bottom-right resize.
- [DONE] Fixed Agent information panel close behavior by replacing the Solid
  store `panels` object with `reconcile(panels)` instead of shallow-merging a
  filtered object.
- [DONE] Fixed the desktop debug noise from the 2026-05-18 code-error pass:
  `blueprint-list-models` Windows `spawn EPERM`, Solid DnD nonexistent
  droppable/draggable cleanup, stale PTY WebSocket teardown, and blueprint SVG
  render computations.
- [DONE] Documented clean Electron debug startup after packaging notes:
  `ELECTRON_ENABLE_LOGGING=1`, `ELECTRON_ENABLE_STACK_DUMPING=1`, and no
  default `DEBUG=*`.
- [DONE] Reduced Test Agent debug JSON to v2 message arrays only:
  `agentReplies`, `userMessages`, and `frameworkMessages`.
- [DONE] Mapped Agent panel `status` events into structured UI and removed
  raw `status`, `message.started`, `queue.updated`, tool traces, stderr
  deltas, reasoning deltas, and Codex internal log lines from the visible
  transcript.
- [DONE] Fixed Agent panel interaction gaps: panels can be dragged outside the
  viewport after opening, display text is selectable/copyable, and the panel
  body handles wheel scrolling.
- [DONE] Removed hard-coded user-machine absolute path defaults from blueprint
  code. `skill_dir` and `rule_dir` start empty and are supplied through the
  blueprint common config panel when needed.
- [DONE] Added common config `?` help buttons using the same popover
  interaction as inspector `?` buttons.
- [DONE] Blocked blueprint start when required common config paths are missing
  or not absolute. The guard exists in the renderer before save/start and in
  the desktop service `blueprint.start` path for IPC/direct calls.
- [DONE] Changed rule catalog selection values to filenames relative to common
  `rule_dir`; the desktop service resolves them at start so Agent `rule_paths`
  no longer capture local absolute paths from the user's machine.
- [DONE] Fixed desktop blueprint live startup so workers are launched from the
  `GraphRuntime` materialized private Agent context, including private
  checkout cwd, private `CODEX_HOME`, `framework-agent-runtime`, `AGENTS.md`,
  Workspace API env/prompt context, and authorized skill/rule materialization.
- [DONE] Retired product-facing start/end terminal nodes from new blueprints:
  Add Node no longer lists them, legacy terminal nodes are hidden, and
  runtime/export paths filter terminal nodes and terminal-connected edges.
- [DONE] Added the Runtime task-planning entry: optional multi-select start
  AgentNodes, required large task textarea, gated submit, and main-chat
  `blueprintPlanning` handoff instead of direct manual start.
- [DONE] Changed the top Start controls to focus the Runtime task-planning
  area, preventing direct starts that bypass task input.
- [DONE] Changed Runtime action buttons into long row controls with large
  action labels and smaller explanatory text.
- [DONE] Added draggable top-level Runtime panels with thick handles, dashed
  in-layout placeholders, and detached pointer-following drag ghosts.
- [DONE] Limited the automatic project workdir confirmation dialog to once per
  app lifetime.

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
  parallel, and Route parallel_reduce entries. Click adds at the viewport
  center; dragging an item onto the canvas adds at the snapped drop point.
  Start and End were later retired from product-facing Add Node UI.
- [DONE] Added visible Agent/Route input and output ports. Start/End terminal
  ports are now legacy import compatibility only, not current product UI.
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
  and empty web/test fallback behavior.
- [DONE] Added CLI/model dropdown behavior. `cli_kind` supports `codemaker`
  and `codex`; changing it refreshes model choices and the runtime export
  generates the command string.
- [DONE] Added task-first Runtime entry with start AgentNode selection, task
  textarea, submit gating, and main-chat `blueprintPlanning` handoff.
- [DONE] Added Runtime top-level panel reordering by dragging the thick handle
  above a panel, with an in-layout placeholder and detached drag ghost.
- [TODO] Manual visual smoke pass in the packaged app for inspector colors,
  select menu readability, `非阻塞` visibility, common config placement,
  skill/rule dropdowns, model loading/failure state, Runtime task planning,
  draggable Runtime panels, and tip popovers.
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
- [DONE] Defined and implemented the first live UI contract between the
  blueprint panel and `GraphRuntimeControlPlane`: `HTTP/IPC` for control
  requests and WebSocket for unified `AgentStreamEvent` streaming.
- [DONE] Extended Electron/preload/platform from catalog/model lookup into
  runtime-owned start/status/end, recent events, agentInfo,
  queueAgentMessage, and agentStreamToken.
- [DONE] Show the first run status projection in GuLiCode: runs, agents,
  queues, outgoing batches, joins, jobs, workspace summary, and recent events.
- [DONE] Keep runtime and Agent panels as projections of
  runtime/control-plane state rather than renderer-owned execution logic.
- [DONE] Hardened `blueprint-list-models` CLI spawning enough for the current
  debug baseline: Windows `EPERM` and missing executable cases are surfaced as
  model-load failures instead of noisy Electron handler exceptions.
- [DONE] Fixed desktop blueprint `live` Agent startup so ordinary/Test Agents
  are launched from `GraphRuntime` materialized private context, not raw
  `CLIWorkerBackend` node configs.
- [DONE] Added task-first manual Runtime entry. The Runtime panel now submits
  required task text through the main chat `blueprintPlanning` flow instead of
  calling live start directly.
- [DONE] Added Runtime top-level panel reorder with handle drag, placeholder,
  and detached ghost.
- [TODO] Manual smoke the live run UI path: task panel submit, automatic
  `blueprintPlanning` chat handoff, staged plan approval, live start, tick,
  status polling,
  Agent long-press progress, right-click `信息面板`, move/resize, close/pin,
  non-pinned outside-click close, WebSocket transcript, and `default/top`
  queue sends.
- [DONE] Fixed the backend workspace regression where
  `test_agent_checkout_dulwich_merge_accepts_non_overlapping_same_file_changes`
  reported a conflict for non-overlapping same-file changes.
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
- [TODO] Consider turning clean debug startup into a helper script if it keeps
  being used during live-runtime smoke:
  `ELECTRON_ENABLE_LOGGING=1`, `ELECTRON_ENABLE_STACK_DUMPING=1`, no `DEBUG=*`,
  then `bun run dev`.

## Immediate next-session checklist

1. Confirm the current local blueprint model:

```powershell
cd GuLiCode\packages\app
bun test --preload ./happydom.ts ./src/pages/session/blueprint-model.test.ts ./src/pages/session/blueprint-side-panel.test.ts ./src/pages/session/blueprint-planning-session.test.ts ./src/components/prompt-input/submit.test.ts ./src/i18n/parity.test.ts
bun run typecheck
```

If touching catalog/model IPC, also run:

```powershell
cd GuLiCode\packages\desktop-electron
bun test ./src/main/blueprint-catalog.test.ts
```

2. Smoke the panel manually:

- open the blueprint panel from the session header
- right-click drag the canvas
- right-click a node and use `Edit` / `Delete`
- left-click a node and confirm the inspector stays closed
- double-click a node and confirm the inspector opens
- add Agent and Route node kinds from the dropdown; Start/End should not be
  present in Add Node
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
- in Runtime, verify the start AgentNode multi-select, task textarea, and
  submit gating
- submit a Runtime task and verify it appears as a main-chat user message with
  the composer switched to `blueprintPlanning`
- drag Runtime panel handles and verify the original panel becomes a dashed
  placeholder while a detached ghost follows the pointer
- click inspector `?` buttons and confirm the popover explains "what" and
  "usage"
- verify the inspector header, field labels, and question buttons are light on
  the dark surface
- verify select controls/options remain readable, especially `非阻塞`
- verify node fills/borders are visually distinct from the dark canvas
- long-press an Agent node and verify the circular progress ring opens the
  information panel
- move during long-press and verify opening is cancelled
- right-click an Agent node and open `信息面板`
- drag the information panel title to move it, then drag the bottom-right
  handle to resize it
- verify close, pin, multiple pinned panels, and outside-click close still work

3. Continue runtime integration from manual live-runtime smoke and hardening.
The Electron/preload catalog boundary has now been extended into runtime
status/start/end and Agent stream APIs; do not add renderer-side scheduler
semantics.

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

Current status: items 1, 2, 3, 4, and 5 have a working baseline.
Blueprint workbench local-draft editing is complete enough for the runtime
binding pass: it has RouteNode, port edges, configurable AgentNode fields,
legacy terminal compatibility without product-facing Start/End nodes, add/drop
interactions, context menu deletion, inspector separation, grid snapping,
common config, catalog-backed skill/rule dropdowns, CLI/model dropdowns,
runtime status projection, task-first Runtime entry, draggable Runtime panels,
and the first Agent information panel. Durable project persistence and manual
live-runtime smoke remain the next UI milestones.
