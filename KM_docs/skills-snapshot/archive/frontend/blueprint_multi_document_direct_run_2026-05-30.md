# Blueprint Multi Document Direct Run - 2026-05-30

## Summary

This pass made the GuLiCode Blueprint side panel project-blueprint aware and
added a direct live-run path from the Runtime panel.

The Blueprint toolbar now selects from project documents stored under
`.multi_agent_workspace/blueprints/*.json` and can create a new blueprint
document. The Runtime task panel keeps the existing Top Agent planning submit
flow, but also exposes a `Run` button that starts the selected blueprint
directly in `live` mode after the user chooses at least one start Agent.

## Implemented

Blueprint document selection:

1. `BlueprintSidePanel` now tracks the selected `blueprintId` and
   `blueprintName`.
2. The top toolbar includes a blueprint dropdown backed by
   `platform.listBlueprints(projectDirectory)`.
3. Switching blueprints flushes the current document with `saveBlueprint`,
   opens the selected document with `openBlueprint(projectDirectory,
   blueprintId)`, replaces the draft, and resets runtime/diff/Agent panel
   state.
4. `New blueprint` opens a small dialog, generates a legal id from the name,
   resolves collisions with `-2`, `-3`, and saves a default graph using the
   current common config.
5. Project save, open, relocate, run listing, flow lock keys, and desktop
   collaboration snapshots now use the current selected blueprint id/name.

Runtime panel:

1. The planning section title now covers start nodes, Top Agent planning, and
   direct run.
2. The existing multi-select start Agent control remains shared by planning and
   direct run.
3. The existing `Submit` button still requires task text and still hands off to
   Top Agent blueprint planning.
4. The new `Run` button is disabled while saving/loading/running, when the
   runtime API is unavailable, or when no start Agent is selected.
5. Direct run detects Python, validates common config, saves the current
   blueprint document, builds `createBlueprintStartPlan(startDraft, {
   startNodes, taskText })`, and calls
   `platform.startBlueprintRun(projectDirectory, currentBlueprintId(), plan,
   "live")`.
6. A successful direct run writes returned run id, status, events, and run list
   state into the existing runtime panel so polling, Agent panels, runtime flow,
   and Blueprint Diff continue through the existing code paths.

Planning session binding:

1. `BlueprintPlanningSubmitInput` now carries `blueprintId` and
   `blueprintName`.
2. The main `session.tsx` planning context records the selected blueprint id and
   passes it to `ensureBlueprintPlanningContext`.
3. Approving a Top Agent staged plan starts the same selected blueprint id
   instead of always starting `default`.
4. Popout blueprint windows forward the selected blueprint id through the
   existing `submitBlueprintWindowPlanning` bridge type.

Tests:

1. Renderer source tests now assert selected-id persistence and the presence of
   both `data-blueprint-runtime-task-submit` and
   `data-blueprint-runtime-direct-run`.
2. Renderer source tests assert the direct-run path includes
   `createBlueprintStartPlan(startDraft, { startNodes, taskText })` and
   `platform.startBlueprintRun(..., "live")`.
3. Desktop runtime bridge tests now save/open two blueprint ids and verify
   `start`/`listRuns` filter by blueprint id.

## Files Changed

Frontend/app:

1. `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.tsx`
2. `GuLiCode/packages/app/src/pages/session.tsx`
3. `GuLiCode/packages/app/src/context/platform.tsx`
4. `GuLiCode/packages/app/src/i18n/en.ts`
5. `GuLiCode/packages/app/src/i18n/zh.ts`
6. `GuLiCode/packages/app/src/i18n/zht.ts`

Tests:

1. `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.test.ts`
2. `GuLiCode/packages/app/src/pages/session/blueprint-planning-session.test.ts`
3. `GuLiCode/packages/desktop-electron/src/main/blueprint-runtime.test.ts`

Desktop bridge types:

1. `GuLiCode/packages/desktop-electron/src/preload/types.ts`

## Verification

Renderer:

```powershell
cd D:\agent\multi_agent_tcp\GuLiCode\packages\app
bun test --preload ./happydom.ts ./src/pages/session/blueprint-model.test.ts ./src/pages/session/blueprint-side-panel.test.ts ./src/pages/session/blueprint-planning-session.test.ts
bun run typecheck
```

Observed result: 35 tests passed, typecheck passed.

Desktop Electron:

```powershell
cd D:\agent\multi_agent_tcp\GuLiCode\packages\desktop-electron
bun test ./src/main/blueprint-runtime.test.ts
bun run typecheck
```

Observed result: 10 tests passed, typecheck passed.

Local dev server:

```text
http://localhost:5173/ returned HTTP 200
```

## Follow-Up Queue

1. Manual smoke in the desktop app:
   create two blueprints, switch between them, confirm each keeps a different
   graph, then direct-run one with multiple selected start Agents.
2. Visual smoke at narrow Runtime panel widths for the blueprint dropdown, new
   dialog, selected Agent pills, and the new Run/Submit button row.
3. Consider adding rename/delete/copy blueprint document operations only if the
   product asks for full blueprint document management.

## Skill/Archive Files

Installed skill:

```text
C:\Users\13429\.codex\skills\multi-agent-tcp\archive\frontend\blueprint_multi_document_direct_run_2026-05-30.md
```

Repository snapshot:

```text
KM_docs/skills-snapshot/archive/frontend/blueprint_multi_document_direct_run_2026-05-30.md
```
