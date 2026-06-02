# Runtime Backend Archive

This folder contains runtime and local backend records:

1. GraphRuntime and GraphRuntimeControlPlane behavior.
2. Blueprint MCP runtime and desktop service bridge behavior.
3. AgentTCP, CLIWorkerBackend, Codex adapter, ring runtime, workspace state,
   queues, demux, completion, and archive behavior.

Use this folder when the next task touches Python runtime files, local desktop
services, worker process orchestration, MCP tools, or run/workspace state.

Latest high-priority handoff:

- `gulicode_bp_plugin_singleton_service_2026-06-02.md`: Codex `gulicode-bp`
  plugin singleton service boundary, stateless stdio proxies, Workbench attach
  wrapper, service runtime metadata, owner takeover, duplicate active-run guard,
  and clean reload process inventory.
- `gulicode_bp_mcp_transport_bootstrap_logging_2026-06-02.md`: `gulicode-bp`
  MCP transport/bootstrap/Workbench lifecycle boundaries, stale bootstrap lock
  cleanup, bootstrap/MCP logs, `mcp_status.json` heartbeat diagnostics, and the
  current Codex stdio reconnect boundary after `Transport closed`.
- `gulicode_bp_first_run_bootstrap_packaging_2026-06-01.md`: `gulicode-bp`
  standalone first-run runtime bootstrap, release package shape, and personal
  plugin/cache `.mcp.json` behavior.
- `gulicode_bp_plugin_direct_control_start_plan_2026-06-01.md`: `gulicode-bp`
  plugin direct CRUD/start-plan control, two-step confirmed run UI, and the P0
  standalone-distribution boundary for install-only users.
