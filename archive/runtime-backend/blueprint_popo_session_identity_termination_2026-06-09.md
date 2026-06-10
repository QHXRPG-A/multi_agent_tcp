# Blueprint POPO Session Identity and Termination

Date: 2026-06-09

## Summary

This archive records the runtime/backend refactor that separates direct
Workbench run-slot sessions from POPO-triggered Blueprint sessions and moves
POPO robot entry ownership onto the start full AgentNode.

The main product rules are now:

- Direct Workbench run-slot messages use the real session key
  `main+<blueprintId>` and no longer create synthetic `bps_...` session ids.
- POPO-triggered Blueprint sessions keep the previous POPO session-key
  construction.
- A Blueprint may enable POPO forwarding on at most one full AgentNode.
- The POPO-enabled full AgentNode must be the saved start AgentNode.
- A Blueprint whose saved start full AgentNode has POPO forwarding enabled is
  treated as a POPO Blueprint.
- POPO Blueprint session history is saved only for the start full Agent.
- `/new` clears the corresponding Blueprint session history without deleting
  the Blueprint session identity.

## Session Identity

Direct Workbench messages sent in the Blueprint run slot now resolve to:

```text
main+<blueprintId>
```

This path is intended for the user directly running the Blueprint from the
Workbench. It intentionally does not use the POPO `bps_...` identity path.

POPO callback messages continue to use the existing POPO identity derivation
based on the robot binding and incoming conversation identity. This preserves
separate POPO conversations while keeping the direct Workbench session stable
per Blueprint.

## POPO Entry Ownership

POPO robot configuration moved from blueprint-level `runtime.popo_entry` to the
full AgentNode model as `popo_entry`.

Runtime document loading still accepts legacy blueprint-level
`runtime.popo_entry` and migrates it to the saved start full Agent when possible.
This keeps older documents usable while making the start full Agent the source
of truth for POPO forwarding.

Validation now rejects documents where:

- More than one full AgentNode has `popo_entry.enabled = true`.
- The enabled POPO full AgentNode is not the saved start AgentNode.
- A POPO slot/message path needs robot config but the enabled entry is
  incomplete.

Normal non-POPO Blueprints do not require these restrictions beyond the saved
start-node checks needed for execution.

## `/new`

When a user sends `/new` through the corresponding Blueprint session entry,
the service clears that session's persisted transcript/context and keeps the
session identity available for future messages.

For an active direct slot session, the active run is cancelled as part of the
clear operation so later messages start from clean context instead of resuming
stale work.

## POPO Termination

POPO Blueprint sessions can now be closed by the framework asking the start full
Agent whether the session should terminate and save history.

The idle check requires all of the following:

- Every runtime Agent is idle.
- No Script Function Node call is currently running.
- No resident-service call is currently in flight for the Blueprint session.

`GraphRuntime` owns the idle decision and throttles termination prompts so the
start full Agent is not repeatedly asked while the same session remains idle.

`GraphRuntimeControlPlane` activity wrappers mark ScriptNode execution and
resident-service calls as active while the call is in progress. This covers the
current synchronous execution model, including transparent script execution and
`blueprint_service_call`.

Known boundary: resident services are long-lived plugin services. The runtime
currently tracks whether a session has an in-flight call to a service, not
whether a service has retained durable session ownership after returning. If a
future service starts asynchronous background work for a Blueprint session, it
should register explicit session activity with the runtime instead of relying
on the synchronous call wrapper.

## MCP Termination Tool

`blueprint_terminate_session` was added to the private MCP runtime as a tool
available only to the POPO start full Agent for its current run/session.

The tool is not exposed to arbitrary full Agents or public Codex MCP callers.
The token store enables it only for the start full Agent context, and the
DesktopBlueprintService callback performs the actual session termination.

This keeps the authority model narrow:

- Framework detects idle POPO Blueprint conditions.
- Framework asks the start full Agent.
- Start full Agent calls `blueprint_terminate_session` only when it decides the
  session should close.
- The framework saves the start-Agent conversation record and ends the session.

## Main Files

- `desktop_blueprint_service.py`
- `graph_runtime.py`
- `graph_control.py`
- `blueprint_mcp_runtime.py`
- `popo_agent_bot_run.py`
- `test_desktop_blueprint_service.py`
- `test_graph_control.py`

## Verification

Commands run from `F:\src\Package\Script\Python\multi_agent_tcp`:

```powershell
python -m py_compile desktop_blueprint_service.py graph_runtime.py graph_control.py blueprint_mcp_runtime.py popo_agent_bot_run.py test_desktop_blueprint_service.py test_graph_control.py
pytest test_desktop_blueprint_service.py -q -k "popo or slot or session_message or run_mcp_popo_termination_tool_is_start_agent_scoped or set_start_agent"
pytest test_graph_control.py -q
git diff --check
```

Results:

- Python compile passed.
- Focused desktop service/runtime tests passed: `18 passed, 84 deselected`.
- Graph control tests passed: `27 passed`.
- `git diff --check` passed with only existing CRLF warnings.

Plugin packaging and restart:

```powershell
python plugins\gulicode-bp\scripts\install_personal_plugin.py --force
.\start-gulicode-debug.ps1 -NoOpen -SkipPluginInstall
python plugins\gulicode-bp\scripts\smoke_standalone_plugin.py --plugin-root C:\Users\qiuhaoxuan\plugins\gulicode-bp --timeout 90
```

Post-restart health checks passed:

- `http://127.0.0.1:8787/api/health`
- `http://127.0.0.1:3040/mobile`
- `http://127.0.0.1:3040/console`
- `http://127.0.0.1:3100/health`
- active Workbench blueprint-window URL

The standalone plugin smoke reported `ok: true` and loaded the installed runtime
package from the personal plugin venv.
