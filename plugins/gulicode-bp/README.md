# GuLiCode Blueprint Codex Plugin

This plugin is the default GuLiCode Blueprint development surface for Codex. It
exposes the Blueprint runtime through a skill, stdio MCP tools, and a local
Blueprint web workbench without starting the full Electron desktop shell.

The default local debug stack is:

- `gulicode-bp` plugin workbench at `/<project>/blueprint-window/<blueprint>`
- GuLiCode app dev server pages at `/mobile` and `/console`
- Collaboration Server and the existing Python Blueprint runtime/control plane

The GuLiCode Electron desktop remains available for explicit desktop-shell,
IPC, packaging, or taskbar work, but it is not part of the default plugin debug
startup.

Install or refresh the personal plugin mirror:

```powershell
python plugins\gulicode-bp\scripts\install_personal_plugin.py --force
```

The installer rebuilds/copies `GuLiCode/packages/app/dist` into `web/dist`,
copies this plugin to `~/plugins/gulicode-bp`, builds the `multi-agent-tcp`
runtime wheel into `runtime/wheels`, rewrites the personal MCP config to the
bootstrap entrypoint, and updates `~/.agents/plugins/marketplace.json`. It also
synchronizes the Codex plugin cache under
`~/.codex/plugins/cache/personal/gulicode-bp/<version>` and rewrites existing
cache `.mcp.json` files away from repo-local `GULICODE_BP_REPO_ROOT` or
`PYTHONPATH`.

Use `--skip-web-build` when the GuLiCode app dist has already been built.
Installed plugin mode does not require a local `multi_agent_tcp` checkout. On
first MCP/workbench startup, `scripts/bootstrap_mcp.py` creates the plugin-owned
`.runtime/venv`, installs the bundled `runtime/wheels/multi_agent_tcp-*.whl`
with dependencies, validates imports, and then starts the MCP server through the
private Python. `GULICODE_BP_REPO_ROOT` is only a development override for
running directly from this repository.

Build a standalone release package without installing the personal mirror:

```powershell
python plugins\gulicode-bp\scripts\install_personal_plugin.py --force --skip-web-build --release-dir dist\gulicode-bp-0.1.3 --only-release
```

The release package contains `web/dist`, `runtime/wheels`, the MCP/bootstrap
scripts, and no `.runtime` state. `.runtime` is created on the user's machine at
first run.

Start the plugin-first debug stack from the repo root:

```powershell
.\start-gulicode-debug.cmd
```

This refreshes the personal plugin, starts the local Blueprint workbench,
starts or reuses the app dev server for `/mobile` and `/console`, and skips the
Electron desktop shell. `.\start-gulicode-bp-plugin.cmd` is an alias for the
same plugin-first workflow.

`start_blueprint_workbench` serves the built GuLiCode app at a
`/<project>/blueprint-window/<blueprint>` route and injects a local-only token so
the existing `BlueprintSidePanel` can call the plugin `/api/blueprint` bridge.

Blueprint runs are a two-step flow in v1:

1. Generate and validate a start plan with `blueprint_plan_create` or
   `blueprint.plan.create`.
2. Start only after user/UI confirmation by passing that confirmed plan to
   `blueprint_start`.

The plugin also exposes direct CRUD tools:

- `blueprint_create`
- `blueprint_delete` (soft delete to `.multi_agent_workspace/blueprints/.trash`)
- `blueprint_open`
- `blueprint_save`
- `blueprint_validate`

The runtime source of truth remains `DesktopBlueprintService` and
`GraphRuntimeControlPlane`; the plugin only forwards commands and serves a
local browser UI.

Script Function Node files import `blueprint_node` from the generated local
`.multi_agent_workspace/scripts/gulicode_blueprint.py` shim. Editors jump to
that project-local API file instead of the internal runtime package; old scripts
that import `multi_agent_tcp.blueprint_script_nodes.blueprint_node` remain
compatible.
