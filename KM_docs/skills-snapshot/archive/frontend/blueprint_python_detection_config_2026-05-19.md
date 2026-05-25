# Blueprint Python Detection Config - 2026-05-19

## Summary

The GuLiCode blueprint common config now treats the Python interpreter as a
user-visible local path, with both automatic detection and an explicit Detect
button in the panel. Desktop runtime startup no longer silently depends on a
plain `python` command being on PATH.

## Completed

1. Added `python_path` to blueprint common config and made it required before
   start, alongside `project_workdir`.
2. Added a `Python interpreter` field to the blueprint common config panel.
   It has:
   - a file picker button for manually selecting the Python executable,
   - a visible Detect button,
   - invalid red-border feedback,
   - detecting/failed status text.
3. The common config panel remains attached to the toolbar next to Add Node,
   opens/collapses by click, scrolls vertically, and is widened to `360px` so
   the Detect and picker controls have enough room.
4. The renderer tries to auto-fill Python on common config backfill and again
   just before blueprint start. If detection fails, startup validation keeps
   the field red and shows the config-required dialog.
5. Added desktop Electron IPC/preload/platform plumbing:
   - `blueprint-detect-python`
   - `blueprint-configure-runtime`
6. `BlueprintRuntime` now resolves Python in this order:
   - user configured `python_path`,
   - `GULICODE_PYTHON`,
   - `python`,
   - `python3`,
   - Windows `py -3`,
   - project/package `.venv`.
7. Detection verifies candidates by running:

   ```text
   -c "import sys; print(sys.executable)"
   ```

   The UI only stores a verified absolute `sys.executable` path.
8. Manual Detect can validate the current input box value, but can also ignore
   stale runtime configuration when the input is blank.
9. Backend service validation now also requires `python_path`, so renderer,
   IPC, and direct service paths share the same requirement.
10. Cleaned adjacent local-path assumptions:
    - `dev-desktop.ts` now prefers `ELECTRON_BUILDER_CACHE`,
      `ELECTRON_BUILDER_CACHE_DIR`, and `LOCALAPPDATA` for electron-builder
      cache lookup before falling back to `homedir()`.
    - example cluster paths were changed away from local `F:/src` examples.

## Files Touched

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
- `GuLiCode/scripts/dev-desktop.ts`
- `desktop_blueprint_service.py`
- `test_desktop_blueprint_service.py`
- `examples/cluster.json`
- `cluster.py`

## Verification

Passed:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\app
bun test --preload ./happydom.ts ./src/pages/session/blueprint-model.test.ts ./src/pages/session/blueprint-side-panel.test.ts ./src/i18n/parity.test.ts
bun run typecheck
bun run build

cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\desktop-electron
bun test ./src/main/blueprint-runtime.test.ts ./src/main/ipc-blueprint-runtime.test.ts
bun run typecheck
bun run build

cd F:\src\Package\Script\Python\multi_agent_tcp
pytest -q test_desktop_blueprint_service.py
python -m py_compile desktop_blueprint_service.py cluster.py
```

Notes:

- App and desktop builds still emit the existing Vite/electron-vite
  chunk/dynamic import/eval warnings; no functional failure was observed.
- Because new Electron main/preload IPC was added, an already running debug
  Electron window must be restarted before the Detect button can call the new
  runtime detection path.

## Next

1. Restart the desktop debug window and manually smoke the Python Detect
   button from the blueprint common config panel.
2. Start a live blueprint with the detected Python path and user-selected
   `project_workdir` / `skill_dir` / `rule_dir`.
3. Keep avoiding machine-local absolute defaults in renderer, runtime, and
   examples.
