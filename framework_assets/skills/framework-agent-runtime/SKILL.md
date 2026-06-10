---
name: framework-agent-runtime
description: Baseline multi-agent runtime, MCP tools, dispatch, and private context workflow.
---
# Framework Agent Runtime

Use the injected `framework_context` for your current message envelope, including `outgoing_batch_id`, required downstream targets, and `agent_dispatch` usage. `framework_context.message_envelope.outgoing_batch_id` is the current batch available to this Agent. If you need the current batch context, call `agent_context({})` with no explicit batch_id. Batch ids in the message body from upstream Agents are source/audit labels and must not be passed to `agent_context(batch_id=...)`.

The framework runtime skill is stable for the worker context; per-message state changes are provided through `framework_context`.

If Codex lists a framework MCP server such as `framework_ordinary`, use those MCP tools first. They are the preferred interface for checkout/status/diff/submit/sync, publish/publish_file, downstream dispatch, and task status reporting. Read project files and temporary shared workspace files directly from the read-only paths injected into AGENTS.md, the prompt preamble, and the Codex Execution Context. The shared workspace includes reports, artifacts, manifest.json, and logs; write reports and artifacts through publish tools.

Your final CLI reply is only a minimal framework-private utterance record containing who spoke, what was said, time, and task/message identity. It is not a communication channel to other AgentNodes and is not proof of submitted work.

For code changes, edit the private checkout in the current working directory, fetching only task-relevant project files with `workspace_checkout`, inspect with `workspace_status` / `workspace_diff`, then submit through `workspace_submit`. If a direct write outside the private checkout is denied by sandbox policy, recover by using the framework checkout/submit flow rather than treating the denial as completed work.

For reports and artifacts, publish through `workspace_publish` / `workspace_publish_file` as shared run context. Use summaries, file paths, versions, and changeset ids when another AgentNode needs code context. `workspace_publish` writes complete file content, not a line-level append patch. If you need to continue from an existing shared file, read that file and the shared `manifest.json` directly, build the full new content, and pass the current version as `expected_version`. When updating a shared path previously written by another AgentNode, pass `expected_version` or publish to a unique per-agent path; silent last-write-wins overwrites are blocked. When `framework_context.message_envelope.required_outgoing_targets` is empty, treat the message as leaf work: do not call `agent_dispatch` or `join_contribute`; process the message and publish the result or receipt as a shared report.

For downstream messages, use the `agent_dispatch` MCP tool. The target must be listed in the current message's `framework_context.message_envelope.required_outgoing_targets`.

If `framework_context.message_envelope.required_script_calls` is non-empty, call `blueprint_script_call` for each listed Script Function Node instead of dispatching directly to its downstream AgentNode. The framework executes the Python function and automatically delivers function name, description, arguments, and outputs to connected downstream AgentNodes.

`framework_context.resident_services` lists global resident services visible to Agent class nodes. Use `blueprint_service_docs(service_name)` to inspect interfaces and `blueprint_service_call(service_name, method_name, arguments)` to call a service; ordinary Agent tools cannot start or stop services.

If a target has no work, dispatch `""` or `0` for that target; the framework records it as no-op and does not queue a downstream task. If `required_outgoing_targets` is empty, there is no downstream dispatch to perform.

Use `join_contribute` only when the framework or task explicitly provides a real `join_id`. Outgoing batch ids such as `out-*` are not join ids. For leaf results, receipts, or simple status reporting, publish a shared report instead.

If `blueprint_reply_popo_user` is available and you use it, that tool is the user-visible POPO reply and records the current task as completed; do not add a second natural-language final reply. For non-POPO task status, call `agent_task_status` before your final CLI reply. Use `completed` after your own work is done, `blocked` when a framework or project condition prevents completion, `needs_input` when user input is required, and `failed` for unrecoverable errors. If the framework asks with `framework_summary_request`, summarize only your own current task and then call `agent_task_status`; do not summarize the ring or the whole blueprint.
