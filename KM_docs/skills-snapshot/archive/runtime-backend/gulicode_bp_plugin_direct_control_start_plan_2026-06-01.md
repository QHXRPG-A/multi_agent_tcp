# GuLiCode BP Plugin Direct Control and Start Plan - 2026-06-01

## Summary

This pass moved user-visible blueprint control into the `gulicode-bp` plugin
surface and removed the plugin's public dependency on the old standalone
`blueprint.planning.*` / Top Agent planning entrypoints.

The plugin now owns CRUD-facing MCP tools, deterministic start-plan generation,
start-plan validation, and the confirmed start flow. `DesktopBlueprintService`
and `GraphRuntimeControlPlane` remain the runtime source of truth; the plugin
does not copy the scheduler.

## Implemented

Plugin MCP/API:

1. Added allowlisted commands:
   - `blueprint.create`
   - `blueprint.delete`
   - `blueprint.plan.create`
   - `blueprint.plan.validate`
2. Added MCP convenience tools:
   - `blueprint_create`
   - `blueprint_delete`
   - `blueprint_plan_create`
   - `blueprint_plan_validate`
3. Removed public plugin allowlist/tool exposure for `blueprint.planning.*`.
4. Kept `blueprint_start` as an execution command that accepts a confirmed
   plan instead of generating one.

DesktopBlueprintService:

1. Added blueprint create with a default graph document.
2. Added soft delete to `.multi_agent_workspace/blueprints/.trash`.
3. Added `BLUEPRINT_IN_USE` rejection when a live run still owns the blueprint.
4. Added deterministic start-plan generation from the current graph, user task,
   and selected `startNodeIds`.
5. Added plan override handling limited to `user_goal`,
   `agent_descriptions`, `tasks`, and `run_policy`.
6. Added plan validation using the existing runtime validation contract.
7. Changed user-facing `BAD_START_PLAN` wording away from
   `TopAgentStartPlan`; internal class names remain for compatibility.

Frontend/workbench:

1. Added platform bridge methods for create/delete/plan create/plan validate.
2. Removed plugin workbench implementations of `blueprint.planning.*`.
3. Changed the Blueprint runtime panel into a two-step flow:
   `Generate start plan` -> `Confirm run`.
4. Added plan preview display with validation errors and warnings.
5. Hid the composer blueprint-planning mode when the platform does not expose
   the old planning API.
6. Updated English, Simplified Chinese, and Traditional Chinese runtime copy.

Docs/skill/plugin:

1. Updated `plugins/gulicode-bp/README.md`.
2. Updated `plugins/gulicode-bp/skills/blueprint/SKILL.md`.
3. Updated the installed `multi-agent-tcp` skill wording around plugin-owned
   start plans.
4. Reinstalled the personal plugin mirror with
   `python plugins\gulicode-bp\scripts\install_personal_plugin.py --force`.

## Files Changed

Plugin:

1. `plugins/gulicode-bp/mcp/gulicode_bp_mcp.py`
2. `plugins/gulicode-bp/README.md`
3. `plugins/gulicode-bp/skills/blueprint/SKILL.md`
4. `plugins/gulicode-bp/web/dist/**` through the installer build.

Backend/runtime service:

1. `desktop_blueprint_service.py`
2. `test_desktop_blueprint_service.py`

Frontend/workbench:

1. `GuLiCode/packages/app/src/context/platform.tsx`
2. `GuLiCode/packages/app/src/entry.tsx`
3. `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.tsx`
4. `GuLiCode/packages/app/src/components/prompt-input.tsx`
5. `GuLiCode/packages/app/src/i18n/en.ts`
6. `GuLiCode/packages/app/src/i18n/zh.ts`
7. `GuLiCode/packages/app/src/i18n/zht.ts`

Docs/skill:

1. `README.md`
2. `C:\Users\qiuhaoxuan\.codex\skills\multi-agent-tcp\SKILL.md`
3. `C:\Users\qiuhaoxuan\.codex\skills\multi-agent-tcp\tasks\current_goals.md`
4. `KM_docs/skills-snapshot/tasks/current_goals.md`

## Verification

Python:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp
python -m py_compile desktop_blueprint_service.py plugins\gulicode-bp\mcp\gulicode_bp_mcp.py
# pass

pytest -q test_desktop_blueprint_service.py
# 52 passed, 1 skipped
```

Frontend:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\app
bun run typecheck
# pass
```

Plugin:

```powershell
python C:\Users\qiuhaoxuan\.codex\skills\.system\plugin-creator\scripts\validate_plugin.py F:\src\Package\Script\Python\multi_agent_tcp\plugins\gulicode-bp
# pass

python plugins\gulicode-bp\scripts\install_personal_plugin.py --force
# pass
```

Manual/smoke:

1. Imported the installed personal plugin MCP module from
   `C:\Users\qiuhaoxuan\plugins\gulicode-bp`.
2. Ran create -> plan.create -> plan.validate -> delete against a temp project.
3. Opened the workbench route with Playwright and verified the runtime panel
   shows the `Generate start plan` and `Confirm run` actions.

## Known Boundary

The plugin is still repo-bound after this pass. The MCP process locates runtime
code through `GULICODE_BP_REPO_ROOT` or by walking parents for
`desktop_blueprint_service.py`. A user who installs only the plugin but does
not have a local `multi_agent_tcp` checkout cannot use most functionality.

This boundary is now the highest priority task in `tasks/current_goals.md`.

Preferred next direction:

1. Package the Python runtime as a wheel or plugin-private install payload.
2. Create a plugin-owned venv during install.
3. Rewrite `.mcp.json` to use the plugin-owned Python/runtime path.
4. Keep repo-bound development mode as a first-class local workflow.

## Skill/Archive Files

Installed skill:

```text
C:\Users\qiuhaoxuan\.codex\skills\multi-agent-tcp\archive\runtime-backend\gulicode_bp_plugin_direct_control_start_plan_2026-06-01.md
```

Repository snapshot:

```text
KM_docs/skills-snapshot/archive/runtime-backend/gulicode_bp_plugin_direct_control_start_plan_2026-06-01.md
```
