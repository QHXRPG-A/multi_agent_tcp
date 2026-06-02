# Blueprint Script Function Node UI, IDE, Compile - 2026-05-31

## Summary

This pass added user-authored Python Function Nodes to the GuLiCode Blueprint
canvas and made Script Function Nodes feel like native Blueprint nodes.

The user workflow now centers on right-click node search, IDE-backed script
creation/opening, a canvas-local compile button, and a Python-logo-inspired
Function Node visual with dynamic ports.

## Implemented

Right-click node search:

1. Right-button drag still pans the Blueprint canvas.
2. Right-button click opens a UE-style node search card at the clicked canvas
   position.
3. The search card contains an auto-focused search box, a scrollable node list,
   and a `+` action for creating Script Function Nodes.
4. The list reuses the existing Agent/Route/Script add options and places the
   selected node at the clicked Blueprint coordinates.
5. The old toolbar add-node button was replaced by the Script editor selector.

Script creation UI:

1. The `+` button opens a dialog for Function Node name and optional
   description.
2. Creation calls `platform.createBlueprintScriptNode(projectDir, name,
   description)`.
3. The created script is added to the catalog and immediately placed on the
   canvas.
4. The description is stored in the decorator and becomes the collapsed node
   subtitle; empty descriptions render as the localized "no description" copy.

IDE workflow:

1. The toolbar now exposes a Script editor dropdown backed by
   `platform.listBlueprintEditors()`.
2. The selected editor is persisted with
   `Persist.global("blueprint.scriptEditor.v1")`.
3. Double-clicking a Script Function Node opens the corresponding Python script
   in the selected editor via `openBlueprintScriptInEditor`.
4. Non-script node double-click behavior remains unchanged.

Compile workflow:

1. Added a fixed canvas-top-left `Compile` button that does not move with pan or
   zoom.
2. Compile calls the existing script catalog scan and does not import or execute
   user code.
3. Already placed Script Nodes are refreshed in place by `script_id`, with
   fallback to `module_path + function_name`.
4. Node id, layout, selection, collapsed state, and inspector state are
   preserved.
5. Connections to removed script ports are automatically cleaned and reported.
6. The Inspector "refresh script" action now reuses the same compile flow.

Script node visual:

1. Script Function Nodes support collapsed and expanded states.
2. Collapsed nodes show the Python mark, node title, and description.
3. Expanded nodes show per-port labels, with input ports on the left and output
   ports on the right.
4. Ports are small triangles instead of circular pins.
5. Input triangles are yellow; output triangles remain cyan.
6. The node uses a Python-inspired blue/yellow block treatment.
7. The blue/yellow split uses a sharp Z-shaped seam with shadow/highlight
   layering so the two color blocks read as fitted pieces.

I18n:

1. Added English, Simplified Chinese, and Traditional Chinese copy for right
   click search, script creation, editor selection, compile state, inspector
   fields, collapse/expand, and bridge errors.

## Files Changed

Frontend/app:

1. `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.tsx`
2. `GuLiCode/packages/app/src/pages/session/blueprint-model.ts`
3. `GuLiCode/packages/app/src/context/platform.tsx`
4. `GuLiCode/packages/app/src/pages/session.tsx`
5. `GuLiCode/packages/app/src/i18n/en.ts`
6. `GuLiCode/packages/app/src/i18n/zh.ts`
7. `GuLiCode/packages/app/src/i18n/zht.ts`

Tests:

1. `GuLiCode/packages/app/src/pages/session/blueprint-model.test.ts`
2. `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.test.ts`
3. `GuLiCode/packages/app/src/pages/session/blueprint-planning-session.test.ts`

Desktop renderer/preload surface:

1. `GuLiCode/packages/desktop-electron/src/preload/types.ts`
2. `GuLiCode/packages/desktop-electron/src/preload/index.ts`
3. `GuLiCode/packages/desktop-electron/src/renderer/index.tsx`

## Verification

Renderer focused tests:

```powershell
cd D:\agent\multi_agent_tcp\GuLiCode\packages\app
bun test --preload ./happydom.ts ./src/pages/session/blueprint-model.test.ts ./src/pages/session/blueprint-side-panel.test.ts
bun test --preload ./happydom.ts ./src/pages/session/blueprint-side-panel.test.ts
bun run typecheck
```

Observed result:

```text
blueprint-side-panel focused suite: 17 passed
app typecheck passed
```

Manual visual check:

1. Loaded the local GuLiCode app at `http://127.0.0.1:3040/.../session`.
2. Injected a test Script Function Node with three inputs and two outputs.
3. Verified the expanded node rendered input/output labels.
4. Verified input triangle color:
   `rgb(250, 204, 21)`.
5. Verified output triangle color:
   `rgb(125, 211, 252)`.
6. Verified the seam clip path:
   `polygon(0 0, 42% 0, 55% 30%, 47% 30%, 60% 58%, 52% 58%, 64% 100%, 0 100%)`.
7. Verified the seam shadow exists with `stroke-width=5.2` and
   `drop-shadow(rgba(8, 47, 73, 0.42) 2px 0px 4px)`.

## Follow-Up Queue

1. Add a real UI interaction test around right-click search once the test
   harness can reliably drive pointer button distinction.
2. Revisit the Script Function Node visual after more real graph density is
   available; the current visual is intentionally distinct from Agent nodes.
3. Consider adding script node rename/delete actions after the script catalog
   workflow stabilizes.

## Skill/Archive Files

Installed skill:

```text
C:\Users\13429\.codex\skills\multi-agent-tcp\archive\frontend\blueprint_script_function_node_ui_ide_compile_2026-05-31.md
```

Repository snapshot:

```text
KM_docs/skills-snapshot/archive/frontend/blueprint_script_function_node_ui_ide_compile_2026-05-31.md
```
