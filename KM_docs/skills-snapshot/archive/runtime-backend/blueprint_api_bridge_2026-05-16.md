# Blueprint API Bridge Archive - 2026-05-16

This archive records the Blueprint 1-3 implementation so later agents can
start from the current GuLiCode desktop/runtime boundary without replaying the
UI history.

## Summary

Implemented the first project-level blueprint API bridge for GuLiCode desktop.
The blueprint panel now has a closed load/save/validate path through Electron
main and a long-lived Python service. Full run-state UI was intentionally left
for the later middle-layer pass.

## Landed

1. Added `BlueprintDocument v1`:
   - `schema_version`
   - `id`
   - `name`
   - runtime-shaped `graph`
   - private workbench `ui`
2. Added project JSON persistence:
   - path: `<project>/.multi_agent_workspace/blueprints/<blueprintId>.json`
   - default id: `default`
   - default name: `Default Blueprint`
3. Added Python desktop blueprint service:
   - `desktop_blueprint_service.py`
   - HTTP JSON API using standard-library `ThreadingHTTPServer`
   - implemented commands at the time: `blueprint.list`, `blueprint.open`,
     `blueprint.save`, `blueprint.validate`
   - validation uses `graph_definition_from_dict(...).validate_runnable()`
   - runtime lifecycle commands were initially reserved for the middle layer
4. Added CLI entry:
   - `python -m multi_agent_tcp desktop-blueprint-service --port 0 --token ...`
   - service prints a JSON ready payload with URL and token for Electron main.
5. Added Electron main bridge:
   - `GuLiCode/packages/desktop-electron/src/main/blueprint-runtime.ts`
   - main process starts and owns the Python service subprocess
   - renderer never sees Python command, service URL, or token
   - `projectDir` is validated as an absolute existing directory
6. Added IPC/preload/platform methods:
   - `blueprint-list`
   - `blueprint-open`
   - `blueprint-save`
   - `blueprint-validate`
   - `blueprint-start`
   - `blueprint-status`
   - `blueprint-end`
   - `blueprint-recent-events`
7. Wired the blueprint panel:
   - first open calls project `default`
   - if missing, imports existing `blueprint-draft.v1` or default draft and
     saves it as project JSON
   - later saves go through project JSON API
   - service failure falls back to local draft and shows a readable error

## Files

- `desktop_blueprint_service.py`
- `test_desktop_blueprint_service.py`
- `__main__.py`
- `__init__.py`
- `GuLiCode/packages/desktop-electron/src/main/blueprint-runtime.ts`
- `GuLiCode/packages/desktop-electron/src/main/blueprint-runtime.test.ts`
- `GuLiCode/packages/desktop-electron/src/main/ipc-blueprint-runtime.test.ts`
- `GuLiCode/packages/desktop-electron/src/main/ipc.ts`
- `GuLiCode/packages/desktop-electron/src/main/index.ts`
- `GuLiCode/packages/desktop-electron/src/preload/index.ts`
- `GuLiCode/packages/desktop-electron/src/preload/types.ts`
- `GuLiCode/packages/desktop-electron/src/renderer/index.tsx`
- `GuLiCode/packages/app/src/context/platform.tsx`
- `GuLiCode/packages/app/src/pages/session/blueprint-model.ts`
- `GuLiCode/packages/app/src/pages/session/blueprint-model.test.ts`
- `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.tsx`
- `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.test.ts`

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

## Follow-up

The follow-up middle-layer pass replaced the lifecycle placeholders with a
service-owned live run registry backed by `GraphRuntimeControlPlane` /
`GraphRuntime`. See
`archive/blueprint_runtime_middle_layer_2026-05-16.md`.
