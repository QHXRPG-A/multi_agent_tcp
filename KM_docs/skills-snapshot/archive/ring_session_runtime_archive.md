# Ring session runtime archive

This archive records the recent ring / 环状结构 runtime work so the current knowledge base can stay focused on the live spec.

## Date

2026-05-11

## Summary

- Added single-pass ring-session support to the runtime/control plane path.
- Treats the ring-class `agent` as a normal outer `agent`; the ring behavior stays inside framework-owned runtime scheduling.
- Added dynamic reachable-target views for ring phases, entry-message merging, auditor gating, and idempotent final output.
- Added control-plane support for `ring.register` and ring-aware dispatch/batch handling.

## Repo files changed in the implementation

- `graph_runtime.py`
- `graph_control.py`
- `__init__.py`
- `test_agent_runtime.py`
- `test_graph_control.py`

## Verification

```text
python -m pytest test_agent_runtime.py test_graph_control.py test_workspace_api.py test_workspace_manager.py -q
120 passed
```

## Current knowledge location

- `knowledge_base/ring_structure_solution.md`
