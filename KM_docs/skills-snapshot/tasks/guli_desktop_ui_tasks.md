# Guli desktop UI tasks

## Current positioning

The current UI workstream is:

```text
Guli productization
  -> blueprint embedded in GuLiCode desktop
  -> runtime-backed desktop workbench
```

Do not treat the old Ryven/editor line as the current UI target.

## Already landed

- [DONE] Added a blueprint entry button to the session header.
- [DONE] Added i18n copy for the blueprint placeholder entry.
- [DONE] Replaced the new-session center mark with `GULI`.
- [DONE] Replaced desktop icon assets for `dev` / `beta` / `prod`.
- [DONE] Brought up one-click packaged startup through `start-gulicode-desktop.cmd --packaged`.
- [DONE] Fixed packaged main-window bring-up failures caused by off-screen saved state and icon-load crashes.
- [DONE] Stabilized packaged output to `dist/packaged-launch/current`.
- [DONE] Patched the final packaged `exe` icon through `rcedit`.

## In progress

### 1. Blueprint entry embedding

- [DONE] Put the blueprint entry in the desktop chrome.
- [TODO] Wire the click action to a real route, panel, or workbench entry.
- [TODO] Decide whether blueprint first lands as:
  - a dedicated route,
  - a right-side panel,
  - or a full workbench surface.

### 2. Guli productization

- [DONE] Replaced the empty-state mark with `GULI`.
- [DONE] Replaced desktop icon resources.
- [TODO] Audit remaining user-visible `OpenCode` wording across desktop-facing surfaces.
- [TODO] Decide the visible brand split between `GULI` and `GuLiCode` for headers, titles, onboarding, and packaging.

### 3. Runtime-backed UI

- [TODO] Show run status, agent status, outgoing-batch status, join status, workspace changes, artifacts, and reports in GuLiCode.
- [TODO] Keep these views as projections of runtime/control-plane state rather than renderer-owned execution logic.
- [TODO] Add top-agent/operator audit views such as utterance history without exposing them as ordinary-Agent message context.

### 4. Desktop shell hardening

- [DONE] Off-screen saved window state is clamped back into a visible display.
- [DONE] Packaged icon failures no longer abort main-window creation.
- [TODO] Add a simple repeatable smoke helper for packaged bring-up and icon verification.
- [TODO] Keep provider/model setup guidance out of repo files and inside runtime/user configuration only.

## File ownership reminders

- `GuLiCode/packages/app`: blueprint entrypoints, routes, workbench layout, desktop content surfaces
- `GuLiCode/packages/ui`: shared iconography and reusable UI building blocks
- `GuLiCode/packages/desktop-electron`: Electron shell, packaged identity, icon/taskbar behavior, startup hardening
- `GuLiCode/scripts/dev-desktop.ts`: one-click startup and packaged-smoke behavior

## Acceptance direction

This task line is in a good first state when:

1. A user can launch GuLiCode from one command.
2. The desktop shell visibly looks like Guli rather than Electron/OpenCode leftovers.
3. The blueprint entry opens a GuLiCode-owned surface.
4. That surface reads runtime/control-plane state rather than reimplementing scheduler rules.
5. Taskbar/window identity remains stable across repeated packaged launches.
