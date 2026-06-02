# Blueprint Script Call MCP Runtime - 2026-05-31

## Summary

This pass changed Agent -> Script -> Agent execution from implicit transform
delivery to an explicit framework-mediated MCP workflow.

Ordinary Agents now call a generic `blueprint_script_call(function_name,
arguments, script_node_id?, batch_id?)` tool when the current message requires
a Script Function Node. The framework validates the current Agent and batch,
executes the Python `@blueprint_node` function, records script-call state, and
automatically delivers structured script output to downstream Agents.

## Implemented

MCP public tool:

1. Added ordinary MCP tool `blueprint_script_call`.
2. The tool is available to ordinary workspace Agents and message-only full
   Agents.
3. The tool requires an active message context with the current
   `outgoing_batch_id`.
4. Passing another batch id is rejected.
5. The requested function must be in the current batch's required script calls.
6. Function-name ambiguity requires `script_node_id`.
7. Tool calls are recorded in the MCP audit stream with sanitized arguments.

Batch script-call state:

1. `OutgoingMessageBatch` now carries `script_paths_by_target`.
2. `OutgoingMessageBatch` now carries `script_calls`.
3. Each script-call record stores script node id, script id, module path,
   function name, title, description, inputs, outputs, required downstream
   targets, delivered targets, caller, arguments, outputs, result, status, and
   error.
4. Runtime status/batch snapshots expose `script_calls` for UI and debugging.
5. Multiple Agents pointing at the same Script Node are tracked per source
   batch, not globally.

Control-plane execution:

1. Added `script.call` control-plane command.
2. Added `GraphRuntimeControlPlane.call_script_node(...)`.
3. Successful calls emit `ScriptNodeRunning` and `ScriptNodeCompleted`.
4. Failed calls emit `ScriptNodeFailed`, store the error, and do not deliver
   downstream Agent messages.
5. Repeated calls after completion return the existing result rather than
   re-running the user function.
6. `agent.dispatch` is rejected for targets behind a Script path, including
   no-op bodies, so Agents cannot bypass `blueprint_script_call`.

Automatic downstream delivery:

1. After a successful script call, the framework stages downstream Agent
   messages automatically.
2. The downstream body has type `blueprint_script_result`.
3. The body includes function name, script title, description, full arguments,
   `arguments_summary`, structured `outputs`, scalar `result`, script path
   results, source Agent/node/batch, and normal `framework_context`.
4. Paths containing multiple Script Nodes deliver only after every required
   script in that target path is completed.
5. Once every required target for a script receives delivery, that script record
   moves to `delivered`.

Idle reminder:

1. When a source Agent returns idle with pending required script calls, the
   runtime queues a top-priority reminder.
2. Reminder body type is `blueprint_script_call_reminder`.
3. Reminder content includes function name, title, description, inputs, outputs,
   `script_node_id`, `batch_id`, status, and downstream target ids.
4. Reminder context injects `required_script_calls` into
   `framework_context.message_envelope`.
5. Reminder duplication is suppressed per batch until call state changes.
6. Successful calls or failures reset script reminder keys.

Agent guidance:

1. Framework rules now tell ordinary Agents to call `blueprint_script_call`
   before dispatching when `required_script_calls` is non-empty.
2. Guidance states the framework will execute the script and deliver downstream
   output automatically.
3. Legacy automatic script transform helpers remain as implementation details,
   but the new Agent workflow is MCP-call driven.

## Files Changed

Runtime/backend:

1. `graph_runtime.py`
2. `graph_control.py`
3. `blueprint_mcp_runtime.py`
4. `agent_launch_context.py`

Tests:

1. `test_graph_control.py`
2. `test_agent_runtime.py`
3. `test_desktop_blueprint_service.py`

## Verification

Python compile:

```powershell
python -m py_compile graph_runtime.py graph_control.py blueprint_mcp_runtime.py agent_launch_context.py
```

Focused runtime/control tests:

```powershell
python -m pytest test_graph_control.py -q
python -m pytest test_desktop_blueprint_service.py -q
python -m pytest test_agent_runtime.py -q -k "empty_string_or_zero_marks_target_no_op_without_queueing or graph_runtime_reminds_idle_source_about_required_script_calls or outgoing_batch or outgoing_message or downstream or dispatch or script"
```

Observed result:

```text
test_graph_control.py: 13 passed
test_desktop_blueprint_service.py: 46 passed, 1 skipped
test_agent_runtime focused subset: 9 passed
```

Note:

`test_agent_runtime.py` full-file execution was attempted once and timed out
after roughly three minutes on this machine, so the verification uses focused
coverage for the changed runtime surfaces.

## Known Limits

1. The MCP tool currently executes required Script Nodes by function name and
   optional `script_node_id`; it does not support arbitrary script invocation.
2. `arguments_summary` is compact and intended for Agent context, not for exact
   replay. Full `arguments` remain in the message body and script-call record.
3. Multi-script path delivery waits for all script records in the target path,
   but richer per-edge output/input mapping is still future work.

## Follow-Up Queue

1. Add live desktop smoke coverage with a real Agent using
   `blueprint_script_call` once worker cost is acceptable.
2. Surface `script_calls` state more directly in the Blueprint runtime UI.
3. Consider UI affordances for retrying failed script calls from the runtime
   panel.

## Skill/Archive Files

Installed skill:

```text
C:\Users\13429\.codex\skills\multi-agent-tcp\archive\runtime-backend\blueprint_script_call_mcp_runtime_2026-05-31.md
```

Repository snapshot:

```text
KM_docs/skills-snapshot/archive/runtime-backend/blueprint_script_call_mcp_runtime_2026-05-31.md
```
