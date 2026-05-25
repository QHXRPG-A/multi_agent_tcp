# Blueprint Flow Progress Overlay And Plan Sync - 2026-05-25

## Summary

This session implemented and debugged the blueprint flow progress overlay in
the GuLiCode embedded blueprint panel.

The target behavior is:

1. From right-panel blueprint task submit through Top Agent planning and staged
   plan confirmation, the blueprint panel is locked with a white mask and an
   indeterminate progress HUD.
2. During `Approve and start`, the blueprint panel is locked while the app
   starts the runtime.
3. Once the runtime reaches `running`, the mask and progress HUD disappear so
   the user can inspect the active run.
4. When runtime summary readiness appears, the UI can show summary/ending
   transitional phases while automatically requesting Top Agent summary and
   completing the run.
5. The left chat/composer remains available for planning approval, rejection,
   questions, and summary output.

## Frontend Shape

Primary changes:

1. `BlueprintProgressOverlay` renders a pointer-blocking white mask and a
   bottom-canvas indeterminate progress HUD.
2. The overlay is positioned from `canvasRef` measurements, with a bottom-center
   fallback.
3. Progress phases are `planning`, `start`, `summary`, and `ending`.
4. The earlier `running` progress phase was removed. A running runtime is shown
   through the green canvas frame, node runtime glow, and edge flow projection,
   not through a blocking overlay.
5. `BlueprintSidePanel` keeps a lightweight flow lock and persists it in a
   module-level store so closing and reopening the blueprint panel does not lose
   planning/start progress.
6. A module-level auto-complete dedupe set prevents duplicate runtime complete
   calls after panel remounts.
7. If automatic runtime complete fails, the run is manually unlocked so the user
   can use the right runtime controls.

Session integration:

1. `session.tsx` derives `blueprintPlanningProgress` and passes it through
   `SessionSidePanel` into `BlueprintSidePanel`.
2. A new `planningRequested` state records that a blueprint planning submit was
   accepted by the main composer path.
3. `planningRequested` keeps the overlay active even before the Top Agent status
   stream has produced a pending question or staged plan.
4. Silent automatic summary requests do not set `planningRequested`, so runtime
   summary output does not re-lock the blueprint panel as a normal planning
   request.
5. `blueprintPlanningStatus` is now pulled immediately when a planning session
   exists, then polled while the session is busy, `planningRequested` is true,
   or a pending question/plan exists.
6. This fixed the missed confirmation card issue where Top Agent had already
   staged a plan but the frontend stopped polling before `pendingPlan` was
   applied.

## User-Visible Fixes

Observed issues fixed during live debugging:

1. Closing and reopening the blueprint panel dropped the progress overlay.
2. Clicking right-panel `Submit` did not show progress immediately.
3. Top Agent streaming planning output could outlive the local 10-second
   grace window, causing the progress overlay to disappear too early.
4. Once runtime reached `RUNNING`, the progress overlay stayed visible and
   blocked the active run. It now disappears on `running`.
5. Top Agent could stage a plan successfully while no confirm/reject card
   appeared. Immediate and sustained `blueprintPlanningStatus` polling now
   recovers `pendingPlan`.

## Files Changed

Frontend/app files:

1. `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.tsx`
2. `GuLiCode/packages/app/src/pages/session.tsx`
3. `GuLiCode/packages/app/src/pages/session/session-side-panel.tsx`
4. `GuLiCode/packages/app/src/index.css`
5. `GuLiCode/packages/app/src/i18n/en.ts`
6. `GuLiCode/packages/app/src/i18n/zh.ts`
7. `GuLiCode/packages/app/src/i18n/zht.ts`
8. `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.test.ts`
9. `GuLiCode/packages/app/src/pages/session/blueprint-planning-session.test.ts`

Skill/archive files:

1. `C:\Users\qiuhaoxuan\.codex\skills\multi-agent-tcp\SKILL.md`
2. `C:\Users\qiuhaoxuan\.codex\skills\multi-agent-tcp\archive\frontend\blueprint_flow_progress_overlay_plan_sync_2026-05-25.md`
3. `KM_docs/skills-snapshot/SKILL.md`
4. `KM_docs/skills-snapshot/archive/frontend/blueprint_flow_progress_overlay_plan_sync_2026-05-25.md`

## Verification

Commands:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\app
bun test --preload ./happydom.ts ./src/pages/session/blueprint-side-panel.test.ts ./src/pages/session/blueprint-planning-session.test.ts ./src/i18n/parity.test.ts
bun run typecheck
```

Observed result:

1. Targeted app tests passed: 14 tests, 468 assertions.
2. App typecheck passed.

Whitespace check:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp
git diff --check -- GuLiCode/packages/app/src/pages/session.tsx GuLiCode/packages/app/src/pages/session/blueprint-planning-session.test.ts GuLiCode/packages/app/src/pages/session/blueprint-side-panel.tsx GuLiCode/packages/app/src/pages/session/blueprint-side-panel.test.ts
```

Observed result: only Git CRLF conversion warnings.

## Debug Notes

Recent debug launches used:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode
bun run dev:desktop
```

The renderer served at `http://localhost:5173/`. Sidecar ports are dynamically
allocated per launch, with recent observed values including `6533`, `14488`,
`8898`, `2621`, and `14352`.

Electron/Vite warnings about eval in the bundled opencode node build and
experimental SQLite were nonfatal during these runs.

## Current Follow-ups

1. Manual smoke the full submit -> Top Agent staged plan -> confirm/reject card
   path after a fresh app launch.
2. Manual smoke confirm/start to verify overlay disappears as soon as runtime
   status becomes `running`.
3. Manual smoke summary readiness to verify automatic Top Agent summary request
   and automatic runtime complete still dedupe correctly after panel reopen.

