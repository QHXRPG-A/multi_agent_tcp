# Blueprint Runtime Task Entry And Panel Reorder - 2026-05-21

## Summary

This pass changed the GuLiCode blueprint runtime entry from a direct manual
start button into a task-planning handoff through the main chat Top Agent
planning flow.

The runtime panel now asks for an optional set of starting AgentNodes plus a
required task. Submitting the task creates a real user-side message in the main
chat, switches the composer to `blueprintPlanning`, and lets the existing Top
Agent planning path stage or reject the blueprint start.

The runtime panel also gained draggable top-level sections. Users drag the
small thick line above each panel; the original panel becomes a dashed
placeholder, and a detached dashed ghost follows the pointer until drop.

## Implemented Shape

Frontend graph model:

1. New default blueprints no longer create product-facing start/end terminal
   nodes.
2. The default runtime graph keeps only AgentNode/RouteNode execution edges.
3. The Add Node menu no longer exposes start/end nodes.
4. Legacy terminal nodes remain accepted by document import for compatibility,
   but they are hidden from the canvas, inspector, runtime plan, export, and
   runtime draft.
5. `toRuntimeGraphDraft` and `toBlueprintDocument` filter terminal nodes and
   terminal-connected edges.
6. `fromBlueprintDocument` still accepts old documents that contain
   `terminal_nodes`.
7. `createBlueprintStartPlan` now depends on explicit `startNodes`. If none
   are supplied it emits an empty `start_nodes`, leaving backend validation to
   return the expected start-plan error.

Backend validation:

1. `blueprint.validate`, `blueprint.start`, and
   `blueprint.planning.ensureContext` no longer call the old
   `validate_runnable()` terminal start/end requirement.
2. Desktop service validation now checks graph DAG/reference integrity and
   requires at least one AgentNode.
3. `TopAgentStartPlan` remains strict: final `start_nodes` must be non-empty,
   unique, reference AgentNodes, and have matching task entries.
4. Legacy fixture/executor paths that intentionally use `validate_runnable()`
   were left intact.

Runtime panel:

1. A task-planning panel was added at the top of "Runtime".
2. The start-node selector is a multi-select dropdown over AgentNodes. Empty
   selection means "Top Agent chooses during planning".
3. The task input is a large textarea, and task text is required for manual
   submission.
4. Submit is gated while runtime is busy, config is missing, API is
   unavailable, save fails, or the task is empty.
5. The top toolbar Start button and runtime header start icon no longer call
   `startBlueprintRun` directly. They focus the task-planning panel instead.
6. The runtime action buttons were restyled as vertical long rows with large
   action text and smaller explanatory copy.
7. The automatic "confirm project workdir" prompt is now guarded once per app
   lifetime. Manual directory selection and conflict confirmation dialogs are
   unchanged.

Main chat handoff:

1. `SessionSidePanel -> BlueprintSidePanel -> SessionComposerRegion ->
   PromptInput` now has a one-shot blueprint planning submit request path.
2. A panel submit switches the main composer to `blueprintPlanning`, writes
   the task as the user prompt, and submits through the existing
   `prepareBlueprintPlanningMessage` override.
3. The message sent to chat includes the user task and the start-node
   constraint. If the user selected AgentNodes, the prompt requires Top Agent
   to use them as final `start_nodes`. If none were selected, it states that
   Top Agent may choose, but final staged plans still need non-empty
   `start_nodes`.
4. If the main composer already has unsent draft text/context, the panel
   submit is blocked to avoid overwriting the user's draft.

Runtime panel reorder:

1. Each top-level runtime panel is wrapped in `RuntimePanelShell`.
2. Each wrapper exposes a thick draggable handle above the panel.
3. During drag, the original panel is replaced by a dashed placeholder in the
   normal layout.
4. A fixed-position dashed ghost follows the pointer and is detached from the
   runtime layout.
5. Pointer movement reorders panels by comparing the pointer Y position to
   visible panel midpoints.
6. Pointer up/cancel/blur ends the drag and drops the panel in the current
   placeholder position.

## Verification

Frontend planning-entry pass:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\app
bun test --preload ./happydom.ts ./src/pages/session/blueprint-model.test.ts ./src/pages/session/blueprint-side-panel.test.ts ./src/pages/session/blueprint-planning-session.test.ts ./src/components/prompt-input/submit.test.ts ./src/i18n/parity.test.ts
bun run typecheck
```

Observed result: 33 tests passed, typecheck passed.

Backend pass:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp
python -m pytest -q test_desktop_blueprint_service.py
python -m py_compile desktop_blueprint_service.py graph_runtime.py graph_control.py test_desktop_blueprint_service.py
```

Observed result: 32 passed, 1 skipped, py_compile passed.

Runtime panel drag refinement:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\app
bun run typecheck
bun test --preload ./happydom.ts ./src/pages/session/blueprint-side-panel.test.ts ./src/i18n/parity.test.ts
```

Observed result: typecheck passed, 11 tests passed.

Debug startup after implementation:

```text
Renderer: http://localhost:5173/
Sidecar:  http://127.0.0.1:4671
Electron main PID: 20644
Logs:
  F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\logs\gulicode-desktop-direct.log
  %TEMP%\gulicode-dev\dev-desktop.out.log
  %TEMP%\gulicode-dev\dev-desktop.err.log
```

## Files Touched

Frontend:

- `GuLiCode/packages/app/src/pages/session/blueprint-model.ts`
- `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.tsx`
- `GuLiCode/packages/app/src/pages/session.tsx`
- `GuLiCode/packages/app/src/pages/session/session-side-panel.tsx`
- `GuLiCode/packages/app/src/pages/session/composer/session-composer-region.tsx`
- `GuLiCode/packages/app/src/components/prompt-input.tsx`
- `GuLiCode/packages/app/src/components/prompt-input/submit.ts`
- `GuLiCode/packages/app/src/context/platform.tsx`
- `GuLiCode/packages/app/src/i18n/en.ts`
- `GuLiCode/packages/app/src/i18n/zh.ts`
- `GuLiCode/packages/app/src/i18n/zht.ts`

Backend:

- `desktop_blueprint_service.py`
- `test_desktop_blueprint_service.py`

Tests:

- `GuLiCode/packages/app/src/pages/session/blueprint-model.test.ts`
- `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.test.ts`
- `GuLiCode/packages/app/src/pages/session/blueprint-planning-session.test.ts`
- `GuLiCode/packages/app/src/components/prompt-input/submit.test.ts`

## Follow-Up Queue

1. Manual desktop smoke for the intended user path:
   task panel submit -> main chat user message -> automatic
   `blueprintPlanning` mode -> Top Agent staged plan -> approve -> live run.
2. Visual smoke on narrow Runtime panel widths: multi-select dropdown,
   selected AgentNode pills, textarea, submit button, long action buttons, and
   draggable panel ghost/placeholder should not overlap.
3. Decide whether runtime panel order should persist across panel sessions or
   remain in-memory only.
4. Keep terminal-node support compatibility-only. Do not reintroduce
   start/end as product-facing Add Node choices unless the product direction
   changes.
