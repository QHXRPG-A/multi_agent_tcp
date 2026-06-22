# Blueprint Session Instances, Slot Removal, and Plugin Restart

Date: 2026-06-11

## Summary

This archive records the 2026-06-11 runtime/backend change that removed the
Blueprint run-slot model and made a Blueprint session map directly to one live
run instance.

The new contract is:

- `blueprint.sessions.message` is the only message entrypoint for UI and POPO.
- If a session already has an active run, the message is queued into that run.
- If a session has no active run, the service creates a new live run instance,
  binds it to the session, then queues the message.
- Different POPO sessions create different live run instances without a
  framework-imposed three-session cap.
- Session terminate, `/new`, and auto idle cleanup directly close the bound run.
- The 10 minute idle cleanup rule is retained and still checks pending work,
  Agent state, Script work, and resident-service activity.

There is no longer an idle slot pool, queued-session dispatcher, slot reset, or
run reuse path.

## Removed Slot API Surface

The public/internal command surface no longer exposes:

```text
blueprint.slots.start
blueprint.slots.status
blueprint.slots.terminate
blueprint.slots.message
```

These commands were removed from:

- `DesktopBlueprintService.handle_request`
- the `gulicode-bp` MCP command allowlists
- the POPO callback path
- the Workbench/Electron platform bridge

The active POPO callback now calls:

```text
blueprint.sessions.message
```

The installed plugin runtime was checked after reinstall:

```text
has_start_blueprint_slot False
has_message_blueprint_slot False
has_message_blueprint_session True
```

The installed MCP allowlist contains `blueprint.sessions.message` and no
`blueprint.slots.*` entries.

## POPO Routing Semantics

Robot-to-Blueprint binding discovery is still preserved:

- existing POPO sessions are preferred when the incoming identity matches
- otherwise the currently opened Workbench Blueprint is used when it is a valid
  candidate binding
- otherwise multi-Blueprint ambiguity still returns a conflict with candidate
  details

The old "unique idle slot" selection rule was removed because there are no
idle slots. A new POPO session simply creates a new live run instance for the
resolved Blueprint session.

## Run Summary and Legacy Data

Run summaries no longer expose slot-oriented fields such as slot status, slot
pool key, or bound session key. Durable sessions still retain:

- `sessionKey`
- `activeRunId`
- `lastRunId`
- `status`
- `messageCount`
- `transcript`
- POPO identity metadata when applicable

Legacy persisted `poolKey`, queued-message, and slot-related fields are tolerated
when reading older sessions, but they are no longer part of the runtime model.

## Tests

Focused verification from this thread:

```powershell
python -m py_compile desktop_blueprint_service.py popo_agent_bot_run.py plugins/gulicode-bp/mcp/gulicode_bp_mcp.py
pytest -q test_desktop_blueprint_service.py -k "session or popo or idle or mcp"
pytest -q test_desktop_blueprint_service.py -k "session or popo or idle or mcp or slots"
pytest -q test_popo_agent_bot_run.py
```

Final results:

- `test_desktop_blueprint_service.py -k "session or popo or idle or mcp"`:
  65 passed, 11 skipped, 84 deselected
- `test_desktop_blueprint_service.py -k "session or popo or idle or mcp or slots"`:
  66 passed, 11 skipped, 83 deselected
- `test_popo_agent_bot_run.py`: 4 passed

`git diff --check` passed for the touched files.

## Plugin Reinstall and Restart

The first reinstall attempt found a corrupted personal plugin runtime venv:

```text
ModuleNotFoundError: No module named 'pywin32_bootstrap'
ModuleNotFoundError: No module named 'pywintypes'
```

Repair steps:

1. Stopped old plugin-owned Python processes.
2. Stopped stale `multi_agent_tcp broker` / `multi_agent_tcp agent` worker
   processes that held venv log files open.
3. Removed the damaged personal plugin `.runtime\venv`.
4. Re-ran plugin install and runtime bootstrap.
5. Restarted the plugin stack without rebuilding the already-built web bundle.

Successful restart command:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\restart-gulicode-bp-plugin.ps1 -SkipWebBuild
```

Health checks returned HTTP 200 for:

- Collaboration: `http://127.0.0.1:8787/api/health`
- POPO callback: `http://127.0.0.1:3100/health`
- Workbench:
  `http://127.0.0.1:6750/Rjpcc3JjXFBhY2thZ2VcU2NyaXB0XFB5dGhvblxtdWx0aV9hZ2VudF90Y3A/blueprint-window/default`

Observed runtime state after restart:

- singleton service pid: `65896`
- singleton service URL: `http://127.0.0.1:7029`
- Workbench URL:
  `http://127.0.0.1:6750/Rjpcc3JjXFBhY2thZ2VcU2NyaXB0XFB5dGhvblxtdWx0aV9hZ2VudF90Y3A/blueprint-window/default`

Restarting the plugin invalidated the already-loaded MCP transport in the
current Codex thread. The new HTTP services were healthy, but Codex may need a
plugin/MCP reconnect before in-thread MCP tools work again.

## Main Files

- `desktop_blueprint_service.py`
- `popo_agent_bot_run.py`
- `plugins/gulicode-bp/mcp/gulicode_bp_mcp.py`
- `test_desktop_blueprint_service.py`
- `test_popo_agent_bot_run.py`
