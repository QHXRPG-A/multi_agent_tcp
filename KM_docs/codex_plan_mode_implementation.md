# Codex Plan Mode Implementation Notes

Last refreshed: 2026-05-21 from checkout `D:\codex`.

This note records the implementation details observed while tracing Codex Plan
mode, especially the question flow driven by `request_user_input`.

## High-Level Model

Codex Plan mode is implemented as a `CollaborationMode`, not as the
`update_plan` checklist tool. The active mode travels through TUI,
app-server, and core, then core injects mode-specific developer instructions
into the model context.

The effective chain is:

```text
TUI mode selection
  -> CollaborationMode on turn/thread settings
  -> app-server fills built-in developer instructions
  -> core injects <collaboration_mode> developer block
  -> model follows Plan prompt and may call request_user_input
```

## Built-In Mode Definitions

Key files in `D:\codex`:

- `codex-rs\models-manager\src\collaboration_mode_presets.rs`
  - `builtin_collaboration_mode_presets()` returns Plan and Default presets.
  - Plan preset sets `mode = ModeKind::Plan`.
  - Plan preset default reasoning is `ReasoningEffort::Medium`.
  - Plan preset developer instructions come from
    `codex_collaboration_mode_templates::PLAN`.
- `codex-rs\collaboration-mode-templates\templates\plan.md`
  - Defines the behavioral contract for Plan mode.
  - Says the model stays in Plan mode until developer instructions end it.
  - Allows non-mutating exploration.
  - Forbids implementation and repo-tracked mutations.
  - Strongly prefers `request_user_input` for important questions.
  - Requires final plans to be wrapped in `<proposed_plan>...</proposed_plan>`.
- `codex-rs\protocol\src\config_types.rs`
  - Defines `ModeKind`.
  - `TUI_VISIBLE_COLLABORATION_MODES` is `[Default, Plan]`.
  - `ModeKind::allows_request_user_input()` returns true only for Plan by
    default.

## App-Server Normalization

The app-server accepts `collaboration_mode` from both:

- `turn/start`
- `thread/settings/update`

Relevant file:

- `codex-rs\app-server\src\request_processors\turn_processor.rs`

Important behavior:

- `normalize_collaboration_mode()` checks whether
  `collaboration_mode.settings.developer_instructions` is missing.
- If missing, it looks up the matching built-in preset.
- For Plan mode, that fills the Plan mode developer prompt automatically.

This means a client can send a lightweight mode object with `mode = Plan` and
`developer_instructions = None`; the server completes it before core sees the
turn.

## Core Prompt Injection

Relevant files:

- `codex-rs\core\src\context\collaboration_mode_instructions.rs`
- `codex-rs\core\src\session\mod.rs`
- `codex-rs\core\src\context_manager\updates.rs`
- `codex-rs\protocol\src\protocol.rs`

Core wraps the current mode instructions in a developer message using:

```text
<collaboration_mode>
...
</collaboration_mode>
```

The wrapper is produced by `CollaborationModeInstructions`, whose role is
`developer`. Initial context injection happens in `Session::build_initial_context`
when `include_collaboration_mode_instructions` is true. That config defaults to
true.

When settings change between turns, `context_manager\updates.rs` can emit an
updated collaboration-mode developer message.

## Why Plan Mode Asks Questions

There is no hardcoded "ask a question now" branch in Plan mode. The behavior is
produced by prompt plus tool availability:

1. The Plan prompt says to ask until intent and implementation details are
   decision complete.
2. The Plan prompt strongly prefers the `request_user_input` tool for important
   questions.
3. Core exposes `request_user_input` as a tool.
4. The `request_user_input` handler rejects calls when the current mode is not
   allowed.

The model decides when to call the tool, but the runtime enforces whether the
tool is valid for the current collaboration mode.

## request_user_input Tool Flow

Key files:

- `codex-rs\core\src\tools\handlers\request_user_input_spec.rs`
- `codex-rs\core\src\tools\handlers\request_user_input.rs`
- `codex-rs\tools\src\tool_config.rs`
- `codex-rs\core\src\session\mod.rs`
- `codex-rs\protocol\src\request_user_input.rs`
- `codex-rs\tui\src\chatwidget\tool_requests.rs`
- `codex-rs\tui\src\bottom_pane\request_user_input\mod.rs`
- `codex-rs\app-server\src\bespoke_event_handling.rs`

Runtime sequence:

```text
Model calls request_user_input
  -> RequestUserInputHandler parses and validates arguments
  -> handler verifies root thread only
  -> handler checks current CollaborationMode against available modes
  -> Session::request_user_input stores a oneshot sender
  -> core emits EventMsg::RequestUserInput
  -> app-server forwards the request to the client
  -> TUI shows RequestUserInputOverlay in the bottom pane
  -> user answers
  -> app-server submits Op::UserInputAnswer
  -> Session::notify_user_input_response resolves the oneshot
  -> tool result returns JSON answers to the model
```

Default mode availability:

- `request_user_input_available_modes()` includes modes where
  `ModeKind::allows_request_user_input()` is true.
- By default this is only Plan.
- Feature `DefaultModeRequestUserInput` can also allow Default mode.

The tool schema requires one to three short questions. Each question must have
2-3 mutually exclusive options. The handler also sets `is_other = true`, so the
client can add a free-form "Other" path.

## update_plan Is Separate

Relevant file:

- `codex-rs\core\src\tools\handlers\plan.rs`

`update_plan` is a checklist/progress tool, not Plan mode. In Plan mode it is
explicitly rejected:

```text
update_plan is a TODO/checklist tool and is not allowed in Plan mode
```

Outside Plan mode, `update_plan` emits `EventMsg::PlanUpdate`.

## proposed_plan Rendering Flow

Plan mode final plans are expected to contain:

```text
<proposed_plan>
...
</proposed_plan>
```

Key files:

- `codex-rs\utils\stream-parser\src\proposed_plan.rs`
- `codex-rs\utils\stream-parser\src\assistant_text.rs`
- `codex-rs\core\src\session\turn.rs`
- `codex-rs\core\src\stream_events_utils.rs`
- `codex-rs\tui\src\chatwidget\streaming.rs`
- `codex-rs\tui\src\streaming\controller.rs`
- `codex-rs\tui\src\chatwidget\turn_runtime.rs`
- `codex-rs\tui\src\chatwidget\plan_implementation.rs`

Flow:

```text
Assistant streams text containing <proposed_plan>
  -> stream parser extracts ProposedPlanSegment values
  -> core emits item/plan/delta for plan body
  -> core completes TurnItem::Plan with extracted plan text
  -> normal assistant text has proposed_plan blocks stripped
  -> TUI renders a "Proposed Plan" history cell
  -> after turn completion, TUI may prompt "Implement this plan?"
```

The implementation prompt offers:

- `Yes, implement this plan`: switches to Default mode and submits
  `Implement the plan.`
- `Yes, clear context and implement`: starts implementation in fresh context
  using the plan as source intent.
- `No, stay in Plan mode`: closes the prompt and keeps planning.

## TUI Mode Switching

Key files:

- `codex-rs\tui\src\collaboration_modes.rs`
- `codex-rs\tui\src\chatwidget\constructor.rs`
- `codex-rs\tui\src\chatwidget\settings.rs`
- `codex-rs\tui\src\chatwidget\slash_dispatch.rs`
- `codex-rs\tui\src\chatwidget\interaction.rs`
- `codex-rs\tui\src\chatwidget\input_submission.rs`
- `codex-rs\tui\src\app_server_session.rs`

Important behavior:

- TUI starts in Default mode.
- `/plan` applies the Plan collaboration mask.
- Shift+Tab cycles between visible collaboration modes.
- `effective_collaboration_mode()` applies the active mask to the stored
  current mode.
- On user submission, TUI attaches the effective `CollaborationMode` to the
  user turn.
- The app-server then normalizes missing Plan developer instructions.

## Runtime Enforcement Boundaries

Observed hard enforcement:

- `request_user_input` is mode-checked.
- `request_user_input` only works from the root thread.
- `update_plan` is rejected in Plan mode.
- `<proposed_plan>` blocks are stripped from normal assistant text and rendered
  through the plan item path.

Observed prompt-level enforcement:

- "Do not mutate repo-tracked files in Plan mode" is primarily enforced by the
  Plan developer instructions.
- There is no broad runtime guard found here that blocks every possible
  mutating shell or file operation solely because `ModeKind::Plan` is active.

## Tests Worth Reading

Useful tests in `D:\codex`:

- `codex-rs\app-server\tests\suite\v2\plan_item.rs`
  - Verifies `<proposed_plan>` produces `ThreadItem::Plan`.
  - Verifies no plan item is emitted without `<proposed_plan>`.
- `codex-rs\core\tests\suite\request_user_input.rs`
  - Verifies `request_user_input` round trip in Plan.
  - Verifies Default mode is rejected unless the feature flag enables it.
  - Verifies hidden Execute/Pair aliases are rejected.
- `codex-rs\tui\src\chatwidget\tests\plan_mode.rs`
  - Verifies `/plan` switches mode.
  - Verifies implementation popup behavior.
  - Verifies Default startup and Plan-to-Default implementation flow.

## Mental Model for Future Changes

When changing Plan mode behavior, first identify which layer owns the concern:

- Prompt behavior: edit `collaboration-mode-templates\templates\plan.md`.
- Preset metadata: edit `models-manager\src\collaboration_mode_presets.rs`.
- Mode serialization and allowed modes: edit `protocol\src\config_types.rs`.
- App-server defaults: edit `app-server\src\request_processors\turn_processor.rs`.
- Tool availability and validation: edit `core\src\tools\handlers\...` and
  `tools\src\tool_config.rs`.
- Plan block parsing: edit `utils\stream-parser`.
- TUI rendering and prompts: edit `tui\src\chatwidget` and
  `tui\src\bottom_pane`.

