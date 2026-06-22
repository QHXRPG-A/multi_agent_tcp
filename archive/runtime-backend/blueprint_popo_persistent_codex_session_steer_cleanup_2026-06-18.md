# Blueprint POPO Persistent Codex Session, Steer, and Restart Cleanup

Date: 2026-06-18

## Summary

This archive records the persistent POPO start-Agent session work and the
follow-up runtime cleanup fixes.

The fixed contract is:

- A POPO `sessionKey` with a live active run reuses the same start Agent worker
  and the same Codex app-server thread.
- POPO-bound saved start full Agent nodes default to the new Codex app-server
  backend. Ordinary Agents and Worker Agents keep the existing `codex exec`
  path unless explicitly configured otherwise.
- The first activation of a POPO session injects
  `_build_blueprint_session_context()` history. Later messages in the same
  active run send only the current POPO input, attachments, and minimal session
  metadata.
- If the Agent is busy and the adapter has an active Codex turn, incoming POPO
  text is first sent through `turn/steer`. If steer is unavailable or rejected,
  the message falls back to the existing Agent queue and is delivered after the
  current turn.
- The POPO callback no longer sends the framework-owned
  `blueprint run still processing` timeout status to the POPO user while a
  persistent run is active.
- Restarting the plugin intentionally ends live in-memory session continuity.
  The restart path now kills plugin-owned cluster broker/agent process trees so
  their child `codex app-server` processes cannot survive as orphans.

Use this record when:

- a POPO user says every message talks to a different Agent
- later POPO turns repeat `[Recent BlueprintSession Messages]`
- runtime logs show per-message `codex exec` for a POPO start Agent
- `turn/steer` does not inject an in-flight POPO message
- a POPO user receives `蓝图运行仍在处理中`
- `blueprint.sessions.message` returns missing or inconsistent
  `sameAgentSession`, `conversationBackend`, `conversationId`, `steered`,
  `queued`, or `fallbackReason`
- plugin restart leaves `multi_agent_tcp_cluster` broker/agent processes or
  `codex app-server --listen stdio://` running after the new service starts

## Main Files

- `codex_app_server_bridge.py`
- `adapters.py`
- `broker.py`
- `client.py`
- `cluster.py`
- `graph_runtime.py`
- `desktop_blueprint_service.py`
- `popo_agent_bot_run.py`
- `restart-gulicode-bp-plugin.ps1`
- `test_agent_runtime.py`
- `test_desktop_blueprint_service.py`
- `test_popo_agent_bot_run.py`

## Codex App-Server Backend

`CodexAppServerAdapter` keeps one long-lived
`codex app-server --listen stdio://` process inside the worker lifetime.

On the first message it calls:

```text
thread/start
turn/start
```

and stores the Codex `threadId` plus the active `turnId`. Later idle turns call
`turn/start` against the same `threadId`; they do not start `codex exec`.

The common adapter surface now exposes:

```text
conversation_backend
conversation_id
active_turn_id
supports_steer
steer_message(message, metadata)
```

The app-server backend is selected through adapter options:

```json
{
  "codex_backend": "app_server",
  "conversation_backend": "codex_app_server"
}
```

For POPO saved start full Agents, `DesktopBlueprintService` sets these options
by default. Non-POPO Agent launches and Worker Agent launches keep the previous
`exec` backend to limit blast radius.

## POPO Session Routing

The session mapping is:

```text
sessionKey -> activeRunId -> startNodeId -> worker agent_id -> Codex threadId
```

When `blueprint.sessions.message` sees an existing live active run for the same
session, it does not create a new run. It routes the message to the existing
start node and reports diagnostics such as:

```text
sameAgentSession = true
conversationBackend = codex_app_server
conversationId = <Codex threadId>
historyContextInjected = false
```

For a new active run, or after `/new`, `/stop`, idle cleanup, or plugin restart,
the first message builds the normal POPO session context and injects recent
`transcript.jsonl` history. During an active run, the Codex app-server thread is
the authoritative context source.

The persistent session smoke for qiuhaoxuan used:

```text
sessionKey = bps_popo_qiuhaoxuan-corp.netease.com+fill-planning-form
runId = run-3fc55991d505
conversationBackend = codex_app_server
threadId = 019ed5f2-68c6-7ec1-aa9d-6495f7e8d526
```

The observed transcript behavior was:

- first POPO message: `historyContextInjected = true`
- later normal POPO messages: `historyContextInjected = false`
- in-flight POPO message: `type = steered_message`

## In-Flight Steer

When the Agent is running and the adapter reports an active turn,
`GraphRuntime` calls `steer_message(...)`, which maps to Codex:

```text
turn/steer(threadId, expectedTurnId, input)
```

Successful steer records:

```text
framework.message.steered
```

Rejected steer records:

```text
framework.message.steer_rejected
```

The fallback path is intentionally conservative. If the app-server disconnects,
the active turn id does not match, the turn is not steerable, or the adapter is
not a steer-capable backend, the message is queued through the existing
`GraphRuntime.queue_agent_message()` path and is sent to the same Codex thread
after the current turn finishes.

## POPO Callback Timeout Reply

`popo_agent_bot_run.py` previously returned a direct framework status message
when `call_blueprint()` waited for a reply and the run was still active:

```text
蓝图运行仍在处理中。
会话：...
运行：...
状态：running
```

Persistent sessions make `running` a normal state, so this message should not
be sent to POPO. The callback now logs:

```text
[BLUEPRINT] run still active after callback wait; no direct POPO status reply
```

and returns an empty string. `handle_and_reply()` therefore sends nothing to
POPO for that timeout case. `/new`, `/stop`, `/help`, `/excel-log`, errors, and
terminal run summaries keep their existing direct-reply behavior.

## Restart Cleanup

Plugin restart cannot preserve active in-memory Codex app-server threads. After
a restart, the POPO session should be treated as idle; the next POPO message
creates a fresh run and injects history from `transcript.jsonl`.

The problem found during the qiuhaoxuan smoke was worse than expected: the new
service no longer knew about `run-3fc55991d505`, but old plugin-owned worker
processes and their child `codex app-server` process were still alive.

`restart-gulicode-bp-plugin.ps1` now:

- recognizes plugin-owned `-m multi_agent_tcp broker` and
  `-m multi_agent_tcp agent` processes when their command line contains both
  the installed plugin root and `multi_agent_tcp_cluster`
- groups matched processes by root process so child targets are not redundantly
  killed
- kills root process trees with `taskkill /T /F` on Windows
- treats already-missing PIDs as success, because an earlier root tree may have
  already removed them

This keeps the restart cleanup scoped to the installed `gulicode-bp` runtime and
avoids killing ordinary Codex desktop processes.

## Verification

Syntax and targeted callback tests:

```powershell
py -3.13 -m py_compile popo_agent_bot_run.py test_popo_agent_bot_run.py
py -3.13 -m pytest test_popo_agent_bot_run.py -q
```

Observed result:

```text
20 passed
```

The persistent POPO smoke verified one active run, one worker Agent, and one
Codex app-server thread across multiple qiuhaoxuan POPO messages, with the
fourth message steered into the active turn.

Restart cleanup was verified with:

```powershell
F:\src\Package\Script\Python\multi_agent_tcp\restart-gulicode-bp-plugin.cmd -NoOpen -ProjectDir F:\src\Package\Script\Python\multi_agent_tcp -BlueprintId fill-planning-form -HealthTimeoutSeconds 120
```

Observed result:

```text
stopping 8 plugin-owned Python process(es), 2 root tree(s)
collaboration = 200 http://127.0.0.1:8787/api/health
popo = 200 http://127.0.0.1:3100/health
health ok = True
```

After the restart, a process scan for:

```text
multi_agent_tcp_cluster
codex app-server
app-server --listen stdio://
```

found no residual plugin worker or Codex app-server process.

