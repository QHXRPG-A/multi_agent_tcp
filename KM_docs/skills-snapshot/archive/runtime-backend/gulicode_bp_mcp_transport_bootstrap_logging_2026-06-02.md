# gulicode-bp MCP Transport, Bootstrap Lock, and Status Logging

Date: 2026-06-02

## Summary

This archive records the `gulicode-bp` MCP transport investigation and the
runtime reliability fixes added after the user saw repeated `Transport closed`
behavior while the Blueprint Workbench was still visible.

The important boundary is that these are separate lifecycles:

- `transport`: Codex's stdio client connection to the plugin MCP server.
- `bootstrap`: `scripts/bootstrap_mcp.py` plus `bootstrap_runtime.py`, which
  prepares the plugin-owned runtime and then starts the MCP server.
- `Workbench`: the plugin-served HTTP Blueprint web UI. It can stay up even
  when the MCP stdio transport for the current Codex thread is closed.

The plugin MCP server itself was verified with a manual JSON-RPC smoke. The
remaining current-thread failure was a Codex host/client lifecycle issue:
after a stdio MCP client reaches `Transport closed`, the current manager does
not automatically reconnect that stdio client from shell-side plugin changes.

## Source Findings

- Codex loads plugin MCP servers from installed and enabled plugin metadata,
  not from ordinary `[mcp_servers]`.
- The required plugin state is:
  - `[plugins."gulicode-bp@personal"] enabled = true` in Codex config.
  - `~/.codex/plugins/cache/personal/gulicode-bp/<version>/.codex-plugin/plugin.json`.
  - A plugin `.mcp.json` that starts `scripts/bootstrap_mcp.py`.
- `~/plugins/gulicode-bp` source alone does not mean the current Codex thread
  has an active `gulicode-bp` MCP tool transport.
- Codex app-server source shows plugin/MCP refresh is queued for loaded
  threads and normally applied on the next active turn. Existing tool calls use
  the current `McpConnectionManager` client.
- Codex has recovery for some streamable HTTP session expiry cases, but this
  did not provide a shell-triggered stdio MCP reconnect after `Transport closed`.
- The current Windows desktop app-server instance did not expose an accessible
  websocket/control socket that could be used from shell to force the current
  thread's MCP manager to reconnect.

## Key Changes

- `plugins/gulicode-bp/scripts/bootstrap_runtime.py`
  - Enhanced `bootstrap.lock` to store `pid`, creation time, and command name.
  - Removes dead-PID locks immediately instead of waiting for the age timeout.
  - Keeps the age timeout as a fallback for live or unparseable lock cases.
  - Writes bootstrap lifecycle logs to
    `.runtime/state/logs/gulicode-bp-bootstrap.log`.
  - Updates `.runtime/state/mcp_status.json` for prepare start, complete, and
    error states.
- `plugins/gulicode-bp/scripts/bootstrap_mcp.py`
  - Logs prepare, `start-mcp`, `mcp-exited`, and bootstrap errors.
  - Updates status before and after launching the MCP server.
- `plugins/gulicode-bp/mcp/gulicode_bp_mcp.py`
  - Writes MCP lifecycle logs to
    `.runtime/state/logs/gulicode-bp-mcp.log`.
  - Updates `.runtime/state/mcp_status.json` with `starting`, `running`,
    `exited`, and `error` states.
  - Adds heartbeat fields `heartbeatAt` and `staleAfterSeconds` so a hard-kill
    or host-side termination can be detected even when Python cannot write a
    final `exited` status.
- `plugins/gulicode-bp/.codex-plugin/plugin.json`
  - Reduced `interface.defaultPrompt` to three prompts to remove the Codex
    warning that a maximum of three prompts is supported.
- `test_desktop_blueprint_service.py`
  - Added coverage for dead-PID stale lock cleanup, live lock timeout,
    bootstrap logging/status behavior, MCP logging/status/heartbeat symbols,
    and plugin manifest prompt count.

## Verification

Commands and results from the implementation session:

- `python -m pytest test_desktop_blueprint_service.py -k "bootstrap or mcp_whitelists_python_detection or plugin_manifest_default" -q`
  - Result: `8 passed, 67 deselected`.
- `python -m compileall plugins\gulicode-bp\mcp\gulicode_bp_mcp.py plugins\gulicode-bp\scripts\bootstrap_mcp.py plugins\gulicode-bp\scripts\bootstrap_runtime.py`
  - Result: passed.
- `.\package-gulicode-bp-plugin.cmd`
  - Result: package and standalone smoke passed.
  - Package summary: `logs\gulicode-bp-package-ready.json`, `ok: true`,
    `smoke: true`, timestamp `2026-06-02T04:58:33.5106661Z`.
- Manual installed-plugin MCP protocol smoke:
  - First run timed out during runtime installation and left a dead-PID lock.
  - `python scripts\bootstrap_mcp.py --print-runtime-json` cleaned the stale
    lock and installed the runtime.
  - The following JSON-RPC smoke succeeded: `initialize` returned serverInfo
    `gulicode-bp 1.27.2`, and `tools/list` returned 27 tools including
    `blueprint_list`.
  - `mcp_status.json` included `heartbeatAt` and `staleAfterSeconds: 20.0`.
- No lingering `bootstrap_mcp.py` or `gulicode_bp_mcp.py` processes remained
  after the manual smoke.

## Operational Notes

Use these files first when diagnosing plugin-side MCP startup:

- `C:\Users\qiuhaoxuan\plugins\gulicode-bp\.runtime\state\mcp_status.json`
- `C:\Users\qiuhaoxuan\plugins\gulicode-bp\.runtime\state\logs\gulicode-bp-bootstrap.log`
- `C:\Users\qiuhaoxuan\plugins\gulicode-bp\.runtime\state\logs\gulicode-bp-mcp.log`

Interpretation rules:

- `running` with a fresh `heartbeatAt` means the plugin MCP server is alive.
- `running` with `heartbeatAt` older than `staleAfterSeconds` means the process
  was likely hard-killed or the host closed it without a normal Python exit.
- `exited` after `--print-runtime-json` is expected for runtime-inspection smoke
  and does not mean a long-lived MCP server should still be running.
- Workbench HTTP availability does not prove current-thread MCP transport
  health.
- Calling `start_blueprint_workbench` can start the HTTP Workbench but does not
  itself attach a closed MCP transport back to the current Codex thread.
- If the current thread still reports `Transport closed` after the plugin fix,
  trigger a Codex MCP/plugin reload from the app or restart/open a fresh Codex
  manager. Shell-side Workbench restarts cannot repair that closed stdio client
  when no app-server control channel is exposed.

## When To Use This Archive

Load this record when the user reports:

- `gulicode-bp` MCP tools are visible but calls return `Transport closed`.
- MCP startup appears stuck behind `bootstrap.lock`.
- Workbench is open but MCP tools cannot be called.
- `mcp_status.json` says `running` while the MCP process is gone.
- The user asks what transport, bootstrap, or Workbench means.
- The user asks whether plugin Workbench restart is enough to reconnect MCP.
- Codex logs warn that `interface.defaultPrompt` has too many prompts.

Do not solve these cases by adding `gulicode-bp` to ordinary `[mcp_servers]`.
The intended path remains Codex plugin install/enable plus plugin `.mcp.json`
dynamic MCP merging.
