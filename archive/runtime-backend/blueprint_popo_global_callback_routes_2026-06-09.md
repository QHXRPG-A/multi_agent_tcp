# Blueprint POPO Global Callback Robot Routes

Date: 2026-06-09

## Summary

This archive records the backend/runtime work that makes POPO callback robot
entry configuration a plugin-level callback-service concern instead of a
Blueprint document or AgentNode concern.

The POPO callback service now accepts only globally configured callback robots.
AgentNode `popo_entry` remains the Blueprint binding/routing target used after a
callback has been accepted, but it no longer answers "which robots may hit this
callback service".

## Route Store

Global callback robots are stored in the plugin runtime state file:

```text
popo_robot_routes.json
```

The state file is resolved from `DesktopBlueprintService.resident_service_data_dir()`.
In a packaged personal plugin install this is under:

```text
C:\Users\qiuhaoxuan\plugins\gulicode-bp\.runtime\state
```

Each robot route is normalized with these fields:

- `enabled`
- `robot_app_key`
- `robot_name`
- `robot_app_secret`
- `callback_token`
- `aes_key`
- `updated_at`

`robot_app_key` is unique. Disabled routes remain stored but do not participate
in callback forwarding.

Enabled callback robots must have complete credentials. The service rejects
attempts to enable or save an enabled robot when any required callback
credential is missing.

## Internal Commands

`DesktopBlueprintService.handle_request()` handles these plugin-internal
commands:

- `blueprint.popo.robots`
- `blueprint.popo.robot.save`
- `blueprint.popo.robot.delete`
- `blueprint.popo.robot.enabled`
- `blueprint.popo.callbackConfig`

The Workbench calls the list/save/delete/toggle commands through the plugin
singleton `/api/blueprint` bridge. These commands are intentionally internal to
the Workbench/plugin bridge because they can persist POPO callback credentials.

Public Codex MCP callers must not get write access to this credential store.
The public boundary can expose callback service status, but not arbitrary robot
route mutation.

## Callback Resolution

`popo_agent_bot_run.py` now calls `blueprint.popo.callbackConfig` to resolve the
actual callback robot configuration for both route forms:

```text
/popo/callback/<robot_app_key>
/popo/callback
```

For `/popo/callback/<robot_app_key>`:

- Missing global route returns `BLUEPRINT_POPO_ROBOT_NOT_BOUND`.
- Disabled global route returns `BLUEPRINT_POPO_ROBOT_DISABLED`.
- Incomplete enabled global route returns a structure/conflict error.
- Enabled complete route supplies the callback token, AES key, robot app secret,
  and normalized robot app key used by the callback service.

For legacy `/popo/callback`:

- Exactly one enabled global route is auto-resolved.
- No enabled global route returns `BLUEPRINT_POPO_ROBOT_NOT_BOUND`.
- Multiple enabled global routes return `BLUEPRINT_POPO_ROBOT_STRUCTURE_CONFLICT`
  and require POPO to use `/popo/callback/<robot_app_key>`.

The callback server command-line `--app-key` is deprecated. Legacy route
resolution is driven by plugin state, not by a process-wide default app key.

## Blueprint Routing

After a callback robot is accepted and its signature/AES checks pass,
`popo_agent_bot_run.py` still sends the message into Blueprint slot routing with
`sourceIdentity.robotAppKey`.

That means the global callback route controls whether the callback service
accepts the robot at all. The existing Blueprint slot/session lookup still
decides which POPO-enabled Blueprint target receives the accepted message.

The old `blueprint.popo.config` command remains for Blueprint binding
compatibility. It resolves the Blueprint/AgentNode `popo_entry` target and does
not replace the global callback robot allowlist.

## Plugin Status

`service.popoStatus` reports callback URL metadata used by the Workbench:

```text
callbackUrlTemplate = http://127.0.0.1:3100/popo/callback/<robot_app_key>
legacyCallbackUrl = http://127.0.0.1:3100/popo/callback
legacyCallbackAutoResolve = true
```

The callback process prints the same callback URL forms on startup.

## Main Files

- `desktop_blueprint_service.py`
- `popo_agent_bot_run.py`
- `plugins/gulicode-bp/mcp/gulicode_bp_mcp.py`
- `test_desktop_blueprint_service.py`

## Verification

Commands run from `F:\src\Package\Script\Python\multi_agent_tcp`:

```powershell
python -m py_compile popo_agent_bot_run.py desktop_blueprint_service.py plugins\gulicode-bp\mcp\gulicode_bp_mcp.py
python -m pytest test_desktop_blueprint_service.py -q -k "popo"
python plugins\gulicode-bp\scripts\install_personal_plugin.py --force
```

Results:

- Python compile passed.
- POPO backend tests passed: `15 passed, 92 deselected`.
- Personal plugin rebuild/install completed with `ok: true`.
- Packaged singleton service restarted with PID `55416`.
- Packaged POPO callback service restarted with PID `42692`.
- Callback health URL is `http://127.0.0.1:3100/health`.
- Workbench URL after restart is
  `http://127.0.0.1:1474/Rjpcc3JjXFBhY2thZ2VcU2NyaXB0XFB5dGhvblxtdWx0aV9hZ2VudF90Y3A/blueprint-window/default`.

Manual API checks:

- `blueprint.popo.robots` returned `ok` and the expected state path
  `C:\Users\qiuhaoxuan\plugins\gulicode-bp\.runtime\state\popo_robot_routes.json`.
- `GET http://127.0.0.1:3100/popo/callback?nonce=codex-test` no longer fails
  because of a missing process default app key; with no enabled route it returns
  the expected `BLUEPRINT_POPO_ROBOT_NOT_BOUND` path.
