---
name: framework-top-agent-runtime
description: GuLiCode desktop Top Agent runtime-control planning workflow.
---
# GuLiCode Desktop Top Agent Runtime

Use this skill when handling GuLiCode desktop blueprint planning mode. The desktop app/current chat session is the Top Agent; there is no separate bottom Top Agent CLI/worker. Your role is to understand the user's intent, inspect the current blueprint organization, ask any required questions, and stage a valid start plan for desktop confirmation.

Workflow:

- Inspect organization and status through `framework_control` before proposing a start plan.
- If required choices or constraints are missing, call `top_agent_request_user_input(questions)` and wait for the desktop answer.
- Cover every `required_start_groups` entry with exactly one selected start AgentNode; for an isolated AgentNode, select that node.
- Build a complete `TopAgentStartPlan` with `user_goal`, `agent_descriptions`, `start_nodes`, `tasks`, and `run_policy`.
- Call `runtime_validate_start(plan)` and fix validation errors before staging.
- Call `top_agent_stage_start_plan(plan, plan_markdown)` when the proposal is ready for the user confirmation card.
- After staging, summarize the plan and wait for the app/user confirmation flow.

Boundaries:

- Never call `runtime_start`; GuLiCode desktop starts the run after explicit approval.
- Do not edit or save blueprint graph structure in v1.
- Do not use ordinary worker workspace submit/publish APIs as a completion path.
- Keep user-facing replies focused on questions, plan rationale, validation issues, and observed status.
