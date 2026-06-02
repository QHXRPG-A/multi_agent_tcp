# gulicode-bp Plugin Singleton Service

Date: 2026-06-02

## Summary

This archive records the Codex `gulicode-bp` plugin lifecycle consolidation
work. The scope is intentionally limited to the Codex plugin and excludes the
GuLiCode Electron desktop app lifecycle.

The new runtime model is:

- One machine/user-level stateful `gulicode-bp` plugin service owns
  `PluginState`, `DesktopBlueprintService`, Workbench host, planning requests,
  live-run registry, and plugin-managed Collaboration Server lifecycle.
- Codex stdio MCP entries may still create multiple per-session
  `bootstrap_mcp.py` / proxy processes. Those processes are stateless and
  forward calls to the singleton service.
- `scripts/start_workbench.py` is an attach/debug wrapper. It starts or reuses
  the singleton service, asks it to open Workbench, writes the ready file, and
  exits. It must not own `PluginState`.

## Key Changes

- Added `plugins/gulicode-bp/mcp/gulicode_bp_singleton.py`.
  - Owns `service.lock`, `service.json`, and `service.log.jsonl`.
  - Provides service health checks and loopback JSON RPC forwarding.
  - Starts the singleton service under the canonical installed personal plugin
    runtime state directory.
  - Waits for briefly unhealthy `service.json` entries to recover before
    cleaning them up, preventing a duplicate service during reconnect races.
  - On Windows, launches the service with base Python plus venv
    `site-packages` in the process environment to avoid persistent venv
    launcher parent processes that look like duplicate plugin services.
- Reworked `plugins/gulicode-bp/mcp/gulicode_bp_mcp.py`.
  - Adds `SingletonServiceServer` for `--service` mode.
  - Adds `SingletonProxyState` for stateless stdio MCP proxy mode.
  - Keeps public MCP tool names and payloads stable.
  - Writes proxy diagnostics to `mcp_status.json`; `service.json` is the
    service authority.
  - Moves Workbench ownership inside the singleton service.
  - Records `owner_changed` when a new Codex thread performs a write/control
    call. Read calls do not change owner.
  - Allows pending/claimed planning requests to be reassigned to the attached
    active Codex thread during takeover; completed/failed/cancelled requests
    remain immutable.
- Reworked `plugins/gulicode-bp/scripts/bootstrap_mcp.py`.
  - Prepares the private runtime.
  - Ensures the singleton service exists.
  - Starts a stateless stdio proxy with `GULICODE_BP_SINGLETON_ROLE=proxy`.
- Reworked `plugins/gulicode-bp/scripts/start_workbench.py`.
  - No longer imports `gulicode_bp_mcp.state`.
  - No longer sleeps forever.
  - Attaches to the singleton service and exits after writing the ready JSON.
- Updated plugin `.mcp.json` generation in
  `plugins/gulicode-bp/scripts/install_personal_plugin.py`.
  - Personal and Codex cache `.mcp.json` now resolve
    `GULICODE_BP_RUNTIME_HOME` and `GULICODE_BP_DATA_DIR` to the same personal
    plugin `.runtime` directory.
- Updated `start-gulicode-debug.ps1`.
  - Uses the personal plugin workbench wrapper when available.
  - Does not kill healthy singleton Workbench state.
  - Does not independently start the Collaboration Server; the singleton
    service owns it.
- Updated `desktop_blueprint_service.py`.
  - Prevents duplicate active runs for the same `projectDir + blueprintId`.
  - A second valid start request returns the existing active run with
    `alreadyActive: true`.
  - Start plans are preflight-validated before duplicate-run reuse so invalid
    plans still fail with `START_PLAN_INVALID`.

## Runtime State Files

Canonical installed runtime state:

```text
C:\Users\qiuhaoxuan\plugins\gulicode-bp\.runtime\state
```

Important files:

- `service.lock`: atomic startup ownership.
- `service.json`: singleton service PID, URL, token, generation, startedAt,
  heartbeatAt, and staleAfterSeconds.
- `logs/service.log.jsonl`: service lifecycle, attach, takeover, stale cleanup,
  and shutdown events.
- `workbench_ready.json`: latest Workbench route and service PID.
- `mcp_status.json`: proxy/bootstrap diagnostics only, not global service truth.

## Verification

Code-level verification during this session:

- `python -m py_compile plugins/gulicode-bp/mcp/gulicode_bp_singleton.py plugins/gulicode-bp/mcp/gulicode_bp_mcp.py plugins/gulicode-bp/scripts/bootstrap_mcp.py plugins/gulicode-bp/scripts/start_workbench.py plugins/gulicode-bp/scripts/install_personal_plugin.py desktop_blueprint_service.py test_desktop_blueprint_service.py`
  - Result: passed.
- `python -m pytest test_desktop_blueprint_service.py -q`
  - Result: `74 passed, 1 skipped`.
- Targeted post-patch tests:
  - `test_gulicode_bp_mcp_whitelists_python_detection_command`
  - `test_gulicode_bp_standalone_mcp_payload_uses_plugin_runtime`
  - Result: passed.
- `python plugins\gulicode-bp\scripts\install_personal_plugin.py --force`
  - Result: refreshed personal plugin and Codex cache.
- `python plugins\gulicode-bp\scripts\install_personal_plugin.py --force --skip-web-build`
  - Result: refreshed Python-only singleton fixes into personal plugin and
    Codex cache.

Final clean reload verification:

- Killed all matching `gulicode-bp` plugin processes:
  - `gulicode_bp_mcp.py`
  - `bootstrap_mcp.py`
  - `start_workbench.py`
  - plugin runtime `multi_agent_tcp collaboration-server`
- Removed stale runtime metadata:
  - `service.lock`
  - `service.json`
  - `workbench_ready.json`
  - `mcp_status.json`
- Started the refreshed personal plugin wrapper:

```text
python C:\Users\qiuhaoxuan\plugins\gulicode-bp\scripts\start_workbench.py --project-dir F:\src\Package\Script\Python\multi_agent_tcp --blueprint-id default --ready-file C:\Users\qiuhaoxuan\plugins\gulicode-bp\.runtime\state\workbench_ready.json
```

Final observed state:

```json
{
  "ServiceJsonPid": 29236,
  "ServiceUrl": "http://127.0.0.1:3076",
  "HealthOk": true,
  "ServiceProcessCount": 1,
  "ProxyProcessCount": 0,
  "BootstrapProcessCount": 0,
  "WorkbenchWrapperProcessCount": 0,
  "CollaborationProcessCount": 1,
  "CollaborationListenerPids": "4548"
}
```

Workbench ready file:

```json
{
  "ok": true,
  "url": "http://127.0.0.1:3092/Rjpcc3JjXFBhY2thZ2VcU2NyaXB0XFB5dGhvblxtdWx0aV9hZ2VudF90Y3A/blueprint-window/default",
  "projectDir": "F:\\src\\Package\\Script\\Python\\multi_agent_tcp",
  "blueprintId": "default",
  "planningThreadId": "",
  "pid": 29236,
  "servicePid": 29236,
  "persistent": true,
  "singleton": true,
  "generation": "1780384697866-438720db",
  "wrapperPid": 13896
}
```

Installed personal plugin and Codex cache `.mcp.json` both point to the
personal plugin root and runtime state:

```text
GULICODE_BP_PLUGIN_ROOT=C:\Users\qiuhaoxuan\plugins\gulicode-bp
GULICODE_BP_RUNTIME_HOME=C:\Users\qiuhaoxuan\plugins\gulicode-bp\.runtime
GULICODE_BP_DATA_DIR=C:\Users\qiuhaoxuan\plugins\gulicode-bp\.runtime\state
GULICODE_BP_DISABLE_REPO_FALLBACK=1
```

## Operational Notes

The desired uniqueness boundary is stateful plugin ownership, not every Codex
access process:

- Exactly one `gulicode_bp_mcp.py --service` should be healthy.
- Exactly one plugin-managed Collaboration Server should be owned by that
  service.
- `start_workbench.py` should not remain after startup.
- Multiple Codex sessions may temporarily create multiple `bootstrap_mcp.py`
  and stateless proxy `gulicode_bp_mcp.py` processes. That is allowed as long
  as they do not own `PluginState`.

If process inventory shows duplicate `gulicode_bp_mcp.py --service` or multiple
plugin runtime Collaboration Servers:

1. Read `service.json` and check `/health` using its token.
2. Keep the healthy PID from `service.json`.
3. Stop stale duplicate service or non-listening Collaboration Server PIDs.
4. If `service.json` is unhealthy, remove stale metadata and restart through
   `scripts/start_workbench.py` or normal Codex plugin reload.

Avoid treating `mcp_status.json` as service truth. It is proxy/bootstrap
diagnostics. Use `service.json` for singleton service state.

## When To Use This Archive

Load this record when the user reports or asks about:

- Whether `bootstrap_mcp.py`, `gulicode_bp_mcp.py`, or `start_workbench.py`
  should be unique.
- Duplicate Blueprint Workbench, duplicate Collaboration Server, or duplicate
  plugin-owned runtime state.
- Plugin reload after killing all related processes.
- Singleton service health, stale `service.json`, or stale `service.lock`.
- Codex sessions attaching to the same plugin service from multiple stdio MCP
  proxies.
- Planning request takeover between Codex threads.
- Duplicate active blueprint runs for the same project and blueprint.
