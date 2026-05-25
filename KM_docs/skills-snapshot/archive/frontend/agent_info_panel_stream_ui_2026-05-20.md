# Agent Information Panel Stream UI - 2026-05-20

## Scope

This pass focused on the GuLiCode blueprint Agent information panel transcript
and status surface. The implementation lives in:

- `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.tsx`
- `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.test.ts`

## User-Facing Behavior

1. The panel defaults to a tall shape: `420 x 620`.
2. The header no longer exposes a width/height preset selector.
3. The compact status strip always shows four cards: status, queue, messages,
   and busy count.
4. The status detail expander in the status strip reveals only the extra
   runtime details, including "运行状态" and "JSON 位置". These details do not
   appear in the chat body or composer.
5. User messages sent from the panel are inserted into the transcript
   immediately for all Agents, not only Test Agent nodes.
6. Runtime/user-message status still syncs from runtime events and stream
   events; Test Agent JSON persistence remains limited to Test Agent nodes.

## Transcript Projection

The Agent panel now projects `AgentStreamEvent` into structured display rows:

- user messages: visible, tone `user`
- Agent replies: visible, tone `reply`
- Agent reasoning summaries: visible and collapsible, tone `reasoning`
- tool calls: visible and collapsible, tone `tool`
- queue failures/cancellations: visible, tone `error`
- raw status and scheduler tick events: hidden

Codex internal log lines are filtered from reply text.

## Tool Call Aggregation

Consecutive tool calls are grouped by default when there is no visible
interruption between them.

Grouping rules:

- `tool.started` and `tool.completed` are accumulated into the current tool
  group.
- `status`, `message.started`, and ordinary `queue.updated` events do not
  interrupt the group.
- User messages, Agent replies, Agent reasoning, queue errors, and other
  visible content flush the current tool group before rendering the next row.
- A multi-tool segment renders as `工具调用组 · N 个工具`.
- The group is collapsible; expanding shows the individual tool entries with
  name, status, detail, input, output, and error sections when present.
- A single-tool segment keeps the normal `工具调用 · name` appearance but uses a
  stable group id so it can grow into a multi-tool group during streaming
  without being treated as a brand-new row every tick.

The implementation uses:

- `agentPanelTimelineItems(events, userMessages)` to build a single ordered
  user/event timeline.
- `flushAgentPanelToolGroup()` inside `visibleAgentPanelEvents()` to enforce
  visible interruption boundaries.
- `agentPanelToolGroupDisplayEvent()` to produce either the single-tool row or
  grouped row.

## Collapsible Stability

Event collapsibles are controlled by `agentPanelEventOpen`, keyed by display
event id. This prevents stream/status ticks from automatically collapsing rows
that the user has expanded.

## Verification

Latest relevant verification:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\app
bun test --preload ./happydom.ts ./src/pages/session/blueprint-side-panel.test.ts
bun run typecheck
```

Observed result:

- `blueprint-side-panel.test.ts`: 9 passed
- app typecheck: passed

