# Blueprint Session `/stop` User Command

Date: 2026-06-12

## Summary

This archive records the 2026-06-12 runtime/backend change that adds a user
command for force-ending the current Blueprint session:

```text
/stop
```

The command is handled through the existing `blueprint.sessions.message`
entrypoint used by both Workbench Runtime panel messages and POPO callback
messages.

The command is intentionally not a new public MCP/API surface. It is a session
message control command, matching the existing `/new` pattern.

## Runtime Behavior

`DesktopBlueprintService.message_blueprint_session()` now recognizes exact,
trimmed, lowercase `/stop` after resolving the session key and migrating legacy
POPO session keys, but before normal user-message persistence, Agent queueing,
or `/excel-log` handling.

Behavior:

- Active session: close the session's bound live run through the existing
  `terminate_blueprint_session()` / `_terminate_active_blueprint_session()`
  path.
- Existing idle session: mark the session `terminated` and append a
  `session_terminated` transcript event.
- Missing session: return a no-op success with `alreadyStopped: true`, without
  creating a session file, transcript file, live run, or Agent dispatch.

Successful active/idle responses include:

```json
{
  "stopped": true,
  "message": "已结束当前会话"
}
```

Missing-session no-op responses include:

```json
{
  "stopped": true,
  "alreadyStopped": true,
  "message": "当前没有正在运行的会话"
}
```

The command preserves session history. It does not clear the transcript and does
not delete the session. Future normal messages can still reuse the same session
key and start a new live run instance according to the current
session-instance model.

## POPO Behavior

`popo_agent_bot_run.call_blueprint()` now treats `stopped` or `terminated`
session-message responses as direct user-visible confirmations.

Default POPO reply:

```text
已结束当前会话
```

Existing direct command behavior is preserved:

- `/new` returns `已开启新会话`
- `/excel-log ...` returns the rendered log text
- queued normal messages remain silent

## Test Coverage

Focused tests added or updated:

- active `/stop` terminates the session and does not dispatch `/stop` to an
  Agent
- idle existing `/stop` marks the session terminated without starting a run
- missing-session `/stop` returns no-op success without creating files
- POPO `/stop` calls `blueprint.sessions.message` and returns
  `已结束当前会话`
- stale session-instance tests were aligned with the current MCP session-history
  tool naming and fake live-run helper

Verification from this thread:

```powershell
python -m py_compile desktop_blueprint_service.py popo_agent_bot_run.py
pytest -q test_desktop_blueprint_service.py -k "session_message or popo or idle or stop"
pytest -q test_popo_agent_bot_run.py
git diff --check -- desktop_blueprint_service.py popo_agent_bot_run.py test_desktop_blueprint_service.py test_popo_agent_bot_run.py
```

Results:

- `py_compile`: passed
- `test_desktop_blueprint_service.py -k "session_message or popo or idle or stop"`:
  41 passed, 5 skipped, 124 deselected
- `test_popo_agent_bot_run.py`: 5 passed
- `git diff --check`: passed; Git only reported existing LF/CRLF working-copy
  warnings

## Plugin State

No plugin mirror refresh, packaged plugin reinstall, Workbench bundle rebuild,
or singleton-service restart was performed in this change. The implementation
only touched backend/session-message behavior and POPO reply handling.
