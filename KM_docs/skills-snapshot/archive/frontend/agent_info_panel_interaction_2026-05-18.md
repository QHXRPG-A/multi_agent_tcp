# Agent Info Panel Interaction Archive - 2026-05-18

## Scope

This archive records the follow-up interaction pass for the GuLiCode blueprint
Agent information panel. It supersedes the earlier "hover for 2 seconds"
opening behavior recorded in `agent_info_panel_live_runtime_2026-05-18.md`.

## Current Behavior

- Agent information panels no longer open on mouse hover.
- Left mouse long-press on an Agent node opens the information panel.
  - Long-press duration: `800ms`.
  - Moving the pointer by `8px` or more cancels the long-press.
  - A circular progress ring appears on the Agent node while the long-press is
    charging.
  - `pointercancel`, canvas click, connection drag, and port interactions clear
    pending long-press state.
- The Agent node right-click context menu now includes `Info panel` /
  `信息面板` / `資訊面板`, which opens the same panel directly.
- The Agent information panel is now movable and resizable.
  - Drag the title area to move it.
  - Drag the bottom-right resize handle to resize it.
  - Default size is `374 x 410`.
  - Minimum size is `320 x 300`.
  - Position and size are clamped inside the blueprint canvas.
  - Panel state now carries `x`, `y`, `width`, and `height`.
- Existing panel behavior remains:
  - close
  - pin
  - multiple pinned panels
  - non-pinned outside-click close
  - stream transcript
  - `default` / `top` queue send modes
  - read-only static display when no live run exists

## Code-Level Debug Fixes In The Same Desktop Pass

- `blueprint-list-models` no longer throws raw Electron handler `spawn EPERM`
  for common Windows CLI resolution failures. The catalog path resolves CLI
  candidates more defensively and returns readable model-load failures.
- Solid DnD cleanup warnings for nonexistent droppable/draggable entries were
  removed from the sidebar/layout flow.
- Terminal stale PTY WebSocket errors are guarded so renderer teardown does not
  report noisy stale socket failures.
- The blueprint SVG edge rendering path no longer creates Solid computations
  inside render callbacks that can trigger runtime warnings.

## Main Files

- `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.tsx`
- `GuLiCode/packages/app/src/i18n/en.ts`
- `GuLiCode/packages/app/src/i18n/zh.ts`
- `GuLiCode/packages/app/src/i18n/zht.ts`
- `GuLiCode/packages/desktop-electron/src/main/blueprint-catalog.ts`
- `GuLiCode/packages/app/src/components/terminal.tsx`
- `GuLiCode/packages/app/src/pages/layout/sidebar-shell.tsx`

## Latest Verification

App checks:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\app
bun test --preload ./happydom.ts ./src/pages/session/blueprint-side-panel.test.ts
bun test --preload ./happydom.ts ./src/i18n/parity.test.ts
bun run typecheck
bun run build
```

Clean desktop debug startup:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\desktop-electron
set ELECTRON_ENABLE_LOGGING=1&& set ELECTRON_ENABLE_STACK_DUMPING=1&& set DEBUG=&& bun run dev
```

Observed clean debug instance:

```text
GuLiCode/packages/desktop-electron/debug-logs/dev-20260518-151513.log
-> renderer dev server: http://localhost:5173/
-> sidecar: http://127.0.0.1:6168
-> server ready
-> no new Uncaught / EPERM / Cannot remove / agentHoverTimer errors observed
```

Expected remaining debug noise:

- Electron insecure CSP warning in dev mode.
- Occasional `ghostty-vt` unsupported terminal control sequence warnings.

## Next Manual Smoke

- Open blueprint panel in the GuLiCode desktop debug app.
- Long-press an Agent node and verify the circular progress ring fills before
  the panel opens.
- Move the pointer during long-press and verify the progress cancels.
- Right-click an Agent node and open `信息面板`.
- Drag the panel title area and verify it moves without dragging canvas nodes.
- Drag the bottom-right handle and verify resizing clamps to the canvas.
- Verify close/pin/multiple pinned panels/outside-click close still work.
- With a live run, verify WebSocket transcript and `default/top` sends still
  work.
