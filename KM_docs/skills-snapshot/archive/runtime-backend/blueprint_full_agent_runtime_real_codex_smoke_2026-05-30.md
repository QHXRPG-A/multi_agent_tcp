# Blueprint Full Agent Runtime and Real Codex Smoke - 2026-05-30

## Summary

This pass added a full CLI `Agent` runtime path alongside the existing
framework-managed `Worker Agent`.

Full `Agent` nodes skip private checkout and shared-workspace rewriting. They
launch directly in `project_workdir`, can opt into dangerous Codex access, and
only receive framework message MCP tools when message tools are enabled.

The original Agent behavior remains available as `worker_agent`: private
checkout, shared workspace, workspace MCP tools, and the controlled submit flow
are preserved.

## Implemented

Runtime model:

1. `AgentNode` serializes `node_type` and `access_policy`.
2. Missing `node_type` defaults to `worker_agent` for old blueprint documents.
3. `agent` and `worker_agent` share the existing `AgentNode` Python class to
   keep compatibility with graph/runtime code.

Launch behavior:

1. `GraphRuntime._node_for_launch()` sends `worker_agent` through
   `materialize_private_agent_context()` as before.
2. Full `agent` nodes use the new full-agent launch context path and keep cwd
   at the project root.
3. Full `agent` nodes do not receive workspace context env vars or workspace
   RPC tokens.
4. Full `agent` nodes default to Codex and, when allowed by access policy,
   launch with `danger-full-access`, `dangerous_access=true`, and
   `--dangerously-bypass-approvals-and-sandbox`.
5. `codex_bridge.py` now only permits dangerous/bypass sandbox behavior for
   `node_type="agent"` when the relevant policy switches are enabled.
6. `worker_agent` continues to reject dangerous access arguments.

MCP scope:

1. `blueprint_mcp_runtime.py` now creates message-only ordinary scopes without
   a workspace RPC token for full `agent` nodes.
2. Message-only scopes expose only:
   `agent_dispatch`, `agent_context`, `agent_task_status`, and
   `join_contribute`.
3. Workspace MCP tools remain reserved for framework-managed Worker Agents.

Framework messages:

1. Full `Agent` nodes receive the standard framework message context in
   `body.context.framework_context`.
2. The context includes agent identity, graph organization, downstream agents,
   and `message_envelope.outgoing_batch_id`.
3. A real `agent_dispatch` MCP call from a full Agent queues the downstream
   Worker Agent message with standard `body.context.framework_context`.

## Files Changed

Runtime/backend:

1. `graph_runtime.py`
2. `agent_launch_context.py`
3. `blueprint_mcp_runtime.py`
4. `codex_bridge.py`

Tests:

1. `test_agent_runtime.py`
2. `test_desktop_blueprint_service.py`

## Verification

Focused Python tests:

```powershell
python -m pytest test_agent_runtime.py::test_full_agent_receives_standard_context_and_dispatches_via_message_mcp test_agent_runtime.py::test_graph_runtime_full_agent_skips_private_workspace test_desktop_blueprint_service.py::test_run_mcp_provisions_full_agent_message_only_context test_desktop_blueprint_service.py::test_run_mcp_streamable_http_tools_are_split_by_token -q
```

Observed result:

```text
4 passed in 2.13s
```

Real Codex direct probe:

1. PowerShell cannot invoke `codex.ps1` because local script execution is
   disabled.
2. The `.CMD` shim works:
   `C:\Users\13429\AppData\Roaming\npm\codex.CMD`.
3. `codex --version` through the shim reported `codex-cli 0.130.0`.
4. A direct JSONL probe returned `REAL_CODEX_DIRECT_PROBE_OK`.

Real GraphRuntime smoke:

1. Started a real `CLIWorkerBackend` broker.
2. Launched a real Codex worker for a full `Agent` node.
3. Used a mixed graph: `agent` source node to external `worker_agent` target.
4. Verified full-Agent launch config:
   `cwd=project`, `sandbox="danger-full-access"`,
   `dangerous_access=true`, and
   `--dangerously-bypass-approvals-and-sandbox`.
5. Verified no workspace env was injected:
   no `MULTI_AGENT_WORKSPACE_CONTEXT`, no
   `MULTI_AGENT_WORKSPACE_RPC_TOKEN`.
6. Verified message MCP token existed and the scope had only message tools.
7. The real Codex worker wrote a file in the project cwd.
8. The real Codex worker wrote a file outside the project cwd.
9. The real Codex worker called the MCP `agent_dispatch` tool.
10. The downstream Worker Agent queue received one standard framework message.
11. The run manifest recorded:
    `event_type="framework_mcp_tool_call"` and
    `tool_name="agent_dispatch"`.

Observed final marker:

```text
REAL_FULL_AGENT_SMOKE_OK REAL_FULL_AGENT_PROJECT_WRITE_OK REAL_FULL_AGENT_OUTSIDE_WRITE_OK REAL_FULL_AGENT_MCP_DISPATCH_OK
```

## Known Limits

1. The real smoke validates dispatch up to the downstream Worker Agent queue.
   It does not launch a second real Worker Agent process to consume that queued
   message.
2. The smoke used a temporary project under
   `D:\agent\multi_agent_tcp\.tmp_real_codex_smoke`.
3. Full-repo Python and Bun suites were not rerun after this focused smoke.

## Follow-Up Queue

1. Add an optional real-Codex smoke test that launches both a full Agent and a
   real Worker Agent consumer when runtime cost is acceptable.
2. Keep the dangerous access checks centralized so `worker_agent` cannot regain
   bypass-sandbox behavior through adapter options.
3. If Codex CLI changes MCP tool naming, refresh the smoke prompt and the
   expected message-tool list together.

## Skill/Archive Files

Installed skill:

```text
C:\Users\13429\.codex\skills\multi-agent-tcp\archive\runtime-backend\blueprint_full_agent_runtime_real_codex_smoke_2026-05-30.md
```

Repository snapshot:

```text
KM_docs/skills-snapshot/archive/runtime-backend/blueprint_full_agent_runtime_real_codex_smoke_2026-05-30.md
```
