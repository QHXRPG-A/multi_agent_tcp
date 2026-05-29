# GuLiCode Mobile Agent Info Sheet Mock

Date: 2026-05-28

## Scope

This archive records the `/mobile` Blueprint tab interaction pass for clickable
nodes, Diff expansion, and the mobile Agent information sheet. The work remains
frontend-only mock UI. It does not connect to GuLiCode desktop runtime,
Blueprint APIs, `D:\codex`, message sending, approval, or runtime controls.

## Implemented

- Kept the top tab visual direction light and minimal: milk-white surfaces,
  soft rose borders, low contrast shadows, and no black active tab.
- Removed the standalone `->` execution-order affordance from the structure
  overview rows.
- Made Blueprint nodes clickable from:
  - the structure overview list
  - the structure preview map
  - the fullscreen structure map
- Removed the inline node detail card under `结构总览`.
- Added a bottom Agent information sheet for selected nodes:
  - light INS-style card treatment matching the mobile mock
  - fixed header with agent name, adapter kind, state, and close button
  - metric grid for status, task status, queue, message count, busy count, and
    update time
  - `运行状态` details collapsed by default, expandable by tap
  - larger agent output/chat reading area
  - disabled mock input, mode select, and send button
  - a single scrollable sheet body with a visible thin light scrollbar so the
    details, output, and disabled input area are reachable on small screens
- Added clickable Diff controls:
  - metric buttons for file/add/delete summary details
  - accordion file rows with chevron state
  - light add/delete/context diff preview rows

## State Model

The mobile mock data was expanded only inside the frontend mock types:

```ts
type BlueprintAgentPanelEventTone = "user" | "reply" | "reasoning" | "tool" | "error" | "event"
type BlueprintAgentPanelEvent = ...
type BlueprintAgentPanel = ...
type BlueprintNode = {
  id: string
  label: string
  state: BlueprintNodeState
  role: string
  detail: string
  note: string
  agentPanel: BlueprintAgentPanel
}
```

`BlueprintDiffFile` also carries `previewLines` for mock accordion content. None
of these fields are public backend contracts.

## Files

- `GuLiCode/packages/app/src/mobile/mobile-app.tsx`
- `GuLiCode/packages/app/src/mobile/mobile-state.ts`
- `GuLiCode/packages/app/src/mobile/mock-data.ts`
- `GuLiCode/packages/app/src/mobile/mobile-state.test.ts`
- `GuLiCode/packages/app/e2e/mobile.spec.ts`

## Validation

Commands passed in `GuLiCode/packages/app`:

```powershell
bun test --preload ./happydom.ts ./src/mobile
bun run typecheck
$env:PLAYWRIGHT_PORT='4312'; bun run test:e2e -- e2e/mobile.spec.ts
bun run build
```

Browser verification at `http://127.0.0.1:4311/mobile` confirmed:

- Agent sheet background is light (`rgb(255, 253, 250)`)
- inline `blueprint-node-detail` count is `0`
- structure list, preview map, and fullscreen map open the same Agent sheet
- fullscreen map z-index remains below the Agent sheet backdrop
- `运行状态` is collapsed by default and expands on tap
- Agent sheet body uses `overflow-y: auto` with a thin light scrollbar
- the sheet body can actually scroll and the disabled send controls remain
  reachable
- Diff metric and file accordion interactions still work
- no horizontal document overflow at the checked mobile viewport

## Guardrails

- Keep this surface as a frontend-only mock until product direction changes.
- Do not add message sending, runtime start/stop, node editing, node dragging,
  approvals, or real Blueprint API calls from this mobile sheet.
- Keep the Agent sheet visually aligned with the mobile mock's light
  minimal/INS-style language, not the dark desktop runtime panel.
- Treat this archive as UI context and validation history, not a backend API
  contract.
