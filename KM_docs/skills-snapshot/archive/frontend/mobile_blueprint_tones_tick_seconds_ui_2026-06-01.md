# Mobile Blueprint Tones and Tick Seconds UI - 2026-06-01

## Summary

This pass corrected mobile Blueprint rendering and changed Tick configuration
copy from framework tick counts to user-entered seconds.

Mobile now recovers typed Blueprint nodes from full desktop snapshots and legacy
snapshots, then colors nodes by Blueprint kind instead of giving all mobile
nodes one Worker Agent treatment. Desktop and mobile Tick UI now presents the
interval as seconds using the `every_n_seconds` / `everyNSeconds` model.

## Implemented

Mobile Blueprint projection:

1. Added `normalizedBlueprintNodeKind()` so mobile display can infer
   Agent, Worker Agent, Branch, Tick, and Script nodes from authoritative
   desktop snapshots and older worker-agent-shaped snapshots.
2. Added `nodeDisplayKindLabel()` for compact type labels shared by mobile
   rows, maps, and details.
3. Preserved compatibility with legacy `everyNTicks` values while projecting
   new payloads as `everyNSeconds`.
4. Updated mobile mock data and API tests to use seconds for Tick nodes.

Mobile Blueprint visual treatment:

1. Mobile structure rows now show node kind labels instead of forcing Worker
   Agent for every node.
2. Mobile Blueprint map nodes now use type-specific pastel tones:
   Worker Agent blue, Agent green, Branch orange, Tick cyan, and Script yellow.
3. The node details sheet shows non-agent metrics for structural nodes,
   including the seconds value for Tick nodes.
4. The visual style remains restrained and compact for the existing mobile PWA
   surface.

Desktop Blueprint UI:

1. Replaced the Tick inspector field key from `every_n_ticks` to
   `every_n_seconds`.
2. Replaced the inspector label/copy with the seconds-based i18n key
   `blueprint.field.everyNSeconds`.
3. Changed Tick node subtitle copy to the seconds-based key
   `blueprint.common.tickSubtitle`.
4. Desktop snapshot projection now sends `everyNSeconds` and keeps legacy
   `everyNTicks` only as a read fallback.

I18n:

1. Updated English, Simplified Chinese, and Traditional Chinese strings for
   Tick add-node descriptions, inspector labels, node subtitles, and help tips.

## Files Changed

Frontend/app:

1. `GuLiCode/packages/app/src/pages/session/blueprint-model.ts`
2. `GuLiCode/packages/app/src/pages/session/blueprint-model.test.ts`
3. `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.tsx`
4. `GuLiCode/packages/app/src/components/collaboration-auth.tsx`
5. `GuLiCode/packages/app/src/mobile/mobile-state.ts`
6. `GuLiCode/packages/app/src/mobile/mobile-state.test.ts`
7. `GuLiCode/packages/app/src/mobile/mobile-api.ts`
8. `GuLiCode/packages/app/src/mobile/mobile-api.test.ts`
9. `GuLiCode/packages/app/src/mobile/mobile-app.tsx`
10. `GuLiCode/packages/app/src/mobile/mobile-pwa.test.ts`
11. `GuLiCode/packages/app/src/mobile/mock-data.ts`
12. `GuLiCode/packages/app/src/i18n/en.ts`
13. `GuLiCode/packages/app/src/i18n/zh.ts`
14. `GuLiCode/packages/app/src/i18n/zht.ts`

Backend projection files touched for frontend payload shape:

1. `collaboration_server/app.py`
2. `collaboration_server/schemas.py`

## Verification

Frontend:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\app
bun test --preload ./happydom.ts ./src/pages/session/blueprint-model.test.ts ./src/pages/session/blueprint-side-panel.test.ts ./src/mobile/mobile-state.test.ts ./src/mobile/mobile-api.test.ts ./src/mobile/mobile-pwa.test.ts
# 81 pass

bun run typecheck
# pass
```

Manual browser verification:

1. Used Playwright against the local mobile dev server at
   `http://127.0.0.1:3040/mobile`.
2. Stubbed Collaboration Server API responses with a Tick node containing
   `everyNSeconds: 3`.
3. Opened the Blueprint tab and Tick detail sheet.
4. Verified the details sheet rendered a seconds metric and detail pill:
   `seconds = 3`, `every 3 seconds`.
5. Screenshot:
   `F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\logs\mobile-tick-seconds-sheet-qa.png`

Earlier mobile Blueprint visual QA in the same pass verified Branch, Tick,
Agent, and Worker Agent colors render by node kind, with screenshot:

```text
F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\logs\mobile-blueprint-qa.png
```

## Compatibility Notes

1. `everyNTicks` remains in TypeScript types only as a legacy snapshot fallback.
2. New desktop snapshots and mobile projections use `everyNSeconds`.
3. Mobile kind recovery intentionally supports older snapshots that stored
   Branch or Tick as `worker_agent` with identifying ports or seconds metadata.

## Skill/Archive Files

Installed skill:

```text
C:\Users\qiuhaoxuan\.codex\skills\multi-agent-tcp\archive\frontend\mobile_blueprint_tones_tick_seconds_ui_2026-06-01.md
```

Repository snapshot:

```text
KM_docs/skills-snapshot/archive/frontend/mobile_blueprint_tones_tick_seconds_ui_2026-06-01.md
```
