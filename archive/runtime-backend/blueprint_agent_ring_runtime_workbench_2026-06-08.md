# Blueprint Agent Ring Runtime and Workbench

Date: 2026-06-08

## Summary

This archive records the Blueprint Agent ring implementation across
GraphRuntime, desktop Blueprint service validation, and the Workbench ring UI.
The feature lets Agent and Worker Agent nodes participate in bounded cycles,
shows detected rings in a floating Workbench panel, highlights all rings related
to a hovered Agent node, and carries ring refresh state into the real Agent
framework context.

The runtime contract added two graph-level configuration maps:

- `agent_ring_max_circulations: Record<string, number>`
- `agent_ring_context_refresh_periods: Record<string, number>`

Ring configuration keys prefer stable topology ids such as
`ring-planner-reviewer`, with compatibility for generated ids such as `ring1`
and numeric legacy keys such as `"1"`.

## Runtime Behavior

- `GraphDefinition.agent_rings()` detects simple Agent/Worker Agent cycles and
  treats Script nodes as transparent exec-path nodes.
- Non-Agent cycle members still fail runtime validation; bounded Agent rings are
  accepted by `validate_agent_ring_graph()`.
- `AgentRing.to_dict()` now includes `context_refresh_period`.
- `GraphRuntime` tracks per-ring:
  - `completed_circulations`
  - `context_generation`
  - `last_context_refresh_circulation`
- A closing edge consumes one remaining circulation and emits
  `AgentRingCirculationAdvanced`.
- Every `context_refresh_period` completed closures increments the ring
  generation and emits `AgentRingContextRefreshed`.
- When remaining circulations reach zero, the runtime emits
  `AgentRingCirculationExhausted` and prunes further ring forwarding.
- `ordinary_agent_framework_context()` injects `ring_context` into the current
  Agent context and organization view, so every ring participant sees the same
  generation, remaining count, completed count, refresh period, and last refresh
  circulation.

Defaults:

- Maximum circulations default to `1` and allow `0`.
- Context refresh period defaults to `1` and must be at least `1`.

## Workbench UI

The Workbench gained a ring list floating panel:

- Press `r` to open the panel.
- `Escape` closes the panel.
- The shortcut is ignored inside inputs, textareas, selects, and
  contenteditable elements.
- The panel supports dragging and resizing through the same pointer model as
  existing floating panels.
- Ring cards display ring id, Agent count, path, max circulations, refresh
  period, remaining count, completed count, and generation when live status is
  available.
- Double-clicking one ring card opens its settings view in the same panel.
- Settings edit the draft graph maps for max circulations and context refresh
  period.
- During a live run, settings are read-only and communicate that edits apply to
  the next run.
- Hovering any Agent or Worker Agent node highlights all rings containing that
  node, including overlapping rings. The highlight covers related visual edge
  paths and ring Agent node outlines.

The frontend model added TypeScript ring detection with stable topology ids and
transparent Script path expansion for visual edge highlighting.

## Main Files

- `graph_runtime.py`
- `graph_control.py`
- `desktop_blueprint_service.py`
- `test_agent_runtime.py`
- `test_graph_control.py`
- `test_desktop_blueprint_service.py`
- `GuLiCode/packages/app/src/pages/session/blueprint-model.ts`
- `GuLiCode/packages/app/src/pages/session/blueprint-model.test.ts`
- `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.tsx`
- `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.test.ts`
- `GuLiCode/packages/app/src/i18n/en.ts`
- `GuLiCode/packages/app/src/i18n/zh.ts`
- `GuLiCode/packages/app/src/i18n/zht.ts`

## Verification

Backend compile and targeted unit tests:

```powershell
python -m py_compile graph_runtime.py graph_control.py desktop_blueprint_service.py test_agent_runtime.py test_graph_control.py test_desktop_blueprint_service.py
python -m pytest -q test_graph_control.py::test_graph_definition_json_loads_agent_ring_refresh_periods test_agent_runtime.py::test_graph_runtime_refreshes_ring_context_on_configured_period test_agent_runtime.py::test_graph_runtime_overlapping_rings_refresh_independently test_agent_runtime.py::test_graph_definition_validate_agent_ring_graph_allows_bounded_agent_cycles test_agent_runtime.py::test_graph_definition_validate_agent_ring_graph_rejects_non_agent_cycles test_desktop_blueprint_service.py::test_blueprint_service_validation_allows_bounded_agent_ring_graph test_desktop_blueprint_service.py::test_real_codex_live_blueprint_agent_ring_limits_and_refresh_context
```

Result: `6 passed, 1 skipped` when the real Codex gate was not enabled.

Additional backend coverage:

```powershell
python -m pytest -q test_agent_runtime.py -k "ring or cycle or validate_agent_ring_graph" test_graph_control.py -k "agent_ring or graph_definition_json_loads"
```

Result: `5 passed, 132 deselected`.

Frontend typecheck and tests from `GuLiCode/packages/app`:

```powershell
bun run typecheck
bun test --preload ./happydom.ts ./src/pages/session/blueprint-model.test.ts ./src/pages/session/blueprint-side-panel.test.ts ./src/i18n/parity.test.ts
```

Result: typecheck passed, frontend tests passed with `49 pass`.

Browser smoke used the local Vite Workbench at:

```text
http://127.0.0.1:5175/Rjpcc3JjXFBhY2thZ2VcU2NyaXB0XFB5dGhvblxtdWx0aV9hZ2VudF90Y3A/blueprint-window/default
```

Verified:

- A draft with overlapping rings loaded in the Workbench.
- Hovering an Agent highlighted all related ring nodes and edges.
- Pressing `r` opened the ring panel.
- The panel moved and resized.
- Double-clicking a ring opened settings.
- Editing max circulations and refresh period persisted after closing and
  reopening the panel.

Smoke output:

```json
{
  "highlightedNodes": 3,
  "cardCount": 2,
  "movedDistance": 165.4206758540177,
  "moved": true,
  "resized": true,
  "persisted": true
}
```

## Real Codex Agent Smoke

The gated real test is:

```powershell
$env:MULTI_AGENT_TCP_RUN_REAL_CODEX_MCP = "1"
python -m pytest -q test_desktop_blueprint_service.py::test_real_codex_live_blueprint_agent_ring_limits_and_refresh_context -vv -s
```

It requires `codex` on PATH and copies runtime Codex state into a temporary
`CODEX_HOME`.

The first real attempt exposed a Codex CLI option conflict:

- Full Agent launch context automatically injected
  `--dangerously-bypass-approvals-and-sandbox`.
- The test also supplied `--full-auto`.
- Current `codex exec` rejects that combination.

The real smoke options were fixed by removing explicit `--full-auto` from the
desktop service real Codex smokes. The framework-owned dangerous bypass still
keeps the run non-interactive for this gated live test.

After the fix:

```text
test_real_codex_live_blueprint_agent_ring_limits_and_refresh_context PASSED
1 passed, 2 warnings in 104.41s
```

The `max=1`, `refresh_period=1` run started two real Codex Agents, completed
`planner -> reviewer -> planner`, emitted refresh and exhaustion events, and
recorded at least two real `agent_dispatch` MCP calls.

An additional manual real Codex smoke validated `max=2`,
`refresh_period=1`. It completed two full closures and stopped at exhaustion:

```json
{
  "run_id": "run-real-mcp-ring-max2",
  "agent_dispatch_calls": 4,
  "ring_status": {
    "max_circulations": 2,
    "context_refresh_period": 1,
    "remaining_circulations": 0,
    "completed_circulations": 2,
    "context_generation": 2,
    "last_context_refresh_circulation": 2
  },
  "advanced_events": 2,
  "refreshed_events": 2,
  "exhausted_events": 1
}
```

## Notes

- The `max=2` live smoke was intentionally kept as a manual validation rather
  than replacing the shorter gated pytest, because it requires four real
  `agent_dispatch` calls plus a final planner message and is slower.
- The Vite Workbench dev server used during browser smoke auto-selected port
  `5175` after `5174` was occupied.
- The repository had pre-existing dirty files before this implementation; avoid
  treating the whole dirty diff as one isolated change set without reviewing the
  earlier work.
