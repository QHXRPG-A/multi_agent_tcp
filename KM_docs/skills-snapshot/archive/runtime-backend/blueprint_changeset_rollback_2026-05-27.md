# Blueprint Changeset Rollback Backend - 2026-05-27

## Summary

This pass implemented Codex-style rollback for GuLiCode Blueprint workspace
submissions. The rollback unit is one accepted `workspace_submit` changeset,
which is the current MCP tool call boundary that mutates the shared project.

The implementation is append-only:

1. Accepted changeset archives keep reversible before/after content.
2. Rollback and restore operations write journal markers.
3. `blueprint.runDiff` projects the effective state from changesets plus the
   rollback journal.
4. Historical changeset archives are not deleted or rewritten.

Unlike Codex snapshots, Blueprint must also restore the real shared project
files through the workspace manager.

## Implemented

Workspace manager:

1. Accepted changesets now write a reversible manifest with before/after hash,
   content references, file status, and binary/text metadata.
2. Reversible content covers added, deleted, modified, text, and binary files.
3. New rollback journal entries are written under the run archive and include
   rollback/restore event kind, changeset ids, actor, reason, timestamp, and
   integration references.
4. `rollback_changesets` supports tail rollback from a selected accepted
   changeset through the latest accepted changeset.
5. `restore_latest_rollback` restores the most recent restorable rollback.
6. Hash guards protect user or external edits. Rollback expects the current file
   to match the target changeset `after` hash; restore expects the current file
   to match the rollback `before` hash.
7. Old changesets without reversible manifests remain visible but are not
   rollbackable.

Desktop service:

1. Added `blueprint.rollbackChangesets`.
2. Added `blueprint.restoreRollback`.
3. Rollback and restore are rejected while a run is active.
4. A pending rollback guard prevents concurrent rollback/restore operations on
   the same run.
5. Terminal statuses allowed for rollback are completed, cancelled, and failed.

Electron bridge:

1. Main IPC exposes `blueprint-rollback-changesets` and
   `blueprint-restore-rollback`.
2. Preload and renderer platform surfaces expose matching methods.

## Diff Projection Rules

`blueprint.runDiff` now returns effective state:

1. Rolled-back changesets remain in `changesets`.
2. Rolled-back changesets are excluded from `acceptedDiffs`.
3. Changesets include status metadata such as `accepted`, `rolled_back`,
   `conflict`, `rejected`, `pending`, and `failed`.
4. Changesets include rollback metadata:
   `reversible`, `rollbackable`, `restorable`, `rollbackId`, `rolledBackAt`,
   and `rollbackDisabledReason`.
5. Summary includes rolled-back/restorable counts.

## Public Commands

Python service commands:

```text
blueprint.rollbackChangesets
blueprint.restoreRollback
```

Renderer platform methods:

```ts
rollbackBlueprintChangesets?(runId: string, toChangesetId: string, reason?: string)
restoreBlueprintRollback?(runId: string, rollbackId?: string)
```

## Files Changed

Backend/runtime:

1. `workspace_manager.py`
2. `desktop_blueprint_service.py`
3. `test_workspace_manager.py`
4. `test_desktop_blueprint_service.py`

Desktop bridge:

1. `GuLiCode/packages/desktop-electron/src/main/blueprint-runtime.ts`
2. `GuLiCode/packages/desktop-electron/src/main/ipc.ts`
3. `GuLiCode/packages/desktop-electron/src/main/ipc-blueprint-runtime.test.ts`
4. `GuLiCode/packages/desktop-electron/src/preload/index.ts`
5. `GuLiCode/packages/desktop-electron/src/preload/types.ts`
6. `GuLiCode/packages/desktop-electron/src/renderer/index.tsx`

Renderer platform:

1. `GuLiCode/packages/app/src/context/platform.tsx`

## Verification

Python:

```powershell
python -m pytest test_workspace_manager.py test_desktop_blueprint_service.py -q
# 45 passed
```

Electron:

```powershell
bun test ./src/main/ipc-blueprint-runtime.test.ts
# 2 passed

bun run typecheck
# pass
```

App platform typecheck was also run from `GuLiCode/packages/app` and passed.

## Operational Notes

1. Restart the Python sidecar / desktop debug service before judging rollback
   behavior, because already-running service processes keep old Python code
   loaded.
2. Rollback deliberately refuses hash conflicts instead of overwriting disk.
3. v1 does not support arbitrary middle changeset removal; it only rolls back a
   tail sequence.
4. v1 does not add manual accept/reject. `workspace_submit` remains the
   automatic accept boundary.
