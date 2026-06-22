# GuLiCode BP Reinstall Workbench Guardrail

Date: 2026-06-17

## Summary

This archive records the reinstall/restart script hardening after a packaged
Workbench opened the wrong project and, in another run, served the fallback web
UI instead of the built GuLiCode app.

The fixed contract is:

- One-click reinstall/restart should target the main project by passing
  `-ProjectDir F:\src\Package\Script\Python\multi_agent_tcp`.
- `start-gulicode-debug.ps1` and `restart-gulicode-bp-plugin.ps1` must keep the
  repo root and the target Blueprint project separate.
- The returned Workbench URL is valid only after `config.js`, built-app HTML,
  and `blueprint.list(projectDir)` are verified.
- `--skip-web-build` is allowed only when `GuLiCode\packages\app\dist` is a
  complete built app with `index.html` and `assets\`.
- If the GuLiCode app source exists but dist is missing or incomplete, the
  installer must not silently copy `plugins\gulicode-bp\web\index.html` as the
  Workbench.
- A restart exit code `1` can be ignored only when health and Workbench binding
  checks pass. Build/install errors such as missing `vite`, missing app dist, or
  fallback UI are real failures.

Use this record when:

- the user asks why reinstall/restart returned exit code `1`
- the Workbench URL points at a temporary Codex worktree
- the Workbench shows the simple fallback page instead of the GuLiCode app
- `--skip-web-build` installs an old or incomplete frontend
- restart logs mention `command not found: vite`, `GuLiCode app dist is
  missing`, or `fallback web UI`
- one-click reinstall/restart should return only the plugin Workbench URL

## Main Files

- `plugins/gulicode-bp/scripts/install_personal_plugin.py`
- `start-gulicode-debug.ps1`
- `restart-gulicode-bp-plugin.ps1`
- `restart-gulicode-bp-plugin.cmd`
- `test_desktop_blueprint_service.py`
- `KM_docs/skills-snapshot/SKILL.md`
- `C:\Users\qiuhaoxuan\.codex\skills\multi-agent-tcp\SKILL.md`

## Installer Behavior

The plugin installer now treats the GuLiCode app dist as complete only when:

```text
GuLiCode\packages\app\dist\index.html
GuLiCode\packages\app\dist\assets\
```

both exist.

When building the app, the installer checks the GuLiCode workspace for
`node_modules\.bin\vite*`. If it is missing and `bun.lock` is present, it runs:

```powershell
bun install
```

from the GuLiCode workspace root before running:

```powershell
bun run build
```

from `GuLiCode\packages\app`.

When `--skip-web-build` is used and the app dist is missing or incomplete, the
installer raises an explicit error containing:

```text
Refusing to install the fallback web UI as the plugin Workbench.
```

Fallback `plugins\gulicode-bp\web\index.html` is reserved only for packages that
do not include the GuLiCode app source.

## Runtime Wheel Refresh

The runtime wheel install path was changed to avoid unnecessary dependency
reinstalls while still refreshing same-version source code:

```text
pip install --upgrade <wheel>
pip install --upgrade --force-reinstall --no-deps <wheel>
```

Runtime wheel validation also checks that required package files exist before a
release package is accepted.

## Start Script Binding

`start-gulicode-debug.ps1` now accepts:

```powershell
-ProjectDir <project-dir>
```

The script still uses its own repo root for the installer and app source, but
uses `ProjectDir` for:

- the Workbench `--project-dir`
- `logs\gulicode-bp-workbench-ready.json`
- Workbench stdout/stderr logs
- the binding checks after startup

The new binding check reads:

```text
<origin>/config.js
```

and verifies:

- `projectDir` equals the requested project
- `blueprintId` equals the requested Blueprint id
- the page HTML is the built GuLiCode app, not fallback HTML containing
  `<main class="shell">`
- the page references built assets through `assets/index-*`
- `POST <origin>/api/blueprint` with `blueprint.list(projectDir)` succeeds

The script prints:

```text
[start-gulicode-debug] project = ...
[start-gulicode-debug] blueprints = N
```

so a caller can see which project was actually loaded.

## Restart Script Binding

`restart-gulicode-bp-plugin.ps1` also accepts `-ProjectDir` and passes it through
to `start-gulicode-debug.ps1`.

The ready file is read from the target project logs, not always the repo where
the script lives:

```text
<ProjectDir>\logs\gulicode-bp-workbench-ready.json
```

This prevents a restart launched from a temporary Codex worktree from returning
a Workbench URL bound to that temporary worktree when the intended project is:

```text
F:\src\Package\Script\Python\multi_agent_tcp
```

## Skill Rule

The `multi-agent-tcp` skill now makes this the default one-click command:

```powershell
F:\src\Package\Script\Python\multi_agent_tcp\restart-gulicode-bp-plugin.cmd -Install -SkipWebBuild -SyncFrameworkAssets -NoOpen -ProjectDir F:\src\Package\Script\Python\multi_agent_tcp
```

For one-click reinstall/restart requests, if the user did not ask for logs or
diagnostics, the final response should default to only the plugin Workbench URL.

## Verification

Syntax and parser checks:

```powershell
python -m py_compile plugins\gulicode-bp\scripts\install_personal_plugin.py test_desktop_blueprint_service.py
```

PowerShell parser checks passed for:

```text
start-gulicode-debug.ps1
restart-gulicode-bp-plugin.ps1
```

Targeted pytest passed:

```text
test_gulicode_bp_installer_installs_runtime_dependencies_and_validates
test_gulicode_bp_installer_skip_web_build_refuses_fallback_when_app_dist_missing
test_gulicode_bp_installer_build_installs_gulicode_dependencies_when_vite_missing
test_gulicode_bp_release_package_contains_bootstrap_runtime_wheel_and_web_dist
```

Result:

```text
4 passed
```

Live smoke command:

```powershell
.\start-gulicode-debug.ps1 -SkipPluginInstall -SkipWebBuild -NoOpen -ProjectDir F:\src\Package\Script\Python\multi_agent_tcp -BlueprintId default
```

Smoke result:

```text
health = True
workbench = True http://127.0.0.1:3884/Rjpcc3JjXFBhY2thZ2VcU2NyaXB0XFB5dGhvblxtdWx0aV9hZ2VudF90Y3A/blueprint-window/default
blueprints = 1
```

