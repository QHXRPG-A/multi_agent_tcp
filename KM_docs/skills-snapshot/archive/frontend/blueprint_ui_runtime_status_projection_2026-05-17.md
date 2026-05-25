# Blueprint UI Runtime Status Projection Archive - 2026-05-17

This archive records the first complete status-coupling pass between the
GuLiCode blueprint panel and the framework-owned Blueprint Runtime middle
layer.

## Summary

The blueprint panel now saves the current project blueprint before starting a
runtime run, derives a deterministic `TopAgentStartPlan` from the visible graph,
stores the returned `runId`, polls runtime status/events, and projects
`GraphRuntimeControlPlane` / `GraphRuntime` state back into the UI.

This pass intentionally remains status-only. It still uses
`DesktopBlueprintNoopBackend`; no broker, CLI worker, automatic tick loop, or
renderer-side scheduler was added.

## Landed

1. Added `createBlueprintStartPlan(draft)` in the app blueprint model.
   - `agent_descriptions` covers every `AgentNode`.
   - empty prompts receive stable fallback text.
   - `start_nodes` are derived by walking `exec` edges from start terminals,
     passing through `RouteNode`, and collecting the first reachable agents in
     graph order with de-duplication.
   - `tasks` cover only the derived `start_nodes` and include backend-required
     `goal`, `expected_output`, and `acceptance` fields.
   - `run_policy` is fixed to
     `{ allow_parallel: true, source: "blueprint-ui-derived" }`.
2. Added runtime projection APIs in the Python desktop service.
   - `blueprint.listRuns(projectDir?, blueprintId?)` returns run summaries from
     the service-owned in-memory registry.
   - `blueprint.status` preserves `{ ok, runId, run, status }` and appends
     `explanation: runtime.explain_status(graph=graph)`.
   - `blueprint.start` accepts controlled `executionMode`; default/status mode
     is supported and `live` is explicitly rejected for now.
3. Extended Electron/preload/platform runtime boundaries.
   - `BlueprintRuntime.listRuns`
   - IPC/preload renderer bridge for `blueprint-list-runs`
   - app platform method `listBlueprintRuns`
4. Coupled the blueprint side panel to runtime lifecycle state.
   - Start saves the project `BlueprintDocument` first.
   - Save success then calls `startBlueprintRun(projectDirectory, "default",
     createBlueprintStartPlan(draft))`.
   - The panel records `runId`, `status`, `events`, `explanation`, loading,
     error, and last-updated state.
   - The panel polls `blueprintRunStatus` and `blueprintRecentEvents(runId, 50)`
     every 2 seconds while the run is non-terminal.
   - Polling stops automatically for `completed`, `cancelled`, `failed`, and
     `paused`; manual Refresh remains available.
   - Start, Refresh, Complete, Pause, and Cancel controls are available.
     End actions call `endBlueprintRun` and immediately refresh.
5. Added a thin Runtime side panel projection.
   - Overview: run state, status, counts, queue totals, job totals, workspace
     counters, last update.
   - Agents: agent states and queued work.
   - Queues: queues, outgoing batches, joins, and jobs directly from
     `status_snapshot`.
   - Events: bounded recent runtime events.
   - Workspace: workspace state, changes, artifacts, reports, and related
     counters where present.

## Thin-Client Boundary

The renderer does not implement graph dispatch, fan-out/fan-in, queue
advancement, join aggregation, workspace/archive semantics, top-agent
governance, or worker lifecycle control. It only derives the initial start plan
from the saved blueprint draft and displays runtime-provided status snapshots
and explanations.

## Files

- `desktop_blueprint_service.py`
- `test_desktop_blueprint_service.py`
- `GuLiCode/packages/app/src/pages/session/blueprint-model.ts`
- `GuLiCode/packages/app/src/pages/session/blueprint-model.test.ts`
- `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.tsx`
- `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.test.ts`
- `GuLiCode/packages/app/src/context/platform.tsx`
- `GuLiCode/packages/app/src/i18n/en.ts`
- `GuLiCode/packages/app/src/i18n/zh.ts`
- `GuLiCode/packages/app/src/i18n/zht.ts`
- `GuLiCode/packages/desktop-electron/src/main/blueprint-runtime.ts`
- `GuLiCode/packages/desktop-electron/src/main/blueprint-runtime.test.ts`
- `GuLiCode/packages/desktop-electron/src/main/ipc.ts`
- `GuLiCode/packages/desktop-electron/src/main/ipc-blueprint-runtime.test.ts`
- `GuLiCode/packages/desktop-electron/src/preload/index.ts`
- `GuLiCode/packages/desktop-electron/src/preload/types.ts`
- `GuLiCode/packages/desktop-electron/src/renderer/index.tsx`

## Verification

```powershell
cd D:\agent\multi_agent_tcp
pytest -q test_desktop_blueprint_service.py test_graph_control.py
python -m py_compile desktop_blueprint_service.py __main__.py __init__.py

cd D:\agent\multi_agent_tcp\GuLiCode\packages\app
bun test --preload ./happydom.ts ./src/pages/session/blueprint-model.test.ts ./src/pages/session/blueprint-side-panel.test.ts
bun run build

cd D:\agent\multi_agent_tcp\GuLiCode\packages\desktop-electron
bun test ./src/main/blueprint-runtime.test.ts ./src/main/ipc-blueprint-runtime.test.ts ./src/main/blueprint-catalog.test.ts
bun run build
```

Observed result:

```text
Python: 17 passed; py_compile passed
App: 18 pass; build passed
Electron: 9 pass; build passed
```

`bun run build` completed with the existing Vite warnings only.

## Next Handoff

Do not add renderer-owned scheduling. The next step is a manual packaged/UI
smoke of this status projection, then the second execution-coupling phase:

- service-owned automatic tick loop;
- real `CLIWorkerBackend` startup;
- controlled `executionMode=live`;
- worker/job/message/workspace results displayed by the existing thin Runtime
  projection.
