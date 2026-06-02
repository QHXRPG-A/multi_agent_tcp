# Blueprint Tick Every Seconds Runtime - 2026-06-01

## Summary

This pass changed framework-owned Blueprint Tick nodes from "every N framework
ticks" to "every X seconds". Users now configure Tick with a seconds interval,
and the runtime emits one Tick message only after that interval has elapsed.

The old `every_n_ticks` field remains readable for old graph documents and
snapshots, but runtime state and new graph exports use `every_n_seconds`.

## Implemented

CommonNode model:

1. Added `CommonNode.every_n_seconds` with a minimum value of `1.0`.
2. Kept `CommonNode.every_n_ticks` only as a legacy constructor/from-dict
   compatibility path.
3. Updated `CommonNode.to_dict()` to emit `every_n_seconds` for Tick nodes.
4. Updated `CommonNode.from_dict()` to read `every_n_seconds`, falling back to
   `every_n_ticks` when loading older documents.

GraphRuntime scheduling:

1. Added `_common_tick_last_emit_at` to track per-Tick-node last emission time.
2. `configure_common_nodes()` now prunes stale last-emission state when common
   nodes are removed or converted.
3. `_process_common_nodes()` still runs from the framework frame loop, but Tick
   node emission is now time-based.
4. The first frame after a Tick node is configured records the baseline time and
   does not emit immediately.
5. A Tick emits only when `now - last_emit_at >= every_n_seconds`.
6. Tick payloads now include `every_n_seconds`.
7. Runtime status snapshots include `last_emit_at` for common Tick node state.

Desktop service and Collaboration Server:

1. Desktop Blueprint start still configures common nodes during
   `GraphRuntimeControlPlane.start_run()`.
2. Live desktop runs start the framework tick loop only after `start_run`
   succeeds.
3. Collaboration Server snapshot projection accepts `everyNSeconds` and keeps
   `everyNTicks` as a legacy fallback.

## Runtime Timing Semantics

For a live Blueprint run:

1. `DesktopBlueprintService._start_live_runtime()` calls
   `control.start_run(...)`.
2. `GraphRuntimeControlPlane.start_run()` validates the graph and calls
   `runtime.configure_completion_tracking(graph)`, which configures common
   nodes.
3. If the start result is successful, the desktop service calls
   `runtime.start_tick_loop()`.
4. The tick loop immediately runs one framework frame, records a baseline for
   each Tick node, then sleeps by the framework frame interval.
5. The first user-visible Tick node message appears after the configured
   seconds interval has elapsed, on the next framework frame.

With the current default `tick_interval_sec = 0.5`, a Tick configured as
`every_n_seconds = 3` emits about three seconds after run start, rounded to the
next half-second framework frame.

## Files Changed

Runtime/backend:

1. `graph_runtime.py`
2. `test_agent_runtime.py`
3. `test_graph_control.py`
4. `test_collaboration_server.py`
5. `collaboration_server/app.py`
6. `collaboration_server/schemas.py`

Frontend payload/model files were updated in the paired frontend archive:

```text
archive/frontend/mobile_blueprint_tones_tick_seconds_ui_2026-06-01.md
```

## Verification

Python:

```powershell
cd F:\src\Package\Script\Python\multi_agent_tcp
python -m py_compile graph_runtime.py collaboration_server/app.py collaboration_server/schemas.py test_agent_runtime.py test_graph_control.py test_collaboration_server.py
# pass

python -m pytest -q test_agent_runtime.py::test_graph_runtime_tick_emits_on_interval_and_applies_backpressure test_graph_control.py::test_graph_definition_parses_common_nodes_and_validates_port_types test_collaboration_server.py
# 21 passed
```

Frontend and TypeScript verification for the payload rename is recorded in the
paired frontend archive.

## Compatibility Notes

1. Old runtime graph documents using `every_n_ticks` still load.
2. Old desktop/mobile snapshots using `everyNTicks` still project.
3. New runtime graph documents, snapshots, and mobile projections should use
   seconds fields.
4. Tick emissions remain subject to existing backpressure behavior, so queued
   Tick messages are not duplicated into saturated downstream queues.

## Skill/Archive Files

Installed skill:

```text
C:\Users\qiuhaoxuan\.codex\skills\multi-agent-tcp\archive\runtime-backend\blueprint_tick_every_seconds_runtime_2026-06-01.md
```

Repository snapshot:

```text
KM_docs/skills-snapshot/archive/runtime-backend/blueprint_tick_every_seconds_runtime_2026-06-01.md
```
