# Blueprint Prompt Editor and Popout Chrome Polish

Date: 2026-06-03

## Scope

Polished the Blueprint Prompt node editing UX and removed redundant chrome from
the plugin-served Blueprint popout window.

This is a frontend-only follow-up to the 2026-06-02 Prompt node / Agent port
work. Runtime prompt injection behavior was not changed.

## Prompt Node Editor

- Prompt nodes keep their compact on-canvas textarea and once/always trigger
  segmented control.
- Double-clicking a Prompt node now opens a separate editor dialog instead of
  expanding the canvas node itself.
- The dialog has a draggable title bar:
  `data-blueprint-prompt-dialog-header`.
- The dialog has an explicit bottom-right resize handle:
  `data-blueprint-prompt-dialog-resize`.
- The dialog uses controlled screen-pixel geometry stored in
  `PromptEditorState`, with drag modes:
  `prompt-editor-move` and `prompt-editor-resize`.
- The editor dialog is rendered as a canvas overlay, outside the viewport
  transform layer, so moving/resizing is not distorted by canvas pan/zoom.
- Native CSS `resize: both` is intentionally not used. Resize behavior is
  handled by the custom pointer drag path so it works reliably inside the
  transformed Blueprint surface.
- `ResizeObserver` keeps the signal state synchronized if the element size is
  changed by layout constraints.
- `Escape` closes the editor dialog.

## Popout Window Chrome

- In `/blueprint-window/:id?` and `/:dir/blueprint-window/:id?`, the floating
  Blueprint side panel no longer renders the old top title bar containing the
  `session.header.blueprint` label, dock button, and close button.
- The main Blueprint toolbar remains visible. It starts with the project
  blueprint selector (`Default Blueprint`), script editor selector, global
  config button, diff toggle, runtime controls, fit/reset buttons, and reset
  draft command.
- The embedded/non-floating side panel still renders the header and keeps the
  drag-to-popout behavior.
- `BlueprintWindowPage` no longer passes an `onDock` callback, because the
  floating title bar that exposed the dock button is hidden.

## Main Files

- `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.tsx`
- `GuLiCode/packages/app/src/pages/session/blueprint-window.tsx`
- `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.test.ts`

## Verification

Commands run from `GuLiCode/packages/app`:

```powershell
bun test --preload ./happydom.ts ./src/pages/session/blueprint-side-panel.test.ts ./src/pages/session/blueprint-model.test.ts ./src/i18n/parity.test.ts
bun run typecheck
```

Plugin cache refresh:

```powershell
python plugins\gulicode-bp\scripts\install_personal_plugin.py --force
```

Browser smoke:

- Opened the plugin-served workbench at
  `http://127.0.0.1:3461/.../blueprint-window/default`.
- Verified the Prompt editor opens at the default `440x300` size.
- Verified header cursor is `move`, the custom resize handle cursor is
  `nwse-resize`, and native resize is `none`.
- Verified title-bar dragging changes position without changing size.
- Verified bottom-right handle dragging increases width and height.
- Verified `Escape` closes the dialog.
- Verified floating popout `data-blueprint-float-handle` and
  `data-blueprint-dock-button` counts are both `0`.
- Verified the document toolbar still renders, including
  `data-blueprint-document-select`.

## Notes

- Existing Vite chunk/import warnings and pip invalid-distribution warnings from
  the plugin runtime venv were observed during cache refresh and were not part
  of this UI change.
- The hidden popout title bar means docking is no longer exposed from the
  plugin-served Blueprint workbench UI. Browser/window close remains controlled
  by the host browser or desktop shell.
