# Guli desktop UI productization and blueprint embedding

This document records the current effective knowledge for the Guli desktop UI line inside `multi_agent_tcp/GuLiCode`.

## Position

The current UI main line is:

```text
Guli productization
  -> blueprint embedded in GuLiCode desktop
  -> runtime/control-plane state rendered inside GuLiCode
```

This means:

- The user-facing product surface is `GuLiCode`, not a separate Ryven-led visual-editor app.
- Blueprint capability should appear as a GuLiCode route, panel, or workbench entry.
- Runtime semantics remain framework-owned by `GraphRuntimeControlPlane` and `GraphRuntime`; the renderer only consumes their state.

## Current landed baseline

As of 2026-05-14, the following desktop/UI baseline is already in place:

1. Desktop bring-up:
   - one-click entry: `F:\src\Package\Script\Python\multi_agent_tcp\start-gulicode-desktop.cmd`
   - packaged smoke: `F:\src\Package\Script\Python\multi_agent_tcp\start-gulicode-desktop.cmd --packaged`
   - packaged output path: `GuLiCode/packages/desktop-electron/dist/packaged-launch/current/win-unpacked/GuLiCode Dev.exe`

2. Productization surfaces:
   - the new-session empty state now shows `GULI`
   - the desktop header now exposes a blueprint entry button
   - clicking the blueprint entry opens a GuLiCode-owned right-side blueprint panel
   - the blueprint panel now hosts a local interactive graph workbench with a
     runtime-shaped draft, route nodes, port-aware edges, node ports,
     add-node dropdown/drop-to-canvas, selection, right-click pan, wheel zoom,
     node drag, context menus, keyboard deletion, reset/fit view, and inspector
     editing
   - the inspector now has per-field `?` tip buttons; clicking one explains
     what the field is and what it is used for
   - the current blueprint visual direction is dark, technology-oriented, and
     minimal: the inspector is dark with light labels/buttons, node fills and
     borders are differentiated from the canvas, and native select controls
     have readable dark options including `nonblocking` / `非阻塞`
   - the canvas now has a top-left "blueprint common config" panel for
     `project_workdir`, `skill_dir`, and `rule_dir`
   - the Agent inspector now exposes only per-Agent execution and capability
     fields; framework-owned workspace, scope, and command fields are kept in
     the model/runtime export but are no longer user-editable controls
   - skill and rule selection are multi-select dropdowns populated from the
     configured directories
   - CLI kind and model are dropdowns. Model choices refresh through desktop
     IPC when the CLI changes
   - user-visible blueprint copy is wired in `en` / `zh` / `zht`

3. Desktop shell hardening:
   - packaged main-window creation no longer dies when icon resources are missing or unreadable
   - saved off-screen window state is clamped back to a visible display
   - packaged `exe` icon is post-patched with `rcedit`
   - packaged output path is stable, which helps Windows taskbar identity and repinning

## File ownership map

Use these ownership boundaries when implementing Guli desktop UI work:

```text
GuLiCode/packages/app
  -> desktop routes, panels, layout, session views, blueprint workbench UI

GuLiCode/packages/ui
  -> shared icons, buttons, design tokens, reusable view primitives

GuLiCode/packages/desktop-electron
  -> Electron main/preload/window shell, packaged resources, app identity,
     taskbar behavior, icons, startup hardening

GuLiCode/scripts/dev-desktop.ts
  -> one-click bring-up, packaged launch flow, smoke-oriented launch behavior
```

Current concrete anchor files:

- `GuLiCode/packages/app/src/components/session/session-header.tsx`
- `GuLiCode/packages/app/src/components/session/session-new-view.tsx`
- `GuLiCode/packages/app/src/context/platform.tsx`
- `GuLiCode/packages/app/src/context/layout.tsx`
- `GuLiCode/packages/app/src/i18n/en.ts`
- `GuLiCode/packages/app/src/i18n/zh.ts`
- `GuLiCode/packages/app/src/i18n/zht.ts`
- `GuLiCode/packages/app/src/pages/session.tsx`
- `GuLiCode/packages/app/src/pages/session/session-side-panel.tsx`
- `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.tsx`
- `GuLiCode/packages/app/src/pages/session/blueprint-model.ts`
- `GuLiCode/packages/app/src/pages/session/blueprint-model.test.ts`
- `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.test.ts`
- `GuLiCode/packages/ui/src/components/icon.tsx`
- `GuLiCode/packages/desktop-electron/src/main/blueprint-catalog.ts`
- `GuLiCode/packages/desktop-electron/src/main/blueprint-catalog.test.ts`
- `GuLiCode/packages/desktop-electron/src/main/ipc.ts`
- `GuLiCode/packages/desktop-electron/src/preload/index.ts`
- `GuLiCode/packages/desktop-electron/src/preload/types.ts`
- `GuLiCode/packages/desktop-electron/src/main/windows.ts`
- `GuLiCode/packages/desktop-electron/electron-builder.config.ts`
- `GuLiCode/scripts/dev-desktop.ts`

## Blueprint embedding rules

Use these rules when adding blueprint UI to GuLiCode:

- Place blueprint entrypoints in GuLiCode-owned surfaces such as the session header, sidebar, tabs, or dedicated workbench routes.
- Keep execution semantics in `GraphRuntimeControlPlane` and `GraphRuntime`.
- Let the renderer consume runtime-owned status, events, queues, joins, workspace changes, artifacts, and reports.
- Do not rebuild graph scheduling rules inside `packages/app`.
- It is acceptable for `packages/app` to own a UI-only `BlueprintDraft` model
  for local editing. Keep it shaped so `toRuntimeGraphDraft(draft)` can produce
  `{ terminal_nodes, agent_nodes, route_nodes, edges }` for later runtime
  binding.
- Keep user-editable blueprint-wide configuration in the canvas common config
  panel, not inside each Agent inspector. The current common fields are
  `project_workdir`, `skill_dir`, and `rule_dir`.
- Keep framework-owned execution details hidden from the Agent inspector:
  private checkout cwd rewriting, workspace IDs/roots, read/write/artifact
  scope policy, and generated CLI command strings are runtime concerns.
- Do not place real product logic in `packages/desktop-electron/src/renderer/index.tsx`; that file is only the desktop shell bootstrap.

## Blueprint panel local draft workbench

The current right-side blueprint panel is not just a placeholder. As of
2026-05-14 it contains a runtime-aligned local draft graph workbench:

- draft model: `BlueprintDraft`
- persistence: `Persist.workspace(projectDir, "blueprint-draft.v1")`
- runtime conversion: `toRuntimeGraphDraft(draft)` emits
  `{ terminal_nodes, agent_nodes, route_nodes, edges }`
- blueprint common config: top-left canvas panel with `project_workdir`,
  `skill_dir`, and `rule_dir`; `project_workdir` defaults to the opened project
  directory and is applied to each AgentNode `cwd` during runtime draft export
- seed graph: `start -> planner -> coder -> review -> summary -> end`
- canvas: HTML nodes plus SVG edges
- data model: `AgentNode`, `RouteNode`, terminal nodes, and port-aware edges
  with default `out -> in` exec ports
- interactions: wheel zoom, right-click blank-canvas pan, node drag, click
  selection, double-click inspector, right-click node menu, fit view, reset view
- add node: `Add node` dropdown with Agent, Route sequence, Route parallel,
  Route parallel_reduce, Start, and End; click adds at viewport center, drag
  adds at the snapped canvas drop point
- ports: Start output only, End input only, Agent/Route input and output
- connections: drag from output port to input port; duplicate edges are rejected
- deletion: node right-click menu, selected node/edge `Backspace` / `Delete`,
  and selected-edge inspector action; deleting a node cascades connected edges
- grid: `GRID_SIZE = 24`, and node drag plus node creation snap to grid while
  viewport panning does not
- inspector: Agent fields currently exposed to users are `agent_id`, `prompt`,
  `execution_mode`, `cli_kind`, `model`, `skills`, `rule_paths`,
  `timeout_sec`, `prompt_via_file`, `external`, `adapter_options`, and
  `extra_env`; Route fields include `route_kind`, `targets`, `reduce_target`,
  and `reduce_prompt`; Edge fields include `edge_type`, `output_port`, and
  `input_port`
- hidden AgentNode compatibility fields remain in the draft model for runtime
  export and backend compatibility: `cwd`, `command`, `skill_selection`,
  `workspace_id`, `workspace_root`, `read_scope`, `write_scope`, and
  `artifact_scope`
- skills: selected from `skill_dir` by scanning subdirectories containing
  `SKILL.md`; values export both to `skills` and
  `skill_selection: { mode: "selected", skill_hashes: [...] }`; an empty
  selection exports `skill_selection: { mode: "none" }`
- rules: selected from `rule_dir` by scanning direct rule files with common
  text extensions (`.md`, `.txt`, `.json`, `.yaml`, `.yml`, `.toml`); empty
  `rule_dir` means no options and no error
- CLI/model: `cli_kind` supports `codemaker` and `codex`; command strings are
  generated by the framework (`codemaker` or `codex`) and not shown as an input;
  model dropdown choices are refreshed through Electron IPC
- `adapter_options`: advanced JSON passed through to the selected CLI adapter
  as low-level fallback options, such as Codex sandbox/config/extra_args or
  CodeMaker base_args. Most users should leave it empty
- inspector tips: most Agent, Route, Terminal, and Edge fields have a `?`
  button that opens a small dark popover with "what" and "usage" copy
- JSON fields preserve the previous parsed value and show invalid state while
  the text area contains invalid JSON

Visual guardrails for the next blueprint pass:

- Keep the panel dark and restrained; avoid bright marketing gradients or
  decorative backgrounds.
- Keep node colors distinguishable from the canvas background through fill,
  border, and selected-state contrast.
- Keep inspector text, section title, labels, and `?` buttons light on the dark
  inspector background.
- Keep native select text and option colors readable. The `nonblocking` /
  `非阻塞` option is a required smoke target because it regressed before.

This is still local draft UI only. It does not start runtime execution and does
not put scheduler logic in the renderer.

## Productization rules

- Prefer `GULI` / `GuLiCode` branding in user-visible desktop surfaces.
- Keep app/window/taskbar identity aligned across:
  - Electron app name
  - `AppUserModelId`
  - packaged icon resources
  - empty-state wordmarks
  - visible action labels
- When changing icons, update the desktop-electron channel icon sets (`dev` / `beta` / `prod`) and re-run the packaged startup flow so the final `exe` is repatched.

## Windows taskbar and packaged-icon notes

- The runtime window icon is loaded from `resources/icons`.
- The packaged shell also copies `resources/icons` into `process.resourcesPath/icons`.
- The final `exe` icon is patched after packaging through `rcedit`, because builder output alone may still keep the stale Electron-style icon in the executable resource table.
- Full NSIS packaging can hit electron-builder `winCodeSign` symlink
  extraction failures in a normal Windows session. When that happens, use a
  temporary local builder config with `win.signAndEditExecutable = false` and
  an `afterPack` `rcedit --set-icon resources/icons/icon.ico` hook. The full
  command flow is recorded in `gulicode_desktop.md`.
- If Windows still shows an old pinned icon after the `exe` resource is corrected, repin from the fixed path:

```text
GuLiCode/packages/desktop-electron/dist/packaged-launch/current/win-unpacked/GuLiCode Dev.exe
```

That symptom is usually stale taskbar pin caching, not proof that the latest `exe` is wrong.

## Current known boundaries

- The blueprint header button currently opens a right-side panel with local
  graph draft editing and desktop catalog/model lookup, not runtime-backed
  execution.
- The session/blueprint divider is resizable through the same `ResizeHandle` and `layout.session.width()` path used by the review side panel.
- The next blueprint UI milestone is runtime/control-plane binding, persisted
  project JSON ownership, extending the existing Electron/preload boundary
  from catalog/model lookup into Python runtime start/status/end, and live
  status projection.
- Tauri still exists, but Electron is the default desktop verification path on this machine.
- Blueprint UI should not regress back into a separate legacy Ryven/editor workstream unless the user explicitly reopens that direction.
