# Blueprint Framework Worker Runtime Split and Plugin Restart Scripts

Date: 2026-06-16

## Summary

This archive records the split between Full Agent and Worker Agent framework
runtime instructions, plus the script path used to refresh the installed
`gulicode-bp` plugin runtime after framework asset changes.

The new contract is:

- Top Agent nodes still use `framework-top-agent-runtime`.
- Full Agent nodes (`node_type == "agent"`) use `framework-agent-runtime`.
- Worker Agent nodes (`node_type == "worker_agent"`) use
  `framework-worker-runtime`.
- Full Agent framework skill/rule files keep orchestration and business
  workflow context, including POPO planning-table flow, trunk-to-release table
  sync, game source lookup, and knowledge roots.
- Worker framework skill/rule files only carry workspace execution boundaries:
  private checkout, shared workspace, workspace MCP submit/status/diff/publish,
  downstream dispatch/status, and no direct shared-root mutation.
- Runtime-selected business skill indexes are generated per Agent launch under
  the selected framework runtime skill directory.

Use this record when:

- a Full Agent unexpectedly sees three-workspace or `workspace_submit` rules
- a Worker Agent launches without private-checkout/workspace MCP guidance
- the Inspector or runtime references `framework-agent-runtime` for a Worker
  Agent
- the installed `gulicode-bp` plugin still runs stale framework assets
- `restart-gulicode-bp-plugin.cmd` returns `1` after a package refresh

## Main Files

- `agent_launch_context.py`
- `desktop_blueprint_service.py`
- `framework_assets/skills/framework-agent-runtime/SKILL.md`
- `framework_assets/skills/framework-worker-runtime/SKILL.md`
- `framework_assets/rules/framework-agent-runtime.md`
- `framework_assets/rules/framework-worker-runtime.md`
- `sync-gulicode-bp-framework-assets.ps1`
- `restart-gulicode-bp-framework-fast.cmd`
- `restart-gulicode-bp-plugin.cmd`
- `restart-gulicode-bp-plugin.ps1`
- `test_agent_runtime.py`
- `test_desktop_blueprint_service.py`

## Runtime Selection

`agent_launch_context.py` now defines:

```text
FRAMEWORK_WORKER_RUNTIME_NAME = "framework-worker-runtime"
```

Framework runtime selection is based on the node:

```text
top-agent-*      -> framework-top-agent-runtime
node_type agent  -> framework-agent-runtime
worker_agent     -> framework-worker-runtime
```

`materialize_framework_skill()` and `materialize_framework_rule()` use the same
node-based runtime-name resolver, so the materialized private Codex home and
rule catalog stay aligned.

`copy_skill_dir_to_codex_home()` also uses the Windows long-path wrapper for
delete/copy operations so large private Codex home trees do not fail during
runtime context materialization.

## Skill Index Paths

The selected business skill index is not a fixed repository file. It is
generated for each launched Agent under the selected framework runtime skill:

```text
Full Agent:
<run>\runtime_agent_context\<agent_id>\codex_home\skills\framework-agent-runtime\selected_skills_index.md

Worker:
<run>\agents\<agent_id>\private\codex_home\skills\framework-worker-runtime\selected_skills_index.md
```

The absolute generated path is written into:

```text
adapter_options.execution_context.private_context.selected_skill_index_path
adapter_options.prompt_execution_context.private_context.selected_skill_index_path
```

The fixed planning-table business skill index remains:

```text
F:\trunk_helper\AISkills\planning-table-skill-index.md
```

and is referenced by `planning_table_popo_workflow.md`.

## Full Agent Runtime Content

`framework-agent-runtime` keeps framework orchestration and business context but
does not contain worker-only workspace rules. It includes:

- POPO planning-table workflow
- trunk-to-release planning-table sync guidance
- release-table no-submit rule; release table commits stay user-owned
- game source root: `F:\src\Package\Script\Python`
- game expert knowledge root: `F:\src\Package\Script\Python\.codemaker\expert`
- Excel export/diff-flow references for planning-table changes

It intentionally excludes:

- three workspace zones
- shared workspace operation rules
- private checkout mutation rules
- `workspace_checkout`
- `workspace_submit`
- `workspace_publish`

## Worker Runtime Content

`framework-worker-runtime` is focused on workspace-limited execution. It
describes:

- three workspace zones and their boundaries
- private checkout as the only code-mutation area
- shared workspace as read/coordination context
- workspace MCP status/diff/submit/publish flow
- downstream dispatch/status reporting
- no direct edits in the shared project root

## Installed Plugin Refresh

The one-step packaged-plugin refresh command is:

```powershell
.\restart-gulicode-bp-plugin.cmd -Install -SkipWebBuild -SyncFrameworkAssets -NoOpen
```

This refreshes the personal plugin package, installs or refreshes the plugin
runtime Python package, syncs framework assets, and restarts the plugin service.

`restart-gulicode-bp-framework-fast.cmd` is the faster framework-assets-only
path. It does not force a package reinstall.

`sync-gulicode-bp-framework-assets.ps1` validates that both runtime skill/rule
sets exist after sync:

```text
framework-agent-runtime
framework-worker-runtime
```

## Restart Health Logging

`restart-gulicode-bp-plugin.ps1` now defaults to a longer post-restart health
window and writes a restart transcript:

```text
HealthTimeoutSeconds default: 45
Default log:
F:\src\Package\Script\Python\multi_agent_tcp\logs\restart-gulicode-bp-plugin-YYYYMMDD-HHMMSS.log
```

The script also accepts:

```powershell
-HealthTimeoutSeconds 90
-LogFile logs\custom-restart.log
```

Failures now report the specific failed health check and the last observed
detail, for example whether `collaboration` on `8787` or `popo` on `3100`
timed out.

The earlier observed `exit 1` was a post-restart health-check false negative:
runtime install and service startup had completed, and subsequent checks showed
both health endpoints as `200`.

## Verification

Focused checks run during this work:

```powershell
python -m py_compile agent_launch_context.py
python -m pytest test_agent_runtime.py -q -k "not real_codex"
python -m pytest test_desktop_blueprint_service.py -k framework -q
bun test GuLiCode/packages/app/src/pages/session/blueprint-side-panel.test.ts
.\sync-gulicode-bp-framework-assets.ps1 -Quiet
```

Results:

- `agent_launch_context.py` compile passed
- `test_agent_runtime.py -k "not real_codex"`: 117 passed, 3 deselected
- `test_desktop_blueprint_service.py -k framework`: 6 passed
- `blueprint-side-panel.test.ts`: 34 passed
- framework asset sync passed

Installed runtime import check after plugin refresh:

```text
FRAMEWORK_WORKER_RUNTIME_NAME = framework-worker-runtime
worker skill marker present
worker rule marker present
full-agent worker-only text absent
```

Post-refresh service checks:

```text
http://127.0.0.1:8787/api/health -> 200
http://127.0.0.1:3100/health -> 200
service.json status -> running
```

`restart-gulicode-bp-plugin.ps1` syntax was also checked after adding logging
and `HealthTimeoutSeconds` support:

```text
PowerShell parser: parse ok
```
