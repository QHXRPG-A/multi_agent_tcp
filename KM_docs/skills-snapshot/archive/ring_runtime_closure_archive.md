# Ring Runtime Closure Archive

This archive records the 2026-05-12 closure of the previous ring-session runtime direction.

## Summary

- Removed special ring runtime semantics from the current runtime/control-plane path.
- Deleted ring-session state/API concepts from live code, including `RingSession*`, `ring.register`, `ring_phase`, `ring_session_id`, and ring-only final-output handling.
- Unified cyclic and acyclic graphs under the same runtime behavior: ordinary outgoing batches, required target satisfaction, downstream queues, and fan-in joins.
- Kept cycle detection as observability only through `GraphDefinition.agent_cycle_groups()` and surfaced `cycle_groups` in organization/status views.
- Added structured dispatch no-op semantics: an exact `""` or numeric `0` body satisfies that target without queueing downstream work.
- Documented stable framework skill/rule injection at private worker context materialization/rebind, with per-message runtime state continuing through `framework_context`.

## Current Behavior

Cycles are not scheduling units. Nested cycles, branch cycles, and shared-node cycles are observed as SCC groups, but they do not create special agents, sessions, phases, queue gates, or final-output paths.

The only runtime communication semantic is:

```text
agent.dispatch
  -> outgoing batch staging
  -> all required targets satisfied by message or no-op
  -> downstream AgentNode queues
  -> join aggregation when configured
```

## Files Changed

- `graph_runtime.py`
- `graph_control.py`
- `__init__.py`
- `agent_launch_context.py`
- `test_agent_runtime.py`
- `test_graph_control.py`
- `KM_docs/skills-snapshot/SKILL.md`
- `KM_docs/skills-snapshot/knowledge_base/README.md`
- `KM_docs/skills-snapshot/knowledge_base/ring_structure_solution.md`
- `KM_docs/skills-snapshot/tasks/current_goals.md`
- `KM_docs/skills-snapshot/tasks/node_runtime_tasks.md`

## Verification

```text
python -m pytest -q
126 passed
```

## Current Knowledge Location

- `knowledge_base/ring_structure_solution.md`: current cycle closure note.
- `knowledge_base/core_architecture.md`: `GraphDefinition.agent_cycle_groups()` observation API.
- `tasks/node_runtime_tasks.md`: current runtime priorities and no-op dispatch semantics.

Historical single-pass ring-session details remain in `archive/ring_session_runtime_archive.md` and are not current behavior.

---

## 2026-05-12 Agent Ring Circulation Limit Update

The runtime direction reopened part of cycle handling as a bounded forwarding guard, without restoring the old ring-session scheduler.

Completed:

- Replaced SCC-only cycle observation with concrete simple AgentNode ring detection for direct `exec` AgentNode edges.
- Defined the smallest valid ring as two Agents pointing at each other: `A -> B`, `B -> A`.
- Added `AgentRing` metadata with default IDs such as `ring1`, `ring2`, stable topology metadata, ordered nodes, edge pairs, closing edge, and `max_circulations`.
- Added runtime-owned per-Agent ring circulation count dictionaries, shaped like `{ring1: x, ring2: y}`.
- Kept default `max_circulations` at `1`, with graph config support for later user-provided `agent_ring_max_circulations`.
- Counted one circulation when a message traverses the closing edge of a ring, for example `D -> A` in `A -> B -> C -> D -> A`, or `B -> A` in `A -> B -> A`.
- Preserved independent counters for nested rings, overlapping rings, and shared-edge rings.
- When all rings covering a forwarding edge are exhausted, the runtime removes that target from active downstream connections and rejects new outgoing batches for that edge.
- Kept ordinary outgoing batches, `agent.dispatch`, queueing, joins, and no-op semantics as the communication substrate.

Verification:

```text
python -m pytest test_agent_runtime.py test_graph_control.py -q
78 passed
```

Implementation files:

- `graph_runtime.py`
- `graph_control.py`
- `__init__.py`
- `test_agent_runtime.py`
- `test_graph_control.py`
