---
name: gulicode-bp:blueprint
description: Use the GuLiCode Blueprint plugin to open a local blueprint workbench, inspect project blueprints, query GraphRuntime status/events/diffs, and queue messages to live blueprint AgentNodes through Codex MCP tools.
---

# GuLiCode Blueprint Plugin

Use this skill when the user asks for GuLiCode blueprint work, GraphRuntime
runs, multi-agent blueprint scheduling, blueprint diffs/events, POPO-triggered
Blueprint execution, or the local Blueprint web workbench. Treat the
`gulicode-bp` plugin as the default development and debug entrypoint. For now,
do not start or expand GuLiCode Electron desktop, `/mobile`, `/console`, or
hosted/server product surfaces unless the user explicitly asks for them.

## Default Invocation

When this skill is invoked by name with no other concrete task, for example the
user only enters `$gulicode-bp:gulicode-bp:blueprint`, immediately open the
local Blueprint workbench for the current project and put it in Codex's
in-app side browser. This is the required flow:

1. Call `blueprint_list` with the current absolute project directory.
2. Choose the explicitly requested blueprint when the user named one; otherwise
   choose the current/default blueprint, preferring `default` when it exists.
3. Call `start_blueprint_workbench` with `openBrowser: false`.
4. If the Browser plugin is available, use it to set the in-app browser
   `visibility` capability to `true`, reuse the selected tab when possible or
   create one when needed, and navigate that tab to the workbench URL returned
   by `start_blueprint_workbench`.
5. If the Browser plugin is unavailable, return the workbench URL and clearly
   say that the Codex side browser could not be opened automatically.

Do not rely on `openBrowser: true` for the side browser; that MCP flag uses
Python `webbrowser.open()` and only targets the system default browser. Do not
wait for a second "open blueprint" message.

## Runtime Boundary

- Treat `DesktopBlueprintService` and `GraphRuntimeControlPlane` as the source
  of truth for blueprint state.
- Use the `gulicode-bp` MCP tools instead of recreating queue, join, runtime,
  workspace, event, or diff logic.
- The web workbench is local-only and should be started with
  `start_blueprint_workbench` when the user wants an interactive page.
- Installed plugin mode uses `scripts/bootstrap_mcp.py` to create and validate
  the plugin-owned `.runtime/venv` Python runtime on first start.
  `GULICODE_BP_REPO_ROOT` is only a repository development override, not a
  normal user requirement.
- Installation must be validated against both `~/plugins/gulicode-bp` and the
  Codex cache copy under `~/.codex/plugins/cache/personal/gulicode-bp/<version>`;
  cache `.mcp.json` files must not retain repo `PYTHONPATH` or
  `GULICODE_BP_REPO_ROOT`.
- Script Function Nodes expose `blueprint_node` through the generated local
  `.multi_agent_workspace/scripts/gulicode_blueprint.py` shim. Treat that shim
  as the script-author-facing API; do not direct users to internal runtime
  source unless they are debugging framework internals.
- Current focus is the plugin and POPO invocation chain. GuLiCode desktop,
  `/mobile`, `/console`, and hosted/server product work are temporarily
  compatibility-only unless explicitly requested.

## Common Flow

1. Call `blueprint_list` with an absolute `projectDir`.
2. Use `blueprint_create`, `blueprint_open`, `blueprint_save`,
   `blueprint_validate`, or `blueprint_delete` for normal CRUD.
3. Keep Codex desktop control split into two explicit actions: set the saved
   start AgentNode, then execute a caller-provided plan against that saved
   start node. Slot start/message remains a Workbench/POPO internal path.
4. Poll `blueprint_status`, `blueprint_recent_events`, and `blueprint_run_diff`
   while the run is active.
5. Call `blueprint_end` with `complete`, `cancel`, `fail`, or `pause` when the
   run should close.

Use `blueprint_request` only when a specific command is not covered by a
convenience tool.

## Debug Startup

From the repo root, prefer `.\start-gulicode-bp-plugin.cmd` for plugin-focused
debugging:

- refresh the personal `gulicode-bp` plugin mirror
- serve the local Blueprint workbench
- skip GuLiCode Electron desktop, `/mobile`, `/console`, and broader server
  workflows unless explicitly requested
