"""Persistent Excel operation audit helpers for Blueprint sessions."""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Optional


EXCEL_OPS_DIRNAME = "excel_ops"
EXCEL_OPS_AGENT_DIRNAME = "agent"
EXCEL_OPS_USER_DIRNAME = "user"
EXCEL_OPS_BACKUP_DIRNAME = "backups"
EXCEL_AUDIT_SCHEMA_VERSION = 1
EXCEL_HISTORY_ROW_SNAPSHOT_RETURN_LIMIT = 20
XLTOOL_DEFAULT_EXE = Path(r"D:\excelize-cli\bin\xltool.exe")

XLTOOL_MUTATING_COMMANDS = {
    "append-row",
    "clear-cell",
    "clear-row",
    "copy-formulas",
    "copy-range",
    "copy-style",
    "duplicate-row",
    "import-json",
    "insert-rows",
    "insert-template-row",
    "remove-row",
    "rollback",
    "run-plan",
    "set-cell",
    "set-cells",
    "set-range",
    "set-row",
}
XLTOOL_SERVICE_METHOD_COMMANDS = {
    "append_row": "append-row",
    "clear_cell": "clear-cell",
    "clear_row": "clear-row",
    "copy_formulas": "copy-formulas",
    "copy_range": "copy-range",
    "copy_style": "copy-style",
    "duplicate_row": "duplicate-row",
    "import_json": "import-json",
    "insert_rows": "insert-rows",
    "insert_template_row": "insert-template-row",
    "remove_row": "remove-row",
    "rollback": "rollback",
    "run_plan": "run-plan",
    "set_cell": "set-cell",
    "set_cells": "set-cells",
    "set_range": "set-range",
    "set_row": "set-row",
}
TABLE_RELATED_SERVICES = {"table_queue", "xltool"}
XLTOOL_ROW_SNAPSHOT_COMMANDS = {
    "append-row",
    "clear-row",
    "duplicate-row",
    "insert-rows",
    "insert-template-row",
    "remove-row",
}


@dataclass
class PreparedExcelAudit:
    session_dir: Path
    session_key: str
    op_id: str
    timestamp_ms: int
    filename_stem: str
    service_name: str
    method_name: str
    arguments: Dict[str, Any]
    context: Dict[str, Any]
    category: str
    xltool: Dict[str, Any]


def parse_excel_log_command(text: str) -> Optional[str]:
    value = str(text or "").strip()
    if not value.startswith("/excel-log"):
        return None
    rest = value[len("/excel-log") :].strip()
    return rest


def parse_time_range(expression: str) -> tuple[int, int]:
    value = str(expression or "").strip()
    if not value:
        raise ValueError("time range is required")
    for separator in ("..", "~", "/", " - "):
        if separator in value:
            left, right = value.split(separator, 1)
            return _ordered_range(parse_time_value(left), parse_time_value(right))
    match = re.search(r"(?<=\d)-(?=\d{4}\b)", value)
    if match:
        left = value[: match.start()]
        right = value[match.end() :]
        return _ordered_range(parse_time_value(left), parse_time_value(right))
    numbers = [int(item) for item in re.findall(r"\d+", value)]
    if len(numbers) in {12, 14}:
        half = len(numbers) // 2
        return _ordered_range(_parts_to_epoch_ms(numbers[:half]), _parts_to_epoch_ms(numbers[half:]))
    raise ValueError("time range must contain two timestamps")


def parse_time_value(value: Any) -> int:
    if isinstance(value, (int, float)):
        number = float(value)
        return int(number if number > 10_000_000_000 else number * 1000)
    text = str(value or "").strip()
    if not text:
        raise ValueError("timestamp is required")
    numbers = [int(item) for item in re.findall(r"\d+", text)]
    if len(numbers) in {6, 7} and not re.search(r"[T:]", text):
        return _parts_to_epoch_ms(numbers)
    try:
        normalized = text.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        if len(numbers) in {6, 7}:
            return _parts_to_epoch_ms(numbers)
        raise
    return int(parsed.timestamp() * 1000)


def format_local_time(epoch_ms: int) -> str:
    dt = datetime.fromtimestamp(int(epoch_ms) / 1000.0)
    return dt.strftime("%Y-%m-%d %H:%M:%S.") + f"{int(epoch_ms) % 1000:03d}"


def sortable_time_label(epoch_ms: int) -> str:
    dt = datetime.fromtimestamp(int(epoch_ms) / 1000.0)
    return dt.strftime("%Y%m%d_%H%M%S_") + f"{int(epoch_ms) % 1000:03d}"


def prepare_service_call_audit(
    audit_context: Optional[Dict[str, Any]],
    service_name: str,
    method_name: str,
    arguments: Dict[str, Any],
    *,
    now: Callable[[], float] = time.time,
) -> Optional[PreparedExcelAudit]:
    service = str(service_name or "").strip()
    method = str(method_name or "").strip()
    if service not in TABLE_RELATED_SERVICES:
        return None
    context = dict(audit_context or {})
    raw_session_dir = context.get("session_dir") or context.get("sessionDir")
    session_key = str(context.get("session_key") or context.get("sessionKey") or "").strip()
    if not raw_session_dir or not session_key:
        return None
    session_dir = Path(str(raw_session_dir))
    timestamp_ms = int(float(now()) * 1000)
    op_id = uuid.uuid4().hex[:12]
    filename_stem = f"{timestamp_ms}_{sortable_time_label(timestamp_ms)}_{op_id}"
    clean_arguments = _json_safe(arguments or {})
    category = "xltool" if service == "xltool" else "table_queue"
    xltool = _xltool_audit_details(session_dir, filename_stem, method, clean_arguments) if service == "xltool" else {}
    return PreparedExcelAudit(
        session_dir=session_dir,
        session_key=session_key,
        op_id=op_id,
        timestamp_ms=timestamp_ms,
        filename_stem=filename_stem,
        service_name=service,
        method_name=method,
        arguments=clean_arguments,
        context=context,
        category=category,
        xltool=xltool,
    )


def finalize_service_call_audit(prepared: Optional[PreparedExcelAudit], result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if prepared is None:
        return None
    clean_result = _json_safe(result or {})
    ok = bool(clean_result.get("ok"))
    changed = _result_changed(clean_result)
    if prepared.xltool:
        prepared.xltool["changed"] = changed
        data = clean_result.get("data")
        if isinstance(data, dict):
            output = data.get("output") or data.get("file")
            backup = data.get("backup")
            if output:
                prepared.xltool["resultOutput"] = str(output)
            if backup:
                prepared.xltool["resultBackup"] = str(backup)
        if ok:
            _xltool_capture_after_row_snapshot(prepared.xltool, prepared.method_name, prepared.arguments, clean_result)
    record = {
        "schemaVersion": EXCEL_AUDIT_SCHEMA_VERSION,
        "opId": prepared.op_id,
        "timestampMs": prepared.timestamp_ms,
        "time": format_local_time(prepared.timestamp_ms),
        "sessionKey": prepared.session_key,
        "runId": str(prepared.context.get("run_id") or prepared.context.get("runId") or ""),
        "projectDir": str(prepared.context.get("project_dir") or prepared.context.get("projectDir") or ""),
        "blueprintId": str(prepared.context.get("blueprint_id") or prepared.context.get("blueprintId") or ""),
        "sourceNodeId": str(prepared.context.get("source_node_id") or prepared.context.get("sourceNodeId") or ""),
        "scriptNodeId": str(prepared.context.get("script_node_id") or prepared.context.get("scriptNodeId") or ""),
        "batchId": str(prepared.context.get("batch_id") or prepared.context.get("batchId") or ""),
        "category": prepared.category,
        "serviceName": prepared.service_name,
        "methodName": prepared.method_name,
        "status": "succeeded" if ok else "failed",
        "arguments": prepared.arguments,
        "result": clean_result,
    }
    if prepared.xltool:
        record["xltool"] = prepared.xltool
    _write_record(prepared.session_dir, prepared.filename_stem, record)
    return record


def list_agent_records(session_dir: Path, start_ms: int, end_ms: int) -> list[Dict[str, Any]]:
    agent_dir = Path(session_dir) / EXCEL_OPS_DIRNAME / EXCEL_OPS_AGENT_DIRNAME
    if not agent_dir.is_dir():
        return []
    rows: list[Dict[str, Any]] = []
    for path in sorted(agent_dir.glob("*.json")):
        timestamp_ms = _timestamp_from_filename(path)
        if timestamp_ms is None or timestamp_ms < int(start_ms) or timestamp_ms > int(end_ms):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict):
            data.setdefault("_path", str(path))
            rows.append(data)
    rows.sort(key=lambda item: (int(item.get("timestampMs") or 0), str(item.get("opId") or "")))
    return rows


def render_user_log(session_dir: Path, start_ms: int, end_ms: int) -> str:
    records = list_agent_records(session_dir, start_ms, end_ms)
    header = f"Excel log {format_local_time(start_ms)} - {format_local_time(end_ms)}"
    if not records:
        return header + "\nNo Excel operations found in this session for the requested range."
    lines = [header, f"{len(records)} operation(s).", ""]
    for record in records:
        lines.append(render_user_record(record))
    return "\n".join(lines).rstrip()


def query_excel_history(
    session_dir: Path,
    *,
    start_time: str = "",
    end_time: str = "",
    workbook: str = "",
    field: str = "",
    category: str = "xltool",
    limit: int = 50,
    now: Callable[[], float] = time.time,
) -> Dict[str, Any]:
    session_dir = Path(session_dir)
    category_value = str(category or "xltool").strip().lower()
    if category_value not in {"xltool", "table_queue", "all"}:
        raise ValueError("category must be one of: xltool, table_queue, all")
    start_text = str(start_time or "").strip()
    end_text = str(end_time or "").strip()
    has_time_range = bool(start_text or end_text)
    if has_time_range and not (start_text and end_text):
        raise ValueError("start_time and end_time must both be provided when filtering by time")
    if has_time_range:
        start_ms, end_ms = _ordered_range(parse_time_value(start_text), parse_time_value(end_text))
    else:
        start_ms = 0
        end_ms = 2**63 - 1
    count = max(1, min(int(limit or 50), 200))
    workbook_filter = str(workbook or "").strip()
    field_filter = str(field or "").strip()
    records = list_agent_records(session_dir, start_ms, end_ms)
    filtered = [
        record
        for record in records
        if _record_matches_category(record, category_value)
        and _record_matches_workbook(record, workbook_filter)
        and _record_matches_field(record, field_filter)
    ]
    filtered.sort(key=lambda item: (int(item.get("timestampMs") or 0), str(item.get("opId") or "")), reverse=True)
    selected = filtered[:count]
    return {
        "ok": True,
        "timeRangeProvided": has_time_range,
        "startMs": start_ms if has_time_range else None,
        "endMs": end_ms if has_time_range else None,
        "category": category_value,
        "limit": count,
        "totalMatches": len(filtered),
        "count": len(selected),
        "truncated": len(filtered) > len(selected),
        "rowSnapshotLimit": EXCEL_HISTORY_ROW_SNAPSHOT_RETURN_LIMIT,
        "records": [excel_history_record_summary(record) for record in selected],
    }


def excel_history_record_summary(record: Dict[str, Any], *, row_snapshot_limit: int = EXCEL_HISTORY_ROW_SNAPSHOT_RETURN_LIMIT) -> Dict[str, Any]:
    xltool = record.get("xltool") if isinstance(record.get("xltool"), dict) else {}
    backup_path = str(
        xltool.get("backupPath")
        or xltool.get("backup_path")
        or xltool.get("backup")
        or ""
    )
    backup_available = xltool.get("backupAvailable")
    if backup_available is None:
        backup_available = bool(backup_path and Path(backup_path).is_file())
    target_existed = xltool.get("targetExisted")
    if target_existed is None:
        target_existed = xltool.get("target_existed")
    before_rows, before_total, before_truncated = _limited_row_snapshots(xltool.get("beforeRows"), row_snapshot_limit)
    after_rows, after_total, after_truncated = _limited_row_snapshots(xltool.get("afterRows"), row_snapshot_limit)
    row_snapshot_truncated = before_truncated or after_truncated
    summary = {
        "opId": str(record.get("opId") or ""),
        "timestampMs": int(record.get("timestampMs") or 0),
        "time": str(record.get("time") or ""),
        "sourceNodeId": str(record.get("sourceNodeId") or ""),
        "scriptNodeId": str(record.get("scriptNodeId") or ""),
        "category": str(record.get("category") or ""),
        "serviceName": str(record.get("serviceName") or ""),
        "methodName": str(record.get("methodName") or ""),
        "status": str(record.get("status") or ""),
        "workbook": _record_workbook_text(record),
        "command": str(xltool.get("command") or ""),
        "arguments": _json_safe(record.get("arguments") or {}),
        "resultSummary": _result_summary(record.get("result")),
        "backupPath": backup_path,
        "hasBackup": bool(backup_path and backup_available),
        "targetExisted": target_existed,
        "beforeAfterStatus": str(xltool.get("beforeAfterStatus") or ""),
        "beforeAfter": _json_safe(xltool.get("beforeAfter") or []),
        "rowSnapshotStatus": str(xltool.get("rowSnapshotStatus") or ""),
        "beforeRows": before_rows,
        "afterRows": after_rows,
        "beforeRowsTotal": before_total,
        "beforeRowsReturned": len(before_rows),
        "afterRowsTotal": after_total,
        "afterRowsReturned": len(after_rows),
        "rowSnapshotLimit": max(0, int(row_snapshot_limit or 0)),
        "rowSnapshotTruncated": row_snapshot_truncated,
        "userSummary": render_user_record(record),
    }
    if row_snapshot_truncated:
        total = max(before_total, after_total)
        returned = max(len(before_rows), len(after_rows))
        summary["rowSnapshotMessage"] = (
            f"Row snapshot contains {total} row(s); only {returned} row(s) are returned. "
            "Narrow the workbook, field, time, or row range before using this record for rollback."
        )
    return summary


def render_user_record(record: Dict[str, Any]) -> str:
    status = str(record.get("status") or "unknown").upper()
    service = str(record.get("serviceName") or "")
    method = str(record.get("methodName") or "")
    time_text = str(record.get("time") or format_local_time(int(record.get("timestampMs") or 0)))
    lines = [f"- [{time_text}] {status} {service}.{method}"]
    source = str(record.get("sourceNodeId") or record.get("scriptNodeId") or "")
    if source:
        lines.append(f"  Agent: {source}")
    xltool = record.get("xltool")
    if isinstance(xltool, dict):
        command = str(xltool.get("command") or "")
        workbook = str(xltool.get("workbook") or "")
        if command:
            lines.append(f"  Command: {command}")
        if workbook:
            lines.append(f"  Workbook: {workbook}")
        if xltool.get("mutating"):
            before_after = xltool.get("beforeAfter") if isinstance(xltool.get("beforeAfter"), list) else []
            if before_after:
                lines.append(f"  Old/new cells: {len(before_after)}")
            elif xltool.get("beforeAfterStatus"):
                lines.append(f"  Old/new cells: {xltool.get('beforeAfterStatus')}")
            before_rows = xltool.get("beforeRows") if isinstance(xltool.get("beforeRows"), list) else []
            after_rows = xltool.get("afterRows") if isinstance(xltool.get("afterRows"), list) else []
            if before_rows or after_rows:
                lines.append(f"  Row snapshots: before {len(before_rows)} / after {len(after_rows)}")
            elif xltool.get("rowSnapshotStatus"):
                lines.append(f"  Row snapshots: {xltool.get('rowSnapshotStatus')}")
            if xltool.get("backupPath") or xltool.get("backupAvailable"):
                lines.append(f"  Legacy backup: {'yes' if xltool.get('backupAvailable') else 'no'}")
    if service == "table_queue":
        tables = _table_names_from_arguments(record.get("arguments"))
        if tables:
            lines.append("  Tables: " + ", ".join(tables[:8]))
    error = ""
    result = record.get("result")
    if isinstance(result, dict):
        error = str(result.get("error") or "")
    if record.get("error"):
        error = str(record.get("error") or "")
    if error:
        lines.append(f"  Error: {error}")
    return "\n".join(lines)


def _ordered_range(start_ms: int, end_ms: int) -> tuple[int, int]:
    if start_ms <= end_ms:
        return start_ms, end_ms
    return end_ms, start_ms


def _parts_to_epoch_ms(parts: Iterable[int]) -> int:
    values = list(parts)
    if len(values) not in {6, 7}:
        raise ValueError("timestamp must have 6 or 7 numeric fields")
    year, month, day, hour, minute, second = values[:6]
    millisecond = values[6] if len(values) == 7 else 0
    dt = datetime(year, month, day, hour, minute, second, millisecond * 1000)
    return int(dt.timestamp() * 1000)


def _excel_ops_dir(session_dir: Path) -> Path:
    return Path(session_dir) / EXCEL_OPS_DIRNAME


def _write_record(session_dir: Path, filename_stem: str, record: Dict[str, Any]) -> None:
    root = _excel_ops_dir(session_dir)
    agent_dir = root / EXCEL_OPS_AGENT_DIRNAME
    user_dir = root / EXCEL_OPS_USER_DIRNAME
    agent_dir.mkdir(parents=True, exist_ok=True)
    user_dir.mkdir(parents=True, exist_ok=True)
    (agent_dir / f"{filename_stem}.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (user_dir / f"{filename_stem}.md").write_text(render_user_record(record) + "\n", encoding="utf-8")


def _xltool_audit_details(session_dir: Path, filename_stem: str, method_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    command, command_args = _xltool_command_and_args(method_name, arguments)
    mutating = command in XLTOOL_MUTATING_COMMANDS
    workbook = _xltool_target_workbook(command_args)
    details: Dict[str, Any] = {
        "command": command,
        "mutating": mutating,
        "workbook": str(workbook) if workbook is not None else "",
        "sourceFile": str(command_args.get("file") or ""),
        "backupPath": "",
        "backupAvailable": False,
        "targetExisted": None,
        "beforeAfterStatus": "not_mutating" if not mutating else "",
        "beforeAfter": [],
        "rowSnapshotStatus": "not_mutating" if not mutating else "",
        "beforeRows": [],
        "afterRows": [],
    }
    if not mutating or workbook is None:
        return details
    target = Path(workbook).expanduser()
    details["targetExisted"] = target.is_file()
    source_workbook = _xltool_source_workbook(command_args) or str(workbook)
    source = Path(source_workbook).expanduser()
    details["sourceExisted"] = source.is_file()
    before_after, status = _xltool_before_after_snapshot(command, command_args, source)
    details["beforeAfter"] = before_after
    details["beforeAfterStatus"] = status
    before_rows, row_status, row_metadata = _xltool_before_row_snapshot(command, command_args, source)
    details["beforeRows"] = before_rows
    details["rowSnapshotStatus"] = row_status
    if row_metadata:
        details["rowSnapshotMetadata"] = row_metadata
    return details


def _xltool_before_after_snapshot(command: str, arguments: Dict[str, Any], workbook: Path) -> tuple[list[Dict[str, Any]], str]:
    if command not in {"clear-cell", "set-cell", "set-cells", "set-row"}:
        return [], "unsupported"
    if not workbook.is_file():
        return [], "target_missing"
    sheet_name = _xltool_sheet_name(arguments)
    if not sheet_name:
        return [], "sheet_missing"

    if command in {"clear-cell", "set-cell"}:
        cell = str(arguments.get("cell") or arguments.get("coordinate") or "").strip()
        if not cell:
            return [], "cell_missing"
        data, error = _xltool_read_cell(workbook, sheet_name, cell)
        if error:
            return [], error
        return [
            _xltool_before_after_entry(
                workbook=workbook,
                sheet_name=sheet_name,
                cell_data=data.get("cell") if isinstance(data, dict) else {},
                field="",
                new_value="" if command == "clear-cell" else arguments.get("value"),
            )
        ], "captured"

    row = _int_or_none(arguments.get("row"))
    values = _xltool_write_values(arguments)
    if row is None or not isinstance(values, dict) or not values:
        return [], "row_or_values_missing"
    header_row = _int_or_none(arguments.get("header_row") or arguments.get("headerRow") or arguments.get("header-row"))
    entries: list[Dict[str, Any]] = []
    missing_fields: list[str] = []
    for field, new_value in values.items():
        field_text = str(field)
        data, error = _xltool_read_field(workbook, sheet_name, int(row), field_text, header_row)
        if error and _is_column_key(field_text):
            data, error = _xltool_read_cell(workbook, sheet_name, f"{field_text.upper()}{int(row)}")
        if error:
            missing_fields.append(f"{field_text}({error})")
            continue
        cell_data = data.get("cell") if isinstance(data, dict) else {}
        entries.append(
            _xltool_before_after_entry(
                workbook=workbook,
                sheet_name=sheet_name,
                cell_data=cell_data,
                field=field_text,
                new_value=new_value,
            )
        )
    if entries and not missing_fields:
        return entries, "captured"
    if entries:
        return entries, "partial:" + ",".join(missing_fields[:8])
    return [], "field_missing:" + ",".join(missing_fields[:8])


def _xltool_before_row_snapshot(
    command: str,
    arguments: Dict[str, Any],
    workbook: Path,
) -> tuple[list[Dict[str, Any]], str, Dict[str, Any]]:
    if command not in XLTOOL_ROW_SNAPSHOT_COMMANDS:
        return [], "not_applicable", {}
    if not workbook.is_file():
        return [], "target_missing", {}
    sheet_name = _xltool_sheet_name(arguments)
    if not sheet_name:
        return [], "sheet_missing", {}

    header_row = _xltool_header_row(arguments)
    metadata: Dict[str, Any] = {}
    if command == "append-row":
        max_row, error = _xltool_sheet_max_row(workbook, sheet_name)
        if error:
            return [], "awaiting_after:" + error, metadata
        metadata["sourceMaxRow"] = max_row
        return [], "awaiting_after", metadata

    specs = _xltool_before_row_specs(command, arguments)
    if not specs:
        return [], "row_missing", metadata
    rows, status = _xltool_read_row_snapshots(workbook, sheet_name, specs, header_row)
    return rows, status, metadata


def _xltool_capture_after_row_snapshot(
    xltool: Dict[str, Any],
    method_name: str,
    arguments: Dict[str, Any],
    result: Dict[str, Any],
) -> None:
    command, command_args = _xltool_command_and_args(method_name, arguments)
    if command not in XLTOOL_ROW_SNAPSHOT_COMMANDS:
        return
    workbook_text = str(xltool.get("resultOutput") or xltool.get("workbook") or "").strip()
    if not workbook_text:
        _update_row_snapshot_status(xltool, "after_workbook_missing")
        return
    workbook = Path(workbook_text).expanduser()
    if not workbook.is_file():
        _update_row_snapshot_status(xltool, "after_target_missing")
        return
    sheet_name = _xltool_sheet_name(command_args)
    if not sheet_name:
        _update_row_snapshot_status(xltool, "sheet_missing")
        return
    specs = _xltool_after_row_specs(command, command_args, result, xltool, workbook, sheet_name)
    if not specs:
        _update_row_snapshot_status(xltool, "no_after_rows")
        return
    rows, status = _xltool_read_row_snapshots(workbook, sheet_name, specs, _xltool_header_row(command_args))
    xltool["afterRows"] = rows
    _update_row_snapshot_status(xltool, status)


def _xltool_before_row_specs(command: str, arguments: Dict[str, Any]) -> list[tuple[int, str]]:
    if command == "remove-row":
        row = _argument_int(arguments, "row")
        return _row_specs_from_start(row, 1, "deleted")
    if command == "clear-row":
        row = _argument_int(arguments, "row")
        return _row_specs_from_start(row, 1, "before")
    if command == "duplicate-row":
        row = _argument_int(arguments, "from_row", "fromRow", "from-row", "row")
        return _row_specs_from_start(row, 1, "source")
    if command == "insert-template-row":
        row = _argument_int(arguments, "template_row", "templateRow", "template-row")
        return _row_specs_from_start(row, 1, "template")
    if command == "insert-rows":
        return []
    return []


def _xltool_after_row_specs(
    command: str,
    arguments: Dict[str, Any],
    result: Dict[str, Any],
    xltool: Dict[str, Any],
    workbook: Path,
    sheet_name: str,
) -> list[tuple[int, str]]:
    if command == "remove-row":
        return []
    if command == "clear-row":
        row = _argument_int(arguments, "row")
        return _row_specs_from_start(row, 1, "after")
    if command == "insert-rows":
        after_row = _argument_int(arguments, "after_row", "afterRow", "after-row")
        start_row = _argument_int(arguments, "row", "start_row", "startRow", "start-row")
        if start_row is None and after_row is not None:
            start_row = after_row + 1
        return _row_specs_from_start(start_row, _xltool_row_count(arguments), "inserted")
    if command == "insert-template-row":
        after_row = _argument_int(arguments, "after_row", "afterRow", "after-row")
        start_row = after_row + 1 if after_row is not None else _argument_int(arguments, "row")
        return _row_specs_from_start(start_row, 1, "inserted")
    if command == "duplicate-row":
        row = _argument_int(arguments, "to_row", "toRow", "to-row")
        return _row_specs_from_start(row, 1, "inserted")
    if command == "append-row":
        row = _result_row(result)
        if row is None:
            metadata = xltool.get("rowSnapshotMetadata") if isinstance(xltool.get("rowSnapshotMetadata"), dict) else {}
            source_max_row = _int_or_none(metadata.get("sourceMaxRow"))
            if source_max_row is not None:
                row = source_max_row + 1
        if row is None:
            max_row, error = _xltool_sheet_max_row(workbook, sheet_name)
            if not error:
                row = max_row
        return _row_specs_from_start(row, 1, "inserted")
    return []


def _xltool_read_row_snapshots(
    workbook: Path,
    sheet_name: str,
    specs: list[tuple[int, str]],
    header_row: Optional[int],
) -> tuple[list[Dict[str, Any]], str]:
    entries: list[Dict[str, Any]] = []
    errors: list[str] = []
    for row, role in _dedupe_row_specs(specs):
        data, error = _xltool_read_row(workbook, sheet_name, row, header_row)
        if error:
            errors.append(f"{row}({error})")
            continue
        entries.append(
            _xltool_row_snapshot_entry(
                workbook=workbook,
                sheet_name=sheet_name,
                row=row,
                role=role,
                header_row=header_row,
                row_data=data,
            )
        )
    if entries and not errors:
        return entries, "captured"
    if entries:
        return entries, "partial:" + ",".join(errors[:8])
    return [], "row_read_failed:" + ",".join(errors[:8])


def _xltool_row_snapshot_entry(
    *,
    workbook: Path,
    sheet_name: str,
    row: int,
    role: str,
    header_row: Optional[int],
    row_data: Any,
) -> Dict[str, Any]:
    data = row_data if isinstance(row_data, dict) else {}
    entry = {
        "workbook": str(workbook),
        "sheet": sheet_name,
        "row": int(row),
        "role": role,
        "headerRow": header_row,
        "values": _json_safe(data.get("values") if isinstance(data.get("values"), dict) else {}),
        "coordinates": _json_safe(data.get("coordinates") if isinstance(data.get("coordinates"), dict) else {}),
        "cells": _json_safe(data.get("cells") if isinstance(data.get("cells"), list) else []),
    }
    fields = data.get("fields")
    if isinstance(fields, list):
        entry["fields"] = _json_safe(fields)
    return entry


def _xltool_read_row(
    workbook: Path,
    sheet_name: str,
    row: int,
    header_row: Optional[int],
) -> tuple[Dict[str, Any], str]:
    args = ["--file", str(workbook), "--sheet", sheet_name, "--row", str(row)]
    if header_row is not None:
        args.extend(["--header-row", str(header_row)])
    payload, error = _run_xltool_json("read-row", args)
    if error:
        return {}, error
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        return {}, "xltool_invalid_read_row"
    return data, ""


def _xltool_sheet_max_row(workbook: Path, sheet_name: str) -> tuple[Optional[int], str]:
    payload, error = _run_xltool_json("inspect", ["--file", str(workbook)])
    if error:
        return None, error
    data = payload.get("data") if isinstance(payload, dict) else None
    sheets = data.get("sheets") if isinstance(data, dict) else None
    if not isinstance(sheets, list):
        return None, "xltool_invalid_inspect"
    for sheet in sheets:
        if not isinstance(sheet, dict):
            continue
        if str(sheet.get("name") or "") == sheet_name:
            max_row = _int_or_none(sheet.get("max_row") or sheet.get("maxRow"))
            if max_row is None:
                return None, "sheet_max_row_missing"
            return max_row, ""
    return None, "sheet_not_found"


def _xltool_header_row(arguments: Dict[str, Any]) -> Optional[int]:
    return _argument_int(arguments, "header_row", "headerRow", "header-row")


def _xltool_row_count(arguments: Dict[str, Any]) -> int:
    value = _argument_value(arguments, "count", "row_count", "rowCount", "row-count", "num_rows", "numRows", "num-rows", "rows")
    if isinstance(value, list):
        return max(1, len(value))
    count = _int_or_none(value)
    return max(1, count or 1)


def _row_specs_from_start(start_row: Optional[int], count: int, role: str) -> list[tuple[int, str]]:
    if start_row is None or start_row <= 0:
        return []
    safe_count = max(1, int(count or 1))
    return [(start_row + offset, role) for offset in range(safe_count)]


def _dedupe_row_specs(specs: list[tuple[int, str]]) -> list[tuple[int, str]]:
    seen: set[tuple[int, str]] = set()
    output: list[tuple[int, str]] = []
    for row, role in specs:
        key = (int(row), str(role or ""))
        if key in seen:
            continue
        seen.add(key)
        output.append(key)
    return output


def _argument_value(arguments: Dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in arguments:
            return arguments.get(key)
    return None


def _argument_int(arguments: Dict[str, Any], *keys: str) -> Optional[int]:
    return _int_or_none(_argument_value(arguments, *keys))


def _result_row(result: Dict[str, Any]) -> Optional[int]:
    data = result.get("data") if isinstance(result, dict) else None
    candidates: list[Any] = []
    if isinstance(data, dict):
        for key in (
            "matched_row",
            "matchedRow",
            "row",
            "target_row",
            "targetRow",
            "inserted_row",
            "insertedRow",
            "appended_row",
            "appendedRow",
        ):
            candidates.append(data.get(key))
    for key in ("matched_row", "matchedRow", "row"):
        candidates.append(result.get(key))
    for value in candidates:
        row = _int_or_none(value)
        if row is not None:
            return row
    return None


def _update_row_snapshot_status(xltool: Dict[str, Any], after_status: str) -> None:
    before_rows = xltool.get("beforeRows") if isinstance(xltool.get("beforeRows"), list) else []
    after_rows = xltool.get("afterRows") if isinstance(xltool.get("afterRows"), list) else []
    existing = str(xltool.get("rowSnapshotStatus") or "").strip()
    status = str(after_status or "").strip()
    if before_rows and after_rows:
        xltool["rowSnapshotStatus"] = "captured"
        return
    if before_rows:
        xltool["rowSnapshotStatus"] = "captured_before"
        return
    if after_rows:
        xltool["rowSnapshotStatus"] = "captured_after"
        return
    if existing and existing not in {"awaiting_after", "not_applicable"}:
        if status and status not in {existing, "no_after_rows"}:
            xltool["rowSnapshotStatus"] = f"{existing};{status}"
        return
    if status:
        xltool["rowSnapshotStatus"] = status


def _xltool_executable() -> str:
    configured = str(os.environ.get("XLTOOL_EXE") or os.environ.get("XLTOOL_PATH") or "").strip()
    if configured:
        return configured
    if XLTOOL_DEFAULT_EXE.is_file():
        return str(XLTOOL_DEFAULT_EXE)
    return "xltool"


def _run_xltool_json(command: str, args: list[str]) -> tuple[Optional[Dict[str, Any]], str]:
    try:
        completed = subprocess.run(
            [_xltool_executable(), command, *args],
            text=True,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
    except FileNotFoundError:
        return None, "xltool_unavailable"
    except subprocess.TimeoutExpired:
        return None, "xltool_timeout"
    except Exception as exc:  # pragma: no cover - defensive runtime boundary
        return None, "xltool_failed:" + _short_status(str(exc))

    payload: Optional[Dict[str, Any]] = None
    stdout = str(completed.stdout or "").strip()
    if stdout:
        try:
            parsed = json.loads(stdout)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            payload = parsed
    if completed.returncode != 0:
        message = ""
        if isinstance(payload, dict):
            message = str(payload.get("error") or "")
        if not message:
            message = str(completed.stderr or stdout or f"exit_{completed.returncode}")
        return payload, "xltool_error:" + _short_status(message)
    if payload is None:
        return None, "xltool_invalid_json"
    if payload.get("ok") is not True:
        return payload, "xltool_error:" + _short_status(str(payload.get("error") or "not_ok"))
    return payload, ""


def _xltool_read_cell(workbook: Path, sheet_name: str, cell: str) -> tuple[Dict[str, Any], str]:
    payload, error = _run_xltool_json(
        "read-cell",
        ["--file", str(workbook), "--sheet", sheet_name, "--cell", cell],
    )
    if error:
        return {}, error
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict) or not isinstance(data.get("cell"), dict):
        return {}, "xltool_invalid_read_cell"
    return data, ""


def _xltool_read_field(
    workbook: Path,
    sheet_name: str,
    row: int,
    field: str,
    header_row: Optional[int],
) -> tuple[Dict[str, Any], str]:
    args = ["--file", str(workbook), "--sheet", sheet_name, "--row", str(row), "--field", field]
    if header_row is not None:
        args.extend(["--header-row", str(header_row)])
    payload, error = _run_xltool_json("read-field", args)
    if error:
        return {}, error
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict) or not isinstance(data.get("cell"), dict):
        return {}, "xltool_invalid_read_field"
    return data, ""


def _xltool_before_after_entry(
    *,
    workbook: Path,
    sheet_name: str,
    cell_data: Any,
    field: str,
    new_value: Any,
) -> Dict[str, Any]:
    cell = cell_data if isinstance(cell_data, dict) else {}
    return {
        "workbook": str(workbook),
        "sheet": sheet_name,
        "cell": str(cell.get("cell") or ""),
        "row": _int_or_none(cell.get("row")) or 0,
        "column": str(cell.get("col_name") or ""),
        "field": field,
        "oldValue": _excel_value_safe(cell.get("value")),
        "newValue": _excel_value_safe(new_value),
    }


def _xltool_sheet_name(arguments: Dict[str, Any]) -> str:
    return str(arguments.get("sheet") or arguments.get("sheet_name") or arguments.get("sheetName") or "").strip()


def _xltool_write_values(arguments: Dict[str, Any]) -> Any:
    for key in ("values", "json_payload", "json", "data", "cells"):
        value = arguments.get(key)
        if isinstance(value, dict):
            return value
        if key == "json" and isinstance(value, str) and value.strip():
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict):
                return parsed
    for key in ("json_file", "jsonFile", "json-file"):
        value = str(arguments.get(key) or "").strip()
        if not value:
            continue
        try:
            parsed = json.loads(Path(value).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _is_column_key(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z]{1,3}", str(value or "").strip()))


def _int_or_none(value: Any) -> Optional[int]:
    try:
        if value is None or str(value).strip() == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _excel_value_safe(value: Any) -> Any:
    return _json_safe(value)


def _short_status(value: str, limit: int = 180) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _xltool_command_and_args(method_name: str, arguments: Dict[str, Any]) -> tuple[str, Dict[str, Any]]:
    method = str(method_name or "").strip()
    if method == "run":
        command = str(arguments.get("command") or "").strip()
        raw_args = arguments.get("arguments") if isinstance(arguments.get("arguments"), dict) else {}
        return command, dict(raw_args)
    command = XLTOOL_SERVICE_METHOD_COMMANDS.get(method, method.replace("_", "-"))
    return command, dict(arguments)


def _xltool_target_workbook(arguments: Dict[str, Any]) -> Optional[str]:
    output = str(arguments.get("out") or arguments.get("output") or "").strip()
    if output:
        return output
    file_value = str(arguments.get("file") or "").strip()
    return file_value or None


def _xltool_source_workbook(arguments: Dict[str, Any]) -> Optional[str]:
    file_value = str(arguments.get("file") or "").strip()
    return file_value or None


def _result_changed(result: Dict[str, Any]) -> bool:
    if "changed" in result:
        return bool(result.get("changed"))
    data = result.get("data")
    if isinstance(data, dict) and "changed" in data:
        return bool(data.get("changed"))
    return bool(result.get("ok"))


def _timestamp_from_filename(path: Path) -> Optional[int]:
    head = path.name.split("_", 1)[0]
    try:
        return int(head)
    except ValueError:
        return None


def _record_matches_category(record: Dict[str, Any], category: str) -> bool:
    if category == "all":
        return True
    return str(record.get("category") or "").strip().lower() == category


def _record_matches_workbook(record: Dict[str, Any], needle: str) -> bool:
    if not needle:
        return True
    haystack = _record_workbook_text(record).casefold()
    return needle.casefold() in haystack


def _record_matches_field(record: Dict[str, Any], needle: str) -> bool:
    if not needle:
        return True
    value = needle.casefold()
    return any(value in item.casefold() for item in _record_field_texts(record))


def _record_workbook_text(record: Dict[str, Any]) -> str:
    xltool = record.get("xltool") if isinstance(record.get("xltool"), dict) else {}
    workbook = str(xltool.get("workbook") or xltool.get("workbookPath") or xltool.get("workbook_path") or "").strip()
    if workbook:
        return workbook
    tables = _table_names_from_arguments(record.get("arguments"))
    return ", ".join(tables)


def _record_field_texts(record: Dict[str, Any]) -> list[str]:
    texts: list[str] = []
    arguments = record.get("arguments")
    if isinstance(arguments, dict):
        _collect_field_texts(arguments, texts)
        method = str(record.get("methodName") or "")
        _command, command_args = _xltool_command_and_args(method, arguments)
        _collect_field_texts(command_args, texts)
    xltool = record.get("xltool") if isinstance(record.get("xltool"), dict) else {}
    before_after = xltool.get("beforeAfter")
    if isinstance(before_after, list):
        _collect_field_texts(before_after, texts)
    before_rows = xltool.get("beforeRows")
    if isinstance(before_rows, list):
        _collect_field_texts(before_rows, texts)
    after_rows = xltool.get("afterRows")
    if isinstance(after_rows, list):
        _collect_field_texts(after_rows, texts)
    return [item for item in texts if item]


def _collect_field_texts(value: Any, output: list[str], *, key_hint: str = "") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key)
            lower_key = key_text.casefold()
            if "field" in lower_key:
                output.append(key_text)
                if isinstance(item, (str, int, float, bool)):
                    output.append(str(item))
                elif isinstance(item, list):
                    output.extend(str(entry) for entry in item if isinstance(entry, (str, int, float, bool)))
                elif isinstance(item, dict):
                    output.extend(str(entry_key) for entry_key in item.keys())
            if lower_key in {"values", "value", "row", "rows", "updates", "data", "cells"} and isinstance(item, dict):
                output.extend(str(entry_key) for entry_key in item.keys())
            _collect_field_texts(item, output, key_hint=key_text)
    elif isinstance(value, list):
        for item in value:
            _collect_field_texts(item, output, key_hint=key_hint)


def _result_summary(result: Any) -> Dict[str, Any]:
    if not isinstance(result, dict):
        return {"type": type(result).__name__}
    summary: Dict[str, Any] = {}
    for key in ("ok", "code", "error", "changed", "exit_code", "service_name", "method_name"):
        if key in result:
            summary[key] = result.get(key)
    data = result.get("data")
    if isinstance(data, dict):
        data_summary: Dict[str, Any] = {}
        for key in ("changed", "output", "file", "backup", "matched_row", "matchedRow"):
            if key in data:
                data_summary[key] = data.get(key)
        if data_summary:
            summary["data"] = data_summary
    return _json_safe(summary)


def _table_names_from_arguments(arguments: Any) -> list[str]:
    if not isinstance(arguments, dict):
        return []
    value = arguments.get("tableNames")
    if value is None:
        value = arguments.get("tableName")
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _limited_row_snapshots(value: Any, limit: int) -> tuple[list[Dict[str, Any]], int, bool]:
    rows = value if isinstance(value, list) else []
    total = len(rows)
    safe_limit = max(0, int(limit or 0))
    if safe_limit <= 0:
        return [], total, total > 0
    selected = [_json_safe(row) for row in rows[:safe_limit] if isinstance(row, dict)]
    return selected, total, total > len(selected)


def _safe_backup_name(name: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", str(name or "workbook.xlsx"))
    return safe[:120] or "workbook.xlsx"


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value, ensure_ascii=False)
        return value
    except TypeError:
        if isinstance(value, dict):
            return {str(key): _json_safe(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [_json_safe(item) for item in value]
        return str(value)
