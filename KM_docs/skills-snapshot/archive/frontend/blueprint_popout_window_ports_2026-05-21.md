# Blueprint Popout Window And Port Visibility - 2026-05-21

## Summary

This pass changed the GuLiCode blueprint "drag out" behavior from an in-app
floating overlay into a real independent Electron `BrowserWindow`.

The blueprint title bar still acts as the drag handle while embedded in the
right sidebar. Once the drag threshold is crossed, the main window opens a
separate blueprint desktop window, hides the embedded side panel, and keeps the
"dock back to sidebar" action in the popout window. Closing or docking the
popout sends state back to the main session window.

The pass also completed the node endpoint visibility rule: input/output ports
are hidden by default unless the node has a corresponding incoming/outgoing
edge, while hover, selection, and active connection dragging reveal usable
ports for editing.

## Implemented Shape

Electron main process:

1. `windows.ts` owns blueprint popout windows with a
   `blueprintWindowContexts` map keyed by `BrowserWindow.id`.
2. `openBlueprintWindow()` creates a normal independent `BrowserWindow` with
   the shared preload and renderer entry. It does not create an app-internal
   overlay and does not parent/modal-lock the main window.
3. Popout windows are de-duplicated by `projectDir + sessionId`; dragging the
   same blueprint out again focuses the existing popout.
4. Popout context is exposed to the renderer through `blueprint-window-context`.
5. Docking sends `blueprint-window-dock-request` to the main renderer, focuses
   the main window, and closes the popout without also emitting the normal
   closed event.
6. Closing the popout sends `blueprint-window-closed` so the main session can
   clear the floating state.
7. Blueprint popouts skip the main frameless titlebar overlay path so the
   child window uses the OS window frame normally.

IPC / preload / platform:

1. Preload exposes `openBlueprintWindow`, `dockBlueprintWindow`,
   `closeBlueprintWindow`, `getBlueprintWindowContext`, and event listeners for
   dock/closed/planning-submit messages.
2. The app `Platform` type includes desktop-only blueprint window APIs.
3. Runtime task submit from a popout is forwarded through
   `blueprint-window-submit-planning` to the main renderer and returns an
   `{ accepted }` response.

Renderer routing:

1. Desktop renderer initializes a memory history path from
   `getBlueprintWindowContext()`.
2. Popout renderers open `/:dir/blueprint-window/:id?`.
3. `AppInterface` accepts `visualShell={false}` so the popout can reuse
   providers without rendering the normal app shell/sidebar.
4. `blueprint-window.tsx` renders only `BlueprintSidePanel` in the popout.

Session behavior:

1. `session.tsx` no longer renders `data-blueprint-floating-panel`; the old
   fixed overlay path is removed.
2. Dragging the embedded blueprint header calls `platform.openBlueprintWindow`
   once the drag threshold is crossed, then marks the session blueprint panel
   as floating so the side panel no longer occupies width.
3. Main session listens for:
   - `gulicode:blueprint-window-dock`
   - `gulicode:blueprint-window-closed`
   - `gulicode:blueprint-planning-submit`
4. Dock reopens the embedded side panel. Closed clears the panel/floating
   state. Planning submit forwards the popout task into the main chat
   blueprint-planning handoff.

Node endpoint visibility:

1. `incomingNodeIds` and `outgoingNodeIds` are derived from visible edges.
2. `BlueprintNodeView` receives `hasIncomingEdge`, `hasOutgoingEdge`,
   `isConnectTargetVisible`, and `interactive`.
3. Input ports render only when the node supports input and has an incoming
   edge, is a current connection target, or is interactive.
4. Output ports render only when the node supports output and has an outgoing
   edge or is interactive.

## Verification

App source constraints and i18n parity:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\app
bun test --preload ./happydom.ts ./src/pages/session/blueprint-side-panel.test.ts ./src/i18n/parity.test.ts
```

Observed result: 13 tests passed.

Desktop Electron IPC/window source constraints:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\desktop-electron
bun test ./src/main/ipc-blueprint-runtime.test.ts
```

Observed result: 2 tests passed.

Typecheck:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\app
bun run typecheck

cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\desktop-electron
bun run typecheck
```

Observed result: both typechecks passed.

Whitespace check:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp
git diff --check
```

Observed result: no whitespace errors; Git only reported existing CRLF
conversion warnings.

Desktop dev startup:

```text
Renderer: http://localhost:5173/
Sidecar:  http://127.0.0.1:9484
Electron main PID: 50604
Log:      F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\logs\gulicode-desktop-direct.log
```

Observed result: main window created, server ready, no startup errors in the
desktop log.

## Files Touched

App:

- `GuLiCode/packages/app/src/app.tsx`
- `GuLiCode/packages/app/src/context/layout.tsx`
- `GuLiCode/packages/app/src/context/platform.tsx`
- `GuLiCode/packages/app/src/pages/session.tsx`
- `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.tsx`
- `GuLiCode/packages/app/src/pages/session/blueprint-window.tsx`
- `GuLiCode/packages/app/src/pages/session/session-side-panel.tsx`
- `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.test.ts`
- `GuLiCode/packages/app/src/i18n/en.ts`
- `GuLiCode/packages/app/src/i18n/zh.ts`
- `GuLiCode/packages/app/src/i18n/zht.ts`

Desktop Electron:

- `GuLiCode/packages/desktop-electron/src/main/index.ts`
- `GuLiCode/packages/desktop-electron/src/main/ipc.ts`
- `GuLiCode/packages/desktop-electron/src/main/windows.ts`
- `GuLiCode/packages/desktop-electron/src/preload/index.ts`
- `GuLiCode/packages/desktop-electron/src/preload/types.ts`
- `GuLiCode/packages/desktop-electron/src/renderer/index.tsx`
- `GuLiCode/packages/desktop-electron/src/main/ipc-blueprint-runtime.test.ts`

## Follow-Up Queue

1. Manual visual smoke in the desktop app:
   drag the embedded blueprint title bar out, verify a separate OS window
   opens, move it independently, dock it back, and close it.
2. Manual runtime smoke from the popout:
   submit a task from the independent blueprint window and verify it appears
   in the main session blueprint-planning composer flow.
3. Manual node-editing smoke:
   verify isolated nodes hide both ports by default, hover/selection reveals
   ports, and connection dragging still allows adding new edges.
4. Consider whether popout window size/position should persist independently
   from the old in-layout floating rectangle.
