# Blueprint Run Diff And Workspace Scope - 2026-05-26

## Summary

This session implemented and live-debugged the GuLiCode Blueprint Diff path for
run-scoped `workspace_submit` changesets. The key product rule is that
Blueprint Diff is backed by the run archive, not the right global Review panel.

The feature reads only:

```text
changesets/<changeset_id>/changeset.json
changesets/<changeset_id>/patch.diff
changesets/<changeset_id>/submit_result.json
```

`acceptedDiffs` includes only accepted textual patches. Conflict, rejected,
pending, and failed changesets remain in grouped metadata/status UI and do not
enter accepted text diff rendering. Binary files are metadata only.

## Implemented

Backend/runtime:

1. `workspace_manager.py` now exposes Blueprint run summary/detail helpers and
   file metadata for `binary` / `has_patch`.
2. Blueprint Diff lookup handles archived runs: after `archive_run`, the
   `RunWorkspace` path is updated, and the desktop service can reopen
   active/archived/failed run paths when the old active path is stale.
3. Final report archive mapping was adjusted to preserve the pre-archive path
   for relative path computation.
4. `workspace_publish` cross-Agent same-path writes now block silent
   last-write-wins overwrites. A later Agent must read the shared file and
   `shared/manifest.json`, then publish the full replacement content with
   `expected_version`.
5. Ordinary Agent rules and MCP tool docs now explicitly describe the
   `expected_version` workflow for shared report/artifact continuation.
6. Default AgentNode `write_scope` is now project-wide `["**"]`; legacy
   `["shared/reports/**"]` nodes are migrated to the new default. Users should
   not need to manually add `docs/**` for normal Blueprint Diff smoke runs.

Desktop bridge / UI:

1. `desktop_blueprint_service.py` exposes `blueprint.runDiff` and
   `blueprint.changesetDiff`.
2. Electron main/preload/renderer Platform surfaces expose
   `blueprintRunDiff` and `blueprintChangesetDiff`.
3. `BlueprintSidePanel` renders the compact `蓝图 Diff` button after
   `蓝图通用配置` and shows an absolute overlay inside the blueprint canvas
   area, not in the global Review panel.
4. The overlay groups by Agent/task/changeset, displays status/file/line
   counts, and lazy-loads changeset details.
5. Accepted changeset signature changes dispatch `workspace.diff.changed` so
   the global VCS refresh path can run without making the global Review panel
   the Blueprint Diff source.

## Live Debug Findings

Observed run:

```text
D:\agents_work_test\.multi_agent_workspace\runs\archived\run-0ee31b7da2bc
```

Facts after backend fix:

```text
summary.total = 3
summary.accepted = 3
summary.files = 3
summary.additions = 42
acceptedDiffs files:
- docs/blueprint_diff_test_agent_3.md
- docs/blueprint_diff_test_agent_1.md
- docs/blueprint_diff_test_agent_2.md
```

The right global Review panel can still show `0` for `D:\agents_work_test`
because that project is not a Git repository. For these manual checks, the
Blueprint Diff overlay is the expected source of truth.

## Remaining High-Priority Manual Tests

1. Sequential same-file Blueprint Diff smoke:
   - Three Agents run sequentially/blocking.
   - All use `workspace_checkout` / `workspace_submit`.
   - All target one project file such as
     `docs/blueprint_diff_shared_test.md`.
   - Agent 1 creates the file; Agent 2 syncs/reads current content and appends
     section two; Agent 3 syncs/reads current content and appends section
     three.
   - Expected result: Blueprint Diff shows three changesets for one file, and
     detail lazy-load displays correct incremental diffs.
2. `workspace_submit` conflict Blueprint Diff smoke:
   - Three Agents run in `parallel_all`.
   - All use `workspace_checkout` / `workspace_submit`.
   - All edit the same first line of
     `docs/blueprint_diff_conflict_test.md` with different content.
   - Expected result: Blueprint Diff shows accepted/conflict/rejected status
     distribution correctly; non-accepted changesets do not enter
     `acceptedDiffs`.

## Verification Run During This Session

Python:

```powershell
python -m pytest test_workspace_manager.py test_desktop_blueprint_service.py
python -m pytest test_workspace_api.py test_agent_runtime.py -k "publish or workspace"
python -m pytest test_agent_runtime.py::test_agent_node_from_dict_auto_generates_node_id test_agent_runtime.py::test_agent_node_from_dict_migrates_legacy_report_only_write_scope test_agent_runtime.py::test_agent_node_from_dict_and_worker_config
```

Frontend/app:

```powershell
bun --cwd GuLiCode/packages/app test:unit src/pages/session/blueprint-model.test.ts
bun --cwd GuLiCode/packages/app test:unit src/pages/session/blueprint-side-panel.test.ts
bun --cwd GuLiCode/packages/app typecheck
```

Electron:

```powershell
bun test GuLiCode/packages/desktop-electron/src/main/ipc-blueprint-runtime.test.ts
bun --cwd GuLiCode/packages/desktop-electron typecheck
```

Latest debug startup observed:

```text
renderer: http://localhost:5173/
sidecar: http://127.0.0.1:2559
server ready
```
