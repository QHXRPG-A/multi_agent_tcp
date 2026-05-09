"""Controlled workspace API for blueprint agent outputs."""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict
from urllib import request

from .workspace_manager import DulwichWorkspaceManager


CONTEXT_ENV = "MULTI_AGENT_WORKSPACE_CONTEXT"
VALID_AREAS = {"artifacts", "reports"}


def _json_out(data: Dict[str, Any]) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def _load_context() -> Dict[str, Any]:
    raw = os.environ.get(CONTEXT_ENV)
    if not raw:
        raise RuntimeError(f"{CONTEXT_ENV} is not set")
    path = Path(raw).expanduser()
    if not path.is_file():
        raise FileNotFoundError(f"workspace API context not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("workspace API context must be a JSON object")
    return data


def _rpc_result(ctx: Dict[str, Any], command: str, args: Dict[str, Any]) -> Dict[str, Any]:
    url = str(ctx.get("rpc_url") or "").strip()
    token = str(ctx.get("rpc_token") or "").strip()
    if not url or not token:
        raise ValueError("workspace RPC context requires rpc_url and rpc_token")
    payload = json.dumps(
        {"token": token, "command": command, "args": args},
        ensure_ascii=False,
    ).encode("utf-8")
    req = request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with request.urlopen(req, timeout=30) as response:
        data = json.loads(response.read().decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("workspace RPC response must be a JSON object")
    if data.get("ok") is False and "error" in data:
        raise RuntimeError(str(data.get("error") or "workspace RPC command failed"))
    return data


def _is_rpc_context(ctx: Dict[str, Any]) -> bool:
    return ctx.get("transport") == "rpc" or bool(ctx.get("rpc_url"))


def _manager_and_run() -> tuple[DulwichWorkspaceManager, Any, Dict[str, Any]]:
    ctx = _load_context()
    project_root = ctx.get("project_root")
    workspace_root = ctx.get("workspace_root")
    run_id = ctx.get("run_id")
    if not project_root or not workspace_root or not run_id:
        raise ValueError("workspace API context requires project_root, workspace_root, and run_id")
    manager = DulwichWorkspaceManager.open_or_init(
        Path(str(project_root)),
        workspace_root=Path(str(workspace_root)),
        create=False,
    )
    run = manager.open_run(str(run_id))
    return manager, run, ctx


def _area_path(area: str, rel_path: str = "") -> str:
    if area not in VALID_AREAS:
        raise ValueError(f"invalid area {area!r}; expected one of {sorted(VALID_AREAS)}")
    normalized = rel_path.replace("\\", "/").strip("/")
    if normalized:
        parts = normalized.split("/")
        if any(part in {"", ".", ".."} for part in parts):
            raise ValueError("path must be a relative path inside the selected area")
        if ":" in normalized:
            raise ValueError("path must not contain a drive or URI separator")
        return f"{area}/{normalized}"
    return area


def _read_publish_text(args: argparse.Namespace) -> str:
    sources = [
        args.text is not None,
        args.file is not None,
        bool(args.stdin),
    ]
    if sum(1 for item in sources if item) != 1:
        raise ValueError("publish requires exactly one of --text, --file, or --stdin")
    if args.text is not None:
        return str(args.text)
    if args.file is not None:
        return Path(args.file).read_text(encoding="utf-8")
    return sys.stdin.read()


def _cmd_publish(args: argparse.Namespace) -> None:
    ctx = _load_context()
    text = _read_publish_text(args)
    if _is_rpc_context(ctx):
        out = _rpc_result(
            ctx,
            "publish",
            {
                "area": args.area,
                "path": args.path,
                "text": text,
                "owner": args.owner,
                "expected_version": args.expected_version,
            },
        )
        _json_out(out)
        return

    manager, run, ctx = _manager_and_run()
    rel = _area_path(args.area, args.path)
    owner = str(args.owner or ctx.get("agent_id") or "agent")
    manager.write_shared_text(
        run,
        rel,
        text,
        owner=owner,
        expected_version=args.expected_version,
    )
    _json_out(
        {
            "ok": True,
            "area": args.area,
            "path": args.path,
            "owner": owner,
            "version": manager.shared_file_version(run, rel),
        }
    )


def _cmd_publish_file(args: argparse.Namespace) -> None:
    ctx = _load_context()
    data = Path(args.file).read_bytes()
    if _is_rpc_context(ctx):
        out = _rpc_result(
            ctx,
            "publish-file",
            {
                "area": args.area,
                "path": args.path,
                "data_b64": base64.b64encode(data).decode("ascii"),
                "owner": args.owner,
                "expected_version": args.expected_version,
            },
        )
        _json_out(out)
        return

    manager, run, ctx = _manager_and_run()
    rel = _area_path(args.area, args.path)
    owner = str(args.owner or ctx.get("agent_id") or "agent")
    manager.write_shared_bytes(
        run,
        rel,
        data,
        owner=owner,
        expected_version=args.expected_version,
    )
    _json_out(
        {
            "ok": True,
            "area": args.area,
            "path": args.path,
            "owner": owner,
            "bytes": len(data),
            "version": manager.shared_file_version(run, rel),
        }
    )


def _cmd_read(args: argparse.Namespace) -> None:
    ctx = _load_context()
    if _is_rpc_context(ctx):
        out = _rpc_result(
            ctx,
            "read",
            {
                "area": args.area,
                "path": args.path,
                "json": args.json,
                "owner": args.owner,
            },
        )
        if args.json:
            _json_out(out)
        else:
            sys.stdout.write(str(out.get("text", "")))
        return

    manager, run, ctx = _manager_and_run()
    owner = str(args.owner or ctx.get("agent_id") or "agent")
    text = manager.read_shared_text(run, _area_path(args.area, args.path), owner=owner)
    if args.json:
        rel = _area_path(args.area, args.path)
        _json_out(
            {
                "ok": True,
                "area": args.area,
                "path": args.path,
                "version": manager.shared_file_version(run, rel),
                "text": text,
            }
        )
    else:
        sys.stdout.write(text)


def _cmd_list(args: argparse.Namespace) -> None:
    ctx = _load_context()
    if _is_rpc_context(ctx):
        out = _rpc_result(
            ctx,
            "list",
            {
                "area": args.area,
                "path": args.path or "",
            },
        )
        _json_out(out)
        return

    manager, run, _ctx = _manager_and_run()
    rel = _area_path(args.area, args.path or "")
    prefix = f"{args.area}/"
    files = [
        item[len(prefix) :] if item.startswith(prefix) else item
        for item in manager.list_shared_files(run, rel)
    ]
    _json_out({"ok": True, "area": args.area, "path": args.path or "", "files": files})


def _cmd_checkout(args: argparse.Namespace) -> None:
    ctx = _load_context()
    scopes = list(args.scope_path or [])
    paths = list(args.path or [])
    if _is_rpc_context(ctx):
        out = _rpc_result(
            ctx,
            "checkout",
            {
                "write_scope": scopes,
                "checkout_paths": paths,
                "mode": args.mode,
                "owner": args.owner,
            },
        )
        _json_out(out)
        return

    manager, run, ctx = _manager_and_run()
    owner = str(args.owner or ctx.get("agent_id") or "agent")
    checkout = manager.checkout_agent(
        run,
        owner,
        write_scope=scopes,
        checkout_paths=paths,
        mode=args.mode,
    )
    data = checkout.to_dict()
    data["ok"] = True
    _json_out(data)


def _cmd_status(args: argparse.Namespace) -> None:
    ctx = _load_context()
    if _is_rpc_context(ctx):
        out = _rpc_result(ctx, "status", {"owner": args.owner})
        _json_out(out)
        return

    manager, run, ctx = _manager_and_run()
    owner = str(args.owner or ctx.get("agent_id") or "agent")
    checkout = manager.open_agent_checkout(run, owner)
    files = [change.to_dict(include_patch=False) for change in manager.status_checkout(run, checkout)]
    _json_out({"ok": True, "base_ref": checkout.base_ref, "files": files})


def _cmd_diff(args: argparse.Namespace) -> None:
    ctx = _load_context()
    if _is_rpc_context(ctx):
        out = _rpc_result(ctx, "diff", {"owner": args.owner, "path": args.path, "summary": args.summary})
        if args.summary:
            _json_out(out)
        else:
            sys.stdout.write(str(out.get("patch", "")))
        return

    manager, run, ctx = _manager_and_run()
    owner = str(args.owner or ctx.get("agent_id") or "agent")
    checkout = manager.open_agent_checkout(run, owner)
    changes = manager.diff_checkout(run, checkout)
    if args.path:
        wanted = args.path.replace("\\", "/").strip("/")
        changes = [change for change in changes if change.path == wanted]
    if args.summary:
        _json_out(
            {
                "ok": True,
                "base_ref": checkout.base_ref,
                "files": [change.to_dict(include_patch=False) for change in changes],
            }
        )
        return
    sys.stdout.write("\n".join(change.patch or "" for change in changes if change.patch))


def _cmd_submit(args: argparse.Namespace) -> None:
    ctx = _load_context()
    if _is_rpc_context(ctx):
        out = _rpc_result(
            ctx,
            "submit",
            {
                "owner": args.owner,
                "task_id": args.task_id,
                "summary": args.summary or "",
            },
        )
        _json_out(out)
        return

    manager, run, ctx = _manager_and_run()
    owner = str(args.owner or ctx.get("agent_id") or "agent")
    checkout = manager.open_agent_checkout(run, owner)
    result = manager.submit_checkout(
        run,
        checkout,
        task_id=args.task_id,
        summary=args.summary or "",
    )
    _json_out(result.to_dict())


def _cmd_sync(args: argparse.Namespace) -> None:
    ctx = _load_context()
    if _is_rpc_context(ctx):
        out = _rpc_result(ctx, "sync", {"owner": args.owner})
        _json_out(out)
        return

    manager, run, ctx = _manager_and_run()
    owner = str(args.owner or ctx.get("agent_id") or "agent")
    checkout = manager.open_agent_checkout(run, owner)
    checkout = manager.sync_checkout(run, checkout)
    _json_out({"ok": True, "checkout_id": checkout.checkout_id, "base_ref": checkout.base_ref})


def _cmd_list_archives(args: argparse.Namespace) -> None:
    ctx = _load_context()
    if _is_rpc_context(ctx):
        out = _rpc_result(ctx, "list-archives", {"owner": args.owner})
        _json_out(out)
        return

    manager, _run, _ctx = _manager_and_run()
    _json_out({"ok": True, "archives": manager.list_long_term_archives()})


def _cmd_extract_archive(args: argparse.Namespace) -> None:
    ctx = _load_context()
    if _is_rpc_context(ctx):
        out = _rpc_result(
            ctx,
            "extract-archive",
            {
                "owner": args.owner,
                "archive_id": args.archive_id,
                "path": args.path or "",
            },
        )
        _json_out(out)
        return

    manager, run, ctx = _manager_and_run()
    owner = str(args.owner or ctx.get("agent_id") or "agent")
    path = manager.extract_long_term_archive(
        run,
        owner,
        args.archive_id,
        path=args.path or "",
    )
    _json_out({"ok": True, "archive_id": args.archive_id, "path": str(path)})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Publish and inspect blueprint workspace outputs")
    sub = parser.add_subparsers(dest="cmd", required=True)

    publish = sub.add_parser("publish", help="publish UTF-8 text into a run outcome area")
    publish.add_argument("--area", choices=sorted(VALID_AREAS), required=True)
    publish.add_argument("--path", required=True, help="relative output path inside the area")
    src = publish.add_mutually_exclusive_group(required=True)
    src.add_argument("--text", help="literal UTF-8 text to publish")
    src.add_argument("--file", type=Path, help="read UTF-8 text from this file")
    src.add_argument("--stdin", action="store_true", help="read UTF-8 text from stdin")
    publish.add_argument("--owner", help="override owner recorded in the manifest")
    publish.add_argument("--expected-version", type=int, help="fail if the target path version changed")
    publish.set_defaults(func=_cmd_publish)

    publish_file = sub.add_parser("publish-file", help="publish any local file into a run outcome area")
    publish_file.add_argument("--area", choices=sorted(VALID_AREAS), required=True)
    publish_file.add_argument("--path", required=True, help="relative output path inside the area")
    publish_file.add_argument("--file", type=Path, required=True, help="local file to publish")
    publish_file.add_argument("--owner", help="override owner recorded in the manifest")
    publish_file.add_argument("--expected-version", type=int, help="fail if the target path version changed")
    publish_file.set_defaults(func=_cmd_publish_file)

    read = sub.add_parser("read", help="read UTF-8 text from a run outcome area")
    read.add_argument("--area", choices=sorted(VALID_AREAS), required=True)
    read.add_argument("--path", required=True, help="relative path inside the area")
    read.add_argument("--json", action="store_true", help="wrap output in JSON")
    read.add_argument("--owner", help="override owner recorded in the lock manifest")
    read.set_defaults(func=_cmd_read)

    list_cmd = sub.add_parser("list", help="list files in a run outcome area")
    list_cmd.add_argument("--area", choices=sorted(VALID_AREAS), required=True)
    list_cmd.add_argument("--path", default="", help="optional relative directory inside the area")
    list_cmd.set_defaults(func=_cmd_list)

    checkout = sub.add_parser("checkout", help="create or refresh the agent private code checkout")
    checkout.add_argument("--scope-path", action="append", default=[], help="allowed code path glob; repeatable")
    checkout.add_argument("--path", action="append", default=[], help="specific relative code file or directory to fetch; repeatable")
    checkout.add_argument("--mode", default="full", choices=["full"])
    checkout.add_argument("--owner", help="override agent id")
    checkout.set_defaults(func=_cmd_checkout)

    status = sub.add_parser("status", help="summarize private checkout changes")
    status.add_argument("--owner", help="override agent id")
    status.set_defaults(func=_cmd_status)

    diff = sub.add_parser("diff", help="print private checkout patch")
    diff.add_argument("--path", help="optional single relative path")
    diff.add_argument("--summary", action="store_true", help="return JSON summary instead of patch text")
    diff.add_argument("--owner", help="override agent id")
    diff.set_defaults(func=_cmd_diff)

    submit = sub.add_parser("submit", help="submit private checkout changes for integration")
    submit.add_argument("--task-id", help="optional task id for provenance")
    submit.add_argument("--summary", help="short changeset summary")
    submit.add_argument("--owner", help="override agent id")
    submit.set_defaults(func=_cmd_submit)

    sync = sub.add_parser("sync", help="refresh private checkout from current integration state")
    sync.add_argument("--owner", help="override agent id")
    sync.set_defaults(func=_cmd_sync)

    list_archives = sub.add_parser("list-archives", help="list long-term run archive zips")
    list_archives.add_argument("--owner", help="override agent id")
    list_archives.set_defaults(func=_cmd_list_archives)

    extract_archive = sub.add_parser("extract-archive", help="extract a long-term run archive into private workspace")
    extract_archive.add_argument("--archive-id", required=True, help="archive id or zip file name")
    extract_archive.add_argument("--path", default="", help="optional relative path inside the archive")
    extract_archive.add_argument("--owner", help="override agent id")
    extract_archive.set_defaults(func=_cmd_extract_archive)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except Exception as exc:
        _json_out({"ok": False, "error": str(exc)})
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
