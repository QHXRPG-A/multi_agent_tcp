# Blueprint Workbench External Run Sync

Date: 2026-06-02

## Summary

This archive records the Workbench-side changes around removing the planning
request button and making already-open Workbench pages discover Blueprint runs
that are started externally through Codex MCP tools.

The UI should support two distinct paths:

- Codex chat handles negotiated start plans and calls MCP tools directly.
- Workbench offers a compact direct-run shortcut and observes runtime state.

## Planning UI Removal

Removed from the Workbench runtime panel:

- `data-blueprint-runtime-plan-create`
- task textarea / `data-blueprint-runtime-task-input`
- planning request status block
- Workbench-to-Codex planning submit bridge

Kept:

- `RuntimeStartNodeSelect`
- `data-blueprint-runtime-confirm-run`
- direct run via `createBlueprintStartPlan(draft, { startNodes })`
- `platform.startBlueprintRun(..., "live")`

Direct run no longer depends on a free-form task textarea. With selected start
AgentNodes, the plan uses their configured prompt/default goal path.

## External MCP Start Sync Bug

Observed issue:

- Codex MCP started `run-470f52a8a2cb` successfully.
- `blueprint_list_runs` returned the running run first.
- A newly opened Workbench page showed `run-470f52a8a2cb` as `running`.
- An already-open Workbench page stayed selected on old terminal
  `run-99aa41fd2871` and showed `CANCELLED`.
- The user had to press Ctrl+R to reload the page before seeing the new active
  run.

Root cause:

- The Workbench initialized `runtime.runId` once from `listBlueprintRuns`.
- After selecting a terminal run, it only polled that run's detail.
- It did not continue polling `listBlueprintRuns` to discover external MCP
  starts.
- Because the selected run was terminal, detail polling also stopped.

Fix:

- Added periodic `listBlueprintRuns` sync in the runtime panel.
- Added `selectPreferredRuntimeRun()`.
- Added `runtimeRunIsActive()`.
- Active/start-pending runs are preferred over a current terminal run.
- If the current run is terminal and a running run appears, the page switches to
  the running run and refreshes its status without requiring Ctrl+R.

## Verification

Frontend tests:

```text
bun test GuLiCode/packages/app/src/pages/session/blueprint-side-panel.test.ts
bun test GuLiCode/packages/app/src/pages/session/blueprint-side-panel.test.ts GuLiCode/packages/app/src/pages/session/blueprint-planning-session.test.ts GuLiCode/packages/app/src/pages/session/blueprint-model.test.ts
bun run --cwd GuLiCode/packages/app typecheck
```

Results:

- `blueprint-side-panel.test.ts`: passed.
- Full relevant Bun set: passed.
- Typecheck: passed.

Manual/browser checks:

- Workbench DOM no longer includes `data-blueprint-runtime-plan-create`.
- Workbench DOM no longer includes `data-blueprint-runtime-task-input`.
- Workbench still includes `data-blueprint-runtime-start-node-select`.
- Workbench still includes `data-blueprint-runtime-confirm-run`.
- A fresh Workbench load displayed running `run-470f52a8a2cb`.
- The page showed `状态: running` and `RUNNING`, not the old cancelled run.

Later observation:

- A later MCP poll showed `run-470f52a8a2cb` had reached terminal
  `status=completed`, `finalStatus=failed`, and MCP `state=closed`.
- This does not change the frontend sync conclusion: the fixed issue was that
  an already-open Workbench page did not discover an externally started active
  run until Ctrl+R.

## Packaging/Runtime Note

Updating the built static bundle does not hot-replace JavaScript already loaded
in an open browser tab. The current open tab must reload once to load the new
bundle. After that, external MCP starts should be discovered by the periodic
run-list sync and should not require Ctrl+R.

## Files Touched In This Work Area

- `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.tsx`
- `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.test.ts`
- `GuLiCode/packages/app/src/context/platform.tsx`
- `GuLiCode/packages/app/src/entry.tsx`
- `GuLiCode/packages/app/src/pages/session/blueprint-window.tsx`
- `GuLiCode/packages/app/src/pages/session.tsx`
- `GuLiCode/packages/app/src/pages/session/session-side-panel.tsx`
- `GuLiCode/packages/app/src/i18n/en.ts`
- `GuLiCode/packages/app/src/i18n/zh.ts`
- `GuLiCode/packages/app/src/i18n/zht.ts`
