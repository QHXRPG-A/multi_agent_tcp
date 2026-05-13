# Guli desktop UI productization and blueprint embedding

This document records the current effective knowledge for the Guli desktop UI line inside `multi_agent_tcp/GuLiCode`.

## Position

The current UI main line is:

```text
Guli productization
  -> blueprint embedded in GuLiCode desktop
  -> runtime/control-plane state rendered inside GuLiCode
```

This means:

- The user-facing product surface is `GuLiCode`, not a separate Ryven-led visual-editor app.
- Blueprint capability should appear as a GuLiCode route, panel, or workbench entry.
- Runtime semantics remain framework-owned by `GraphRuntimeControlPlane` and `GraphRuntime`; the renderer only consumes their state.

## Current landed baseline

As of 2026-05-13, the following desktop/UI baseline is already in place:

1. Desktop bring-up:
   - one-click entry: `F:\src\Package\Script\Python\multi_agent_tcp\start-gulicode-desktop.cmd`
   - packaged smoke: `F:\src\Package\Script\Python\multi_agent_tcp\start-gulicode-desktop.cmd --packaged`
   - packaged output path: `GuLiCode/packages/desktop-electron/dist/packaged-launch/current/win-unpacked/GuLiCode Dev.exe`

2. Productization surfaces:
   - the new-session empty state now shows `GULI`
   - the desktop header now exposes a blueprint entry button
   - user-visible blueprint copy is wired in `en` / `zh` / `zht`

3. Desktop shell hardening:
   - packaged main-window creation no longer dies when icon resources are missing or unreadable
   - saved off-screen window state is clamped back to a visible display
   - packaged `exe` icon is post-patched with `rcedit`
   - packaged output path is stable, which helps Windows taskbar identity and repinning

## File ownership map

Use these ownership boundaries when implementing Guli desktop UI work:

```text
GuLiCode/packages/app
  -> desktop routes, panels, layout, session views, blueprint workbench UI

GuLiCode/packages/ui
  -> shared icons, buttons, design tokens, reusable view primitives

GuLiCode/packages/desktop-electron
  -> Electron main/preload/window shell, packaged resources, app identity,
     taskbar behavior, icons, startup hardening

GuLiCode/scripts/dev-desktop.ts
  -> one-click bring-up, packaged launch flow, smoke-oriented launch behavior
```

Current concrete anchor files:

- `GuLiCode/packages/app/src/components/session/session-header.tsx`
- `GuLiCode/packages/app/src/components/session/session-new-view.tsx`
- `GuLiCode/packages/app/src/i18n/en.ts`
- `GuLiCode/packages/app/src/i18n/zh.ts`
- `GuLiCode/packages/app/src/i18n/zht.ts`
- `GuLiCode/packages/ui/src/components/icon.tsx`
- `GuLiCode/packages/desktop-electron/src/main/windows.ts`
- `GuLiCode/packages/desktop-electron/electron-builder.config.ts`
- `GuLiCode/scripts/dev-desktop.ts`

## Blueprint embedding rules

Use these rules when adding blueprint UI to GuLiCode:

- Place blueprint entrypoints in GuLiCode-owned surfaces such as the session header, sidebar, tabs, or dedicated workbench routes.
- Keep execution semantics in `GraphRuntimeControlPlane` and `GraphRuntime`.
- Let the renderer consume runtime-owned status, events, queues, joins, workspace changes, artifacts, and reports.
- Do not rebuild graph scheduling rules inside `packages/app`.
- Do not place real product logic in `packages/desktop-electron/src/renderer/index.tsx`; that file is only the desktop shell bootstrap.

## Productization rules

- Prefer `GULI` / `GuLiCode` branding in user-visible desktop surfaces.
- Keep app/window/taskbar identity aligned across:
  - Electron app name
  - `AppUserModelId`
  - packaged icon resources
  - empty-state wordmarks
  - visible action labels
- When changing icons, update the desktop-electron channel icon sets (`dev` / `beta` / `prod`) and re-run the packaged startup flow so the final `exe` is repatched.

## Windows taskbar and packaged-icon notes

- The runtime window icon is loaded from `resources/icons`.
- The packaged shell also copies `resources/icons` into `process.resourcesPath/icons`.
- The final `exe` icon is patched after packaging through `rcedit`, because builder output alone may still keep the stale Electron-style icon in the executable resource table.
- If Windows still shows an old pinned icon after the `exe` resource is corrected, repin from the fixed path:

```text
GuLiCode/packages/desktop-electron/dist/packaged-launch/current/win-unpacked/GuLiCode Dev.exe
```

That symptom is usually stale taskbar pin caching, not proof that the latest `exe` is wrong.

## Current known boundaries

- The blueprint header button is only a placeholder entry today; open logic is not wired yet.
- Tauri still exists, but Electron is the default desktop verification path on this machine.
- Blueprint UI should not regress back into a separate legacy Ryven/editor workstream unless the user explicitly reopens that direction.
