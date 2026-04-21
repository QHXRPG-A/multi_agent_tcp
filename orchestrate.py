"""
Connect to an existing broker, run a JSON recipe: send_to / broadcast / wait_for / batch_gather.

Usage::

    python -m multi_agent_tcp.orchestrate --recipe multi_agent_tcp/examples/recipe_chain.json

Broker and target agents must already be running. See HOWTO.txt.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .client import AgentTCPClient
from .log_setup import setup_logging

log = logging.getLogger(__name__)


def _load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _load_body(step: Dict[str, Any], recipe_dir: Path) -> Any:
    if "body" in step:
        return step["body"]
    rel = step.get("body_file")
    if isinstance(rel, str) and rel.strip():
        p = (recipe_dir / rel).resolve()
        with p.open("r", encoding="utf-8") as f:
            return json.load(f)
    raise ValueError("step needs 'body' or 'body_file'")


def _load_body_from_item(item: Dict[str, Any], recipe_dir: Path, step_i: int, item_j: int) -> Any:
    if "body" in item:
        return item["body"]
    rel = item.get("body_file")
    if isinstance(rel, str) and rel.strip():
        p = (recipe_dir / rel).resolve()
        with p.open("r", encoding="utf-8") as f:
            return json.load(f)
    raise ValueError(f"step {step_i} batch_gather items[{item_j}] needs 'body' or 'body_file'")


async def _run_recipe(data: Dict[str, Any], recipe_path: Path) -> List[Dict[str, Any]]:
    br = data.get("broker")
    if not isinstance(br, dict):
        br = {}
    host = str(data.get("broker_host", br.get("host", "127.0.0.1")))
    port = int(data.get("broker_port", br.get("port", 9123)))
    self_id = str(data.get("self_id", "orchestrator")).strip()
    role = data.get("role")
    if role is not None:
        role = str(role)
    steps: List[Dict[str, Any]] = list(data.get("steps") or [])
    if not steps:
        raise ValueError("recipe needs non-empty 'steps'")

    client = AgentTCPClient(self_id, host, port, role=role)
    await client.connect()
    log.info("registered as %s -> %s:%s", self_id, host, port)
    results: List[Dict[str, Any]] = []
    recipe_dir = recipe_path.parent
    try:
        for i, step in enumerate(steps):
            if not isinstance(step, dict):
                raise ValueError(f"step {i} must be an object")
            if "send_to" in step:
                to = str(step["send_to"]).strip()
                body = _load_body(step, recipe_dir)
                await client.send_to(to, body)
                log.info("step %s send_to %s", i, to)
                results.append({"step": i, "action": "send_to", "to": to})
                continue
            if "broadcast" in step:
                b = step["broadcast"]
                if not isinstance(b, dict):
                    raise ValueError(f"step {i} broadcast must be object")
                body = _load_body(b, recipe_dir)
                ex = b.get("exclude_self", True)
                await client.broadcast(body, exclude_self=bool(ex))
                log.info("step %s broadcast", i)
                results.append({"step": i, "action": "broadcast"})
                continue
            if "wait_for" in step:
                w = step["wait_for"]
                if not isinstance(w, dict):
                    raise ValueError(f"step {i} wait_for must be object")
                expect = w.get("from")
                if expect is not None:
                    expect = str(expect).strip()
                timeout = float(w.get("timeout_sec", 300.0))
                accept_b = bool(w.get("accept_broadcast", False))
                msg = await client.wait_for_message(
                    expect_from=expect,
                    timeout_sec=timeout,
                    accept_broadcast=accept_b,
                )
                log.info("step %s wait_for -> type=%s", i, msg.get("type"))
                results.append({"step": i, "action": "wait_for", "message": msg})
                continue
            if "batch_gather" in step:
                bg = step["batch_gather"]
                if not isinstance(bg, dict):
                    raise ValueError(f"step {i} batch_gather must be object")
                gid_raw = bg.get("id")
                gid = str(gid_raw).strip() if isinstance(gid_raw, str) and gid_raw.strip() else str(uuid.uuid4())
                timeout_bg = float(bg.get("timeout_sec", 300.0))
                items_raw = bg.get("items")
                if not isinstance(items_raw, list) or not items_raw:
                    raise ValueError(f"step {i} batch_gather.items must be a non-empty list")
                pairs: List[Tuple[str, Any]] = []
                for j, it in enumerate(items_raw):
                    if not isinstance(it, dict):
                        raise ValueError(f"step {i} batch_gather.items[{j}] must be object")
                    to = it.get("to")
                    if not isinstance(to, str) or not to.strip():
                        raise ValueError(f"step {i} batch_gather.items[{j}].to required")
                    body = _load_body_from_item(it, recipe_dir, i, j)
                    pairs.append((to.strip(), body))
                gr = await client.batch_gather(gid, pairs, timeout_sec=timeout_bg)
                log.info("step %s batch_gather id=%s ok=%s", i, gid, gr.get("ok"))
                results.append({"step": i, "action": "batch_gather", "gather_result": gr})
                continue
            raise ValueError(f"step {i}: unknown keys {list(step.keys())}")
    finally:
        await client.close()
    return results


def main(argv: Optional[List[str]] = None) -> None:
    argv = argv if argv is not None else sys.argv[1:]
    p = argparse.ArgumentParser(description="Broker client recipe runner (send / wait / broadcast / batch_gather)")
    p.add_argument("--recipe", type=Path, required=True, help="JSON recipe path")
    p.add_argument(
        "-o",
        "--output",
        type=Path,
        help="write full results JSON (default: print to stdout)",
    )
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)
    setup_logging(args.verbose, name="orchestrate")
    data = _load_json(args.recipe)
    try:
        results = asyncio.run(_run_recipe(data, args.recipe.resolve()))
    except KeyboardInterrupt:
        raise SystemExit(130)
    ok = True
    for r in results:
        if r.get("action") == "wait_for":
            m = r.get("message")
            if isinstance(m, dict) and m.get("type") == "error":
                ok = False
                break
        if r.get("action") == "batch_gather":
            gr = r.get("gather_result")
            if isinstance(gr, dict) and gr.get("ok") is False:
                ok = False
                break
    out_obj = {"ok": ok, "results": results}
    text = json.dumps(out_obj, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(text, encoding="utf-8")
        log.info("wrote %s", args.output)
    else:
        print(text)
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
