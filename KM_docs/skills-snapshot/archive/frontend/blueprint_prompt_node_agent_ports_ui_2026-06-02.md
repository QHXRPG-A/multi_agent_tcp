# Blueprint Prompt Node and Agent Port UI

Date: 2026-06-02

## Scope

Added a canvas `Prompt` node and changed Agent/Worker Agent canvas rendering to
an expandable, fixed-port model. The UI now treats Agent ports the same way as
Script node ports: collapsed nodes show the normal flow handles, while expanded
nodes show concrete labeled port rows derived from a definition table.

## Frontend Model

- Added `BlueprintPromptNode`, `BlueprintPromptTrigger = "once" | "always"`,
  `graph.prompt_nodes`, and `"str"` to `BlueprintPortDataType`.
- Added `BlueprintAgentNode.collapsed`; default Agent/Worker Agent nodes are
  collapsed.
- Removed active `prompt_input_enabled` product semantics. Old documents may
  still contain the field, but normalization ignores it and the fixed Agent
  `prompt` input remains available.
- Runtime graph/document export keeps `prompt_nodes`; old `run_prompt` remains
  hidden from the inspector and is kept only for compatibility/runtime behavior.

## Canvas UI

- Right-click node search includes `Prompt`.
- `Prompt` nodes render as editable prompt-text nodes with compact input mode,
  double-click textarea expansion, and `1次触发 / 多次触发` controls.
- Agent/Worker Agent nodes expose a bottom expand/collapse button instead of a
  prompt-port add/remove menu.
- Expanded Agent nodes render fixed rows from
  `AGENT_INPUT_PORT_DEFINITIONS` / `AGENT_OUTPUT_PORT_DEFINITIONS`.
- The built-in Agent input ports are currently `in` and `prompt: str`; the
  `prompt` pin uses the triangle shape. Future built-in Agent pins only need to
  be appended to the port definition table.

## Connection Rules

- `PromptNode(out: str) -> Agent(prompt: str)` is always allowed and creates a
  `data` edge automatically.
- `PromptNode` cannot connect to normal Agent flow input, and non-Prompt sources
  cannot connect to Agent `prompt`.
- Prompt data edges do not affect Agent reachability, start groups, framework
  dispatch, or execution flow rendering.

## Verification

- Frontend model/source/i18n tests:
  `bun test --preload ./happydom.ts ./src/pages/session/blueprint-model.test.ts ./src/pages/session/blueprint-side-panel.test.ts ./src/i18n/parity.test.ts`
- Typecheck and build:
  `bun run typecheck`
  `bun run build`
- Browser smoke:
  default Agents are collapsed; expanding an Agent shows `Input`,
  `prompt: str`, and `Output`; `prompt: str` has a triangle pin; collapsing hides
  the rows again; the old prompt add/remove menu is absent; the Prompt node
  search entry remains available.
