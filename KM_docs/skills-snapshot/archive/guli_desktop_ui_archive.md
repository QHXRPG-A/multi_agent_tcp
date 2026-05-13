# Guli desktop UI archive

This archive records the 2026-05-13 desktop/UI productization round for `multi_agent_tcp/GuLiCode`.

## 2026-05-13 - Guli desktop productization baseline and blueprint entry embedding

### Summary

1. Re-centered the active UI line around **Guli productization + blueprint embedded in the GuLiCode desktop app**.
2. Added the first blueprint entry surface in the session header as a placeholder button with i18n copy.
3. Replaced the new-session center mark with `GULI`.
4. Reworked the packaged desktop startup path so `start-gulicode-desktop.cmd --packaged` can build and launch a stable unpacked desktop app.
5. Fixed packaged bring-up blockers:
   - missing `git` in the Bun shell path during prebuild
   - renderer asset race conditions
   - off-screen saved window state
   - icon-load failure aborting main-window creation
6. Replaced desktop icon resources and added a post-package `rcedit` patch so the final `GuLiCode Dev.exe` carries the GuLiCode icon.
7. Stabilized packaged output to a fixed path:

```text
GuLiCode/packages/desktop-electron/dist/packaged-launch/current/win-unpacked/GuLiCode Dev.exe
```

### Affected repository files

- `GuLiCode/packages/app/src/components/session/session-header.tsx`
- `GuLiCode/packages/app/src/components/session/session-new-view.tsx`
- `GuLiCode/packages/app/src/i18n/en.ts`
- `GuLiCode/packages/app/src/i18n/zh.ts`
- `GuLiCode/packages/app/src/i18n/zht.ts`
- `GuLiCode/packages/ui/src/components/icon.tsx`
- `GuLiCode/packages/desktop-electron/icons/dev/*`
- `GuLiCode/packages/desktop-electron/icons/beta/*`
- `GuLiCode/packages/desktop-electron/icons/prod/*`
- `GuLiCode/packages/desktop-electron/src/main/index.ts`
- `GuLiCode/packages/desktop-electron/src/main/windows.ts`
- `GuLiCode/packages/desktop-electron/electron-builder.config.ts`
- `GuLiCode/packages/script/src/index.ts`
- `GuLiCode/scripts/dev-desktop.ts`

### Desktop bring-up result

The validated one-click packaged command for this round is:

```powershell
F:\src\Package\Script\Python\multi_agent_tcp\start-gulicode-desktop.cmd --packaged
```

Observed effective result:

- packaged output is produced under `dist/packaged-launch/current`
- Electron main log reaches `main window created`
- the visible desktop window title is `GuLiCode`
- the packaged `exe` resource icon is the GuLiCode icon rather than the stale Electron-style icon

### Product/UI result

The first desktop productization surfaces now look like this:

- blueprint is visible as a top-level desktop action
- the new-session center surface reads `GULI`
- desktop icon assets are aligned across dev/beta/prod channels

This is still a baseline, not the finished blueprint workbench.

### What remains intentionally unfinished

- The blueprint button open logic is not wired yet.
- The dedicated blueprint route/panel/workbench layout is not built yet.
- Runtime-backed status surfaces for runs, agents, joins, workspace changes, artifacts, and reports are still ahead.
- Some Windows taskbar pins may still need repinning if they were created from older timestamped build paths before the output path was stabilized.

### Documentation cleanup result

This same round also retired the old Ryven/editor UI line from the active skill snapshot and replaced it with:

- `knowledge_base/guli_desktop_ui.md`
- `tasks/guli_desktop_ui_tasks.md`
- `archive/guli_desktop_ui_archive.md`
