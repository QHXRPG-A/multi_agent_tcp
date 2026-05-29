# Collaboration Server Mobile Tick + Blueprint Snapshot Sync

Date: 2026-05-29

## Summary

Closed the registration/login loop for GuLiCode mobile collaboration and
narrowed the mobile polling contract to auth/presence plus blueprint runtime
state. The mobile `/mobile` surface now treats the backend as authoritative for
blueprint structure: nodes, edges, runtime state, and agent status come from the
Collaboration Server tick payload instead of mock data or mobile-side inferred
layout.

The final fix in this pass addressed a misleading mobile map bug: when the
desktop blueprint had three unconnected vertical nodes, mobile displayed them
as a horizontal chain. The cause was fallback edge generation in the mobile API
projection and in the map renderer. Both fallbacks were removed, and desktop
snapshot nodes now carry `x/y` layout coordinates through the server to mobile.

## Implemented Surface

- Auth/session:
  - `/api/auth/login` accepts `clientKind: "mobile" | "desktop"`.
  - Sessions record `client_kind`.
  - `/api/me` reports current user, CSRF, online clients, and `syncReady`.
  - Registration remains user creation; clients auto-login after register.
  - Debug seed credentials were changed to `1` / `1`.

- Development wiring:
  - Vite proxies same-origin `/api` calls to the local Collaboration Server on
    port `8787`.
  - Collaboration Server debug startup uses the seed config.

- Mobile tick:
  - `GET /api/mobile/tick` is the only 1-second polling endpoint.
  - Tick returns auth/presence plus lightweight blueprint state:
    `run`, `blueprint.nodes`, `blueprint.edges`, `agents`, and `pending`.
  - Tick excludes planning requests, diff, events, reports, and artifacts.
  - Tick stops on `401` and returns mobile to the auth gate.
  - `syncReady=false` updates only the waiting-for-desktop state.

- Desktop snapshot sync:
  - Added `POST /api/desktop/blueprint-snapshot`.
  - Desktop blueprint panel posts current agent nodes, edges, agent status
    fields, and node `x/y` layout coordinates.
  - When runtime status is unavailable, `/api/mobile/tick` can still return the
    latest desktop blueprint snapshot.

- Mobile blueprint projection:
  - Mobile no longer creates synthetic sequential edges when the backend returns
    no edges.
  - Mobile map renderer also refuses to draw fallback edges.
  - Desktop `x/y` coordinates are normalized into the mobile canvas so vertical
    or sparse layouts preserve their structure.
  - Agent status projection is limited to the lightweight fields required by
    the tick contract.

- UI shell:
  - Mobile and blueprint collaboration auth share a login/register panel.
  - Mobile settings menu includes logout.
  - Desktop blueprint login is scoped to the blueprint collaboration area and
    does not block unrelated desktop usage.

## Important Files

- `collaboration_server/app.py`
- `collaboration_server/schemas.py`
- `collaboration_server/store.py`
- `test_collaboration_server.py`
- `examples/collaboration_server_debug_seed.json`
- `GuLiCode/packages/app/vite.config.ts`
- `GuLiCode/packages/app/src/components/collaboration-auth.tsx`
- `GuLiCode/packages/app/src/mobile/mobile-api.ts`
- `GuLiCode/packages/app/src/mobile/mobile-app.tsx`
- `GuLiCode/packages/app/src/mobile/mobile-state.ts`
- `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.tsx`

## Validation

Automated checks passed:

```powershell
pytest -q test_collaboration_server.py
cd GuLiCode/packages/app
bun test --preload ./happydom.ts ./src/components/collaboration-auth.test.ts ./src/mobile/mobile-api.test.ts ./src/pages/session/blueprint-side-panel.test.ts
bun run typecheck
cd ../desktop-electron
bun run typecheck
```

Observed results:

- Backend: `13 passed`.
- Frontend targeted tests: `34 passed`.
- App and desktop-electron typecheck passed.
- Local Collaboration Server restarted on `127.0.0.1:8787`.
- Browser smoke against `http://127.0.0.1:3040/mobile` verified:
  - mobile receives desktop snapshot nodes
  - unconnected desktop nodes render with `edgeCount=0`
  - node order/layout follows desktop coordinates instead of a synthetic chain

## Guardrails

- Keep `/api/mobile/tick` narrow. Do not add planning requests, diff, events,
  reports, or artifacts to the 1-second polling response.
- Treat desktop runtime status and desktop blueprint snapshot as authoritative
  for mobile blueprint structure.
- Do not infer edges on mobile. If the backend returns no edges, mobile should
  display no edges.
- Keep mobile blueprint editing disabled; mobile displays the current desktop
  projection and sends only explicitly allowed collaboration actions.

## Follow-Up

- Add a direct component-level test for `BlueprintStructureMap` once the mobile
  view has a stable Solid test harness for map geometry.
- Add retention/pruning policy for `desktop_blueprint_snapshots` if snapshots
  become frequent across many projects.
- Replace remaining mojibake strings in mobile/blueprint UI source with clean
  localized strings in a separate pass.
