# POPO Planning Table Workflow

Use this workflow for POPO messages that may ask the Agent to fill or modify
game planning Excel tables.

## Fixed Local Sources

- Planning table skill index:
  `F:\trunk_helper\AISkills\planning-table-skill-index.md`
- Planning table skill root:
  `F:\trunk_helper\AISkills`
- Planning table workbooks:
  `F:\src\Package\Script\Python\.codex\skills\excel-export-flow\vendor\trunk\策划表格`
- Planning table tool:
  `D:\excelize-cli`

## Triage

1. Read the POPO user message and decide whether it is a planning-table request.
2. If it is not a planning-table request, handle it normally.
3. If it is a planning-table request, do not occupy or write any workbook yet.
4. Read `F:\trunk_helper\AISkills\planning-table-skill-index.md`.
5. Load the most specific matching skill under `F:\trunk_helper\AISkills` before
   making table-specific decisions.
6. If the index has no suitable matching skill, ask the POPO user whether to
   continue with the generic framework workflow or create/update a dedicated
   skill first. Do not occupy or write any workbook until the user chooses.

## Fill Revert Requests

If the POPO user asks to revert, undo, restore, change back, `回撤`,
`撤回`, `改回`, or `恢复` earlier planning-table fills:

1. Treat the request as a normal planning-table fill request whose desired
   values come from historical fill records.
2. First call `blueprint_query_excel_history` to inspect the current
   BlueprintSession's fill records. Filter by time, workbook, or field when the
   user provided enough detail.
3. Do not call automatic Excel rollback, do not restore a workbook backup over
   the current workbook, and do not call `xltool rollback`.
4. Prefer structured `beforeAfter` old/new snapshots from history records when
   determining reverse-fill target values. Legacy backup workbook paths and
   `excel-export-flow` / SVN diff evidence are read-only evidence sources, not
   files to restore over the current workbook.
5. For committed historical fills, use the commit/revision, workbook, row key,
   and field names with `excel_svn_diff.py --text-diff` or available `xltool`
   diff commands as supplemental evidence when the structured snapshot is not
   enough.
6. Determine whether the original fill was committed:
   - If the original fill was not committed, the revert is an uncommitted
     workspace correction. After the user confirms the reverse-fill plan, write
     back through the normal occupation, `svn update`, `xltool`, validation, and
     completion-report flow, but do not ask for a ticket and do not run
     `svn commit`.
   - If the original fill was committed, the revert is a new reverse commit.
     After the user confirms the reverse-fill plan, continue through the normal
     completion-report confirmation, ticket, `svn commit`, and release flow.
   - If the commit state cannot be determined from history/evidence, ask the
     user whether the original fill was committed. Do not default to requiring a
     commit.
7. If the old value cannot be determined from structured history, legacy
   evidence, or committed SVN diff evidence, ask the user for the target value
   instead of guessing.
8. Produce a detailed reverse-fill plan and wait for user confirmation before
   occupying or writing any workbook.

## Before Confirmation

Before any table occupation or write:

1. Analyze the fill strategy against
   `F:\trunk_helper\AISkills\planning-table-skill-index.md` and the selected
   table-specific skill. If no skill matches, ask the user whether to continue
   generically or create/update a skill first.
2. Identify the target workbook filenames, sheets, key rows or insert positions,
   fields, values, related IDs, and validation requirements.
3. For ambiguous points or conflicting skill rules, ask the POPO user for the
   missing details.
4. Record the ticket number if the user has already provided one. Do not invent
   a ticket number.
5. Produce a detailed fill plan and wait for user confirmation. The plan must be
   specific enough to audit, including:
   - workbook filename
   - sheet name
   - target row key or exact row number
   - field name and, when known, cell coordinate
   - value to write
   - whether a new row/template copy is needed
   - validation to run after writing

Do not call `blueprint_script_call`, `blueprint_service_call("xltool", ...)`, or
direct Excel write commands until the user confirms this detailed plan.

## Confirmed Execution

After the POPO user confirms the detailed plan:

1. Occupy every target workbook through the Blueprint `table_queue_service`
   ScriptNode.
   - Use `blueprint_script_call` only when the current message envelope exposes
     the required ScriptNode call for `table_queue_service`.
   - Use action `occupy` with real workbook filenames, not shorthand table names.
   - If the framework does not expose `required_script_calls` for the
     `table_queue_service` path, report that the Blueprint message must be
     routed through the occupation ScriptNode before writing tables.
2. If any workbook is queued instead of occupied, stop and wait for the queue
   notification before editing.
3. Run `svn update` for the relevant planning-table workspace before editing.
   Do this after occupation succeeds and before any workbook write.
4. Use the framework resident-service boundary for all planning-table service
   operations: inspect service interfaces with `blueprint_service_docs` and call
   them with `blueprint_service_call`. Do not bypass this with shell calls to
   `D:\excelize-cli` or direct workbook edits.
5. Use the `xltool` resident service for semantic planning-table writes:
   `blueprint_service_docs("xltool")` first, then
   `blueprint_service_call("xltool", method_name, arguments)`.
   Prefer field/key based commands over raw coordinates when available.
6. Validate the changed rows or cells with the table skill's required checks and
   available `xltool` validation/read commands.
7. Send the POPO user a fill-completion report. The report must include:
   - occupied workbook names
   - changed workbook/sheet/row/key/field/value summary
   - validation results
   - whether a new row/template copy was used
   - whether this workflow requires `svn commit`
   - pending commit message, if commit is required and the ticket number is
     already available
8. For an uncommitted revert whose original fill was not committed, do not ask
   for a ticket and do not run `svn commit`. After validation succeeds and the
   completion report is sent, release every occupied workbook through the
   `table_queue_service` ScriptNode.
9. For normal fills and committed reverts, wait for explicit user confirmation
   before committing. If the user has not provided a ticket number, ask for the
   ticket number in the fill-completion report and do not commit until the user
   provides it.
10. After the user confirms the completion report and the required ticket number
    is available, run `svn commit`. Commit message format:
    `#ticket title - username`
   Example: `#771523 【7月超能力乱斗】- 时间宝石超能 - qiuhaoxuan`.
11. Release every occupied workbook through the `table_queue_service`
    ScriptNode only after the commit succeeds.

## Failure Handling

- If a write or validation step fails after occupation, report the exact failing
  workbook, sheet, key/row, field, and error.
- If the user rejects the fill-completion report, requests changes, or still
  needs to provide a ticket number for a commit-required workflow, do not
  commit. Keep the occupation state explicit in replies until the workflow is
  corrected, cancelled, or confirmed.
- Release workbooks that are safe to release; do not silently leave a table
  occupied.
- If release fails, report the release failure clearly and include the occupied
  workbook names.
- Do not mark the task completed until the write, validation, report, release,
  and commit steps when commit is required have all succeeded, or until the user
  explicitly stops the workflow.

## POPO Reply Discipline

- When asking for details or ticket number, call `agent_task_status` with
  `needs_input` before the final POPO-visible reply.
- When waiting for the initial fill plan confirmation, call `agent_task_status`
  with `needs_input`.
- When waiting for fill-completion report confirmation before a required commit,
  call `agent_task_status` with `needs_input`.
- When blocked by missing ScriptNode routing or unavailable resident services,
  call `agent_task_status` with `blocked`.
- When the table workflow succeeds, call `agent_task_status` with `completed`
  and include the occupied/released tables and validation result. Include commit
  revision and submitted ticket only when a commit was required and performed.
