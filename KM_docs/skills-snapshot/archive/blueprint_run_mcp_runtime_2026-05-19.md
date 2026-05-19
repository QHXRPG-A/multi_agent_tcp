# Blueprint Run MCP Runtime - 2026-05-19

## Summary

Blueprint live runs now have a first-pass run-scoped MCP adapter. Each live
`desktop-blueprint-service` run starts one local ASGI/uvicorn MCP runtime handle
with two mounted FastMCP servers:

- `framework_ordinary` for ordinary AgentNodes.
- `framework_control` for the top-agent/control surface.

The MCP layer is intentionally a protocol adapter. It does not reimplement
workspace, dispatch, status, or lifecycle semantics. Workspace tools call
`WorkspaceRPCServer`, ordinary dispatch calls
`GraphRuntimeControlPlane.dispatch_agent_message()`, and control tools call the
existing runtime/control-plane APIs.

## Completed

1. Added `blueprint_mcp_runtime.py`.
2. Added `RunMCPRuntimeHandle` with:
   - run-local port and URLs;
   - Starlette app;
   - ordinary/control FastMCP servers;
   - uvicorn server thread;
   - token store;
   - summary and close lifecycle.
3. Added Starlette bearer middleware for MCP HTTP requests.
4. Added opaque token scopes for ordinary and control MCP servers.
5. Bound `Mcp-Session-Id` to token scope to prevent session reuse with another
   token.
6. Added ordinary MCP tools:
   - `workspace_checkout`
   - `workspace_status`
   - `workspace_diff`
   - `workspace_submit`
   - `workspace_sync`
   - `workspace_publish`
   - `workspace_publish_file`
   - `workspace_read`
   - `workspace_list`
   - `workspace_list_archives`
   - `workspace_extract_archive`
   - `agent_dispatch`
7. Added control MCP tools:
   - `runtime_status`
   - `runtime_explain_status`
   - `runtime_end`
   - `runtime_agent_context`
   - `runtime_top_agent_utterances`
8. Wired live `DesktopBlueprintRun` lifecycle to start and close the MCP
   runtime handle.
9. Added MCP safe summary to `DesktopBlueprintRun.summary()`.
10. Extended private Codex materialization:
    - writes `[mcp_servers.framework_ordinary]` or
      `[mcp_servers.framework_control]` into private `CODEX_HOME/config.toml`;
    - injects bearer token through env var;
    - exposes only safe MCP summary in `prompt_execution_context`;
    - keeps framework skill/rule injection.
11. Updated `framework-agent-runtime` to be MCP-first while keeping
    Workspace API CLI fallback/debug instructions.
12. Added active-message context refresh from `GraphRuntime` before dispatching
    each Agent message.
13. Added MCP `publish_file` path validation before Workspace RPC:
    - allows private checkout, private scratch, and generated artifact temp dir;
    - rejects path traversal, drive/URI separators, arbitrary absolute paths,
      other private dirs, and symlink/junction escapes.
14. Added explicit MCP runtime dependencies to `pyproject.toml`:
    `mcp>=1,<2`, `uvicorn>=0.30,<1`, `starlette>=0.37,<1`, and
    `httpx>=0.27,<1`.
15. Added MCP tool-call audit events as `framework_mcp_tool_call` with safe
    argument summaries. The audit does not record bearer tokens, RPC tokens,
    private checkout paths, private Codex home paths, or private absolute
    project paths.
16. Added Codex diagnostics capture for live smoke failures:
    JSONL events, stdout/stderr chunks, elapsed time, and extracted final text
    are written under the private Agent diagnostics directory.
17. Added deterministic live MCP flow tests and made the real Codex MCP smoke
    opt-in behind `MULTI_AGENT_TCP_RUN_REAL_CODEX_MCP=1`.
18. Closed the real Codex MCP adoption gap by writing `enabled_tools` and
    per-tool `approval_mode = "approve"` into the private run-scoped
    `CODEX_HOME/config.toml`. Without this approval config, `codex exec` JSONL
    showed `mcp_tool_call` followed by `user cancelled MCP tool call` before
    the request reached the framework MCP server.

## Files Touched

- `blueprint_mcp_runtime.py`
- `desktop_blueprint_service.py`
- `agent_launch_context.py`
- `graph_runtime.py`
- `pyproject.toml`
- `codex_bridge.py`
- `test_desktop_blueprint_service.py`
- `test_agent_runtime.py`

## Verification

Passed during the phase-1 comprehensive follow-up:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp

python -m pip install -e .

python -m py_compile __init__.py blueprint_mcp_runtime.py agent_launch_context.py graph_runtime.py graph_control.py workspace_rpc.py desktop_blueprint_service.py test_desktop_blueprint_service.py test_agent_runtime.py test_workspace_api.py test_workspace_manager.py codex_bridge.py

pytest -q test_desktop_blueprint_service.py test_agent_runtime.py test_workspace_api.py test_workspace_manager.py
# 146 passed, 1 skipped, 2 warnings
```

Real Codex MCP acceptance follow-up passed after the per-tool approval fix:

```powershell
pytest -q test_desktop_blueprint_service.py::test_private_codex_mcp_config_enables_tools_and_clears_stale_nested_tables test_desktop_blueprint_service.py::test_codex_jsonl_event_to_agent_stream_events_maps_mcp_tool_calls -vv
# 2 passed

pytest -q test_desktop_blueprint_service.py::test_blueprint_service_live_mode_prestarts_all_agents_with_private_context -vv
# 1 passed, 2 warnings

pytest -q test_desktop_blueprint_service.py::test_live_blueprint_mcp_workspace_dispatch_flow_with_agent_backend -vv
# 1 passed, 2 warnings

$env:MULTI_AGENT_TCP_RUN_REAL_CODEX_MCP = "1"
pytest -q test_desktop_blueprint_service.py::test_real_codex_live_blueprint_uses_mcp_for_workspace_and_dispatch_flow -vv
# 1 passed, 2 warnings in 292.52s
```

## Phase-1 Comprehensive Test Snapshot

Five requested acceptance points:

1. MCP checkout/commit-style file flow: framework, deterministic live MCP
   client, and real Codex through the full `DesktopBlueprintService` live path
   pass for checkout/status/diff/submit. Acceptance uses `workspace_submit`
   accepted changeset, not direct `git commit`.
2. Behavior boundaries after MCP: deterministic framework tests cover private
   checkout write allowance, Workspace RPC path validation, and
   `publish_file` rejection for traversal, drive-relative paths, arbitrary
   absolute paths, and symlink/junction escape. Extending the real
   MCP-enabled Codex smoke with direct project/shared write denial remains in
   the follow-up queue.
3. Skill/rule injection: private `CODEX_HOME/config.toml`, framework skill,
   selected business skill, selected business rule, and checkout/base
   `AGENTS.md` are materialized. Prompt-facing MCP context only exposes safe
   server/tool summaries.
4. Agent-to-agent information flow: deterministic MCP tests cover
   `agent_dispatch`, required-target checks, message journal staging/queueing,
   and downstream shared-reference reads. Natural language replies remain
   private utterances unless explicitly dispatched.
5. Full framework flow with real Agent logs: `DesktopBlueprintService` live
   start path reaches `WorkspaceRPCServer -> GraphRuntime/ControlPlane -> MCP
   handle -> private CODEX_HOME -> control.start_run()`. The real Codex smoke
   now shows ordinary MCP tool invocation in both Codex JSONL and
   `framework_mcp_tool_call` manifest entries.

## Current Caveats

1. `runtime_end` through control MCP calls `runtime.end_run()` and invalidates
   MCP tokens, but it does not yet route through `DesktopBlueprintService` to
   perform the same backend teardown path as `blueprint.end`. Keep this in the
   remaining P0 queue.
2. `runtime_message_batch`, `runtime_message_stage`, and join control MCP tools
   are intentionally not exposed in v1. Keep them deferred until ordinary
   `agent_dispatch` behavior is stable in real Codex runs.
3. MCP token scope uses mutable current message context. The default path does
   not scan message journal for `batch_id`; that is intentional.

## Next High-Priority Work

P0 real Codex MCP adoption is closed. The accepted closure command is:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp
$env:MULTI_AGENT_TCP_RUN_REAL_CODEX_MCP = "1"
pytest -q test_desktop_blueprint_service.py::test_real_codex_live_blueprint_uses_mcp_for_workspace_and_dispatch_flow -vv
```

Accepted evidence included:

1. Codex JSONL/runtime logs show MCP tool calls, not fallback
   `python -m multi_agent_tcp.workspace_api` CLI commands.
2. `run.shared/manifest.json` had `framework_mcp_tool_call` entries for
   workspace checkout/status/diff/submit/publish/publish_file/read and
   `agent_dispatch`.
3. Workspace API audit still appeared as `workspace_api_call` where MCP tools
   cross into Workspace RPC.
4. The project file contained the submit marker exactly once after
   `workspace_submit`; private checkout writes, MCP publish, and MCP
   publish_file were accepted paths.
5. Final/report text contained framework skill, business skill, and rule
   markers.

Remaining P0 queue:

1. Reproduce the original timeout scenario with MCP enabled:
   - confirm whether Codex streaming continues after an Agent reply;
   - verify subsequent user panel messages refresh active message context;
   - inspect logs for MCP tool calls and Codex JSONL completion events.
2. Harden lifecycle:
   - make control MCP `runtime_end` go through the desktop service close path,
     or document it as status-only until the control surface owns cleanup.
3. Add negative tests for HTTP requests without bearer token and for
   `Mcp-Session-Id` reuse across ordinary/control endpoints.
4. Decide whether top-agent should receive only `framework_control` or both
   control and ordinary MCP servers in its private `CODEX_HOME`.
5. Keep framework skill/rule injection. MCP is the tool protocol; skill/rules
   remain the behavioral contract that tells Agents when and how to call tools.

## Handoff Pointers

Start with these files:

- `blueprint_mcp_runtime.py`
- `desktop_blueprint_service.py`
- `agent_launch_context.py`
- `graph_runtime.py`
- `test_desktop_blueprint_service.py`

For MCP SDK shape, current Codex CLI config was verified as:

```toml
[mcp_servers.framework_ordinary]
enabled = true
url = "http://127.0.0.1:<port>/ordinary/mcp"
bearer_token_env_var = "MULTI_AGENT_MCP_ORDINARY_TOKEN"
enabled_tools = ["workspace_checkout", "...", "agent_dispatch"]

[mcp_servers.framework_ordinary.tools.workspace_checkout]
approval_mode = "approve"
```

Do not expose bearer tokens, workspace RPC tokens, private checkout paths, or
raw RPC URLs in prompt-facing context.
