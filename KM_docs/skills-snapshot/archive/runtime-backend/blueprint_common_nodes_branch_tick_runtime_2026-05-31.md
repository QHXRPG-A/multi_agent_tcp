# Blueprint Common Branch/Tick Runtime - 2026-05-31

## Summary

This pass added runtime support for framework-owned common Blueprint nodes:
`Branch` and `Tick`.

The graph model now accepts `common_nodes`, validates non-Agent/non-Script port
types, lets Agents dispatch to Branch nodes, and runs Tick nodes from the
framework scheduler.

## Implemented

Graph model:

1. Added `CommonNode` with `kind: "branch"` and `kind: "tick"`.
2. Added `every_n_ticks` for Tick nodes and clamps it to at least `1`.
3. Added `common_nodes: Dict[str, CommonNode]` to `GraphDefinition`.
4. `graph_definition_from_dict` parses object and array forms of
   `common_nodes`.
5. Existing Blueprint JSON without `common_nodes` defaults to `{}`.
6. `schema_version` remains `1`.

Port type validation:

1. Added backend port data types: `message`, `bool`, and `tick`.
2. Branch input is `condition: bool`.
3. Branch outputs are `true: message` and `false: message`.
4. Tick output is `tick: tick`.
5. Route and legacy terminal ports default to `message`.
6. Agent and Script ports remain unchecked.
7. `GraphDefinition.validate_port_types()` rejects mismatched checked ports.
8. Runtime start paths call validation so hand-written JSON cannot bypass the
   UI validation.

Control plane:

1. `message.create_batch` can require common node targets.
2. `agent.dispatch` can target a Branch common node.
3. Agent framework context exposes `downstream_nodes`, `downstream_agents`, and
   `common_nodes`.
4. Runtime-active downstream context respects exhausted ring edges.
5. Organization and scoped organization views include common nodes and
   framework connections.

Branch runtime:

1. Branch messages are queued in framework-owned common node queues.
2. `GraphRuntime.tick()` processes Branch queues.
3. Branch reads a strict bool from the message body itself or from
   `body["condition"]`.
4. Non-bool input emits `BranchNodeFailed`; it does not default to false.
5. A true condition emits only the `true` output path.
6. A false condition emits only the `false` output path.
7. Missing downstream edges are treated as no-op and recorded as events.

Tick runtime:

1. Tick nodes are registered by `configure_common_nodes`.
2. Each framework tick increments per-Tick counters.
3. Tick emits only when `tick_count % every_n_ticks == 0`.
4. `every_n_ticks >= 1`, so Tick frequency cannot exceed framework tick
   frequency.
5. Tick emits a standard payload with `type: "tick"`, `tick_node_id`,
   `tick_count`, `every_n_ticks`, and `created_at`.
6. Tick applies backpressure per downstream Agent: if that target already has a
   queued or dispatching tick from the same Tick node, the next emit is skipped
   and a `TickNodeSkipped` event is recorded.
7. Tick-only start plans are allowed when the graph has at least one Tick
   source and no explicit `start_nodes`.

Status and cleanup:

1. Runtime status includes common node state.
2. Queue status includes `by_common_node` and pending common message ids.
3. Final-state summaries include pending common messages.
4. Runtime cancellation clears common queues and pending common messages.

## Files Changed

Runtime/backend:

1. `graph_runtime.py`
2. `graph_control.py`
3. `__init__.py`

Tests:

1. `test_graph_control.py`
2. `test_agent_runtime.py`

## Verification

Python checks:

```powershell
cd D:\agent\multi_agent_tcp
python -m py_compile graph_runtime.py graph_control.py __init__.py
python -m pytest test_graph_control.py -q
python -m pytest test_agent_runtime.py -q -k "not real_codex"
```

Observed result during implementation:

```text
py_compile passed
test_graph_control.py: 13 passed
test_agent_runtime.py -k "not real_codex": 103 passed, 3 deselected
```

Focused new coverage:

1. `common_nodes` JSON parsing and backend port type mismatch rejection.
2. Control-plane `agent.dispatch` to Branch.
3. Branch true/false routing.
4. Branch non-bool failure.
5. Tick interval emission.
6. Tick downstream backpressure.
7. Tick-only start plan validation.

Known external limit:

```text
Full real Codex E2E was not used as a pass/fail gate because the machine hit a
Codex usage limit during an earlier broad test run.
```

## Known Limits

1. Agent and Script endpoints remain untyped by design in this pass.
2. Branch uses strict bool only; string coercion is intentionally not supported.
3. Tick backpressure is per downstream Agent and checks queued/dispatching tick
   messages from the same Tick source.

## Follow-Up Queue

1. Add full live smoke when Codex usage limits are not a blocker.
2. Consider status-panel UI polish for common node queues if users need to
   inspect Branch/Tick internals during long live runs.
3. Extend Script port typing only after compatibility expectations are clear.

## Skill/Archive Files

Installed skill:

```text
C:\Users\13429\.codex\skills\multi-agent-tcp\archive\runtime-backend\blueprint_common_nodes_branch_tick_runtime_2026-05-31.md
```

Repository snapshot:

```text
KM_docs/skills-snapshot/archive/runtime-backend/blueprint_common_nodes_branch_tick_runtime_2026-05-31.md
```
