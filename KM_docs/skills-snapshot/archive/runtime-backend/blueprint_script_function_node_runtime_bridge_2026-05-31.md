# Blueprint Script Function Node Runtime and Bridge - 2026-05-31

## Summary

This pass added Python Script Function Nodes as first-class Blueprint runtime
nodes. User functions live under `.multi_agent_workspace/scripts`, are declared
with `@blueprint_node`, are scanned for catalog metadata without importing user
code, and are executed only when runtime flow crosses a Script Node.

The desktop bridge also gained script catalog, script creation, editor
discovery, and safe editor-open APIs.

## Implemented

Python script node module:

1. Added `multi_agent_tcp.blueprint_script_nodes`.
2. Added `blueprint_node(...)` decorator for user functions.
3. Added AST discovery for `.multi_agent_workspace/scripts/**/*.py`.
4. Discovery infers ports from signatures and type annotations.
5. Decorator overrides support `name`, `description`, `inputs`, and `outputs`.
6. Supported base port types are `int`, `float`, `str`, `bool`, `dict`, `list`,
   and `Any`.
7. Discovery creates the script directory when needed and reports diagnostics
   for syntax errors, missing annotations, and unsupported annotations.
8. Discovery does not import user code.

Script creation:

1. `create_script_node(project_dir, name, description)` writes only inside
   `.multi_agent_workspace/scripts`.
2. Display names are normalized into snake_case function/file names.
3. Name collisions resolve with `_2`, `_3`, and so on.
4. The default template imports `blueprint_node`, preserves the user-entered
   display name and description, and creates a `payload: dict -> dict`
   pass-through function.

Editor development metadata:

1. Script discovery/creation now ensures editor metadata under the scripts
   directory.
2. `pyrightconfig.json` includes the generated framework import root.
3. `.vscode/settings.json` includes `python.analysis.extraPaths`.
4. `blueprint-scripts.code-workspace` includes both the script folder and the
   local `multi_agent_tcp` source folder so users can navigate from
   `from multi_agent_tcp.blueprint_script_nodes import blueprint_node` into the
   framework source.
5. Paths are generated from the current installed source location instead of
   hardcoded machine paths.

Graph/runtime model:

1. Added `ScriptNode` / `script_nodes` to graph parsing and serialization.
2. Graph validation understands script nodes as non-Agent nodes.
3. Agent-to-Agent paths can cross one or more Script Nodes.
4. Runtime dispatch records intermediate script paths and executes them before
   delivering the downstream Agent message.
5. Script input mapping uses matching JSON keys for named parameters.
6. Single-argument functions can receive non-object payloads.
7. Missing required inputs fail the script step.
8. Single-output functions return as `result`.
9. Multi-output functions must return a dict containing every output key.
10. Script exceptions are emitted as `ScriptNodeFailed`; successful steps emit
    `ScriptNodeRunning` and `ScriptNodeCompleted`.

Desktop Blueprint service:

1. Added `blueprint.scriptNodes` command for script catalog discovery.
2. Added `blueprint.createScriptNode` command for safe script file creation.
3. Start/validate checks verify placed Script Nodes still point to discovered
   functions.
4. Missing script functions fail validation before runtime start.
5. Script path resolution rejects absolute paths, `..`, non-`.py` targets, and
   paths escaping `.multi_agent_workspace/scripts`.

Electron bridge:

1. Added `listBlueprintEditors`.
2. Added `createBlueprintScriptNode`.
3. Added `openBlueprintScriptInEditor`.
4. Editor discovery prefers saved selection, `VISUAL` / `EDITOR`, VS Code,
   Cursor, Windsurf, Zed, PyCharm, and finally system default.
5. Windows `.cmd` / `.bat` editor shims are resolved.
6. Editor open validates `modulePath` as relative, non-escaping, and `.py`.
7. The "system default" option opens through OS file association when no known
   IDE is available or selected.

## Files Changed

Runtime/backend:

1. `blueprint_script_nodes.py`
2. `__init__.py`
3. `graph_runtime.py`
4. `graph_control.py`
5. `desktop_blueprint_service.py`

Electron desktop bridge:

1. `GuLiCode/packages/desktop-electron/src/main/apps.ts`
2. `GuLiCode/packages/desktop-electron/src/main/blueprint-runtime.ts`
3. `GuLiCode/packages/desktop-electron/src/main/index.ts`
4. `GuLiCode/packages/desktop-electron/src/main/ipc.ts`
5. `GuLiCode/packages/desktop-electron/src/preload/index.ts`
6. `GuLiCode/packages/desktop-electron/src/preload/types.ts`
7. `GuLiCode/packages/desktop-electron/src/renderer/index.tsx`

Tests:

1. `test_agent_runtime.py`
2. `test_graph_control.py`
3. `test_desktop_blueprint_service.py`
4. `GuLiCode/packages/desktop-electron/src/main/blueprint-runtime.test.ts`
5. `GuLiCode/packages/desktop-electron/src/main/ipc-blueprint-runtime.test.ts`

## Verification

Python:

```powershell
python -m pytest test_desktop_blueprint_service.py -q
python -m pytest test_graph_control.py test_agent_runtime.py -q
```

Observed during implementation:

```text
desktop blueprint service focused tests passed
graph/runtime script path tests passed
```

Desktop Electron:

```powershell
cd D:\agent\multi_agent_tcp\GuLiCode\packages\desktop-electron
bun test ./src/main/ipc-blueprint-runtime.test.ts
bun test ./src/main/blueprint-runtime.test.ts
bun run typecheck
```

Observed during implementation:

```text
desktop-electron IPC/runtime tests passed
desktop-electron typecheck passed
```

Renderer bridge integration:

```powershell
cd D:\agent\multi_agent_tcp\GuLiCode\packages\app
bun run typecheck
```

Observed result:

```text
app typecheck passed
```

## Known Limits

1. Script catalog scanning is AST-only and intentionally does not validate
   arbitrary runtime imports until execution.
2. Multi-output Script Nodes require a dict return. Complex custom objects must
   be converted by user code.
3. Editor discovery is best-effort and falls back to system default file
   opening when a known IDE cannot be resolved.
4. The runtime currently maps script outputs to the downstream message payload;
   richer per-edge output/input mapping can be added later if the product needs
   it.

## Follow-Up Queue

1. Add a full live desktop smoke with Agent -> Script -> Agent once the
   real-worker cost is acceptable.
2. Add explicit UI around script diagnostics so syntax/type annotation errors
   are more visible than catalog toasts.
3. Consider a script file watcher later; the current explicit Compile button is
   deliberate and avoids surprise imports or window reloads.

## Skill/Archive Files

Installed skill:

```text
C:\Users\13429\.codex\skills\multi-agent-tcp\archive\runtime-backend\blueprint_script_function_node_runtime_bridge_2026-05-31.md
```

Repository snapshot:

```text
KM_docs/skills-snapshot/archive/runtime-backend/blueprint_script_function_node_runtime_bridge_2026-05-31.md
```
