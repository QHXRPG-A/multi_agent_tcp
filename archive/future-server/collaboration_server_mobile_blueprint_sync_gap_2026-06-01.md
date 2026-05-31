# Collaboration Server Mobile Blueprint Sync Gap

Date: 2026-06-01

## Summary

This archive records the `/mobile` sync diagnosis after the full-graph mobile
mirror UI pass. The visible symptom was: mobile and desktop were both logged in,
but the mobile Blueprint tab did not receive the desktop blueprint.

The login state was valid. The missing piece was data publication: the
Collaboration Server had no desktop blueprint snapshot, no desktop session
snapshot, and no live runtime run to project into `/api/mobile/tick`.

## Observed Runtime State

- The in-app browser was initially on `http://127.0.0.1:3050/mobile`.
- No process was listening on port `3050`.
- The active frontend dev server was Vite on `127.0.0.1:3040`.
- Vite proxies `/api/*` to the Collaboration Server on `127.0.0.1:8787`.
- Collaboration Server was running with:
  - `python -m multi_agent_tcp collaboration-server --host 127.0.0.1 --port 8787`
  - database: `logs/collaboration_server.sqlite3`
  - seed: `examples/collaboration_server_debug_seed.json`

Database inspection showed:

```text
desktop_blueprint_snapshots 0
desktop_session_snapshots   0
runs                        0
desktop_bridges             1
sessions                    2
projects                    1
runtime_bindings            1
```

A fresh mobile login as `1` / `1` returned:

```json
{
  "clients": { "mobile": true, "desktop": true },
  "syncReady": true
}
```

But `GET /api/mobile/tick` returned:

```json
{
  "project": { "id": "proj-debug", "latestRun": null },
  "run": null,
  "status": null,
  "desktopSessions": {
    "desktop": { "online": true, "loggedIn": true, "stale": true },
    "sessions": [],
    "currentMessages": [],
    "composer": { "modes": [], "activeModeId": null }
  }
}
```

## Root Cause

There are two separate gaps.

1. The live runtime path was unavailable.

   The seed runtime binding still points to:

   ```text
   F:\src\Package\Script\Python\multi_agent_tcp
   ```

   On this machine, the active workspace is:

   ```text
   D:\agent\multi_agent_tcp
   ```

   The binding also has an empty runtime bridge URL/token, so
   `blueprint.listRuns` fails with `RUNTIME_UNAVAILABLE`.

2. Desktop snapshot publication did not happen after collaboration login.

   The desktop Blueprint panel currently posts snapshots from a Solid effect
   keyed on the serialized Blueprint snapshot payload. If the Blueprint was
   already open and unchanged before desktop collaboration login completed, the
   login event itself does not force a new `postDesktopBlueprintSnapshot(...)`.

   The desktop session snapshot path has the same shape: it posts on mount or
   session/composer changes, but desktop collaboration login alone does not
   necessarily republish the current session state.

## Important Code Paths

- `collaboration_server/app.py`
  - `/api/mobile/tick`
  - desktop snapshot fallback into mobile tick status
  - live runtime bridge lookup
- `collaboration_server/runtime_bridge.py`
  - `blueprint.listRuns`
  - `RUNTIME_UNAVAILABLE` failure path
- `examples/collaboration_server_debug_seed.json`
  - debug project `runtimeBinding.projectDir`
- `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.tsx`
  - `desktopBlueprintSnapshot`
  - `postDesktopBlueprintSnapshot(...)`
  - `createDesktopBlueprintSnapshot(...)`
- `GuLiCode/packages/app/src/pages/session.tsx`
  - `postDesktopSessionSnapshot(...)`
  - `scheduleDesktopSessionSnapshot()`
- `GuLiCode/packages/app/src/components/collaboration-auth.tsx`
  - desktop login/register panel
  - `registerDesktopBridge(...)`

## Follow-Up Fix

- Use `http://127.0.0.1:3040/mobile` for the active dev frontend, not the stale
  `3050` URL.
- Fix the debug seed/runtime binding so `projectDir` matches the current
  workspace path, or make debug startup rewrite the seed path to the current
  repo root.
- Add a desktop collaboration sync event after successful desktop auth/bridge
  registration.
- In `blueprint-side-panel.tsx`, listen for that event and immediately repost
  the current desktop Blueprint snapshot.
- In `session.tsx`, listen for the same event and immediately repost the current
  desktop session snapshot.
- Keep `/api/mobile/tick` narrow; it should consume latest snapshot/runtime
  state, not carry heavy diff/events payloads.

## Related Archives

- `archive/future-server/collaboration_server_mobile_tick_blueprint_snapshot_sync_2026-05-29.md`
- `archive/frontend/mock/gulicode_mobile_desktop_mirror_full_graph_2026-05-31.md`

