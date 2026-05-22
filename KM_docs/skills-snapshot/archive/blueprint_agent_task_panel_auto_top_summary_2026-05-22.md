# Blueprint Agent Task Panel And Auto Top Summary - 2026-05-22

## Summary

This session closed the UI gap between Agent runtime state and Agent task
completion, then changed the top-agent completion flow from a passive
"summary-ready" notice into an automatic Top Agent summary request.

The backend behavior remains intentionally split:

- Agent lifecycle state such as `idle` describes availability to receive the
  next framework message.
- Agent task status such as `completed`, `blocked`, `needs_input`, or `failed`
  describes the task outcome for the current run.

The Agent information panel now displays both concepts. The runtime status
panel still shows the run-level `ready_for_top_agent_summary` state, but the
frontend now also bridges that state back into the desktop Top Agent session so
the user does not have to click the final "完成" action just to trigger a
human-facing summary.

## Debug And Runtime Findings

The recent live Test Agent run under inspection was:

```text
run-65ef316cfff5
```

Important observed paths:

```text
D:\agents_work_test\.multi_agent_workspace\runs\active\run-65ef316cfff5
C:\Users\qiuhaoxuan\AppData\Roaming\ai.opencode.desktop.dev\logs\agent-info-panel-tests\agent-panel-test.json
```

The active run had downstream confirmations under:

```text
shared\reports\ui-tests\downstream\test-agent-1-confirmation.json
shared\reports\ui-tests\downstream\test-agent-2-confirmation.json
shared\reports\ui-tests\downstream\test-agent-3-confirmation.json
```

Those downstream confirmation records reported `status: completed` and no
project source modifications. The shared manifest also recorded
`workspace_publish` and `agent_task_status` completion events for the downstream
agents.

The visible `idle` state in the Agent information panel was confirmed to be
backend-intended: `idle` is runtime lifecycle/availability, not task
completion. Completion is separately exposed through `task_status` in
`GraphRuntime.status_snapshot()`, `agent.task_status` stream events, and
`_agent_stream_status_event()`.

Remaining noisy environment issues seen in private Codex logs were plugin sync
403/rate-limit entries, missing curated plugins, and Windows
`CreateProcessWithLogonW failed: 1326`. These did not prevent framework MCP
task-status completion in the inspected run.

## Implemented Shape

Agent information panel task status:

1. `AgentInfoPanel` now computes `latestTaskStatus` from the newest
   `agent.task_status` stream event.
2. It falls back through `statusField("task_status")` and runtime
   `task_status`.
3. The top metric strip now includes a separate `任务状态` card.
4. The status details expander now includes `任务状态`, optional `任务消息`, and
   optional `任务摘要`.
5. The metric grid now uses three columns so the five status cards wrap
   cleanly without over-compressing text.
6. `RuntimeMetric` exposes a `title` for truncated values.

Automatic Top Agent summary request:

1. `BlueprintSidePanel` watches the runtime snapshot for
   `run.ready_for_top_agent_summary === true`.
2. The trigger is deduplicated by `runId + ready_for_top_agent_summary_generation`
   with an in-memory `autoTopAgentSummaryAttempts` map.
3. On readiness, the panel builds a Top Agent summary request containing the
   run id, summary generation, and current per-AgentNode task statuses.
4. The request is submitted through the existing desktop
   `blueprintPlanning` main-composer handoff, because the desktop/current chat
   session is the Top Agent in this product path.
5. The generated prompt tells Top Agent to use
   `framework_control_runtime_status`,
   `framework_control_top_agent_explain_status`, and
   `framework_control_top_agent_utterances` for the active live run.
6. The request explicitly says not to stage a new start plan and not to start a
   new run.
7. If the main composer is busy or has draft/context content, the automatic
   handoff uses `silentBlocked: true` and retries after 10 seconds instead of
   repeatedly showing a blocking toast.
8. Blueprint popout forwarding and Electron preload types now carry the
   optional `silentBlocked` flag.
9. The ready banner copy now says the app is requesting a Top Agent summary,
   instead of saying the Top Agent merely can summarize.

## Files Touched

Primary app files:

```text
GuLiCode/packages/app/src/pages/session/blueprint-side-panel.tsx
GuLiCode/packages/app/src/pages/session.tsx
GuLiCode/packages/app/src/context/platform.tsx
GuLiCode/packages/app/src/pages/session/session-side-panel.tsx
GuLiCode/packages/app/src/i18n/en.ts
GuLiCode/packages/app/src/i18n/zh.ts
GuLiCode/packages/app/src/i18n/zht.ts
```

Electron type bridge:

```text
GuLiCode/packages/desktop-electron/src/preload/types.ts
```

Tests:

```text
GuLiCode/packages/app/src/pages/session/blueprint-side-panel.test.ts
GuLiCode/packages/app/src/pages/session/blueprint-planning-session.test.ts
GuLiCode/packages/desktop-electron/src/main/ipc-blueprint-runtime.test.ts
```

## Verification

App source tests:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\app
bun test --preload ./happydom.ts ./src/pages/session/blueprint-side-panel.test.ts ./src/pages/session/blueprint-planning-session.test.ts
```

Observed result: 13 passed, 0 failed, 342 assertions.

App typecheck:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\app
bun run typecheck
```

Observed result: passed.

Desktop Electron typecheck:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\desktop-electron
bun run typecheck
```

Observed result: passed.

Desktop Electron IPC tests:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\desktop-electron
bun test ./src/main/ipc-blueprint-runtime.test.ts
```

Observed result: 2 passed, 0 failed, 25 assertions.

Whitespace check:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp
git diff --check -- GuLiCode/packages/app/src/pages/session/blueprint-side-panel.tsx GuLiCode/packages/app/src/pages/session.tsx GuLiCode/packages/app/src/context/platform.tsx GuLiCode/packages/app/src/pages/session/session-side-panel.tsx GuLiCode/packages/desktop-electron/src/preload/types.ts GuLiCode/packages/app/src/i18n/en.ts GuLiCode/packages/app/src/i18n/zh.ts GuLiCode/packages/app/src/i18n/zht.ts GuLiCode/packages/app/src/pages/session/blueprint-side-panel.test.ts GuLiCode/packages/app/src/pages/session/blueprint-planning-session.test.ts
```

Observed result: no whitespace errors; Git only reported CRLF conversion
warnings.

## Current Follow-Ups

1. Manual smoke a fresh live fan-out run and verify the Top Agent summary
   request appears in the main desktop session without clicking the runtime
   "完成" action.
2. Verify the retry path by leaving draft text in the main composer until
   `ready_for_top_agent_summary`, then clearing it and confirming the automatic
   summary request is submitted on a later runtime refresh.
3. Decide whether a completed summary request should optionally auto-end the
   run through `runtime_end("complete")`, or whether final run closure should
   remain a deliberate user/Top Agent action.
