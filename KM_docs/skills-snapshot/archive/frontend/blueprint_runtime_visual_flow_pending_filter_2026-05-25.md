# Blueprint Runtime Visual Flow And Pending Filter - 2026-05-25

## Summary

This session focused on the GuLiCode embedded blueprint runtime presentation.
The user asked for the selected-node highlight to stop using an outer glow,
runtime message transfer to become visible on the actual connecting edges,
running nodes to show runtime light states, and the canvas viewport to show a
green running frame.

After a live debug run, a known UI bug was also fixed: the runtime panel treated
raw `status.queues.pending_messages` records as pending work even though the
backend can retain completed message history in that field. The UI now filters
active messages consistently for pending counts, per-agent queue display, and
edge-flow animation.

The earlier cleanup request intentionally removed generated run/archive data
under `docs/blueprints/runs/complex_test_blueprint_latest/`. Those deletions
remain part of the current worktree and should not be restored unless the user
explicitly asks.

## Implemented Shape

Selected-node feedback:

1. `BlueprintNodeCard` no longer uses the node-tone `glow` value as selected
   feedback.
2. Selected nodes now use a brighter selected border and `border-width: 2px`.
3. The edit-oriented `inspecting` and `connecting` outline behavior remains
   intact.
4. Runtime glow is separate from selection, so clicking a node does not add a
   selected outer halo.

Runtime node visual state:

1. `runtimeRunActive` is derived from `runtime.status.run.status === "running"`
   while excluding terminal run states.
2. `runtimeNodeVisualStates` marks every visible node as `active` during an
   active run.
3. Agent nodes become `working` when their lifecycle state is one of
   `dispatching`, `running`, `waiting_for_reply`, or `processing_reply`, or
   when `busy_count > 0`.
4. Route nodes and inactive agents keep the low-strength runtime glow during an
   active run.
5. Working agents receive stronger glow plus the
   `blueprint-runtime-node-breathe` animation.

Runtime edge flow:

1. The existing SVG edge path, arrow marker, and hit-test path are retained.
2. Active flow edges render an additional
   `data-blueprint-runtime-flow` SVG group.
3. Each group renders five small circles with staggered SVG
   `animateMotion` elements along the same source-to-target path.
4. Flow is derived from real message data, not from graph topology alone.
5. The active message statuses are intentionally limited to `queued` and
   `dispatching`.
6. Completed, failed, source-less, and no-matching-edge messages do not produce
   moving dots.

Runtime viewport frame:

1. The blueprint canvas viewport now contains
   `data-blueprint-runtime-frame`.
2. The frame is shown only while `runtimeRunActive` is true.
3. The frame covers the canvas viewport and intentionally does not cover the
   right runtime panel.
4. The frame uses a green border and modest glow to indicate a running
   blueprint.

Pending-message bug fix:

1. `pendingMessages` no longer counts
   `recordEntries(asRecord(queues()?.pending_messages))` directly.
2. New helpers normalize and filter runtime messages:
   `runtimeMessageEntries`, `runtimePendingMessages`,
   `runtimePendingMessageEntries`, and `runtimeMessageIsActive`.
3. `runtimeMessageIsActive` shares the same active status set used by the edge
   flow projection: `queued` and `dispatching`.
4. `queueByAgent` now filters messages with `runtimePendingMessages` and omits
   agents that have no active queued/dispatching work.
5. `runtimeEdgeFlows` uses `runtimePendingMessageEntries`, keeping the runtime
   panel and edge animation semantics aligned.

Reduced-motion behavior:

1. Runtime node/frame highlights remain visible.
2. The breathing animation is disabled.
3. Runtime flow SVG groups are hidden so users who prefer reduced motion do not
   see moving dots.

## Files Changed

Primary app files:

1. `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.tsx`
2. `GuLiCode/packages/app/src/index.css`
3. `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.test.ts`

Skill/archive files:

1. `C:\Users\qiuhaoxuan\.codex\skills\multi-agent-tcp\SKILL.md`
2. `C:\Users\qiuhaoxuan\.codex\skills\multi-agent-tcp\archive\blueprint_runtime_visual_flow_pending_filter_2026-05-25.md`
3. `KM_docs/skills-snapshot/SKILL.md`
4. `KM_docs/skills-snapshot/archive/blueprint_runtime_visual_flow_pending_filter_2026-05-25.md`

## Live Debug Evidence

Debug launch:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode
bun run dev:desktop
```

Observed endpoints and logs:

1. Renderer URL: `http://localhost:5173/`
2. Desktop service sidecar: `http://127.0.0.1:11217`
3. Blueprint service facade observed at `http://127.0.0.1:6943/blueprint`
4. Debug stdout log:
   `F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\logs\gulicode-debug-start-20260525-144613.out.log`
5. Debug stderr log:
   `F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\logs\gulicode-debug-start-20260525-144613.err.log`

The Electron main window was created successfully. The observed warnings were
nonfatal eval/SQLite messages.

Live run analyzed:

1. Run id: `run-2306ff139459`
2. Project dir: `D:\agents_work_test`
3. Execution mode: `live`
4. Runtime status at inspection: `running`
5. `ready_for_top_agent_summary`: `true`
6. All agents observed idle/completed with queue size 0 and busy count 0:
   `test-agent`, `test-agent-1`, `test-agent-2`, and `test-agent-3`.

Runtime evidence paths:

1. Message journal:
   `D:\agents_work_test\.multi_agent_workspace\runs\active\run-2306ff139459\shared\logs\message_journal.jsonl`
2. Diagnostics snapshot:
   `D:\agents_work_test\.multi_agent_workspace\runs\active\run-2306ff139459\shared\logs\blueprint-diagnostics\snapshot.json`

Message flow order:

1. Top Agent queued initial tasks to `test-agent-1`, `test-agent-2`, and
   `test-agent-3` around 15:09:28.
2. `test-agent-3 -> test-agent`: queued at 15:10:16.564, dispatched at
   15:10:17.001, processed by `test-agent` at 15:11:52.276.
   Message id: `msg-79caa974691b`; batch id: `out-38d6b58c33b4`.
3. `test-agent-2 -> test-agent`: queued at 15:10:35.510, dispatched at
   15:11:52.526, processed at 15:12:52.941.
   Message id: `msg-14b79b10e65d`; batch id: `out-ba83cb07d2c2`.
4. `test-agent-1 -> test-agent`: queued at 15:11:14.168, dispatched at
   15:12:53.209, processed at 15:14:09.011.
   Message id: `msg-1d3c429a92ed`; batch id: `out-005df9fabd64`.

Conclusion from the run:

1. The actual fan-in happened in the order `test-agent-3`,
   `test-agent-2`, `test-agent-1`.
2. `test-agent` processed its downstream queue serially.
3. At inspection time there were no active queued/dispatching messages, so the
   visual state should show the running frame/node glow but no edge flow dots.
4. The raw `pending_messages` field still contained completed records, which
   exposed the pending-count bug fixed in this session.

Reports observed:

1. `D:\agents_work_test\.multi_agent_workspace\runs\active\run-2306ff139459\shared\reports\test-agent\dispatch-receipt-test-agent-3-2026-05-25.md`
2. `D:\agents_work_test\.multi_agent_workspace\runs\active\run-2306ff139459\shared\reports\test-agent\receipt-out-005df9fabd64.md`
3. `D:\agents_work_test\.multi_agent_workspace\runs\active\run-2306ff139459\shared\reports\test-agent\receipts\test-agent-2_to_test-agent_2026-05-25.md`
4. `D:\agents_work_test\.multi_agent_workspace\runs\active\run-2306ff139459\shared\reports\test-agent-2\agent-link-test-2026-05-25.md`

## Verification

Commands:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\app
bun test --preload ./happydom.ts ./src/pages/session/blueprint-side-panel.test.ts
bun run typecheck
```

Observed results:

1. Blueprint side-panel tests passed: 12 tests, 336 assertions.
2. App typecheck passed.

The test file includes source-level assertions for:

1. `runtimeEdgeFlows`
2. `data-blueprint-runtime-flow`
3. `data-blueprint-runtime-frame`
4. Runtime visual state deriving from `props.state.status` /
   `runtime().status`
5. No renderer-side scheduler for runtime visual projection
6. Selected-node styling no longer using selected glow
7. Active pending filtering for raw `pending_messages`

## Current Worktree Notes

At archive time, the worktree included:

1. Modified app files:
   `GuLiCode/packages/app/src/index.css`,
   `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.test.ts`,
   and `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.tsx`.
2. Intentional cleanup deletions under
   `docs/blueprints/runs/complex_test_blueprint_latest/`.
3. Newly written skill/archive records for this handoff.

No git staging or commit was performed.

## Follow-ups

1. Manual smoke a live run while messages are still `queued` or `dispatching`
   to confirm the moving dots appear only on the currently active edge.
2. Decide whether `ready_for_top_agent_summary=true` should auto-complete the
   run or continue to require deliberate user closure.
3. Consider backend schema cleanup if the retained history in
   `pending_messages` keeps causing confusion. A split between active pending
   work and message history would make the frontend projection simpler.
4. If the user wants richer runtime playback, build it from the journal or
   event stream as a separate timeline feature instead of changing the active
   flow projection.
