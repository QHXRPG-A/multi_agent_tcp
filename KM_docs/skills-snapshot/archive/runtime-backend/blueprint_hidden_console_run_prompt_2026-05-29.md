# Blueprint Hidden Console and Run Prompt Injection - 2026-05-29

## Summary

This pass changed Blueprint runtime process launch behavior on Windows and added
per-run Agent prompt injection support.

Blueprint startup no longer opens visible `cmd` windows for spawned runtime or
worker processes. Agent-level `run_prompt` now travels through the runtime graph
and is prepended to the first message sent to each Agent during a run.

## Implemented

Process launch:

1. Added `_proc_utils.hidden_subprocess_kwargs(detached=False)` as the common
   Windows subprocess helper.
2. Replaced visible `CREATE_NEW_CONSOLE` worker launches with hidden process
   flags.
3. Applied hidden launch kwargs to Codex and Codex adapter subprocesses.
4. Kept non-Windows launch behavior unchanged.

Runtime graph:

1. Added `AgentNode.run_prompt` with `from_dict` / `to_dict` support.
2. Added per-`AgentInstance` run-prompt injection state.
3. Centralized injection in `_dispatch_agent_message` so queued start messages
   and normal dispatches share the same behavior.
4. Prepends non-empty `run_prompt` once to the first dispatched message body for
   that Agent instance in a run.
5. Resets injection state when run completion tracking is configured.
6. Preserved existing `prompt_via_file` behavior because the injected prompt is
   part of the normal first message body before CLI adapter handling.

## Injection Format

The runtime prepends the run prompt before the original message body using the
fixed header:

```text
# Agent Run Prompt
```

The original message body follows after a blank-line separator. Empty
`run_prompt` values are ignored.

## Files Changed

Runtime/backend:

1. `_proc_utils.py`
2. `__main__.py`
3. `cluster.py`
4. `codex_bridge.py`
5. `codex_bridge.py`
6. `graph_runtime.py`
7. `test_agent_runtime.py`
8. `test_graph_control.py`

## Verification

Python:

```powershell
python -m pytest test_graph_control.py -q
# 10 passed

python -m pytest test_agent_runtime.py::test_hidden_subprocess_kwargs_suppresses_windows_console test_agent_runtime.py::test_cluster_spawn_hides_worker_console_windows -q
# 2 passed
```

Focused run-prompt tests covered:

1. `AgentNode.from_dict` / `to_dict` for `run_prompt`.
2. First message injection once per Agent per run.
3. No repeated injection on later messages in the same run.
4. Independent injection for multiple Agents.
5. Queued start messages after dispatch.

The broader command below still has unrelated pre-existing private checkout
failures in `test_agent_runtime.py`:

```powershell
python -m pytest test_graph_control.py test_agent_runtime.py -q -k "not real_codex"
```

Failing tests observed before archive:

1. `test_blueprint_workspace_application_uses_private_checkout_and_rpc_context`
2. `test_graph_runtime_auto_private_context_uses_project_reference_mode`

## Skill/Archive Files

Installed skill:

```text
C:\Users\qiuhaoxuan\.codex\skills\multi-agent-tcp\archive\runtime-backend\blueprint_hidden_console_run_prompt_2026-05-29.md
```

Repository snapshot:

```text
KM_docs/skills-snapshot/archive/runtime-backend/blueprint_hidden_console_run_prompt_2026-05-29.md
```
