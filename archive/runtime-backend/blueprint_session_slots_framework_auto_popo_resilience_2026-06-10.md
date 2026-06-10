# Blueprint Session Slots, Framework Auto Termination, and POPO Resilience

Date: 2026-06-10

## Summary

This archive records the runtime/backend work from the Blueprint session-slot
debugging thread on 2026-06-10.

The main product correction was to separate three concepts that had been
blurred together:

- A Blueprint session is the user conversation and durable transcript.
- A live run is one backend runtime instance that can serve one running
  session.
- A structure-level Blueprint slot is the pool for one
  `projectDir + blueprintStructureId + source/poolKey`.

The practical result is that Agents no longer own session termination, POPO
messages are not dropped when the main runtime is temporarily busy, and the
service can account for running and queued sessions per Blueprint structure.

## Session and Slot Model

`DesktopBlueprintRun` remains the live runtime instance model. It should not be
described to users as the structure-level run slot.

The user-facing Blueprint slot is now a summary over a pool key. The summary
tracks:

- `status`
- `activeSessionCount`
- `queuedSessionCount`
- `maxActiveSessions`
- `runningRunIds`
- `sessions`
- `poolKey`

The active-session limit is per Blueprint structure/pool, not a single global
limit shared by unrelated Blueprints. A pool can run up to three sessions at the
same time. Additional sessions are persisted as queued instead of failing with
an idle-slot error.

The scheduling rule is:

- If a session is already running, dispatch its message to the bound run.
- If it is not running and the pool has capacity, start or reuse a live run.
- If the pool already has three active runs, persist the session as queued and
  keep its pending message for later dispatch.
- When a running session ends, either reset/reuse the run for the oldest queued
  session in the same pool or close/recycle the run when there is no queued
  session.
- A reset failure marks the run unusable for idle reuse and the scheduler can
  start a fresh run when capacity allows.

## Framework-Owned Termination

The old `blueprint_terminate_session` MCP path was removed from Agent, Worker,
and Script contexts. This includes the start full Agent. Runtime Agents must
not decide whether a session should end.

The UI and internal service layer still keep explicit controls:

- `blueprint.sessions.terminate(sessionKey)` terminates one selected session.
- `blueprint.slots.terminate(projectDir, blueprintId/poolKey)` terminates all
  running and queued sessions in the structure-level slot.

The framework now owns automatic session termination. For a running session, it
can end the session with transcript reason `framework_auto_idle` only when all
of the required idle conditions are true:

- With no queued session in the same pool: Agent, Worker Agent, and script work
  have been idle for at least 10 minutes, and the session's last resident
  service call ended at least 10 minutes ago.
- With a queued session in the same pool: the same idle checks use 5 minutes so
  capacity can be released.
- A currently running resident service blocks auto termination.
- If the session has never called a resident service, the resident-service idle
  condition is treated as satisfied.

Automatic termination writes `session_terminated` but does not call
`runtime.end_run()` and does not mark the live run `completed`.

## MCP Boundary

The ordinary runtime MCP tool boundary after this work is:

- No Agent/Worker/Script context sees `blueprint_terminate_session`.
- No ordinary Agent context sees run-slot termination tools such as
  `runtime_end` or `blueprint_end`.
- `blueprint_reply_popo_user(content)` remains visible only to the POPO start
  full Agent and remains the normal way for that Agent to send the user-visible
  POPO reply.

`popo_session_termination_check` was removed/disabled as a prompt mechanism.
The framework no longer asks the Agent whether the POPO session should be
closed.

## POPO Callback Resilience

One live bug was that later POPO messages did not reach the Blueprint session.
The callback log showed repeated `/popo/callback` HTTP 500 responses around the
user message time, while the session transcript had no corresponding user
message.

The direct failure was:

```text
POPO config rejected for <auto>: timed out
```

The callback process had been synchronously querying the main Blueprint service
for `blueprint.popo.callbackConfig` before decrypting and forwarding the POPO
message. If the main service was busy or blocked, the callback returned 500 and
the user message was lost before `blueprint.slots.message` could be called.

`popo_agent_bot_run.py` now has a local fallback path:

- Read and normalize local `popo_robot_routes.json`.
- Use the local enabled robot config when the main service config RPC returns
  `SERVICE_UNAVAILABLE`, `SERVICE_ERROR`, or a timeout.
- Keep the main service config path as the preferred source when it responds.

This keeps POPO message ingestion alive while the main runtime is temporarily
unresponsive.

## Main Runtime Timeout Root Cause

The main runtime timeout was traced to `DesktopBlueprintService.agent_info()`.

The old implementation held the global service lock while calling slow runtime
inspection methods such as:

- runtime status snapshot
- agent stream event reads
- message journal reads
- framework-related status calls

The Agent information panel polls `agent_info()` frequently. When a runtime
call was slow or blocked, the service lock stayed held. POPO callback config
lookup also needed that service lock to inspect active run bindings, so it
could time out even though the process was still alive.

`agent_info()` now holds the lock only long enough to resolve the run and node,
then releases it before calling runtime methods.

Regression coverage was added with a blocking runtime stub: while
`status_snapshot()` is blocked, another thread can still acquire the service
lock.

## POPO Reply Task Completion

Another observed symptom was that after `blueprint_reply_popo_user`, the Agent
would produce maintenance English such as:

```text
Recording the current agent outcome for the framework and marking this task complete.
```

and then call `agent_task_status`.

The cause was that POPO reply delivery and task completion were treated as
separate obligations. After sending the POPO reply, the framework summary/task
status prompt could still fire.

`blueprint_mcp_runtime.py` now auto-records a completed task status after a
successful `blueprint_reply_popo_user` call. The status metadata marks it as a
framework-generated completion sourced from the POPO reply tool.

`agent_launch_context.py` also clarifies that when `blueprint_reply_popo_user`
is available and used, that tool call is the user-visible POPO reply and the
Agent should not add a second natural-language final reply.

## Main Files

- `desktop_blueprint_service.py`
- `blueprint_mcp_runtime.py`
- `agent_launch_context.py`
- `popo_agent_bot_run.py`
- `test_desktop_blueprint_service.py`
- `test_agent_runtime.py`
- `test_graph_control.py`

Key implementation points after this work:

- `DesktopBlueprintService.agent_info()` releases the service lock before
  runtime inspection calls.
- `popo_agent_bot_run.load_popo_config()` falls back to local route config on
  service timeout/unavailability.
- `_ordinary_blueprint_reply_popo_user()` auto-records completed task status
  after a successful POPO reply.
- Session context injection uses durable `user_message` and `agent_reply`
  transcript events, not `queued_message` or `popo_reply_sent`.

## Verification

Commands run from `F:\src\Package\Script\Python\multi_agent_tcp` during this
thread:

```powershell
python -m py_compile desktop_blueprint_service.py graph_runtime.py blueprint_mcp_runtime.py test_desktop_blueprint_service.py test_graph_control.py
python -m py_compile desktop_blueprint_service.py popo_agent_bot_run.py blueprint_mcp_runtime.py agent_launch_context.py test_desktop_blueprint_service.py
pytest test_desktop_blueprint_service.py -q -k "slot or session or terminate or popo or timeline or idle"
pytest test_desktop_blueprint_service.py -q -k "agent_info or popo or task_status or terminate or session or slot or timeline or idle"
pytest test_graph_control.py -q
pytest test_agent_runtime.py -q -k "task_status or summary"
```

Representative final results:

- Focused desktop service suite: `40 passed, 85 deselected`
- Graph control suite: `27 passed`
- Focused Agent runtime task-status/summary suite: `3 passed, 112 deselected`

## Packaged Plugin

The plugin was rebuilt and restarted multiple times with:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\package-gulicode-bp-plugin.ps1 -NoSmoke
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\start-gulicode-debug.ps1
```

After the final restart in this thread:

- Workbench URL:
  `http://127.0.0.1:3606/Rjpcc3JjXFBhY2thZ2VcU2NyaXB0XFB5dGhvblxtdWx0aV9hZ2VudF90Y3A/blueprint-window/default`
- Main service PID: `75196`
- POPO callback PID: `72632`
- Main service health returned HTTP 200.
- POPO callback health returned `ok`.

One startup produced a transient invalid
`logs\gulicode-bp-workbench-ready.json` because the service was restarted while
the readiness request was being reset by the peer. The service itself was
healthy after a direct MCP workbench start.

## Diagnostic Notes

For future debugging of "POPO sent but Blueprint did not receive":

1. Check `logs\gulicode-bp-popo.out.log` for `/popo/callback` status and
   callback config errors.
2. Check whether `blueprint.slots.message` was logged after the POPO callback.
3. Check the session transcript for `user_message`.
4. If the callback failed before `blueprint.slots.message`, inspect local route
   fallback and main service config lookup timing.

For future debugging of "main runtime config query timeout":

1. Check whether Agent information panel polling is active.
2. Inspect service calls that hold `DesktopBlueprintService._lock` while calling
   into live runtime methods.
3. Keep the lock around in-memory service state only; runtime calls should run
   outside the service lock.
