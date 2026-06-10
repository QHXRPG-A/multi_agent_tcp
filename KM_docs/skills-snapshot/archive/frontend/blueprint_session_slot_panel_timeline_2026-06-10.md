# Blueprint Session Slot Panel and Transcript Timeline

Date: 2026-06-10

## Summary

This archive records the Workbench frontend companion work for the 2026-06-10
Blueprint session-slot and POPO debugging thread.

The UI now treats the current conversation and the Blueprint structure-level
slot as separate surfaces:

- Current session: whether the opened session is running.
- Blueprint slot: whether the structure-level pool has running sessions.

The Agent information panel also moved toward using the durable Blueprint
session transcript as the conversation timeline, so POPO logs, session history,
and Agent panel chat order stay aligned across multiple live run instances.

## Runtime Panel Contract

The runtime side panel status card now uses binary user-facing states:

- Current session: `进行中` or `未运行`
- Blueprint run slot: `进行中` or `未运行`

The structure-level slot display shows capacity and queue information instead
of exposing raw live-run lifecycle states:

```text
运行中 X/3
排队 Y
```

The action buttons are:

- `终止会话` for the currently opened/selected session.
- `终止运行槽` for all running and queued sessions in the current Blueprint
  structure slot.

The old `完成` / `暂停` / `取消` / `失败` run-instance button group was removed
from the main runtime card. Those controls were too close to low-level live-run
state and did not match the new session/slot product model.

## Selected Session and Runtime Id

`BlueprintSessionSelect` supports selecting/opening sessions. The default
session is still `main+<blueprintId>`.

The UI should treat `runtime().runId` as following the active run id for the
currently opened session. That lets the canvas runtime visual and Agent detail
panel inspect the live run that is actually serving the selected session, while
the slot card still summarizes the structure-level pool.

## Session Timeline Source

The Agent information panel should use the session transcript timeline for
conversation history:

- `user_message`
- `agent_reply`

Runtime stream events, tool calls, task status, and diagnostics remain useful
inside the current live-run detail view, but they should not be the source of
truth for cross-run conversation ordering.

The backend timeline API is:

```text
blueprint.sessions.timeline(sessionKey)
```

It returns transcript events in durable transcript order, including fields such
as `type`, `timestamp`, `sessionKey`, `runId`, `content`, `source`, and
`reason` when available.

## Maintenance Event Filtering

The frontend projection filters framework maintenance events out of normal
chat bubbles. This was needed because old sessions and intermediate runtime
events could show messages such as task-status summaries or session termination
checks as if they were ordinary Agent replies.

Filtered or diagnostic-only event categories include:

- `agent.task_status`
- `agent_task_status` tool call/result records
- `summary-msg-*`
- `popo_session_termination_check`
- `framework_summary_request`
- `idle_task_status_missing`
- old `blueprint_terminate_session` maintenance records

The stream projection also de-duplicates the common flow where an Agent reply
has already been shown from streaming deltas and a later `message.completed`
event arrives for the same content.

## Crash Fix

After the slot/timeline refactor, one Workbench bundle crashed with:

```text
TypeError: Cannot read properties of undefined (reading 'includes')
```

The crash came from assuming stream event text was always present. The event
content helper now null-guards missing text before calling string methods, so
non-text or partial diagnostic events do not crash the side panel.

## Main Files

- `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.tsx`
- `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.test.ts`
- `GuLiCode/packages/app/src/context/platform.tsx`
- Workbench/Electron bridge files touched by the slot status, session
  terminate, slot terminate, and timeline APIs

## Verification

Commands run during this thread:

```powershell
bun test GuLiCode/packages/app/src/pages/session/blueprint-side-panel.test.ts
```

Representative final result:

- `26 pass`

The frontend bundle was rebuilt through the plugin packaging script and served
from the restarted `gulicode-bp` plugin runtime.

## Debugging Notes

When the panel says the slot is `未运行` even though a live run exists, check
which level the UI is reading:

- Session status should come from the opened session's `activeRunId`.
- Slot status should come from `blueprint.slots.status` for the structure pool.
- A live run id alone is not the same as the structure-level slot summary.

When Agent panel chat order looks wrong:

1. Compare the POPO chat order against the session transcript.
2. Confirm `blueprint.sessions.timeline(sessionKey)` returns the expected
   `user_message` and `agent_reply` sequence.
3. Treat runtime stream/tool events as diagnostics unless they correspond to a
   current live Agent reply that has not yet been persisted to transcript.
