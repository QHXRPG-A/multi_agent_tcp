"""Ryven integration helpers for AgentNode blueprints."""

from __future__ import annotations

import asyncio
import json
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Optional, Type

from .graph_runtime import (
    AgentNode as RuntimeAgentNode,
    BlueprintTerminalNode,
    GraphDefinition,
    GraphEdge,
    GraphEvent,
    GraphExecutor,
    GraphRuntime,
)
from .workspace_manager import DulwichWorkspaceManager, RunWorkspace


BLUEPRINT_START_NODE_ID = "blueprint-start"
BLUEPRINT_END_NODE_ID = "blueprint-end"
WORKSPACE_API_CONTEXT_ENV = "MULTI_AGENT_WORKSPACE_CONTEXT"

_START_POS = (180.0, 260.0)
_END_POS = (760.0, 260.0)


def blueprint_terminal_kind_for_class(node_class: Type[Any]) -> Optional[str]:
    kind = getattr(node_class, "blueprint_terminal_kind", None)
    if kind is None:
        return None
    kind = str(kind).strip().lower()
    return kind if kind in {"start", "end"} else None


def blueprint_terminal_kind_for_node(node: Any) -> Optional[str]:
    return blueprint_terminal_kind_for_class(node.__class__)


def is_blueprint_terminal_class(node_class: Type[Any]) -> bool:
    return blueprint_terminal_kind_for_class(node_class) is not None


def is_blueprint_protected_node(node: Any) -> bool:
    return bool(getattr(node.__class__, "blueprint_protected", False))


def is_hidden_from_node_palette(node_class: Type[Any]) -> bool:
    return bool(getattr(node_class, "hide_from_node_list", False))


def editable_nodes(nodes: Iterable[Any]) -> list[Any]:
    return [node for node in nodes if not is_blueprint_protected_node(node)]


class RyvenFlowCompileError(ValueError):
    """Raised when a Ryven flow cannot be compiled to GraphDefinition."""


@dataclass
class BlueprintRunResult:
    ok: bool
    status: str
    result: Any = None
    events: list[dict[str, Any]] = field(default_factory=list)
    jobs: list[dict[str, Any]] = field(default_factory=list)
    archive_path: Optional[str] = None
    error: Optional[str] = None


def _node_for_graph_id(flow: Any, graph_id: str) -> Any:
    for node in getattr(flow, "nodes", []):
        terminal_kind = blueprint_terminal_kind_for_node(node)
        if terminal_kind is not None:
            expected = BLUEPRINT_START_NODE_ID if terminal_kind == "start" else BLUEPRINT_END_NODE_ID
            if expected == graph_id:
                return node
        runtime_node = getattr(node, "runtime_node", None)
        if callable(runtime_node):
            try:
                if runtime_node().node_id == graph_id:
                    return node
            except Exception:
                continue
    return None


def _set_visual_status(flow: Any, node_id: str, status: str, payload: Optional[dict[str, Any]] = None) -> None:
    node = _node_for_graph_id(flow, node_id)
    if node is None:
        return
    setter = getattr(node, "set_runtime_status", None)
    if callable(setter):
        setter(status, payload or {})


def _workspace_api_doc() -> str:
    doc_path = Path(__file__).resolve().parent / "docs" / "workspace_api.md"
    if not doc_path.is_file():
        return (
            "# Workspace API for Blueprint Agents\n\n"
            "Publish outputs with `python -m multi_agent_tcp.workspace_api publish "
            "--area <code|artifacts|reports> --path <relative-path> --stdin`."
        )
    return doc_path.read_text(encoding="utf-8")


def _apply_run_workspace_to_node(
    node: RuntimeAgentNode,
    *,
    manager: DulwichWorkspaceManager,
    run: RunWorkspace,
    private_dir: Path,
) -> RuntimeAgentNode:
    data = node.to_dict()
    data["cwd"] = str(private_dir)
    data["workspace_id"] = run.run_id
    data["workspace_root"] = str(run.path)
    data["read_scope"] = list(node.read_scope)
    data["write_scope"] = list(node.write_scope)
    data["artifact_scope"] = list(node.artifact_scope)

    api_context_path = private_dir / "workspace_api_context.json"
    api_context_path.write_text(
        json.dumps(
            {
                "project_root": str(manager.project_root),
                "workspace_root": str(manager.workspace_root),
                "run_id": run.run_id,
                "agent_id": node.runtime_agent_id,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    preamble = (
        "You are running inside a visual blueprint run. Do not publish task "
        "outcomes by writing directly to filesystem paths. Use the framework "
        "Workspace API below for code, artifacts, and reports.\n\n"
        f"{_workspace_api_doc()}"
    )
    adapter_options = dict(data.get("adapter_options", {}))
    existing = adapter_options.get("prompt_preamble")
    if isinstance(existing, str) and existing.strip():
        adapter_options["prompt_preamble"] = f"{existing.strip()}\n\n{preamble}"
    else:
        adapter_options["prompt_preamble"] = preamble
    execution_context = dict(adapter_options.get("execution_context", {}))
    execution_context["workspace_api"] = {
        "command": "python -m multi_agent_tcp.workspace_api",
        "context_env": WORKSPACE_API_CONTEXT_ENV,
        "areas": ["code", "artifacts", "reports"],
    }
    adapter_options["execution_context"] = execution_context
    adapter_options.setdefault("codex_home", str(private_dir / "codex_home"))
    data["adapter_options"] = adapter_options
    extra_env = {str(k): str(v) for k, v in dict(data.get("extra_env", {})).items()}
    extra_env[WORKSPACE_API_CONTEXT_ENV] = str(api_context_path)
    package_parent = str(Path(__file__).resolve().parent.parent)
    existing_pythonpath = extra_env.get("PYTHONPATH") or os.environ.get("PYTHONPATH")
    extra_env["PYTHONPATH"] = (
        f"{package_parent}{os.pathsep}{existing_pythonpath}"
        if existing_pythonpath
        else package_parent
    )
    data["extra_env"] = extra_env
    return RuntimeAgentNode.from_dict(data)


class BlueprintRunController:
    """Run/stop lifecycle for one Ryven blueprint flow."""

    def __init__(
        self,
        flow: Any,
        *,
        project_root: Optional[Path] = None,
        port: int = 9140,
        verbose: bool = False,
        event_callback: Optional[Callable[[GraphEvent], None]] = None,
    ) -> None:
        self.flow = flow
        self.project_root = Path(project_root or Path.cwd()).resolve()
        self.port = int(port)
        self.verbose = verbose
        self.event_callback = event_callback
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._task: Optional[asyncio.Future] = None
        self._done_callbacks: list[Callable[[BlueprintRunResult], None]] = []
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    def add_done_callback(self, callback: Callable[[BlueprintRunResult], None]) -> None:
        self._done_callbacks.append(callback)

    def start(self, *, initial_prompt: str = "") -> None:
        if self._running:
            raise RuntimeError("blueprint is already running")
        self._running = True
        self._thread = threading.Thread(
            target=self._thread_main,
            args=(initial_prompt,),
            name="BlueprintRunController",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        if self._loop is not None and self._task is not None:
            self._loop.call_soon_threadsafe(self._task.cancel)

    def _thread_main(self, initial_prompt: str) -> None:
        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)
        task = asyncio.ensure_future(self._run(initial_prompt))
        self._task = task
        try:
            result = loop.run_until_complete(task)
        except asyncio.CancelledError:
            result = BlueprintRunResult(ok=False, status="cancelled")
        except Exception as exc:
            result = BlueprintRunResult(ok=False, status="failed", error=str(exc))
        finally:
            self._running = False
            for callback in list(self._done_callbacks):
                try:
                    callback(result)
                except Exception:
                    pass
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.close()

    async def _run(self, initial_prompt: str) -> BlueprintRunResult:
        from .cluster import CodeMakerCluster

        graph = compile_ryven_flow(self.flow, validate=True)
        manager = DulwichWorkspaceManager.open_or_init(self.project_root)
        run = manager.create_run()
        private_dirs: dict[str, Path] = {}
        adjusted = GraphDefinition(
            terminal_nodes=dict(graph.terminal_nodes),
            route_nodes=dict(graph.route_nodes),
            edges=list(graph.edges),
        )
        for node_id, node in graph.agent_nodes.items():
            private_dir = manager.agent_workspace_dir(run, node.runtime_agent_id)
            private_dirs[node_id] = private_dir
            adjusted.agent_nodes[node_id] = _apply_run_workspace_to_node(
                node,
                manager=manager,
                run=run,
                private_dir=private_dir,
            )

        cluster = await CodeMakerCluster.create(
            [node.to_worker_config() for node in adjusted.agent_nodes.values()],
            port=self.port,
            verbose=self.verbose,
        )
        events: list[dict[str, Any]] = []
        private_workspace_rows = [
            {"node_id": node_id, "private_workspace": str(path)}
            for node_id, path in private_dirs.items()
        ]

        def on_event(event: GraphEvent) -> None:
            events.append(event.to_dict())
            if event.node_id:
                _set_visual_status(
                    self.flow,
                    event.node_id,
                    event.status or event.event_type,
                    event.payload,
                )
            if self.event_callback is not None:
                self.event_callback(event)

        archive_status = "completed"
        try:
            runtime = GraphRuntime(cluster)
            executor = GraphExecutor(runtime)
            result = await executor.run_blueprint(
                adjusted,
                initial_prompt=initial_prompt,
                event_callback=on_event,
            )
            manager.write_shared_text(
                run,
                "reports/blueprint_result.json",
                json.dumps(
                    {
                        "run_id": run.run_id,
                        "status": archive_status,
                        "ok": archive_status == "completed",
                        "result": result,
                        "events": events,
                        "private_workspaces": private_workspace_rows,
                    },
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                ),
                owner="blueprint-controller",
            )
            archive = manager.archive_run(run, status=archive_status)
            result["shared_workspace"] = str(archive / "shared")
            result["shared_code_workspace"] = str(archive / "shared" / "code")
            result["shared_reports_workspace"] = str(archive / "shared" / "reports")
            result["archive_path"] = str(archive)
            return BlueprintRunResult(
                ok=archive_status == "completed",
                status=archive_status,
                result=result,
                events=events,
                jobs=private_workspace_rows,
                archive_path=str(archive),
            )
        except asyncio.CancelledError:
            manager.write_shared_text(
                run,
                "reports/blueprint_result.json",
                json.dumps(
                    {
                        "run_id": run.run_id,
                        "status": "cancelled",
                        "ok": False,
                        "events": events,
                        "private_workspaces": private_workspace_rows,
                    },
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                ),
                owner="blueprint-controller",
            )
            archive = manager.archive_run(run, status="cancelled")
            return BlueprintRunResult(
                ok=False,
                status="cancelled",
                events=events,
                jobs=private_workspace_rows,
                archive_path=str(archive),
            )
        except Exception as exc:
            manager.write_shared_text(
                run,
                "reports/blueprint_result.json",
                json.dumps(
                    {
                        "run_id": run.run_id,
                        "status": "failed",
                        "ok": False,
                        "error": str(exc),
                        "events": events,
                        "private_workspaces": private_workspace_rows,
                    },
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                ),
                owner="blueprint-controller",
            )
            archive = manager.archive_run(run, status="failed")
            return BlueprintRunResult(
                ok=False,
                status="failed",
                error=str(exc),
                events=events,
                jobs=private_workspace_rows,
                archive_path=str(archive),
            )
        finally:
            await cluster.stop()


def _node_title(node: Any) -> str:
    return str(getattr(node.__class__, "title", node.__class__.__name__) or node.__class__.__name__)


def _node_state_id(node: Any) -> Optional[str]:
    get_state = getattr(node, "get_state", None)
    if not callable(get_state):
        return None
    try:
        state = get_state()
    except Exception:
        return None
    if not isinstance(state, dict):
        return None
    raw_id = state.get("node_id")
    if raw_id is None:
        return None
    node_id = str(raw_id).strip()
    return node_id or None


def _unique_terminal_id(
    *,
    node: Any,
    kind: str,
    terminal_id_counts: dict[str, int],
) -> str:
    fallback = BLUEPRINT_START_NODE_ID if kind == "start" else BLUEPRINT_END_NODE_ID
    base_id = _node_state_id(node) or fallback
    count = terminal_id_counts.get(base_id, 0) + 1
    terminal_id_counts[base_id] = count
    if count == 1:
        return base_id
    return f"{base_id}#{count}"


def _port_name(port: Any, ports: list[Any], fallback_prefix: str) -> str:
    label = str(getattr(port, "label_str", "") or "").strip()
    if label:
        return label
    try:
        index = ports.index(port)
    except ValueError:
        index = -1
    return f"{fallback_prefix}:{index}"


def _edge_type_for_ports(output_port: Any, input_port: Any) -> Optional[str]:
    output_type = str(getattr(output_port, "type_", "") or "").strip().lower()
    input_type = str(getattr(input_port, "type_", "") or "").strip().lower()
    if output_type and input_type and output_type != input_type:
        raise RyvenFlowCompileError(
            f"connection type mismatch: output {output_type!r} -> input {input_type!r}"
        )
    return output_type or input_type or None


def compile_ryven_flow(
    flow: Any,
    *,
    ensure_terminals: bool = True,
    validate: bool = False,
) -> GraphDefinition:
    """Compile a live Ryven flow into the backend GraphDefinition IR.

    The compiler maps blueprint terminal wrappers to
    ``BlueprintTerminalNode``, visual AgentNode wrappers to backend
    ``AgentNode`` objects, and Ryven port connections to ``GraphEdge`` with
    explicit ``edge_type`` values such as ``exec`` or ``data``.
    """

    if ensure_terminals:
        ensure_blueprint_terminal_nodes(flow)

    graph = GraphDefinition()
    visual_to_graph_id: dict[Any, str] = {}
    compiled_ids: set[str] = set()
    terminal_id_counts: dict[str, int] = {}

    for node in list(getattr(flow, "nodes", [])):
        terminal_kind = blueprint_terminal_kind_for_node(node)
        if terminal_kind is not None:
            node_id = _unique_terminal_id(
                node=node,
                kind=terminal_kind,
                terminal_id_counts=terminal_id_counts,
            )
            graph.terminal_nodes[node_id] = BlueprintTerminalNode(
                node_id=node_id,
                terminal_kind=terminal_kind,
            )
        else:
            runtime_node_fn = getattr(node, "runtime_node", None)
            if not callable(runtime_node_fn):
                raise RyvenFlowCompileError(
                    f"unsupported Ryven node for graph compilation: {_node_title(node)}"
                )
            runtime_node = runtime_node_fn()
            if not isinstance(runtime_node, RuntimeAgentNode):
                raise RyvenFlowCompileError(
                    f"{_node_title(node)}.runtime_node() did not return AgentNode"
                )
            node_id = runtime_node.node_id
            graph.agent_nodes[node_id] = runtime_node

        if node_id in compiled_ids:
            raise RyvenFlowCompileError(f"duplicate compiled node_id: {node_id}")
        compiled_ids.add(node_id)
        visual_to_graph_id[node] = node_id

    for node in list(getattr(flow, "nodes", [])):
        source_id = visual_to_graph_id[node]
        for output_port in list(getattr(node, "outputs", [])):
            connected_inputs = flow.connected_inputs(output_port)
            for input_port in connected_inputs:
                target_node = getattr(input_port, "node", None)
                if target_node not in visual_to_graph_id:
                    raise RyvenFlowCompileError(
                        f"connection target is outside compiled flow: {_node_title(node)}"
                    )
                target_id = visual_to_graph_id[target_node]
                graph.edges.append(
                    GraphEdge(
                        source=source_id,
                        target=target_id,
                        output_port=_port_name(
                            output_port,
                            list(getattr(node, "outputs", [])),
                            "output",
                        ),
                        input_port=_port_name(
                            input_port,
                            list(getattr(target_node, "inputs", [])),
                            "input",
                        ),
                        edge_type=_edge_type_for_ports(output_port, input_port),
                    )
                )

    if validate:
        graph.validate_runnable()
    return graph


def _registered_terminal_classes(session: Any) -> dict[str, Type[Any]]:
    classes: dict[str, Type[Any]] = {}
    for node_class in getattr(session, "nodes", set()):
        kind = blueprint_terminal_kind_for_class(node_class)
        if kind and kind not in classes:
            classes[kind] = node_class
    return classes


def _flow_terminal_nodes(flow: Any, kind: str) -> list[Any]:
    return [
        node
        for node in getattr(flow, "nodes", [])
        if blueprint_terminal_kind_for_node(node) == kind
    ]


def _set_node_item_pos(flow_view: Any, node: Any, pos: tuple[float, float]) -> None:
    if flow_view is None:
        return
    item = getattr(flow_view, "node_items", {}).get(node)
    if item is None:
        return
    try:
        from qtpy.QtCore import QPointF

        item.setPos(QPointF(pos[0], pos[1]))
    except Exception:
        item.setPos(*pos)


def ensure_blueprint_terminal_nodes(flow: Any, flow_view: Any = None) -> None:
    """Ensure one start and one end node exist in a Ryven flow.

    The helper is intentionally idempotent. It repairs missing terminals but
    does not remove duplicates; duplicate terminal nodes are treated as a
    validation error by the backend runnable-graph contract.
    """

    session = getattr(flow, "session", None)
    if session is None:
        return

    classes = _registered_terminal_classes(session)
    start_class = classes.get("start")
    end_class = classes.get("end")
    if start_class is None or end_class is None:
        return

    start_nodes = _flow_terminal_nodes(flow, "start")
    end_nodes = _flow_terminal_nodes(flow, "end")

    if not start_nodes:
        start = flow.create_node(start_class)
        if start is not None:
            _set_node_item_pos(flow_view, start, _START_POS)
    if not end_nodes:
        end = flow.create_node(end_class)
        if end is not None:
            _set_node_item_pos(flow_view, end, _END_POS)

    if flow_view is not None:
        flow_view.clear_selection()


def _flow_has_terminal(flow: Any, kind: str) -> bool:
    return bool(_flow_terminal_nodes(flow, kind))


def install_blueprint_hooks() -> None:
    """Install runtime hooks used by the bundled Ryven nodes package."""

    import ryvencore

    session_cls = ryvencore.Session
    if not getattr(session_cls, "_multi_agent_tcp_blueprint_hooks", False):
        original_create_flow = session_cls.create_flow

        def create_flow_with_blueprint_terminals(self, title: str, data=None):
            flow = original_create_flow(self, title, data)
            flow_view = getattr(getattr(self, "gui", None), "flow_views", {}).get(flow)
            ensure_blueprint_terminal_nodes(flow, flow_view)
            return flow

        session_cls.create_flow = create_flow_with_blueprint_terminals
        session_cls._multi_agent_tcp_blueprint_hooks = True

    flow_cls = ryvencore.Flow
    if not getattr(flow_cls, "_multi_agent_tcp_blueprint_hooks", False):
        original_remove_node = flow_cls.remove_node

        def remove_node_preserving_blueprint_terminals(self, node):
            if is_blueprint_protected_node(node):
                return None
            return original_remove_node(self, node)

        flow_cls.remove_node = remove_node_preserving_blueprint_terminals
        flow_cls._multi_agent_tcp_blueprint_hooks = True

    if os.environ.get("RYVEN_MODE") == "gui":
        _install_gui_hooks()


def _install_gui_hooks() -> None:
    try:
        from qtpy.QtCore import QTimer
        from qtpy.QtWidgets import QMessageBox
        from ryvencore_qt.src.flows.FlowCommands import RemoveComponents_Command
        from ryvencore_qt.src.flows.FlowView import FlowView
        from ryvencore_qt.src.flows.node_list_widget.NodeListWidget import NodeListWidget
        from ryvencore_qt.src.flows.nodes.NodeItem import NodeItem
    except Exception:
        return

    if not getattr(NodeListWidget, "_multi_agent_tcp_blueprint_hooks", False):
        original_update_list = NodeListWidget.update_list

        def update_list_without_hidden_nodes(self, nodes):
            visible_nodes = [
                node_class
                for node_class in nodes
                if not is_hidden_from_node_palette(node_class)
            ]
            return original_update_list(self, visible_nodes)

        NodeListWidget.update_list = update_list_without_hidden_nodes
        NodeListWidget._multi_agent_tcp_blueprint_hooks = True

    if not getattr(FlowView, "_multi_agent_tcp_blueprint_hooks", False):
        original_create_node = FlowView.create_node__cmd
        original_remove_selected = FlowView.remove_selected_components__cmd
        original_get_nodes_data = FlowView._get_nodes_data
        original_get_connections_data = FlowView._get_connections_data
        original_get_output_data = FlowView._get_output_data
        original_init = FlowView.__init__

        def init_with_blueprint_controls(self, *args, **kwargs):
            original_init(self, *args, **kwargs)
            self._multi_agent_tcp_blueprint_controller = None

            run_action = self.menu().addAction("Run Blueprint")
            stop_action = self.menu().addAction("Stop Blueprint")
            stop_action.setEnabled(False)
            self._multi_agent_tcp_run_action = run_action
            self._multi_agent_tcp_stop_action = stop_action

            def show_message(title: str, text: str) -> None:
                QMessageBox.information(self, title, text)

            def finish(result: BlueprintRunResult) -> None:
                def update_ui() -> None:
                    run_action.setEnabled(True)
                    stop_action.setEnabled(False)
                    status = result.status
                    if result.error:
                        text = f"Blueprint {status}: {result.error}"
                    else:
                        text = f"Blueprint {status}."
                        if result.archive_path:
                            text += f"\nArchive: {result.archive_path}"
                    show_message("Blueprint", text)

                QTimer.singleShot(0, update_ui)

            def run_blueprint() -> None:
                if getattr(self, "_multi_agent_tcp_blueprint_controller", None) is not None:
                    controller = self._multi_agent_tcp_blueprint_controller
                    if controller.running:
                        return
                controller = BlueprintRunController(self.flow)
                controller.add_done_callback(finish)
                self._multi_agent_tcp_blueprint_controller = controller
                run_action.setEnabled(False)
                stop_action.setEnabled(True)
                try:
                    controller.start()
                except Exception as exc:
                    run_action.setEnabled(True)
                    stop_action.setEnabled(False)
                    show_message("Blueprint", f"Failed to start blueprint: {exc}")

            def stop_blueprint() -> None:
                controller = getattr(self, "_multi_agent_tcp_blueprint_controller", None)
                if controller is not None:
                    controller.stop()
                stop_action.setEnabled(False)

            run_action.triggered.connect(run_blueprint)
            stop_action.triggered.connect(stop_blueprint)

        def create_node_without_duplicate_terminals(self, node_class):
            kind = blueprint_terminal_kind_for_class(node_class)
            if kind and _flow_has_terminal(self.flow, kind):
                return None
            return original_create_node(self, node_class)

        def remove_selected_without_terminals(self):
            selected = [
                item
                for item in self._current_selected
                if not (
                    isinstance(item, NodeItem)
                    and is_blueprint_protected_node(item.node)
                )
            ]
            if not selected:
                self.viewport().update()
                return None
            previous = self._current_selected
            self._current_selected = selected
            try:
                return original_remove_selected(self)
            finally:
                self._current_selected = previous

        def get_nodes_data_without_terminals(self, nodes):
            return original_get_nodes_data(self, editable_nodes(nodes))

        def get_connections_data_without_terminals(self, nodes):
            return original_get_connections_data(self, editable_nodes(nodes))

        def get_output_data_without_terminals(self, nodes):
            return original_get_output_data(self, editable_nodes(nodes))

        FlowView.__init__ = init_with_blueprint_controls
        FlowView.create_node__cmd = create_node_without_duplicate_terminals
        FlowView.remove_selected_components__cmd = remove_selected_without_terminals
        FlowView._get_nodes_data = get_nodes_data_without_terminals
        FlowView._get_connections_data = get_connections_data_without_terminals
        FlowView._get_output_data = get_output_data_without_terminals
        FlowView._multi_agent_tcp_blueprint_hooks = True

    if not getattr(RemoveComponents_Command, "_multi_agent_tcp_blueprint_hooks", False):
        original_init = RemoveComponents_Command.__init__

        def init_without_terminals(self, flow_view, items):
            filtered = [
                item
                for item in items
                if not (
                    isinstance(item, NodeItem)
                    and is_blueprint_protected_node(item.node)
                )
            ]
            original_init(self, flow_view, filtered)

        RemoveComponents_Command.__init__ = init_without_terminals
        RemoveComponents_Command._multi_agent_tcp_blueprint_hooks = True
