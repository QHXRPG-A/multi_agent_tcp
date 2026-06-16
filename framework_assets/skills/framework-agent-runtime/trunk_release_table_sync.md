# Trunk To Release Planning Table Sync

Use this workflow when a planner asks the Agent to sync selected planning-table
content from trunk into release/re planning tables. Typical wording includes
"sync trunk to release", "copy this ticket to re", "move planning-table changes
to release", or "apply the trunk table diff to release".

This is a write workflow. It does not end at diagnosis. Once the required
number and target diff are clear, update the release/re planning table and then
summarize the changes. Do not commit release/re table changes.

## Fixed Local Sources

- Game source root:
  `F:\src\Package\Script\Python`
- Game expert knowledge root:
  `F:\src\Package\Script\Python\.codemaker\expert`
- Excel export skill root:
  `F:\src\Package\Script\Python\.codex\skills\excel-export-flow`
- Diff helpers:
  `F:\src\Package\Script\Python\.codex\skills\excel-export-flow\scripts\excel_svn_diff.py`
  and
  `F:\src\Package\Script\Python\.codex\skills\excel-export-flow\scripts\excel_id_blame.py`

Resolve the exact trunk/release planning-table workbook roots from
`excel-export-flow` (`paths.py`, `sync_vendor.json`, or the skill docs). Do not
hard-code a guessed Chinese workbook directory name when the helper can resolve
it.

## Required Input

The user must provide a number that identifies the trunk change: a ticket/order
number, Redmine number, SVN revision, or an explicit revision range.

- If the user did not provide such a number, ask for it before reading or
  writing tables.
- If the supplied number cannot be mapped to a trunk SVN revision or workbook
  change, ask for either the SVN revision/range or the affected workbook/id.
- If the user supplies exact revisions, use them directly.

Call `agent_task_status` with `needs_input` before replying when this required
input is missing.

## Guardrails

- Never run `svn commit`, `svn ci`, release export, or any submit step for this
  workflow. Release/re table commits must be performed by the user.
- Do not copy an entire workbook from trunk to release/re.
- Apply only cell/row changes proven by the trunk diff and relevant to the
  request.
- Preserve release-specific values, skip/re gating, columns, and branch-only
  rows.
- Before editing, run `svn update` for the relevant trunk and release/re
  planning-table working copies.
- When the Blueprint context exposes `table_queue_service`, occupy the target
  release/re workbook before writing and release it after the write/readback
  report. This release is table-occupation release, not SVN commit.
- Before editing release/re, inspect local status. If the target workbook
  already has unrelated local changes, report them and ask how to proceed.
- If release/re lacks the target workbook, sheet, row, or column, resolve the
  real release workbook name from generated data headers, `svn ls`, or the
  Excel export skill. If the mapping is still ambiguous, ask.
- If the current release/re value differs from both the trunk old value and the
  intended trunk new value, treat it as a branch conflict and ask before
  overwriting.

## Diff Lookup

1. Read the `excel-export-flow` skill or the helper docs if command details are
   needed.
2. Refresh the relevant vendor working copies.
3. Use the provided number to identify the trunk revision or revision range.
   Prefer SVN log evidence from the trunk planning-table working copy. If the
   number is a ticket/order number, search commit messages for that number.
4. For a known workbook, run:

   ```text
   python scripts/excel_svn_diff.py --file <workbook.xlsx> --branch trunk --rev-old <before> --rev-new <after> --text-diff
   ```

5. For row/id focused evidence, use `--id <id>` or
   `python scripts/excel_id_blame.py <id> --branch trunk --prefer <workbook>`.
6. Read `report.json`, especially `text_diff.sheets[].added_rows`,
   `removed_rows`, `modified_rows`, and cell-level `old`/`new` values.
7. Record the exact workbook, sheet, row key or row number, field/header, old
   value, new value, and source revision.

Do not use raw `svn diff` for `.xlsx`; it is binary and not a cell-level table
diff.

## Release/Re Edit

When the diff evidence is unambiguous:

1. Locate the matching release/re workbook and sheet.
2. Occupy the matching release/re workbook through `table_queue_service` when
   that ScriptNode path is available.
3. Read the current release/re target cells before writing.
4. Build the minimal edit set:
   - changed cells: write trunk new value into the matching release/re cell;
   - added rows: copy only the required row fields when the row should exist in
     release/re;
   - removed rows: do not delete release/re rows unless the user explicitly
     asked and the diff proves this is the intended release change.
5. Use the normal planning-table write boundary available in the current
   Blueprint context, such as the `xltool` resident service after consulting
   `blueprint_service_docs("xltool")`. If no resident-service boundary is
   available, use the existing safe workbook tooling from the local planning
   table workflow; do not hand-edit opaque workbook binaries blindly.
6. Read back the edited cells or rows after writing.
7. Release the table occupation if it was acquired.
8. Leave the release/re workbook modified locally for the user to review and
   commit.

This workflow is an explicit exception to the normal "wait for commit
confirmation" planning-table fill sequence: after an unambiguous sync request,
perform the release/re workbook edit, but stop before any commit.

## Completion Report

After editing, report:

- the input number and resolved trunk revision/range;
- trunk workbook/sheet/row/field diff evidence used;
- release/re workbook/sheet/cells changed;
- before and after values read back from release/re;
- any conflicts or skipped changes;
- validation/readback result;
- a clear note that no commit was performed and that the release/re table
  commit must be done by the user.

Call `agent_task_status` with `completed` only after the release/re workbook was
edited and read back, or with `needs_input` / `blocked` when the workflow cannot
proceed.
