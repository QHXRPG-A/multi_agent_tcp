# Codex-Only Worker Cleanup - 2026-06-02

## Summary

The project runtime, desktop UI, docs, examples, and local project artifacts
were cleaned up to use Codex-only worker execution.

## Changes

- Removed the retired CLI adapter path and package exports.
- Updated backend defaults, registry loading, graph nodes, Blueprint UI model
  catalogs, Electron model discovery, tests, and examples to use Codex.
- Cleaned project docs, knowledge snapshots, diagrams, ignored local artifacts,
  generated bundles, logs, and workspace snapshots so the current tree has no
  remaining retired-worker references.

## Verification

- `python -m pytest -q test_agent_runtime.py`
- `python -m pytest -q test_desktop_blueprint_service.py`
- `python -m pytest -q test_multi_agent_tcp_cli.py test_registry_skill_selection.py test_skill_space.py`
- `bun test --preload ./happydom.ts ./src/pages/session/blueprint-model.test.ts ./src/i18n/parity.test.ts`
- `bun run typecheck` in `GuLiCode/packages/app`
- `bun test ./src/main/blueprint-catalog.test.ts`
- `bun run typecheck` in `GuLiCode/packages/desktop-electron`
- Final full-tree retired-worker keyword search returned no matches.
