# Blueprint Full MCP Control + Real Codex Smoke - 2026-05-19

## Summary

The blueprint MCP layer moved from the first ordinary-Agent adoption pass to a
full run-scoped interface over `GraphRuntimeControlPlane`, with a clear split
between ordinary Agent tools and top-agent control tools.

The opt-in real Codex MCP smoke now passes through the full
`DesktopBlueprintService` live path. The smoke launches real Codex workers,
uses the generated private `CODEX_HOME` MCP config, calls
`framework_ordinary` tools, dispatches to a downstream reviewer Agent, and
verifies the downstream Agent reads the shared report through MCP.

## Implemented MCP Surface

Ordinary Agents receive only execution-scoped tools:

- Workspace write/read flow:
  `workspace_checkout`, `workspace_status`, `workspace_diff`,
  `workspace_submit`, `workspace_sync`, `workspace_publish`,
  `workspace_publish_file`, `workspace_read`, `workspace_list`,
  `workspace_list_archives`, and `workspace_extract_archive`.
- `agent_context` returns only the current ordinary Agent scoped framework
  context.
- `agent_dispatch` is bound to the active message context, outgoing batch, and
  required outgoing targets.
- `join_contribute` derives `source_node_id` from token scope so ordinary
  Agents cannot impersonate another node.

Top Agent / control receives orchestration and observation tools:

- Organization and top-agent context:
  `organization_read`, `top_agent_context`, `top_agent_start_session`,
  `top_agent_ask`, `top_agent_explain_status`, `top_agent_utterances`.
- Run lifecycle:
  `runtime_validate_start`, `runtime_start`, `runtime_status`,
  `runtime_end`, and permission-gated `runtime_execute_fixture`.
- Message and Agent control:
  `runtime_message_batch`, `runtime_message_stage`, `agent_context`,
  `agent_dispatch`.
- Join control:
  `join_create`, `join_contribute`.
- Read-only workspace inspection:
  `workspace_read`, `workspace_list`, `workspace_list_archives`,
  `workspace_extract_archive`.

Compatibility aliases remain:

- `runtime_explain_status` -> `top_agent_explain_status`
- `runtime_top_agent_utterances` -> `top_agent_utterances`

The old ambiguous `runtime_agent_context` path is no longer the semantic entry
point; use `top_agent_context` for the top Agent and `agent_context` for scoped
ordinary/control-side Agent context.

## Permission Boundary

Server-side permission checks are enforced, not just Codex `enabled_tools`.

- `ask`: `top_agent_start_session`, `top_agent_ask`
- `start`: `runtime_validate_start`, `runtime_start`, message batch/stage,
  control-side `agent_dispatch`, `join_create`, `join_contribute`
- `status`: organization/status/explain/agent context/top read-only workspace
- `end`: `runtime_end`
- `utterances`: `top_agent_utterances`
- `fixture`: `runtime_execute_fixture`; default top-agent permissions do not
  include this debug/test capability

Top Agent does not receive Workspace write/submit/publish tools. Ordinary
Agents do not receive global run lifecycle, organization, utterance, message
batch, or join-create tools.

## Runtime End

`runtime_end` now routes through the `DesktopBlueprintService` live-run close
callback when available, so MCP end tears down the desktop backend path and
closes MCP tokens. It falls back to `GraphRuntime.end_run()` only when there is
no desktop close callback.

## Real Codex Smoke Findings

The first opt-in real smoke exposed two non-framework issues:

1. Windows pytest temp directories can be inaccessible to Codex's command
   sandbox. The smoke now creates its project under
   `%LOCALAPPDATA%\multi_agent_tcp\real_codex_mcp` by default, with
   `MULTI_AGENT_TCP_REAL_CODEX_MCP_ROOT` available as an override.
2. Real Codex can emit very large stderr noise and large stdout/stderr result
   payloads. The worker diagnostics still preserve full stdout/stderr/final
   text on disk, but live stderr streaming and broker transport payloads are
   capped so the final worker reply reaches `GraphRuntime` instead of timing
   out behind debug output.

`MULTI_AGENT_TCP_KEEP_REAL_CODEX_MCP=1` can be used to retain the temporary
real-smoke project for inspection after a successful run.

## Verification

Latest focused verification from the repository root:

```powershell
$env:MULTI_AGENT_TCP_RUN_REAL_CODEX_MCP = "1"
python -m pytest -q test_desktop_blueprint_service.py::test_real_codex_live_blueprint_uses_mcp_for_workspace_and_dispatch_flow -vv
# 1 passed, 2 warnings in 135.84s

python -m pytest -q test_desktop_blueprint_service.py
# 29 passed, 1 skipped, 2 warnings

python -m pytest -q test_agent_runtime.py -k "not real_codex_cli"
# 77 passed, 3 deselected

python -m pytest -q test_graph_control.py test_workspace_api.py test_workspace_manager.py
# 59 passed
```

## Files Touched In This Pass

- `blueprint_mcp_runtime.py`
- `desktop_blueprint_service.py`
- `graph_runtime.py`
- `agent_launch_context.py`
- `codex_bridge.py`
- `adapters.py`
- `test_desktop_blueprint_service.py`
- `test_agent_runtime.py`

