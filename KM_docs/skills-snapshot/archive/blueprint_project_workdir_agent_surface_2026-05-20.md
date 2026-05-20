# Blueprint Project Workdir + Agent Tool Surface - 2026-05-20

## Summary

This session closed two related product/runtime boundaries:

1. The GuLiCode blueprint project workdir became the real session/workspace
   root decision point. Changing it now relocates the blueprint document to the
   target workdir and reloads the session so Workspace/MCP authority moves with
   the UI-selected project directory.
2. Ordinary Agent capability was simplified to MCP tools plus direct read-only
   filesystem reads. Project and current-run shared workspace reads no longer
   go through Workspace read/list/archive tools, and CLI framework commands are
   no longer exposed in ordinary Agent prompt-facing context.

The resulting Agent mental model is:

```text
read project/shared directly
edit code only in private checkout
submit code through MCP
publish reports/artifacts through MCP
communicate through agent_dispatch / join_contribute
```

## Project Workdir Relocation

Implemented behavior:

- On entering the blueprint panel, the app shows a project workdir confirmation
  dialog with the current path and a folder picker.
- The common config `project_workdir` input is read-only/disabled; users change
  it through the folder picker.
- Runtime/start/stop loading disables the common config button and closes the
  panel if it is already open.
- `blueprint.relocateProjectWorkdir` compares the current and target
  directories in the desktop Python service.
- If unchanged, it returns `changed: false`.
- If changed, it writes the current blueprint document into
  `<target>/.multi_agent_workspace/blueprints/default.json`, updates only
  `ui.config.project_workdir`, and preserves graph/layout/selection plus
  python/skill/rule config.
- If the target already has a blueprint, the backend returns
  `conflict: "target_exists"`; the UI lets the user overwrite with the current
  blueprint, load the existing target blueprint, or cancel.
- Successful relocation opens the target project through `layout.projects.open`
  and navigates to the target session so the whole blueprint/Workspace root
  reloads together.

Primary files:

- `desktop_blueprint_service.py`
- `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.tsx`
- `GuLiCode/packages/app/src/pages/session/blueprint-model.ts`
- `GuLiCode/packages/app/src/context/platform.tsx`
- `GuLiCode/packages/desktop-electron/src/main/blueprint-runtime.ts`
- `GuLiCode/packages/desktop-electron/src/main/ipc.ts`
- `GuLiCode/packages/desktop-electron/src/preload/index.ts`

## Agent Read/Write Boundary

Implemented behavior:

- Ordinary Agents may directly read:
  - `code_workspace.project_context`
  - `code_workspace.project_code_root`
  - `shared_workspace.root`
  - `shared_workspace.reports`
  - `shared_workspace.artifacts`
  - `shared_workspace.manifest`
  - `shared_workspace.logs`
- `AGENTS.md`, prompt preamble, and Codex Execution Context all expose those
  read-only roots.
- Code edits remain scoped to `checkout_path` and must be submitted through
  `workspace_submit`.
- Reports/artifacts still go through `workspace_publish` /
  `workspace_publish_file`.
- `validate_codex_launch_safety` rejects `danger-full-access` and rejects
  `--add-dir` entries overlapping `project_context`, `project_code_root`, or
  the run `shared_workspace.root`.

Removed Agent-facing read interfaces:

- Ordinary MCP no longer exposes:
  - `workspace_read`
  - `workspace_list`
  - `workspace_list_archives`
  - `workspace_extract_archive`
- Control MCP no longer exposes those workspace read/archive tools either.
- `workspace_api.py` no longer registers CLI subcommands:
  - `read`
  - `list`
  - `list-archives`
  - `extract-archive`
- `WorkspaceRPCServer` rejects the removed commands and no longer advertises
  `archive_commands`.

Internal manager read/archive methods were intentionally kept for framework
archiving, reports, tests, and status projection.

Primary files:

- `blueprint_mcp_runtime.py`
- `agent_launch_context.py`
- `workspace_api.py`
- `workspace_rpc.py`
- `codex_bridge.py`
- `docs/workspace_api.md`
- `test_workspace_api.py`
- `test_agent_runtime.py`
- `test_desktop_blueprint_service.py`

## Agent Prompt Surface

Implemented behavior:

- `workspace_api` and `submit_command` stay in full internal
  `execution_context`, and `MULTI_AGENT_WORKSPACE_CONTEXT` still exists for
  backend/debug/test paths.
- Ordinary Agent `prompt_execution_context` no longer includes
  `workspace_api` or CLI command recipes.
- The generated `framework-agent-runtime` skill no longer tells Agents to use
  the Workspace API CLI fallback.
- Ordinary Agent prompt context now centers on:
  - MCP tool names
  - direct read-only project/shared roots
  - skill/rule catalogs
  - current message framework context

Current ordinary MCP tool surface:

- `workspace_checkout`
- `workspace_status`
- `workspace_diff`
- `workspace_submit`
- `workspace_sync`
- `workspace_publish`
- `workspace_publish_file`
- `agent_dispatch`
- `agent_context`
- `join_contribute`

The CLI/RPC path remains useful for framework internals and tests, but is not
the Agent-facing interface.

## Operational Findings

- A test run against `C:\test.txt` failed at submit with
  `[Errno 13] Permission denied: 'C:\\test.txt'`; this was a root-directory
  write permission problem, not a general MCP failure.
- Moving the project workdir to a normal project directory such as
  `D:\agents_work_test` is the right direction because the blueprint session
  root and Workspace root must be the same authority.
- Merely setting Agent `cwd` is not enough; the blueprint project workdir must
  drive the session/project root so Workspace submit writes to the intended
  authoritative directory.
- Localhost MCP `502` / `503` failures on other machines can be caused by
  proxy interception. Keep `NO_PROXY` / system proxy bypass notes in
  `environment_setup.md`.

## Verification

Focused checks run during this session:

```powershell
python -m py_compile blueprint_mcp_runtime.py agent_launch_context.py workspace_api.py workspace_rpc.py codex_bridge.py test_workspace_api.py test_agent_runtime.py test_desktop_blueprint_service.py
pytest -q test_workspace_api.py test_agent_runtime.py test_desktop_blueprint_service.py
# Observed full related pass before later prompt-surface doc cleanup:
# 127 passed, 1 skipped, 2 warnings

pytest -q test_desktop_blueprint_service.py::test_live_blueprint_mcp_workspace_dispatch_flow_with_agent_backend
pytest -q test_agent_runtime.py::test_real_codex_cli_framework_private_checkout_submit_and_archive_flow
pytest -q test_agent_runtime.py::test_real_codex_cli_framework_blocks_direct_project_and_shared_writes

cd GuLiCode\packages\app
bun run typecheck
bun test --preload ./happydom.ts ./src/pages/session/blueprint-side-panel.test.ts

cd GuLiCode\packages\desktop-electron
bun test ./src/main/blueprint-runtime.test.ts ./src/main/ipc-blueprint-runtime.test.ts
bun run typecheck
```

Latest focused prompt-surface check after hiding CLI from ordinary Agents:

```powershell
python -m py_compile agent_launch_context.py test_agent_runtime.py test_desktop_blueprint_service.py
pytest -q test_agent_runtime.py::test_graph_runtime_private_context_materializes_codex_skill_and_rules test_desktop_blueprint_service.py::test_blueprint_service_live_mode_prestarts_all_agents_with_private_context
# 2 passed, 2 warnings
```

One full-suite rerun hit a transient real Codex broker startup timeout in
`test_real_codex_cli_framework_blocks_direct_project_and_shared_writes`; the
same test passed when rerun alone.

## Follow-Up Queue

1. Run a manual GuLiCode desktop smoke with a user-selected project workdir,
   especially the first-entry workdir confirmation dialog and conflict branches.
2. Verify a full MCP live run under `D:\agents_work_test` or another normal
   project directory, not `C:\`.
3. Exercise Agent panel follow-up sends after the MCP/read-boundary changes:
   message context refresh, idle/running status projection, and late replies.
4. Keep real Codex smoke coverage around direct project/shared writes versus
   private checkout writes.
5. Add UI/operator clarity for MCP status and runtime tool availability without
   exposing internal CLI/RPC commands to ordinary Agents.
