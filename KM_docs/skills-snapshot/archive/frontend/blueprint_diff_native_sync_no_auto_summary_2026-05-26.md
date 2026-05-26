# Blueprint Diff Native Sync And No Auto Summary - 2026-05-26

## Summary

This pass fixed two GuLiCode desktop blueprint UX problems found during live
debugging:

1. Blueprint accepted diffs were visible in the blueprint overlay but not in the
   right native global Review/FileTree diff.
2. Reloading the renderer with Ctrl+R after a completed blueprint run could
   auto-submit a Top Agent summary prompt and create a new "思考中" turn.

The product decision after this pass is:

- Blueprint Diff remains the run-scoped status/source UI for all changesets.
- The right native Review/FileTree diff should also show accepted blueprint
  textual diffs for review/navigation.
- Completed runs must not auto-trigger Top Agent. Users can decide whether to
  ask for a summary in chat.

## Native Global Diff Sync Fix

Root cause:

1. `BlueprintSidePanel` initially synced accepted diffs only by dispatching
   `window.dispatchEvent(new CustomEvent("workspace.diff.changed", ...))`.
2. On reload/remount, the first non-empty diff could be emitted before
   `session.tsx` registered its listener.
3. The blueprint side then recorded the signature as already synced, so later
   runtime ticks with the same accepted changeset signature did not emit again.
4. Additionally, non-git project-reference sessions fall back to `turn` review
   mode. The previous merge path only merged blueprint diffs into `git/branch`
   review modes, so `D:\agents_work_test` could keep showing `0` changes in the
   right panel.

Implemented frontend shape:

1. `BlueprintSidePanel` now exports `BlueprintDiffFile` and
   `BlueprintDiffSyncPayload`.
2. `BlueprintSidePanel` calls `props.onBlueprintDiffChanged?.(payload)` when
   the accepted changeset signature changes.
3. The existing `workspace.diff.changed` event remains as a refresh/fallback
   path.
4. `SessionSidePanel` passes the callback through to `BlueprintSidePanel`.
5. `session.tsx` stores `blueprintReviewDiffs`, refreshes VCS/FileTree views,
   and merges blueprint accepted diffs into both `git/branch` and `turn` review
   modes.

Observed data:

```text
run-739420ebbb3d
summary.total = 4
summary.accepted = 3
summary.rejected = 1
acceptedDiffs = 3 files
```

Expected UI behavior:

- Blueprint overlay shows all changesets, including rejected/conflict status.
- Right native global diff shows accepted textual blueprint diffs only.
- Rejected/conflict changesets do not enter `acceptedDiffs`.

## Auto Top Agent Summary Removal

Root cause:

1. `GraphRuntime` sets `ready_for_top_agent_summary=true` when all visible
   completion Agents reach terminal task status.
2. The frontend used this flag to auto-submit a prompt:
   `Summarize completed blueprint run`.
3. Duplicate prevention lived only in an in-memory
   `autoTopAgentSummaryAttempts` map.
4. Ctrl+R remounted the frontend, cleared that map, restored the completed run
   state, and triggered the auto prompt again.

Implemented change:

1. Removed `autoTopAgentSummaryAttempts`.
2. Removed the `createEffect` that called `props.onBlueprintPlanningSubmit`
   for `Summarize completed blueprint run`.
3. Removed `buildTopAgentSummaryMessage`.
4. Kept the automatic run-complete/final-result calculation path.
5. Updated i18n text from "requesting Top Agent summary" to "calculating final
   results".

Expected UI behavior:

- Ctrl+R after a completed run must not create a new chat turn.
- The right runtime panel may still show finalization state, but it should not
  invoke the Top Agent automatically.

## Files Changed

Frontend/app:

1. `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.tsx`
2. `GuLiCode/packages/app/src/pages/session/session-side-panel.tsx`
3. `GuLiCode/packages/app/src/pages/session.tsx`
4. `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.test.ts`
5. `GuLiCode/packages/app/src/i18n/en.ts`
6. `GuLiCode/packages/app/src/i18n/zh.ts`
7. `GuLiCode/packages/app/src/i18n/zht.ts`

## Verification

```powershell
cd GuLiCode\packages\app
bun test src/pages/session/blueprint-side-panel.test.ts
# 13 pass

bun run typecheck
# pass
```

Additional backend data check:

```text
D:\agents_work_test\.multi_agent_workspace\runs\archived\run-739420ebbb3d
acceptedDiffs files:
- docs/blueprint_diff_test_agent_2.md
- docs/blueprint_diff_test_agent_3.md
- docs/blueprint_diff_test_agent_1.md
```

## Remaining Manual Checks

1. Restart the desktop renderer/service and run a fresh live blueprint smoke.
2. Verify native global diff sync during runtime and after archive.
3. Verify Ctrl+R on a completed run restores UI state without a new "思考中"
   assistant turn.
