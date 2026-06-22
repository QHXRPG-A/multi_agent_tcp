---
name: framework-agent-runtime
description: Full Agent runtime for framework messages, planning-table workflows, and source lookup.
---
# Framework Agent Runtime

Assume every user talking to you is remote and cannot see local code changes or runtime effects. Unless the user explicitly asks to change, fix, implement, or submit code, do not edit code; provide analysis, findings, or actionable instructions instead.

When the user explicitly asks for a code change, local edits alone are not a completed result because remote users cannot see them. For SVN-backed game, export, hotfix, reload, or toolchain code, complete the work with the required `svn commit` unless the user explicitly says not to commit. If a ticket number, commit message, approval, or other required submit detail is missing, ask for it and do not mark the task completed.

Use the injected `framework_context` for your current message envelope, including `outgoing_batch_id`, required downstream targets, and `agent_dispatch` usage. `framework_context.message_envelope.outgoing_batch_id` is the current batch available to this Agent. If you need the current batch context, call `agent_context({})` with no explicit batch_id. Batch ids in the message body from upstream Agents are source/audit labels and must not be passed to `agent_context(batch_id=...)`.

The framework runtime skill is stable for the Full Agent context; per-message state changes are provided through `framework_context`.

Full Agent shell work must use `py -3.13` as the default Python command unless a workflow explicitly provides a different project interpreter. On this machine it resolves to `C:\Users\qiuhaoxuan\AppData\Local\Programs\Python\Python313\python.exe`. Do not spend time probing `python`, `py`, Python 3.11, or other interpreters for framework/Hunter scripts; use `py -3.13` directly and do not modify global Python environment variables or installs.

Treat Excel export pipeline issues and game source-code questions as read-only analysis by default. Do not modify Excel export flow/toolchain code, game source, hotfix/reload code, or related project scripts unless the user explicitly asks to change, fix, implement, or submit code. If the wording is ambiguous, ask before editing.

When the user explicitly asks for an Excel export pipeline code change, do not run the full Excel export/TOP export flow as verification. Use code review, syntax checks, or targeted tests where practical, and state that remote end-to-end export behavior was not locally verified.

If Codex lists a framework MCP server such as `framework_ordinary`, use those MCP tools first for message context, downstream dispatch, Script Function Node calls, resident-service calls, and task status reporting.

For downstream messages, use the `agent_dispatch` MCP tool. The target must be listed in the current message's `framework_context.message_envelope.required_outgoing_targets`.

If `framework_context.message_envelope.required_script_calls` is non-empty, call `blueprint_script_call` for each listed Script Function Node instead of dispatching directly to its downstream AgentNode. The framework executes the Python function and automatically delivers function name, description, arguments, and outputs to connected downstream AgentNodes.

`framework_context.resident_services` lists global resident services visible to Agent class nodes. Use `blueprint_service_docs(service_name)` to inspect interfaces and `blueprint_service_call(service_name, method_name, arguments)` to call a service; ordinary Agent tools cannot start or stop services.

When the local AISkills/private skill context has no relevant skill for a user task, inspect `skill_square` through `blueprint_service_docs("skill_square")`, then call `blueprint_service_call("skill_square", "search", {"query": "<task keywords>", "limit": 10})`. The Skill Square boundary is strictly G83US: ignore and do not install any result outside that scope. To use a matching G83US skill, call `read` first, then `install` only when the user request requires adding the skill; installed Skill Square skills go to the global `CODEX_HOME/skills` directory maintained by the service.

For POPO-bound sessions, send a local image or file to the current POPO user by calling `blueprint_send_popo_file(path)`. Pass only the local filesystem path; the framework resolves the active receiver and robot binding. Do not ask the user for robot credentials, receiver ids, or upload tokens.

For POPO/user messages that include a `.graph` file, uploaded graph attachment, graph path, or graph filename, read `graph_file_workflow.md` in this skill directory before analysis or modification.

For POPO messages that may ask for game planning Excel table fills, edits, or reverts, read `planning_table_popo_workflow.md` in this skill directory before deciding what to do. That workflow controls the sequence: classify the message, query fill history first for revert requests, read the planning-table skill index, ask for missing details, produce a cell-level plan, wait for user confirmation, occupy workbooks through `table_queue_service`, run `svn update`, write through the `xltool` resident service, send a fill-completion report, then either release without ticket/commit for uncommitted reverts or wait for user confirmation/ticket number and run `svn commit` for normal fills and committed reverts before release.

For POPO/user messages that contain Excel export failures, 导表报错, TOP export links, `[Error tips]`, Traceback from ExcelToData, `check_rule`, `post_process`, or generated data reference errors, read `excel_export_error_workflow.md` in this skill directory before diagnosing. That workflow requires branch identification first: TOP plan id `1469` is trunk, TOP plan id `796` is release/re, and if neither a branch nor a recognized plan id is present, ask the user instead of guessing.

For POPO/user messages asking to sync selected trunk planning-table changes into release/re planning tables, read `trunk_release_table_sync.md` in this skill directory before acting. This workflow requires a ticket/order number, SVN revision, or explicit revision range; if the user did not provide one, ask for it. Once the diff evidence is unambiguous, update the release/re workbook, summarize the changed cells, and do not commit. Release/re table commits must be performed by the user.

For POPO/user messages asking to debug a game client, send commands to a client, inspect device logs, use Hunter, run a remote REPL, or verify a hotfix/runtime change on a client, read `remote_client_debugging.md` in this skill directory before acting. That workflow requires concrete target information such as an IP, device id, device name, owner, or binding name; `local` or `本地` alone is not enough.

When a task requires game source-code inspection, use `F:\src\Package\Script\Python` as the default source root and `F:\src\Package\Script\Python\.codemaker\expert` as the default expert knowledge root. Check the expert knowledge first when it is relevant, then search source with targeted commands.

If a target has no work, dispatch `""` or `0` for that target; the framework records it as no-op and does not queue a downstream task. If `required_outgoing_targets` is empty, there is no downstream dispatch to perform.

Use `join_contribute` only when the framework or task explicitly provides a real `join_id`. Outgoing batch ids such as `out-*` are not join ids.

For POPO-bound sessions, the start Agent's final natural-language CLI reply is the user-visible POPO reply; the framework forwards it after your work is complete. Call `agent_task_status` before your final CLI reply unless the framework has already recorded a terminal status. Use `completed` after your own work is done, `blocked` when a framework or project condition prevents completion, `needs_input` when user input is required, and `failed` for unrecoverable errors. If the framework asks with `framework_summary_request`, summarize only your own current task and then call `agent_task_status`; do not summarize the ring or the whole blueprint.
