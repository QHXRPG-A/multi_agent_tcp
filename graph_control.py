"""Runtime control-plane helpers for graph orchestration.

The control plane is intentionally thin: it exposes stable JSON-shaped
commands while keeping scheduling and validation semantics inside
``GraphRuntime`` and ``GraphDefinition``.
"""

from __future__ import annotations

import asyncio
import json
import secrets
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional, Sequence
from urllib.parse import urlparse

from .graph_runtime import (
    AgentNode,
    BlueprintTerminalNode,
    GraphDefinition,
    GraphEdge,
    GraphExecutor,
    GraphRuntime,
    GuLiCodeTopAgentProfile,
    RouteNode,
    TopAgentStartPlan,
    is_dispatch_no_op_body,
)


@dataclass
class GraphControlResponse:
    ok: bool
    data: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {"ok": self.ok, **self.data}


def graph_definition_from_dict(data: Dict[str, Any]) -> GraphDefinition:
    """Build a GraphDefinition from a JSON-friendly dict."""

    if not isinstance(data, dict):
        raise ValueError("graph definition must be a JSON object")
    agents_raw = data.get("agent_nodes", data.get("agents", {}))
    if isinstance(agents_raw, list):
        agent_nodes = {
            str(item.get("node_id", "")).strip(): AgentNode.from_dict(item)
            for item in agents_raw
            if isinstance(item, dict)
        }
    elif isinstance(agents_raw, dict):
        agent_nodes = {}
        for key, value in agents_raw.items():
            if not isinstance(value, dict):
                raise ValueError("agent_nodes entries must be objects")
            node_data = dict(value)
            node_data.setdefault("node_id", str(key))
            node = AgentNode.from_dict(node_data)
            agent_nodes[node.node_id] = node
    else:
        raise ValueError("graph agent_nodes must be an object or array")
    if any(not node_id for node_id in agent_nodes):
        raise ValueError("every AgentNode must have a node_id")

    routes_raw = data.get("route_nodes", {})
    route_nodes: Dict[str, RouteNode] = {}
    if isinstance(routes_raw, list):
        route_items = enumerate(routes_raw)
    elif isinstance(routes_raw, dict):
        route_items = routes_raw.items()
    else:
        raise ValueError("graph route_nodes must be an object or array")
    for key, value in route_items:
        if not isinstance(value, dict):
            raise ValueError("route_nodes entries must be objects")
        node_id = str(value.get("node_id", key)).strip()
        route_nodes[node_id] = RouteNode(
            node_id=node_id,
            route_kind=str(value.get("route_kind", "sequence")),
            targets=[str(item) for item in value.get("targets", [])],
            reduce_target=(
                str(value["reduce_target"])
                if value.get("reduce_target") is not None
                else None
            ),
            reduce_prompt=(
                str(value["reduce_prompt"])
                if value.get("reduce_prompt") is not None
                else None
            ),
        )

    terminals_raw = data.get("terminal_nodes", {})
    terminal_nodes: Dict[str, BlueprintTerminalNode] = {}
    if isinstance(terminals_raw, list):
        terminal_items = enumerate(terminals_raw)
    elif isinstance(terminals_raw, dict):
        terminal_items = terminals_raw.items()
    else:
        raise ValueError("graph terminal_nodes must be an object or array")
    for key, value in terminal_items:
        if isinstance(value, str):
            node_id = str(key).strip()
            kind = value
        elif isinstance(value, dict):
            node_id = str(value.get("node_id", key)).strip()
            kind = str(value.get("terminal_kind", value.get("kind", "")))
        else:
            raise ValueError("terminal_nodes entries must be strings or objects")
        terminal_nodes[node_id] = BlueprintTerminalNode(node_id, kind)

    edges_raw = data.get("edges", [])
    if not isinstance(edges_raw, list):
        raise ValueError("graph edges must be an array")
    edges = []
    for edge in edges_raw:
        if not isinstance(edge, dict):
            raise ValueError("edge entries must be objects")
        source = edge.get("source", edge.get("from"))
        target = edge.get("target", edge.get("to"))
        edges.append(
            GraphEdge(
                str(source),
                str(target),
                output_port=(
                    str(edge["output_port"])
                    if edge.get("output_port") is not None
                    else None
                ),
                input_port=(
                    str(edge["input_port"])
                    if edge.get("input_port") is not None
                    else None
                ),
                edge_type=(
                    str(edge["edge_type"])
                    if edge.get("edge_type") is not None
                    else None
                ),
            )
        )
    ring_limits_raw = data.get(
        "agent_ring_max_circulations",
        data.get("ring_max_circulations", {}),
    )
    if ring_limits_raw is None:
        ring_limits_raw = {}
    if not isinstance(ring_limits_raw, dict):
        raise ValueError("agent_ring_max_circulations must be an object")

    return GraphDefinition(
        agent_nodes=agent_nodes,
        route_nodes=route_nodes,
        terminal_nodes=terminal_nodes,
        edges=edges,
        agent_ring_max_circulations={
            str(key): int(value)
            for key, value in ring_limits_raw.items()
        },
    )


def load_graph_definition(path: Path) -> GraphDefinition:
    return graph_definition_from_dict(json.loads(path.read_text(encoding="utf-8")))


def load_top_agent_profile(path: Path) -> GuLiCodeTopAgentProfile:
    return GuLiCodeTopAgentProfile.load(path)


def scoped_organization_view(graph: GraphDefinition, *, agent_id: Optional[str] = None) -> Dict[str, Any]:
    """Return full organization or a single ordinary-Agent view."""

    view = graph.agent_organization_view()
    if not agent_id:
        return view
    node_id = str(agent_id).strip()
    if node_id not in view["agents"]:
        raise KeyError(f"unknown AgentNode: {node_id}")
    agent = dict(view["agents"][node_id])
    related = set(agent.get("upstream_agents", [])) | set(agent.get("downstream_agents", [])) | {node_id}
    return {
        "graph": {
            "nodes": sorted(related),
            "agent_nodes": [node_id],
            "edges": [
                edge
                for edge in view["graph"]["edges"]
                if edge["from"] in related and edge["to"] in related
            ],
        },
        "agent": agent,
        "agent_connections": {
            node_id: list(view["agent_connections"].get(node_id, [])),
        },
        "scope": "agent",
    }


def ordinary_agent_framework_context(
    graph: GraphDefinition,
    source_node_id: str,
    *,
    batch: Any = None,
    runtime: Optional[GraphRuntime] = None,
) -> Dict[str, Any]:
    """Build the stable framework tool context injected into ordinary agents."""

    node_id = str(source_node_id).strip()
    if node_id not in graph.agent_nodes:
        raise KeyError(f"unknown AgentNode: {node_id}")
    organization = graph.agent_organization_summary(agent_id=node_id)
    agent_view = organization["agent"]
    downstream = (
        runtime.active_agent_connections(graph, node_id)
        if runtime is not None
        else list(graph.agent_connections().get(node_id, []))
    )
    organization["agent_connections"] = {node_id: list(downstream)}
    organization["agent"]["downstream_agents"] = list(downstream)
    if runtime is not None:
        ring_counts = runtime.agent_ring_circulation_counts_for(node_id)
        if ring_counts:
            organization["agent"]["ring_circulation_counts"] = dict(ring_counts)
    required_targets = list(batch.required_target_node_ids) if batch is not None else []
    remaining_targets = list(batch.remaining_targets) if batch is not None else []
    message_envelope: Dict[str, Any] = {
        "outgoing_batch_id": batch.batch_id if batch is not None else None,
        "required_outgoing_targets": required_targets,
    }
    if batch is not None:
        message_envelope["remaining_targets"] = remaining_targets
    context = {
        "agent_node_id": node_id,
        "agent_id": agent_view["agent_id"],
        "upstream_agents": list(agent_view.get("upstream_agents", [])),
        "downstream_agents": downstream,
        "organization": organization,
        "message_envelope": message_envelope,
    }
    if runtime is not None:
        ring_counts = runtime.agent_ring_circulation_counts_for(node_id)
        if ring_counts:
            context["ring_circulation_counts"] = dict(ring_counts)
    return context


def inject_framework_context(body: Any, context: Dict[str, Any]) -> Dict[str, Any]:
    """Return a JSON body with per-message framework_context attached."""

    if isinstance(body, dict):
        enriched = dict(body)
    elif isinstance(body, str):
        enriched = {"prompt": body}
    else:
        enriched = {"payload": body}

    existing = enriched.get("context")
    if isinstance(existing, str) and existing.strip():
        context_payload: Any = {
            "framework_context": context,
            "user_context": existing,
        }
    elif isinstance(existing, dict):
        context_payload = dict(existing)
        context_payload["framework_context"] = context
    elif existing is not None:
        context_payload = {
            "framework_context": context,
            "user_context": existing,
        }
    else:
        context_payload = {"framework_context": context}
    enriched["context"] = context_payload
    return enriched


class GraphRuntimeControlPlane:
    """JSON command facade over a live GraphRuntime."""

    def __init__(
        self,
        runtime: GraphRuntime,
        graph: GraphDefinition,
        *,
        top_agent: Optional[GuLiCodeTopAgentProfile] = None,
    ) -> None:
        self.runtime = runtime
        self.graph = graph
        self.top_agent = top_agent or GuLiCodeTopAgentProfile()

    def handle_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        command = str(payload.get("command", "")).strip()
        args = payload.get("args", {})
        if not isinstance(args, dict):
            raise ValueError("args must be a JSON object")

        if command == "organization.read":
            return GraphControlResponse(
                True,
                {
                    "organization": scoped_organization_view(
                        self.graph,
                        agent_id=args.get("agent_id"),
                    )
                },
            ).to_dict()

        if command == "top_agent.context":
            return GraphControlResponse(
                True,
                {"context": self.top_agent.organization_context(self.graph)},
            ).to_dict()

        if command == "top_agent.explain_status":
            return GraphControlResponse(
                True,
                {
                    "explanation": self.runtime.explain_status(
                        graph=self.graph,
                        recent_events_limit=int(args.get("recent_events_limit", 20)),
                    )
                },
            ).to_dict()

        if command == "top_agent.utterances":
            return self.top_agent_utterances(
                task_id=(
                    str(args["task_id"])
                    if args.get("task_id") is not None
                    else None
                ),
                agent_id=(
                    str(args["agent_id"])
                    if args.get("agent_id") is not None
                    else None
                ),
                node_id=(
                    str(args["node_id"])
                    if args.get("node_id") is not None
                    else None
                ),
            )

        if command == "run.validate_start":
            plan = TopAgentStartPlan.from_dict(dict(args.get("plan", args)))
            return self.top_agent.validate_start_plan(self.graph, plan).to_dict()

        if command == "run.start":
            manifest_path = (
                Path(str(args["manifest_path"]))
                if args.get("manifest_path") is not None
                else None
            )
            return asyncio.run(
                self.start_run(
                    TopAgentStartPlan.from_dict(dict(args["plan"])),
                    manifest_path=manifest_path,
                    prestart_all_agents=bool(args.get("prestart_all_agents", False)),
                )
            )

        if command == "run.execute_fixture":
            manifest_path = (
                Path(str(args["manifest_path"]))
                if args.get("manifest_path") is not None
                else None
            )
            return asyncio.run(
                self.execute_fixture_to_archive(
                    TopAgentStartPlan.from_dict(dict(args["plan"])),
                    runtime_scenarios=dict(args.get("runtime_scenarios", {})),
                    manifest_path=manifest_path,
                    archive=bool(args.get("archive", True)),
                )
            )

        if command == "run.status":
            return GraphControlResponse(
                True,
                {
                    "status": self.runtime.status_snapshot(
                        graph=self.graph,
                        recent_events_limit=int(args.get("recent_events_limit", 20)),
                    )
                },
            ).to_dict()

        if command == "agent.context":
            batch_id = args.get("batch_id")
            batch = (
                self.runtime.outgoing_batches[str(batch_id)]
                if batch_id is not None
                else None
            )
            return GraphControlResponse(
                True,
                {
                    "context": ordinary_agent_framework_context(
                        self.graph,
                        str(args["source_node_id"]),
                        batch=batch,
                        runtime=self.runtime,
                    )
                },
            ).to_dict()

        if command == "run.end":
            result = self.runtime.end_run(
                str(args["action"]),
                reason=str(args.get("reason", "")),
                archive=bool(args.get("archive", False)),
            )
            return result.to_dict()

        if command == "message.create_batch":
            return asyncio.run(
                self._create_message_batch(
                    str(args["source_node_id"]),
                    [str(item) for item in args.get("required_target_node_ids", [])],
                    batch_id=args.get("batch_id"),
                )
            )

        if command == "message.stage":
            target = self.graph.agent_nodes[str(args["target_node_id"])]
            data = self.runtime.stage_outgoing_message(
                str(args["batch_id"]),
                target,
                args.get("body"),
            )
            return GraphControlResponse(True, data).to_dict()

        if command == "agent.dispatch":
            return asyncio.run(
                self.dispatch_agent_message(
                    str(args["source_node_id"]),
                    str(args["target_node_id"]),
                    args.get("body"),
                    batch_id=(
                        str(args["batch_id"])
                        if args.get("batch_id") is not None
                        else None
                    ),
                )
            )

        if command == "join.create":
            target_arg = args.get("target_node_id")
            target_node = (
                self.graph.agent_nodes[str(target_arg)]
                if target_arg is not None
                else None
            )
            barrier = self.runtime.create_join_barrier(
                required_sources=[str(item) for item in args.get("required_source_node_ids", [])],
                target_node=target_node,
                policy=str(args.get("policy", "wait-all")),
                quorum=(
                    int(args["quorum"])
                    if args.get("quorum") is not None
                    else None
                ),
                timeout_sec=(
                    float(args["timeout_sec"])
                    if args.get("timeout_sec") is not None
                    else None
                ),
                join_id=(
                    str(args["join_id"])
                    if args.get("join_id") is not None
                    else None
                ),
            )
            return GraphControlResponse(True, {"join": barrier.to_dict()}).to_dict()

        if command == "join.contribute":
            data = self.runtime.submit_join_contribution(
                str(args["join_id"]),
                str(args["source_node_id"]),
                status=str(args.get("status", "completed")),
                result=args.get("result"),
                source_agent_id=(
                    str(args["source_agent_id"])
                    if args.get("source_agent_id") is not None
                    else None
                ),
                accepted_changesets=_list_of_dicts(args.get("accepted_changesets", [])),
                conflicts=_list_of_dicts(args.get("conflicts", [])),
                artifacts=_list_of_dicts(args.get("artifacts", [])),
                reports=_list_of_dicts(args.get("reports", [])),
                test_results=_list_of_dicts(args.get("test_results", [])),
                metadata=dict(args.get("metadata", {})),
            )
            return GraphControlResponse(True, data).to_dict()

        raise ValueError(f"unsupported graph runtime command: {command!r}")

    async def start_run(
        self,
        plan: TopAgentStartPlan,
        *,
        manifest_path: Optional[Path] = None,
        prestart_all_agents: bool = False,
    ) -> Dict[str, Any]:
        validation = self.top_agent.validate_start_plan(self.graph, plan)
        if not validation.ok:
            return validation.to_dict()
        queued = []
        organization = scoped_organization_view(self.graph)
        if prestart_all_agents:
            await self.runtime.prestart_agents(list(self.graph.agent_nodes.values()))
        for node_id in plan.start_nodes:
            node = self.graph.agent_nodes[node_id]
            await self.runtime.ensure_agent(node)
            downstream = self.graph.agent_connections().get(node_id, [])
            batch = None
            if downstream:
                batch = await self.runtime.create_outgoing_batch_from_graph(
                    self.graph,
                    node_id,
                    required_target_node_ids=downstream,
                )
            pending = self.runtime.queue_agent_message(
                node,
                inject_framework_context(
                    {
                    "type": "top_agent_task",
                    "prompt": plan.tasks[node_id].goal,
                    "user_goal": plan.user_goal,
                    "agent_description": plan.agent_descriptions[node_id],
                    "task": plan.tasks[node_id].to_dict(),
                    "organization": self.graph.agent_organization_summary(agent_id=node_id),
                    },
                    ordinary_agent_framework_context(
                        self.graph,
                        node_id,
                        batch=batch,
                    ),
                ),
                source_agent_id=self.top_agent.agent_id,
            )
            queued.append(pending.to_dict())
        start_manifest = self.runtime.record_start_manifest(
            top_agent=self.top_agent.to_dict(),
            start_plan=plan.to_dict(),
            organization=organization,
            queued_messages=queued,
            manifest_path=manifest_path,
        )
        return GraphControlResponse(
            True,
            {
                "run_status": self.runtime.status_snapshot()["run"]["status"],
                "validation": validation.to_dict(),
                "queued_messages": queued,
                "start_manifest": start_manifest,
            },
        ).to_dict()

    async def execute_fixture_to_archive(
        self,
        plan: TopAgentStartPlan,
        *,
        runtime_scenarios: Optional[Dict[str, Any]] = None,
        manifest_path: Optional[Path] = None,
        archive: bool = True,
    ) -> Dict[str, Any]:
        start = await self.start_run(plan, manifest_path=manifest_path)
        if not start.get("ok"):
            return start
        execution = await GraphExecutor(self.runtime).run_complex_blueprint_scenario(
            self.graph,
            runtime_scenarios=runtime_scenarios or {},
            initial_prompt=plan.user_goal,
        )
        ended = self.runtime.end_run("complete", reason="complex blueprint completed", archive=archive)
        return GraphControlResponse(
            True,
            {
                "start": start,
                "execution": execution,
                "end": ended.to_dict(),
                "status": self.runtime.status_snapshot(graph=self.graph),
            },
        ).to_dict()

    async def _create_message_batch(
        self,
        source_node_id: str,
        target_node_ids: Sequence[str],
        *,
        batch_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        batch = await self.runtime.create_outgoing_batch_from_graph(
            self.graph,
            source_node_id,
            required_target_node_ids=target_node_ids or None,
            batch_id=batch_id,
        )
        return GraphControlResponse(True, {"batch": batch.to_dict()}).to_dict()

    def top_agent_utterances(
        self,
        *,
        task_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        node_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        if "utterances" not in self.top_agent.allowed_run_permissions:
            raise PermissionError(
                f"top agent {self.top_agent.agent_id!r} is not allowed to read Agent utterances"
            )
        utterances = self.runtime.private_agent_utterances(task_id=task_id)
        if agent_id is not None:
            utterances = [
                item for item in utterances
                if str(item.get("agent_id")) == agent_id
            ]
        if node_id is not None:
            utterances = [
                item for item in utterances
                if str(item.get("node_id")) == node_id
            ]
        return GraphControlResponse(
            True,
            {
                "utterances": utterances,
                "filters": {
                    "task_id": task_id,
                    "agent_id": agent_id,
                    "node_id": node_id,
                },
            },
        ).to_dict()

    async def dispatch_agent_message(
        self,
        source_node_id: str,
        target_node_id: str,
        body: Any,
        *,
        batch_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        if source_node_id not in self.graph.agent_nodes:
            raise KeyError(f"unknown source AgentNode: {source_node_id}")
        if target_node_id not in self.graph.agent_nodes:
            raise KeyError(f"unknown target AgentNode: {target_node_id}")

        if batch_id is None:
            raise ValueError("agent.dispatch requires the current outgoing batch_id")
        batch = self.runtime.outgoing_batches.get(batch_id)
        if batch is None:
            raise KeyError(f"unknown outgoing batch: {batch_id}")
        if batch.source_node_id != source_node_id:
            raise ValueError(
                f"batch {batch_id!r} belongs to source {batch.source_node_id!r}, not {source_node_id!r}"
            )
        if target_node_id not in batch.required_target_node_ids:
            raise ValueError(
                f"target {target_node_id!r} is not in current required_outgoing_targets"
            )
        is_no_op = is_dispatch_no_op_body(body)
        downstream_batch = None
        ring_record: Dict[str, Any] = {"recorded": False, "consumed_ring_ids": []}
        if not is_no_op:
            ring_record = self.runtime.record_outgoing_edge_from_batch(
                batch.batch_id,
                target_node_id,
            )
        downstream = (
            []
            if is_no_op
            else self.runtime.active_agent_connections(self.graph, target_node_id)
        )
        if downstream:
            downstream_batch = await self.runtime.create_outgoing_batch_from_graph(
                self.graph,
                target_node_id,
                required_target_node_ids=downstream,
            )

        staged_body = body if is_no_op else inject_framework_context(
            body,
            ordinary_agent_framework_context(
                self.graph,
                target_node_id,
                batch=downstream_batch,
                runtime=self.runtime,
            ),
        )
        staged = self.runtime.stage_outgoing_message(
            batch.batch_id,
            self.graph.agent_nodes[target_node_id],
            staged_body,
        )
        staged["ring_record"] = dict(ring_record)
        return GraphControlResponse(
            True,
            {
                "batch": batch.to_dict(),
                "dispatch": staged,
            },
        ).to_dict()


def _list_of_dicts(value: Any) -> list[Dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("expected a list")
    return [dict(item) for item in value]


class GraphRuntimeRPCServer:
    """Small HTTP JSON endpoint for a live GraphRuntime control plane."""

    def __init__(
        self,
        control: GraphRuntimeControlPlane,
        *,
        host: str = "127.0.0.1",
        port: int = 0,
        token: Optional[str] = None,
    ) -> None:
        self.control = control
        self.host = host
        self.port = port
        self.token = token or secrets.token_urlsafe(24)
        self._server: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    @property
    def url(self) -> str:
        if self._server is None:
            raise RuntimeError("graph runtime RPC server is not started")
        return f"http://{self._server.server_address[0]}:{self._server.server_address[1]}/graph-runtime"

    def start(self) -> None:
        if self._server is not None:
            return
        server = self

        class Handler(BaseHTTPRequestHandler):
            def _write_json(self, payload: Dict[str, Any], *, status: int = 200) -> None:
                data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self) -> None:  # noqa: N802
                parsed = urlparse(self.path)
                if parsed.path.rstrip("/") != "/graph-runtime":
                    self._write_json({"ok": False, "error": "not found"}, status=404)
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    payload = json.loads(self.rfile.read(length).decode("utf-8"))
                    if not isinstance(payload, dict):
                        raise ValueError("request body must be a JSON object")
                    if payload.get("token") != server.token:
                        raise PermissionError("invalid graph runtime RPC token")
                    response = server.control.handle_request(payload)
                except Exception as exc:  # pragma: no cover - defensive server boundary
                    response = {"ok": False, "error": str(exc)}
                self._write_json(response)

            def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
                return

        self._server = ThreadingHTTPServer((self.host, self.port), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def close(self) -> None:
        if self._server is None:
            return
        self._server.shutdown()
        self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
        self._server = None
        self._thread = None
