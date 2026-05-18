# Blueprint Common Config Paths - 2026-05-19

## Summary

The GuLiCode blueprint path now avoids hard-coded local absolute paths in
renderer/runtime defaults. User-machine paths are owned by the blueprint common
config panel and validated before a blueprint can start.

## Completed

1. Removed the hard-coded default `skill_dir` from the blueprint model.
   `DEFAULT_SKILL_DIR` is now empty, so users must provide their own local
   skill directory when a blueprint uses skills.
2. Added startup validation for blueprint common config:
   - `project_workdir` is always required and must be absolute.
   - `skill_dir` is required when any Agent uses selected/all/upstream skills
     or has a non-empty `skills` list.
   - `rule_dir` is required when any Agent has `rule_paths`.
   - Optional path fields, when filled, must also be absolute.
3. Added `?` help buttons to all blueprint common config fields using the same
   `InspectorTipButton` popover behavior as the inspector.
4. Added a blocking config-required dialog before blueprint start. It appears
   before save/start, lists the missing or invalid fields, and exposes only a
   single confirm button in the dialog body.
5. Changed Electron rule catalog values to store rule filenames instead of
   machine-local absolute paths in Agent `rule_paths`.
6. Added backend `blueprint.start` validation so IPC or direct desktop-service
   calls cannot bypass the common config requirement.
7. Added backend start-time materialization that writes common
   `project_workdir` into Agent `cwd` and resolves relative `rule_paths` from
   common `rule_dir`.
8. Preserved the desktop live private-context path:
   `GraphRuntime(enforce_private_agent_context=True)` now runs through
   framework-managed private checkout, private `CODEX_HOME`,
   `framework-agent-runtime`, `AGENTS.md`, Workspace API context, and
   authorized skill/rule materialization.

## Files Touched

- `GuLiCode/packages/app/src/pages/session/blueprint-model.ts`
- `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.tsx`
- `GuLiCode/packages/app/src/i18n/en.ts`
- `GuLiCode/packages/app/src/i18n/zh.ts`
- `GuLiCode/packages/app/src/i18n/zht.ts`
- `GuLiCode/packages/desktop-electron/src/main/blueprint-catalog.ts`
- `GuLiCode/packages/desktop-electron/src/main/blueprint-runtime.test.ts`
- `desktop_blueprint_service.py`
- `test_desktop_blueprint_service.py`

## Verification

Passed:

```powershell
cd GuLiCode\packages\app
bun test --preload ./happydom.ts ./src/pages/session/blueprint-model.test.ts ./src/pages/session/blueprint-side-panel.test.ts ./src/i18n/parity.test.ts
bun run typecheck
bun run build

cd ..\desktop-electron
bun test ./src/main/blueprint-catalog.test.ts ./src/main/ipc-blueprint-runtime.test.ts ./src/main/blueprint-runtime.test.ts
bun run typecheck
bun run build

cd ..\..\..
pytest -q test_desktop_blueprint_service.py
python -m py_compile desktop_blueprint_service.py test_desktop_blueprint_service.py
```

Known remaining failure outside this change:

```text
pytest -q test_desktop_blueprint_service.py test_workspace_manager.py
```

still fails
`test_workspace_manager.py::test_agent_checkout_dulwich_merge_accepts_non_overlapping_same_file_changes`.
The observed result is a `conflict` status for `src/shared.txt` where the test
expects a successful non-overlapping merge.

## Next

1. Manually smoke the packaged/dev blueprint live run path with user-provided
   common config paths.
2. Fix the `DulwichWorkspaceManager` non-overlapping same-file merge regression
   before treating the backend suite as fully green.
3. Continue durable blueprint persistence decisions around local draft,
   project JSON, workspace records, and migration.
