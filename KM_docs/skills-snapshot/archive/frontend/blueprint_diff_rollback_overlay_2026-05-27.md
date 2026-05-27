# Blueprint Diff Rollback Overlay - 2026-05-27

## Summary

This pass added Blueprint rollback controls to the GuLiCode Blueprint Diff
overlay and synchronized rollback state with the native global diff/FileTree
refresh path.

The overlay remains the primary run-scoped changeset UI. The native global diff
only receives the effective accepted textual diffs after rollback projection.

## Implemented

Blueprint Diff overlay:

1. Shows a rollback button for rollbackable accepted tail changesets.
2. Shows a restore button when the latest rollback is restorable.
3. Disables rollback for non-tail, non-accepted, legacy, active, or otherwise
   non-reversible changesets and surfaces the backend disabled reason.
4. Refreshes `blueprint.runDiff` after rollback/restore.
5. Emits `workspace.diff.changed` after effective accepted changesets change so
   the global Review panel and file tree sync with disk state.

Detail viewing:

1. The `查看` button toggles details open and closed. Clicking the same
   changeset again collapses the detail panel.
2. Accepted changesets render normal red/green diff highlighting.
3. Rolled-back changesets still lazy-load and display their textual patch
   content, but with neutral line styling. Added and removed lines are visible
   as text without red/green backgrounds.
4. If no textual diff exists, the existing empty state is shown.
5. Binary file count remains visible when the changeset has binary files.
6. Restore clears the current expanded detail selection to avoid stale expanded
   UI after state projection changes.

## UI Behavior

Expected behavior after a rollback:

1. The changeset row status changes to `已回退` / `Rolled back`.
2. The row remains visible in Blueprint Diff history.
3. The row no longer contributes to `acceptedDiffs`.
4. Opening `查看` shows its text content in neutral styling.
5. The right global diff does not show the rolled-back changeset as active.
6. Clicking `查看` again collapses the detail panel.

No-file and no-text cases:

1. A changeset with no text diff shows the no-text empty state.
2. A binary-only changeset shows the no-text empty state plus binary metadata.
3. A legacy changeset without reversible content remains viewable if it has a
   patch but cannot be rolled back.

## Files Changed

Frontend/app:

1. `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.tsx`
2. `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.test.ts`
3. `GuLiCode/packages/app/src/context/platform.tsx`
4. `GuLiCode/packages/app/src/i18n/en.ts`
5. `GuLiCode/packages/app/src/i18n/zh.ts`
6. `GuLiCode/packages/app/src/i18n/zht.ts`

Desktop bridge touched by the UI surface:

1. `GuLiCode/packages/desktop-electron/src/preload/index.ts`
2. `GuLiCode/packages/desktop-electron/src/preload/types.ts`
3. `GuLiCode/packages/desktop-electron/src/renderer/index.tsx`

## Verification

Frontend:

```powershell
cd GuLiCode\packages\app

bun test --preload ./happydom.ts ./src/pages/session/blueprint-side-panel.test.ts
# 14 pass

bun run typecheck
# pass
```

Whitespace check:

```powershell
git diff --check -- `
  GuLiCode/packages/app/src/pages/session/blueprint-side-panel.tsx `
  GuLiCode/packages/app/src/pages/session/blueprint-side-panel.test.ts
# pass, with only existing CRLF conversion warnings
```

## Manual Smoke Notes

Live debug startup after the rollback implementation:

```text
renderer: http://localhost:5173/
sidecar: http://127.0.0.1:12558
main window created
```

Smoke path to repeat:

1. Start a Blueprint run.
2. Let an Agent submit a `workspace_submit` changeset.
3. End the run.
4. Roll back the latest changeset from Blueprint Diff.
5. Confirm disk files, Blueprint Diff, native global diff, and file tree all
   reflect the rollback.
6. Click `查看` on the rolled-back changeset and confirm neutral text display.
7. Click `查看` again and confirm it collapses.
8. Restore the latest rollback and confirm accepted diffs return.
