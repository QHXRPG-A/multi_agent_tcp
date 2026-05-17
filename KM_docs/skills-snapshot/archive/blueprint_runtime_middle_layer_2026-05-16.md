# Blueprint Runtime Middle Layer Archive - 2026-05-16

This archive records the first live Blueprint Runtime middle layer for
GuLiCode desktop. It follows the Blueprint API bridge and closes the previous
`start/status/end/recentEvents` placeholder gap.

## Summary

Implemented a Python-service-owned live run registry for desktop blueprint
runs. The desktop bridge can now start a saved `BlueprintDocument`, validate
and queue a complete `TopAgentStartPlan`, poll runtime status/events, and end
the run through framework-owned `GraphRuntimeControlPlane` / `GraphRuntime`
semantics.

This pass intentionally does not start real CLI workers, run an automatic tick
loop, push events over WebSocket/SSE, or let the renderer implement scheduler
logic.

## Landed

1. Added in-memory run registry in `desktop_blueprint_service.py`.
   - `runId` format: `run-<12 hex>`.
   - Registry is guarded by `threading.RLock`.
   - Each run stores project dir, blueprint id, document, `GraphDefinition`,
     `GraphRuntime`, `GraphRuntimeControlPlane`, and timestamps.
2. Implemented `blueprint.start`.
   - Loads the saved project blueprint JSON from
     `.multi_agent_workspace/blueprints/<blueprintId>.json`.
   - Converts `document.graph` through `graph_definition_from_dict(...)`.
   - Calls `validate_runnable()`.
   - Requires a complete `TopAgentStartPlan`; no service-side plan generation
     or partial-plan filling.
   - Uses default `GuLiCodeTopAgentProfile()`.
   - Calls control-plane `run.start`, which queues start-node tasks and records
     runtime manifest/events.
3. Added `DesktopBlueprintNoopBackend`.
   - `ensure_worker()` records worker config only.
   - `run_single()` raises a clear v1 non-execution error.
   - This keeps v1 at registration/queue/status lifecycle depth without
     spawning broker or CLI workers.
4. Implemented `blueprint.status`.
   - Returns `GraphRuntime.status_snapshot(graph=graph)`.
5. Implemented `blueprint.recentEvents`.
   - Returns bounded event windows from status snapshot.
   - Default limit is 20; accepted range is clamped to `0..200`.
6. Implemented `blueprint.end`.
   - Supports desktop actions: `complete`, `cancel`, `fail`, `pause`.
   - Terminal runs remain queryable in the registry.
   - Repeated end calls on terminal runs do not call `GraphRuntime.end_run()`
     again and return `alreadyEnded: true`.
7. Extended service errors with optional `details`.
   - New/important codes: `RUN_NOT_FOUND`, `INVALID_BLUEPRINT_GRAPH`,
     `BAD_START_PLAN`, `START_PLAN_INVALID`, `UNSUPPORTED_RUN_ACTION`.
8. Extended Electron runtime tests.
   - Real Python service path now covers save -> start -> status ->
     recentEvents -> end.

## Response Envelopes

`blueprint.start` returns:

```json
{
  "ok": true,
  "runId": "run-...",
  "run": { "runId": "...", "projectDir": "...", "blueprintId": "...", "createdAt": 0, "updatedAt": 0 },
  "validation": {},
  "queuedMessages": [],
  "startManifest": {},
  "status": {}
}
```

`blueprint.status` returns `{ ok, runId, run, status }`.

`blueprint.recentEvents` returns `{ ok, runId, limit, events }`.

`blueprint.end` returns `{ ok, runId, run, end, status }` and may include
`alreadyEnded: true`.

## Files

- `desktop_blueprint_service.py`
- `test_desktop_blueprint_service.py`
- `GuLiCode/packages/desktop-electron/src/main/blueprint-runtime.test.ts`

The existing Electron facade and IPC/preload methods continue to route the
runtime lifecycle calls; this pass does not require renderer state UI changes.

## Verification

```powershell
cd D:\agent\multi_agent_tcp
pytest -q test_desktop_blueprint_service.py test_graph_control.py
python -m py_compile desktop_blueprint_service.py __main__.py __init__.py

cd D:\agent\multi_agent_tcp\GuLiCode\packages\desktop-electron
bun test ./src/main/blueprint-runtime.test.ts ./src/main/ipc-blueprint-runtime.test.ts
```

Observed result:

```text
17 passed
5 pass
```

## Next Handoff

The next highest priority is not another renderer scheduler. Build the UI
projection over returned runtime/control-plane state:

- start action UX that saves the project blueprint before calling
  `blueprint.start`;
- run/status panel for run, agents, queues, outgoing batches, joins, jobs,
  workspace, artifacts, reports, and recent events;
- top-agent/operator audit surfaces such as utterances without exposing them
  to ordinary Agent message context;
- later automatic tick/live CLI execution, using this registry/envelope as the
  service boundary.
