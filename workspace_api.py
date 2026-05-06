"""Controlled workspace API for blueprint agent outputs."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

from .workspace_manager import DulwichWorkspaceManager


CONTEXT_ENV = "MULTI_AGENT_WORKSPACE_CONTEXT"
VALID_AREAS = {"code", "artifacts", "reports"}


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
    return manager, manager.open_run(str(run_id)), ctx


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
    manager, run, ctx = _manager_and_run()
    rel = _area_path(args.area, args.path)
    owner = str(args.owner or ctx.get("agent_id") or "agent")
    manager.write_shared_text(
        run,
        rel,
        _read_publish_text(args),
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
    manager, run, ctx = _manager_and_run()
    rel = _area_path(args.area, args.path)
    owner = str(args.owner or ctx.get("agent_id") or "agent")
    data = Path(args.file).read_bytes()
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
    manager, run, _ctx = _manager_and_run()
    rel = _area_path(args.area, args.path or "")
    prefix = f"{args.area}/"
    files = [
        item[len(prefix) :] if item.startswith(prefix) else item
        for item in manager.list_shared_files(run, rel)
    ]
    _json_out({"ok": True, "area": args.area, "path": args.path or "", "files": files})


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
