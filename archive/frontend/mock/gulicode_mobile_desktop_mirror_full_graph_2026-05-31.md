# GuLiCode Mobile Desktop Mirror Full Graph Mock

Date: 2026-05-31

## Scope

This archive records the `/mobile` mock update that positions the mobile UI as a
read-only mirror of desktop session and Blueprint state. It keeps the light
mobile style and the three-tab structure while projecting desktop chat,
composer mode, full Blueprint structure, node telemetry, and planning requests.

## Implemented

- Extended desktop Blueprint snapshots and mobile projection with typed nodes:
  `agent`, `worker_agent`, `script`, `branch`, and `tick`.
- Preserved desktop graph edges in the mobile projection and carried optional
  `outputPort` / `inputPort` metadata.
- Updated desktop snapshot creation to emit visible Agent, Script, Branch, and
  Tick nodes instead of only agent nodes.
- Kept `/api/mobile/tick` narrow, using desktop snapshots for graph structure
  while live runtime status can still override node and agent telemetry.
- Updated mobile mock data with desktop session chips, active composer mode,
  segmented chat messages, typed graph nodes, edge ports, and Pending planning
  request cards.
- Updated the mobile node sheet so Agent / Worker Agent nodes keep runtime
  metrics and message controls, while Script / Branch / Tick nodes show summary,
  port, route, and tick configuration details without message controls.
- Kept write operations disabled in mock data because no CSRF token or write
  capability is present.
- Fixed the mobile structure-map fallback layout for the added Script / Branch /
  Tick mock nodes so they do not overlap at a narrow mobile viewport.

## Files

- `collaboration_server/schemas.py`
- `collaboration_server/projection.py`
- `collaboration_server/app.py`
- `GuLiCode/packages/app/src/components/collaboration-auth.tsx`
- `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.tsx`
- `GuLiCode/packages/app/src/mobile/mobile-state.ts`
- `GuLiCode/packages/app/src/mobile/mobile-api.ts`
- `GuLiCode/packages/app/src/mobile/mock-data.ts`
- `GuLiCode/packages/app/src/mobile/mobile-app.tsx`
- `GuLiCode/packages/app/e2e/mobile.spec.ts`
- `test_collaboration_server.py`
- `GuLiCode/packages/app/src/mobile/mobile-api.test.ts`
- `GuLiCode/packages/app/src/mobile/mobile-state.test.ts`
- `GuLiCode/packages/app/src/mobile/mobile-pwa.test.ts`

## Validation

These checks passed:

```powershell
pytest -q test_collaboration_server.py
cd GuLiCode/packages/app; bun test --preload ./happydom.ts ./src/mobile ./src/components/collaboration-auth.test.ts ./src/pages/session/blueprint-side-panel.test.ts
cd GuLiCode/packages/app; bun run typecheck
cd GuLiCode/packages/app; bun run build
cd GuLiCode/packages/app; bun run test:e2e -- e2e/mobile.spec.ts
```

The build still reports existing Vite warnings for JSX import-source handling,
mixed static/dynamic imports, and large chunks.

## Guardrails

- Keep `/mobile` read-only for Blueprint structure.
- Do not add mobile Blueprint editing, node dragging, script editing, or direct
  mobile run-start controls.
- Keep `/api/mobile/tick` as lightweight polling; do not move diff/event streams
  into tick.
- Treat desktop snapshots as the authoritative structure source and live runtime
  as telemetry overlay.
- Keep action controls visible only where useful and enabled only when the
  current mobile server state has the required capability.
