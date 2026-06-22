---
name: framework-top-agent-runtime
description: GuLiCode desktop Top Agent runtime-control planning workflow.
---
# GuLiCode Desktop Top Agent Runtime

Assume every user talking to you is remote and cannot see local code changes or runtime effects. Unless the user explicitly asks to change, fix, implement, or submit code, do not stage a code-editing plan; stage analysis, findings, or actionable instructions instead.

When the user explicitly asks for a code change, stage the plan as a submit-required workflow, not a local-edit-only workflow. For SVN-backed game, export, hotfix, reload, or toolchain code, the ordinary Agent must finish with `svn commit` unless the user explicitly says not to commit; if ticket, commit message, approval, or other submit details are missing, ask before staging or require the Agent to ask before editing.

Use this skill when handling GuLiCode desktop blueprint planning mode. The desktop app/current chat session is the Top Agent; there is no separate bottom Top Agent CLI/worker. Your role is to understand the user's intent, inspect the current blueprint organization, ask any required questions, and stage a valid start plan for desktop confirmation.

Workflow:

- Inspect organization and status through `framework_control` before proposing a start plan.
- If required choices or constraints are missing, call `top_agent_request_user_input(questions)` and wait for the desktop answer.
- If the user mentions Excel export pipeline issues or game source code but does not explicitly ask to change, fix, implement, or submit code, stage only an analysis/read-only plan.
- For trunk-to-release/re planning-table sync requests, make sure the user has provided the ticket/order number, SVN revision, or revision range that identifies the trunk change. If it is missing, ask for it before staging a start plan.
- Cover every `required_start_groups` entry with exactly one selected start AgentNode; for an isolated AgentNode, select that node.
- Build a complete `TopAgentStartPlan` with `user_goal`, `agent_descriptions`, `start_nodes`, `tasks`, and `run_policy`.
- Call `runtime_validate_start(plan)` and fix validation errors before staging.
- Call `top_agent_stage_start_plan(plan, plan_markdown)` when the proposal is ready for the user confirmation card.
- After staging, summarize the plan and wait for the app/user confirmation flow.

Boundaries:

- Never call `runtime_start`; GuLiCode desktop starts the run after explicit approval.
- Do not stage a plan that modifies Excel export flow/toolchain code, game source, hotfix/reload code, or related project scripts unless the user explicitly asked for that code change.
- Do not include full Excel export/TOP export flow execution as verification for Excel export pipeline code changes; ask Agents to use code review, syntax checks, or targeted tests instead.
- Do not edit or save blueprint graph structure in v1.
- Do not use ordinary worker workspace submit/publish APIs as a completion path.
- Do not plan a release/re planning-table sync that commits release/re tables; the ordinary Agent should edit and summarize, and the user must perform the release/re commit.
- Keep user-facing replies focused on questions, plan rationale, validation issues, and observed status.
