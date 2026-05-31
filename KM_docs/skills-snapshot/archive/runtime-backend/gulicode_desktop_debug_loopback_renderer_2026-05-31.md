# GuLiCode Desktop Debug Loopback Renderer - 2026-05-31

## Summary

This pass diagnosed a local Windows debug startup where the GuLiCode Electron
process existed and the desktop bridge was listening, but the user could not
see a successfully loaded desktop app.

The root cause was a stale `127.0.0.1:5173` listener that remained in Windows
TCP state even though its owning process no longer existed. The current
Electron dev renderer was available on IPv6 loopback `[::1]:5173`, while
requests to `127.0.0.1:5173` timed out. Electron's window loader previously
rewrote `localhost` to `127.0.0.1`, which made the desktop window load the bad
loopback endpoint.

## Implemented

Runtime behavior:

1. `normalizedDevRendererUrl(...)` no longer rewrites `localhost` to
   `127.0.0.1`.
2. Electron dev mode can load the exact renderer URL provided by
   `ELECTRON_RENDERER_URL`.
3. This avoids forcing a bad IPv4 loopback endpoint when electron-vite is
   serving the renderer through `localhost` / IPv6 loopback.

Debug launcher:

1. `start-gulicode-debug.ps1` now probes desktop renderer health through
   `http://[::1]:5173/`.
2. The script output now prints the IPv6 loopback desktop URL for the renderer
   health check.
3. Collaboration Server, mobile, and console checks continue to use
   `127.0.0.1` on ports `8787` and `3040`.

Manual recovery:

1. Existing GuLiCode Electron and electron-vite processes were stopped.
2. The debug launcher was run again.
3. A Win32 window check confirmed the GuLiCode window was visible and not
   minimized.
4. The window was restored and moved to the primary display at `(80, 80)`.
5. A screenshot confirmed the desktop UI, Blueprint canvas, and session panel
   were rendered.

## Files Changed

Desktop runtime:

1. `GuLiCode/packages/desktop-electron/src/main/windows.ts`

Debug launcher:

1. `start-gulicode-debug.ps1`

## Verification

Desktop Electron typecheck:

```powershell
cd D:\agent\multi_agent_tcp\GuLiCode\packages\desktop-electron
bun run typecheck
```

Observed result:

```text
desktop-electron typecheck passed
```

Debug stack checks:

```text
http://127.0.0.1:8787/api/health -> 200
http://127.0.0.1:3040/mobile -> 200
http://127.0.0.1:3040/console -> 200
http://[::1]:5173/ -> 200
```

Desktop bridge:

```text
GuLiCode Electron main process: pid=12764, title=GuLiCode
Desktop bridge ready: true
Bridge listeners: 127.0.0.1:65136 and 127.0.0.1:65137
```

Captured screenshot:

```text
D:\agent\multi_agent_tcp\logs\gulicode-window-screenshot.png
```

## Known Limits

1. The stale `127.0.0.1:5173` TCP listener was visible in `Get-NetTCPConnection`
   with an owning PID that no longer existed, so it could not be killed with
   `Stop-Process` or `taskkill`.
2. The launcher workaround uses `[::1]:5173` for renderer health. If another
   machine has no IPv6 loopback support, the script may need a fallback probe
   that tries both `[::1]` and `localhost`.
3. `codemaker` is not installed on this machine, so desktop logs can show
   `spawn codemaker ENOENT` when model listing probes run. That error did not
   block the desktop window or bridge.

## Follow-Up Queue

1. Make `Wait-Http` support multiple candidate URLs and treat either
   `http://[::1]:5173/` or `http://localhost:5173/` as valid.
2. Improve stale renderer detection so a bad `127.0.0.1:5173` listener cannot
   make the launcher report a false desktop failure.
3. Consider logging the exact `ELECTRON_RENDERER_URL` that `loadWindow(...)`
   uses in development builds.

## Skill/Archive Files

Installed skill:

```text
C:\Users\13429\.codex\skills\multi-agent-tcp\archive\runtime-backend\gulicode_desktop_debug_loopback_renderer_2026-05-31.md
```

Repository snapshot:

```text
KM_docs/skills-snapshot/archive/runtime-backend/gulicode_desktop_debug_loopback_renderer_2026-05-31.md
```
