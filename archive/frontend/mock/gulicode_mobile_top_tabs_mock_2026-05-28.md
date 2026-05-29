# GuLiCode Mobile Top-Tabs Mock

Date: 2026-05-28

## Scope

This archive records the current `/mobile` pure frontend mock after clearing the
older project/run/action UI. The page remains a display-only mock and does not
connect to backend services, send messages, edit blueprints, or trigger runtime
actions.

## Product Shape

The mobile shell now has three top tabs:

1. `Top Agent`
2. `蓝图`
3. `待定`

The visual direction is a light, milk-white, minimal Instagram-style treatment:
cream background, white cards, thin gray borders, black body text, and soft
rose/red accent states.

## Implemented

- Replaced the old `/mobile` surface with a single-column mobile app shell.
- Kept the header brand area: `GULICODE / 移动协作台` and `纯前端 Mock`.
- Moved navigation to top tabs and removed bottom navigation.
- Removed project selection, run creation, run actions, approval/archive, event
  stream, report list, and long runtime detail cards from the active UI.
- Added a read-only `Top Agent` chat panel with mock conversation messages.
- Added a lightweight read-only notice: `消息传递暂未接入`.
- Added a read-only `蓝图` tab with:
  - `结构总览`: simplified node chain.
  - `运行情况`: progress, current node, run status, and agent states.
  - `Diff`: file count and line-change summary without large diff bodies.
- Added a `待定` tab with an empty-state placeholder only.
- Preserved PWA registration, update/offline-ready notices, `100dvh`,
  safe-area padding, and no-horizontal-overflow constraints.

## State Model

The active mobile state was reduced to display-only mock data:

```ts
type MobileTab = "chat" | "blueprint" | "pending"
type TopAgentMessage = ...
type BlueprintOverview = ...
type BlueprintRunStatus = ...
type BlueprintDiffSummary = ...
```

`MobileApp` only owns the current tab and PWA update/offline indicators. It no
longer owns project selection, run selection, create-run, approval, archive, or
run-control state.

## Files

- `GuLiCode/packages/app/src/mobile/mobile-app.tsx`
- `GuLiCode/packages/app/src/mobile/mobile-state.ts`
- `GuLiCode/packages/app/src/mobile/mock-data.ts`
- `GuLiCode/packages/app/src/mobile/mobile-state.test.ts`
- `GuLiCode/packages/app/e2e/mobile.spec.ts`

## Validation

Commands passed in `GuLiCode/packages/app`:

```powershell
bun run typecheck
bun test --preload ./happydom.ts ./src/mobile
bun run build
$env:PLAYWRIGHT_PORT='4310'; bun run test:e2e -- e2e/mobile.spec.ts
```

Browser verification at `http://127.0.0.1:4311/mobile` confirmed:

- default tab is `Top Agent`
- no input or send button is present
- top tabs switch to `蓝图` and `待定`
- blueprint sections render `结构总览`, `运行情况`, and `Diff`
- pending tab shows only the reserved empty state
- no horizontal overflow at the checked mobile viewport

## Guardrails

- Do not wire Top Agent message sending in this mock pass.
- Do not add mobile blueprint editing, dragging, runtime start/stop, or approval
  controls.
- Do not reintroduce reports or settings into the `待定` tab until the product
  direction is explicitly updated.

