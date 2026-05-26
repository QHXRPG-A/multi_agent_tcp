# Blueprint Checkout Prune Startup Fix - 2026-05-26

## Summary

This pass diagnosed the slow blueprint run startup reported in GuLiCode desktop.
The visible symptom was a large delay between broker startup and the first Agent
registration.

Observed live run:

```text
broker listening: 2026-05-26 20:03:45
first Agent registered: 2026-05-26 20:06:46
delay: about 181 seconds
```

The delay was not TCP broker startup. It was private Agent workspace checkout.

## Root Cause

The project root used for smoke testing was:

```text
D:\agents_work_test
```

That directory contained a large framework workspace:

```text
D:\agents_work_test\.multi_agent_workspace
~109,825 files
```

`workspace_manager.py` already excluded `.multi_agent_workspace` from copied
workspace content, but `_relative_files()` used:

```python
root.rglob("*")
```

This traversed excluded directories before filtering them out. With
`write_scope=["**"]`, private checkout copied by include-scope and scanned the
project tree for each Agent checkout/base. The excluded workspace was therefore
walked repeatedly even though it was not copied.

## Fix

`workspace_manager._relative_files()` now uses top-down `os.walk(root)` and
prunes excluded directories before descending into them.

`_relative_files_from_candidates()` now applies the same pruning for candidate
directories and skips excluded candidates before walking.

Excluded roots/patterns such as the following are never entered:

```text
.multi_agent_workspace
.git
node_modules
```

## Regression Coverage

Added:

```text
test_project_reference_full_scope_prunes_workspace_root_during_checkout
```

The test creates:

```text
docs/a.txt
.multi_agent_workspace/old/hidden.txt
```

Then it monkeypatches `workspace_manager.os.walk` to record traversed
directories and asserts:

1. `docs/a.txt` is copied.
2. `.multi_agent_workspace` is not copied.
3. `.multi_agent_workspace` was not traversed.

## Verification

Targeted tests:

```powershell
python -m pytest -q `
  test_workspace_manager.py::test_project_reference_full_scope_prunes_workspace_root_during_checkout `
  test_workspace_manager.py::test_project_reference_missing_static_scope_does_not_scan_project_root `
  test_workspace_manager.py::test_project_reference_empty_scope_checkout_stays_empty_and_rejects_changes
# 3 passed
```

Full workspace manager test file:

```powershell
python -m pytest -q test_workspace_manager.py
# 38 passed
```

Compile check:

```powershell
python -m py_compile workspace_manager.py test_workspace_manager.py
# pass
```

Real project timing check:

```text
_copy_project_tree(Path("D:\agents_work_test"), tmp, include_scopes=["**"])
elapsed = 0.015s
files = 4
has_workspace = False
```

## Operational Note

Already-running GuLiCode desktop blueprint service Python processes still have
old code loaded. Restart the desktop/debug service before judging startup speed
again.

## Files Changed

1. `workspace_manager.py`
2. `test_workspace_manager.py`
