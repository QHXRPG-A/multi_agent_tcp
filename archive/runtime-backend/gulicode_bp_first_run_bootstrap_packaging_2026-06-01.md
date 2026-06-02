# gulicode-bp First-Run Bootstrap and Packaging

Date: 2026-06-01

## Summary

This archive records the work that made `gulicode-bp` usable by a new Windows
Codex user without a local `multi_agent_tcp` source checkout.

The plugin now has a first-run bootstrap path:

- `.mcp.json` starts `scripts/bootstrap_mcp.py`.
- `bootstrap_mcp.py` calls `scripts/bootstrap_runtime.py`.
- `bootstrap_runtime.py` creates `<plugin>/.runtime/venv`, installs the bundled
  `runtime/wheels/multi_agent_tcp-*.whl` with dependencies, validates imports,
  then starts `mcp/gulicode_bp_mcp.py` through the private Python runtime.

The release package is generated from the source tree and is separate from the
trunk/source checkout:

- Trunk/source repo: `F:\src\Package\Script\Python\multi_agent_tcp`
- Release package output: `dist\gulicode-bp-<version>`
- User runtime state: `<installed plugin>/.runtime`

`dist/` is ignored because release packages are generated artifacts.

## Key Changes

- Added stdlib-only runtime bootstrap:
  `plugins/gulicode-bp/scripts/bootstrap_runtime.py`
  - Resolves `plugin_root`, `.runtime`, private Python, and bundled runtime wheel.
  - Creates `.runtime/venv` if missing.
  - Repairs pip with `ensurepip` when needed.
  - Runs `pip install --upgrade --force-reinstall <wheel>` without `--no-deps`.
  - Validates `multi_agent_tcp`, `mcp.server.fastmcp.FastMCP`, and
    `DesktopBlueprintService` import from the plugin venv.
  - Writes `.runtime/state/bootstrap.json`.
  - Uses a simple `bootstrap.lock` to avoid concurrent first-run installs.

- Added MCP bootstrap entry:
  `plugins/gulicode-bp/scripts/bootstrap_mcp.py`
  - Supports `--print-runtime-json` for smoke diagnostics.
  - On Windows uses a child process instead of `os.execve` to avoid native
    process crashes while preserving stdio MCP behavior.

- Updated plugin startup:
  - `plugins/gulicode-bp/.mcp.json` points to `scripts/bootstrap_mcp.py`.
  - `plugins/gulicode-bp/scripts/start_workbench.py` can bootstrap runtime when
    no repo fallback is available.
  - `plugins/gulicode-bp/mcp/gulicode_bp_mcp.py` also avoids `os.execve` on
    Windows when re-entering the private runtime.

- Updated packaging/install flow:
  - `plugins/gulicode-bp/scripts/install_personal_plugin.py` now prepares a
    standalone release package with `web/dist`, `runtime/wheels`, bootstrap
    scripts, skills, MCP bridge, and manifest.
  - Personal install and Codex cache are refreshed to use bootstrap `.mcp.json`.
  - Release packages must not include `.runtime`.

- Added fixed packaging command:
  - `package-gulicode-bp-plugin.cmd`
  - `package-gulicode-bp-plugin.ps1`
  - Default action:
    `.\package-gulicode-bp-plugin.cmd`
  - It builds the release package under `dist\gulicode-bp-<version>`, refreshes
    the personal plugin mirror and Codex cache, validates package shape, runs
    release standalone smoke, then removes release `.runtime` created by smoke.
  - `-SmokeInstalledPlugin` explicitly validates the installed personal plugin.
  - `-SkipWebBuild` uses an existing `web/dist`.

## Verification

Focused tests:

```powershell
python -m py_compile plugins\gulicode-bp\mcp\gulicode_bp_mcp.py plugins\gulicode-bp\scripts\bootstrap_runtime.py plugins\gulicode-bp\scripts\bootstrap_mcp.py plugins\gulicode-bp\scripts\install_personal_plugin.py plugins\gulicode-bp\scripts\smoke_standalone_plugin.py plugins\gulicode-bp\scripts\start_workbench.py test_desktop_blueprint_service.py
python -m pytest -q test_desktop_blueprint_service.py::test_gulicode_bp_standalone_mcp_payload_uses_plugin_runtime test_desktop_blueprint_service.py::test_gulicode_bp_bootstrap_creates_runtime_and_installs_wheel test_desktop_blueprint_service.py::test_gulicode_bp_bootstrap_validation_disables_repo_fallback test_desktop_blueprint_service.py::test_gulicode_bp_installer_installs_runtime_dependencies_and_validates test_desktop_blueprint_service.py::test_gulicode_bp_installer_syncs_codex_cache_mcp test_desktop_blueprint_service.py::test_gulicode_bp_release_package_contains_bootstrap_runtime_wheel_and_web_dist test_desktop_blueprint_service.py::test_gulicode_bp_standalone_smoke_env_disables_repo_fallback
```

Result: `7 passed`.

Standalone release smoke:

```powershell
python plugins\gulicode-bp\scripts\install_personal_plugin.py --force --skip-web-build --release-dir <temp-release> --only-release
python plugins\gulicode-bp\scripts\smoke_standalone_plugin.py --plugin-root <temp-release> --timeout 180
```

Verified:

- Release package initially has no `.runtime`.
- First smoke creates `.runtime/venv`.
- Runtime package loads from
  `<temp-release>/.runtime/venv/Lib/site-packages/multi_agent_tcp/__init__.py`.
- Smoke completes:
  `blueprint_create -> list -> plan_create -> plan_validate -> start(status) -> status -> end`.

Packaging command smoke:

```powershell
.\package-gulicode-bp-plugin.cmd -ReleaseDir <temp-release> -SkipWebBuild
```

Verified:

- Release package and installed personal plugin were refreshed.
- Release standalone smoke passed.
- Release `.runtime` was removed after smoke.
- Summary written to `logs/gulicode-bp-package-ready.json`.

## Operational Notes

- A new user still needs an executable `python` on PATH, version compatible with
  `multi-agent-tcp` (`>=3.10`).
- First run is allowed to access the network because dependencies are resolved
  by pip from the bundled runtime wheel metadata.
- The release package is the distribution artifact. Do not edit it directly.
  Make changes in trunk/source and run the packaging command again.
- If the bundled runtime wheel changes, bootstrap detects the wheel identity and
  reinstalls into `.runtime/venv` on next start.
- `GULICODE_BP_REPO_ROOT` is a development override only. Release and installed
  `.mcp.json` must not set it or `PYTHONPATH`.

## When To Use This Archive

Use this file when:

- A user asks whether `gulicode-bp` works without a local `multi_agent_tcp`
  checkout.
- First plugin startup fails before MCP tools become available.
- `.runtime/venv` is missing, stale, locked, or loading from the wrong path.
- A release package contains `.runtime` or lacks `runtime/wheels`.
- The user asks what `release` versus trunk/source means.
- The user asks for `打包`, `插件打包`, `package`, or plugin refresh behavior.
