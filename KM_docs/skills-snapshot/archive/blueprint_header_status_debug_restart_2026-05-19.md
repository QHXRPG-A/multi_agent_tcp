# Blueprint Header Status Debug Restart - 2026-05-19

## Summary

The GuLiCode blueprint header status text now has an expandable detail popover.
This was added after the header showed a truncated Electron IPC error:

```text
Error invoking remote method 'blueprint-configure-runtime':
Error: No handler registered for 'blueprint-configure-runtime'
```

The expandable detail confirmed the root cause: the renderer/preload code was
calling the new IPC method, but the running Electron main process was still an
old process without the handler registered. Restarting the GuLiCode desktop dev
window loaded the updated main/preload bundle and cleared that specific error.

## Completed

1. Replaced the blueprint header persistence text with a compact clickable
   status trigger.
2. Loading and saving states still show as a small one-line status in the
   header.
3. Error state now expands into a popover that shows the full error message
   with wrapping and vertical scrolling.
4. Added localized header-status labels for English, Simplified Chinese, and
   Traditional Chinese.
5. Added source-level assertions that the header status trigger/details exist.
6. Restarted the desktop Electron dev app after the IPC change.

## Files Touched

- `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.tsx`
- `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.test.ts`
- `GuLiCode/packages/app/src/i18n/en.ts`
- `GuLiCode/packages/app/src/i18n/zh.ts`
- `GuLiCode/packages/app/src/i18n/zht.ts`

## Verification

Passed:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\app
bun test --preload ./happydom.ts ./src/pages/session/blueprint-side-panel.test.ts
bun test --preload ./happydom.ts ./src/i18n/parity.test.ts
bun run typecheck
bun run build
```

The app build still emits the existing Vite chunk/dynamic import warnings.

## Desktop Restart

The clean restart used the desktop debug path:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\desktop-electron
$env:ELECTRON_ENABLE_LOGGING = '1'
$env:ELECTRON_ENABLE_STACK_DUMPING = '1'
Remove-Item Env:\DEBUG -ErrorAction SilentlyContinue
bun run dev
```

Observed restart result:

```text
Electron main PID: 20116
Renderer: http://localhost:5173/
Sidecar: http://127.0.0.1:5337
Log: GuLiCode/logs/gulicode-desktop-restart-20260519-122112.log
Error log: GuLiCode/logs/gulicode-desktop-restart-20260519-122112.err.log
```

## Notes

- If this error appears again after IPC/preload work, restart the whole
  Electron main process. Reloading the renderer is not enough.
- The specific `No handler registered` message means main/preload version
  mismatch, not a Python interpreter validation failure.
- `blueprint-configure-runtime` is registered in
  `GuLiCode/packages/desktop-electron/src/main/ipc.ts`.

## Next

1. Manual smoke the reopened blueprint panel and confirm the header error no
   longer appears.
2. Use the expandable header status for future long persistence or IPC errors
   instead of relying on truncated header text.
3. Keep the existing clean debug startup path as the default when main/preload
   IPC changes.
