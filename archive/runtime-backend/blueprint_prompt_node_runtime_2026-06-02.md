# Blueprint Prompt Node Runtime

Date: 2026-06-02

## Scope

Added runtime support for canvas Prompt nodes that append prompt text to
Agent/Worker Agent dispatches through a fixed Agent `prompt` data input.

## Runtime Model

- Added `PromptNode` with `text`, `trigger`, and `expanded`.
- Added `GraphDefinition.prompt_nodes`.
- Added `"str"` to supported blueprint port data types.
- Agent `prompt` input is always a valid fixed port. Legacy
  `prompt_input_enabled` is tolerated in frontend documents but is not a runtime
  field and is not included in organization summaries.

## Validation

- `GraphDefinition.validate_port_types()` recognizes
  `PromptNode(out) -> Agent(prompt)` data edges.
- Prompt edges must use `edge_type="data"`.
- Non-Prompt sources cannot target Agent `prompt`, and Prompt sources cannot
  target other inputs.
- Prompt data edges are excluded from Agent reachability and framework flow.

## Dispatch Injection

- `GraphRuntime.configure_prompt_nodes()` snapshots Prompt node connections at
  run/configure time in document edge order.
- `_dispatch_agent_message` composes prompt sections before sending a real
  non-empty message:
  - legacy `run_prompt` first, under `# Agent Run Prompt`;
  - then connected Prompt nodes under `# Blueprint Prompt: <node_id>`;
  - then `---` followed by the original prompt.
- `once` Prompt nodes inject once per Agent per run, and reset with
  `reset_run_prompt_injections()`.
- `always` Prompt nodes inject on every real non-empty dispatch.
- Empty string, numeric `0`, dict bodies without a non-empty `prompt`, and empty
  Prompt node text are no-ops and do not consume `once` injection state.

## Verification

- Python tests:
  `python -m pytest -q test_agent_runtime.py test_graph_control.py test_desktop_blueprint_service.py`
- Compile check:
  `python -m py_compile graph_runtime.py graph_control.py desktop_blueprint_service.py`
- Plugin refresh:
  `python plugins\gulicode-bp\scripts\install_personal_plugin.py --force`
