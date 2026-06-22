# Excel Export Error Workflow

Use this workflow when a POPO/user message contains an Excel export failure,
导表报错, TOP export link, `[Error tips]`, Traceback from ExcelToData,
`check_rule`, `post_process`, or generated data reference errors.

## First Response Discipline

1. Do not guess the branch or table source.
2. Determine whether the failure is from trunk export or release/re export.
3. If the message does not contain an explicit branch or a recognized TOP plan
   id/link, ask the user which export flow failed before analyzing tables.
4. Do not modify planning tables while diagnosing export failures. This workflow
   is read-only unless the user later asks for a confirmed table fix.
5. Before any refresh, table lookup, generated-data lookup, blame, or diagnosis,
   verify that the pasted notification contains actionable error details, not
   only a TOP link and export status footer.

## Branch Identification

Recognized TOP plan ids:

- `1469`: trunk export.
- `796`: release/re export.

Branch rules:

- If the user says `trunk`, or the TOP link is
  `newTopPlanHome/?#/plan/detail?id=1469`, treat it as trunk.
- If the user says `re`, `release`, or the TOP link is
  `newTopPlanHome/?#/plan/detail?id=796`, treat it as release/re.
- If neither branch nor recognized plan id is present, ask the user for the
  branch. Do not infer branch from table names, author names, or local data
  files.
- If the user supplies a different TOP plan id, ask for confirmation unless the
  message also explicitly says trunk or release/re.

## Minimum Error Detail Gate

After branch identification, but before `svn update` or any local investigation,
check whether the pasted notification includes at least one real diagnostic
line.

Treat the message as insufficient and do not process it when it only contains:

- notification header, commit author, revision, issue link, or changed workbook
  paths such as `U ...xlsx`;
- `导表出错,详情参见：` plus a TOP plan link;
- a lone numeric/footer/status line such as `1`.

Do not use the changed workbook list as a substitute for the missing error
details. A trailing `1` is only a status/footer marker; it is not a diagnosable
export error. If real diagnostic lines are present, ignore a trailing numeric
footer and continue with the real error text.

When the notification is insufficient, call `agent_task_status` with
`needs_input` before replying in POPO-bound sessions, and reply in Chinese:

```text
这段导表通知里没有完整报错信息，只有 TOP 链接/改表列表和末尾的 `1`，无法定位问题。
请重新粘贴完整的导表报错内容，至少包含 `[Error tips]`、Traceback、`check_rule`/`post_process` 报错，或类似 `【图鉴表】以下物品没有识别到获取方式[5100440170]` 这样的具体报错行。
```

Only continue when the pasted log includes an actionable diagnostic signal, such
as:

- `[Error tips] ...`
- Traceback lines.
- `check_rule.py` / `post_process.py` error text.
- A table validation message with a table/module/id/key/field, for example
  `【图鉴表】以下物品没有识别到获取方式[5100440170]`.

## Refresh Before Reading

Before opening tables, reading generated data, or checking SVN history, refresh
the relevant working copy:

- trunk tables: `excel-export-flow/vendor/trunk/策划表格`
- release/re tables: `excel-export-flow/vendor/re/策划表格`
- ExcelToData toolchain: `excel-export-flow/vendor/ExcelToData_py3`

Run `svn update` on the relevant working copy, or run the local
`excel-export-flow` `sync_vendor.py` if that is how the environment is set up.
If the relevant vendor directory is missing and cannot be refreshed, report the
missing local evidence and ask the user for the needed checkout/path.

## Error Extraction

From the user's log, extract:

- TOP plan id/link and branch evidence.
- `[Error tips]` lines.
- Traceback lines, especially the first failing function and exception type.
- Table display name, generated data module, id/key, field name, and referenced
  id/key.
- Whether the failure came from `check_rule.py`, `post_process.py`,
  `excel_to_data.py`, `export_new.py`, or TOP wrapper code.

Keep the raw error text in the final diagnosis so the user can map your answer
back to the original notification.

## Resolve Real Table And Data Source

Notification table names are often short aliases. Do not trust them as exact
`.xlsx` filenames.

Use generated data files as evidence:

1. Search the project `gclient/data`, `gserver/data`, and related generated data
   directories for the involved data module, id, or key.
2. Open the matching `*_origin.py` file and read its header comment to find the
   real source workbook name and sheet/export name.
3. If an `svn log` URL says the path does not exist, list the current branch's
   planning-table directory and resolve the real filename before continuing.

The diagnosis must connect the same id/key across:

- the raw error,
- the real workbook/sheet/row/field,
- the generated `*_data.py` or `*_origin.py`,
- the failing `check_rule` or `post_process` code path.

## Code And Table Trace

Use `vendor/ExcelToData_py3` as the current toolchain source of truth.

Typical mapping:

- `check_rule.py`: cross-table validation, existence checks, time/rule checks,
  DLC/model/icon/payment/task/activity validations.
- `post_process.py`: generated aggregates, collection/get-way generation, DLC
  post checks, derived dictionaries.
- `excel_to_data.py` / `export_new.py`: Excel read/export mechanics.
- TOP `for_svn_py3.py` / `svn_utils.py`: CI wrapper, notification, AI report,
  and Redmine/POPO routing.

If the error mentions `图鉴表 ... 没有识别到获取方式`, treat it as a
`post_process.py` generation problem, not a `check_rule.py` problem.

## Skip And Re/Trunk Data Flow Checks

For release/re failures involving `KeyError`, missing referenced ids, or
`不存在` errors, always check the skip path before concluding that a row is
simply absent:

1. Inspect the referenced row's `skip` value in the real workbook.
2. Inspect `00-skip开关表.xlsx` for the same skip name.
3. Compare `is_skip` and `is_release_skip`.
4. Confirm whether the failure is trunk or release/re.

Do not claim an id exists in release/re just because it exists in trunk
`*_origin.py`. Trunk generated data and release/re export data are separate
flows.

Useful distinction:

- `KeyError: <id>` in `post_process` usually means the merged data dict for that
  branch does not contain the key. For release/re, suspect skip gating first.
- An `[Error tips] ... 没填 DLC` line before failure means the key exists but a
  required DLC field or related value is missing.

## Blame And Responsibility

Do not use the CI notification author, `ExcelToDataAll`, `@mesg` service
accounts, or file-level `svn log -l N` alone as the responsible person.

Responsibility must come from row-level evidence:

1. Extract the row id/key from the error.
2. Use the local `excel-export-flow` blame/diff helper when available, for
   example `excel_id_blame.py <id>... [--prefer workbook]` or
   `excel_svn_diff.py --text-diff`.
3. Inspect the text diff and identify the revision that changed the exact row,
   field, reference, or skip value.
4. Run `svn log -r REV` on the correct branch path and use that revision author
   as the responsibility evidence.
5. If row-level evidence cannot be established, say so and ask for more log or
   table context. Do not invent a responsible person.

On Windows with Chinese workbook names, prefer URL-based `svn log` from the
workbook directory's `svn info URL` plus URL-encoded filename, and write output
as UTF-8 to avoid console encoding errors.

## Diagnosis Output

A useful export-error answer should include:

- Branch: trunk/release and the evidence, such as TOP plan id `1469` or `796`.
- Stage: `check_rule`, `post_process`, export read/write, or TOP wrapper.
- Real workbook/sheet/row/field and involved id/key.
- Failing function and generated data module.
- Root cause in plain language.
- Fix suggestion for the table owner.
- Responsibility evidence when row-level diff identifies it.
- Unknowns or required user input when evidence is missing.

## Rectification Checklist Handoff

If the user asks to整理导表报错, make a整改清单, 写 POPO 在线表格, or 发群:

1. Finish diagnosis first.
2. Build rows with ten columns:
   `序号 | 策划表 | 配置位置 | 问题类型 | 涉及ID | 原始报错 | 原因分析 | 修改建议 | 责任人 | 整改状态`.
3. Responsibility still requires row-level diff evidence.
4. Use the existing `excel-export-flow` rectification publishing workflow when
   available: write the fixed online POPO sheet and send the group notification
   through the Relu robot to group `8229532` with `@` responsible users.
5. If the local publishing config or robot credential is unavailable, report the
   exact missing setup instead of pretending the message was sent.

## Completion Status

- If branch/source is unclear, call `agent_task_status` with `needs_input` before
  replying.
- If the pasted export notification lacks actionable error details and only has
  the notification header, changed workbook list, TOP link, or a lone numeric
  footer such as `1`, call `agent_task_status` with `needs_input` and ask for the
  complete error log.
- If local evidence such as vendor tables or ExcelToData toolchain is missing,
  call `agent_task_status` with `blocked` or `needs_input` depending on whether
  user input can resolve it.
- If diagnosis is complete, call `agent_task_status` with `completed` and
  summarize the branch, root cause, fix, and evidence.
