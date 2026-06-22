# Blueprint POPO Multi-Structure Routing and Plugin Restart

Date: 2026-06-10

## Summary

This archive records the 2026-06-10 fix for POPO robots bound to multiple
Blueprint structures and the follow-up `gulicode-bp` package/restart.

The user-visible bug was:

```text
This POPO robot is bound to multiple Blueprint structures and the service
cannot decide which structure pool should receive the message.
```

That conflict is no longer the default behavior. POPO message routing now uses a
deterministic target selection policy while preserving existing per-session
continuity.

## Routing Semantics

For global POPO messages that do not carry a `projectDir` or `blueprintId`, the
service now collects candidate bindings from:

- active POPO slot runs for the robot
- registered Blueprint projects whose documents enable the same POPO robot

Candidates are deduplicated by:

```text
projectDir + blueprintId + blueprintStructureId
```

The target binding is chosen in this order:

1. If the same POPO identity already has a non-deleted session for a candidate
   pool, keep routing to that pool.
2. Otherwise, if exactly one candidate has an idle empty live slot, route to
   that candidate.
3. Otherwise, route to the Workbench's most recently opened Blueprint, but only
   if that Blueprint is one of the candidate POPO bindings.
4. If there is still no target, raise `BLUEPRINT_POPO_ROBOT_STRUCTURE_CONFLICT`
   with candidate details and a selection reason.

This keeps ongoing POPO conversations stable and gives new conversations a
predictable fallback when multiple Blueprint structures are available.

## Current Blueprint Tracking

`blueprint.open` now records the current Workbench Blueprint in
`blueprint_project_registry.json` after the document opens successfully:

- `lastOpenedBlueprintId`
- `lastOpenedBlueprintName`
- `lastOpenedAt`

The lower-level `open_blueprint()` method remains a pure read and does not
modify current-Blueprint state. This prevents internal scans over registered
Blueprints from accidentally changing the Workbench fallback target.

## Slot and Binding Changes

The old same-robot, one-structure guard was relaxed. A single POPO robot may now
own multiple structure pools at the same time; `message_global_popo_blueprint_slot`
resolves the target pool before calling `message_blueprint_slot`.

`message_blueprint_slot` accepts an internal preselected POPO binding so a
single request does not resolve the target twice and drift between candidates.

The per-structure active session limit remains unchanged.

## Tests

Focused verification:

```text
python -m py_compile desktop_blueprint_service.py test_desktop_blueprint_service.py
python -m pytest test_desktop_blueprint_service.py -k "popo or slot"
python -m pytest test_popo_agent_bot_run.py
```

Results:

- `test_desktop_blueprint_service.py -k "popo or slot"`: 42 passed
- `test_popo_agent_bot_run.py`: 3 passed

A full `test_desktop_blueprint_service.py` run was also attempted and produced
149 passed, 2 skipped, and 3 failures outside this POPO routing change:

- a Workbench fake missing the newer `popo_status_fn` argument
- two existing live start-plan validation failures

## Package and Restart

The plugin was packaged and installed into:

```text
C:\Users\qiuhaoxuan\plugins\gulicode-bp
```

Release package:

```text
F:\src\Package\Script\Python\multi_agent_tcp\dist\gulicode-bp-0.1.3
```

Package summary:

```text
F:\src\Package\Script\Python\multi_agent_tcp\logs\gulicode-bp-package-ready.json
```

The first full package run completed the web build, install, and standalone
smoke, but cleanup of the release `.runtime` failed because the smoke service
left `gulicode-bp-service.err.log` open. The release smoke service was stopped,
the release `.runtime` directory was removed, and packaging was completed with:

```text
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\package-gulicode-bp-plugin.ps1 -SkipWebBuild -NoSmoke
```

The old installed plugin runtime processes were stopped before reinstalling so
the runtime venv was not locked.

The plugin stack was restarted with:

```text
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\start-gulicode-debug.ps1 -NoOpen -SkipPluginInstall
```

Restart verification returned HTTP 200 for:

- Collaboration health: `http://127.0.0.1:8787/api/health`
- POPO callback health: `http://127.0.0.1:3100/health`
- Mobile: `http://127.0.0.1:3040/mobile`
- Console: `http://127.0.0.1:3040/console`
- Workbench:
  `http://127.0.0.1:4554/Rjpcc3JjXFBhY2thZ2VcU2NyaXB0XFB5dGhvblxtdWx0aV9hZ2VudF90Y3A/blueprint-window/default`

Observed runtime state after restart:

- singleton service pid: `50120`
- POPO callback listener pid on port 3100: `65604`
- collaboration server pid on port 8787: `76944`

## Main Files

- `desktop_blueprint_service.py`
- `test_desktop_blueprint_service.py`
- `package-gulicode-bp-plugin.ps1`
- `start-gulicode-debug.ps1`
