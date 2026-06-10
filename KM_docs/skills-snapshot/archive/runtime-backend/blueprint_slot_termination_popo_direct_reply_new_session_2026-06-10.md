# Blueprint Slot Termination and POPO Direct Reply Hardening

Date: 2026-06-10

## Summary

This archive records the later 2026-06-10 fixes for the `gulicode-bp` plugin
and POPO-triggered Blueprint session path.

The main corrections were:

- `终止运行槽` is a structure-level force cleanup, not an idle-instance cleanup.
- POPO callback session writes are safe under concurrent requests in one
  process.
- POPO-triggered Agents can still reply to the original POPO conversation when
  they emit an ordinary Agent reply instead of calling `blueprint_reply_popo_user`.
- `/new` from POPO clears the current session and returns an explicit
  `已开启新会话` confirmation so users do not see only `思考中....`.

## Slot Termination Semantics

`blueprint.slots.terminate` now operates over the whole
`projectDir + blueprintStructureId` slot pool:

- Collect all runs in the structure pool, not only idle/unbound instances.
- Mark running and queued sessions in that pool as `terminated`.
- Clear queued messages and write `session_terminated` transcript events.
- Mark each pool run as `closing` / `closed`.
- Clear `session_key` and `bound_session_key`.
- Best-effort close MCP, runtime, and backend for every live run.
- Do not use the single-session reset/reuse path and do not archive workspaces
  as part of slot termination.

The API result includes:

- `terminated: true`
- `terminatedRunIds`
- `terminatedSessionKeys`
- `closeErrors`

The slot summary after termination should show no running run ids and no
running or queued sessions.

## Status Query Anti-Hang Boundary

`blueprint.slots.status` is deliberately metadata-only. It reads saved
run/session state and does not wait for live runtime status. This keeps the
Workbench slot card responsive even when one runtime backend is blocked.

`blueprint.listRuns` / runtime status paths use short timeout behavior and can
surface pending status instead of blocking the Workbench indefinitely.

## POPO Session Write Race

The observed POPO private-chat failure:

```text
[WinError 5] 拒绝访问:
session.json.<pid>.tmp -> session.json
```

was not a real permission problem. The callback service is threaded, and the
old `_atomic_write_json()` used a process-scoped temp file name
`session.json.<pid>.tmp`. Concurrent callbacks in the same process could race
on the same temp path and Windows `Path.replace()` could fail.

`DesktopBlueprintService._atomic_write_json()` now uses a temp file containing:

- target file name
- process id
- thread id
- random UUID

It also retries short Windows `PermissionError` failures and cleans up the temp
file best-effort.

## POPO Direct Reply Fallback

The group-chat no-reply case was traced to this flow:

- POPO message entered Blueprint normally.
- The start Agent produced an ordinary text reply.
- The Agent did not call `blueprint_reply_popo_user`.
- No `popo_reply_sent` event existed, so the user never received the reply.
- Later framework maintenance could complete the task without sending POPO.

`GraphRuntime` now exposes `agent_reply_callback`. `DesktopBlueprintService`
attaches a callback when stream notifications are attached. For POPO-bound
runs, an ordinary start-Agent reply schedules a short delayed fallback:

- Ignore summary/maintenance message ids such as `summary-msg-*`.
- Ignore empty text and non-POPO runs.
- Ignore replies from non-start Agents.
- Deduplicate by current message id and reply content.
- Call the same service-owned POPO send callback used by
  `blueprint_reply_popo_user`.
- Record transcript events with `messageId` and `fallback: true`.
- Mark the task completed with metadata
  `source_tool: popo_direct_reply_fallback`.

The fallback does not replace `blueprint_reply_popo_user`; it prevents a user
visible drop when the Agent replies naturally.

## `blueprint_reply_popo_user` Regression Fix

A regression was introduced while adding message id propagation to
`blueprint_reply_popo_user`: `_ordinary_blueprint_reply_popo_user()` referenced
an undefined variable named `context`.

The correct source is `scope.current_message_context`. The regression test now
asserts that the service callback receives `message_id="msg-1"` from the
current MCP message context.

## POPO `/new`

`/new` is handled by the Blueprint session layer before the message reaches the
Agent.

For the current POPO session identity:

- Cancel the active run if one exists.
- Clear `contextSummary`.
- Reset `messageCount` to 0.
- Clear `activeRunId`.
- Preserve `lastRunId` when a run was cancelled.
- Empty `transcript.jsonl`.
- Set the session back to `idle`.

`popo_agent_bot_run.call_blueprint()` now returns `已开启新会话` when
`blueprint.slots.message` returns `cleared: true`. `handle_and_reply()` sends
that as the second POPO message after the immediate `思考中....` notice.

## Main Files

- `desktop_blueprint_service.py`
- `graph_runtime.py`
- `blueprint_mcp_runtime.py`
- `popo_agent_bot_run.py`
- `test_desktop_blueprint_service.py`
- `test_popo_agent_bot_run.py`

## Verification

Commands run from `F:\src\Package\Script\Python\multi_agent_tcp`:

```powershell
python -m py_compile desktop_blueprint_service.py graph_runtime.py blueprint_mcp_runtime.py popo_agent_bot_run.py test_desktop_blueprint_service.py test_popo_agent_bot_run.py
python -m pytest test_popo_agent_bot_run.py test_desktop_blueprint_service.py::test_atomic_write_json_uses_unique_temp_files test_desktop_blueprint_service.py::test_popo_reply_mcp_callback_sends_to_saved_reply_target test_desktop_blueprint_service.py::test_popo_direct_agent_reply_fallback_sends_when_tool_was_not_called -q
python -m pytest test_desktop_blueprint_service.py::test_run_mcp_popo_reply_tool_is_start_agent_scoped test_desktop_blueprint_service.py::test_popo_reply_mcp_callback_sends_to_saved_reply_target -q
python -m pytest test_popo_agent_bot_run.py -q
```

Representative results:

- POPO callback focused tests: `3 passed`
- POPO fallback/session write focused tests: `5 passed`
- POPO MCP reply regression tests: `2 passed`

The personal plugin was rebuilt with:

```powershell
python plugins\gulicode-bp\scripts\install_personal_plugin.py --force --skip-web-build
```

and restarted through:

```powershell
C:\Users\qiuhaoxuan\plugins\gulicode-bp\scripts\start_workbench.py --project-dir F:\src\Package\Script\Python\multi_agent_tcp --blueprint-id default
```

Final smoke checks confirmed:

- `/api/config` loaded.
- `blueprint.slots.status` returned in tens of milliseconds.
- `blueprint.listRuns` returned quickly.
- `http://127.0.0.1:3100/health` returned `{"ok": true}`.

Latest observed Workbench URL after this archive set:

```text
http://127.0.0.1:7242/Rjpcc3JjXFBhY2thZ2VcU2NyaXB0XFB5dGhvblxtdWx0aV9hZ2VudF90Y3A/blueprint-window/default
```

## Follow-Up Watch Points

- If POPO sends `思考中....` but no second message, check whether
  `blueprint.slots.message` returned `queued`, `cleared`, a `runId`, or an
  error.
- If group chat receives an Agent reply in Workbench but POPO does not receive
  it, inspect `agent_reply` and `popo_reply_sent` transcript events and their
  `messageId` / `fallback` fields.
- If session status shows `running` with no live run after restart, the next
  `list_blueprint_sessions()` / slot status read should mark stale
  `activeRunId` values idle when the run id is no longer in memory.
