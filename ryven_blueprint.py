"""Ryven integration helpers for AgentNode blueprints."""

from __future__ import annotations

import os
from typing import Any, Iterable, Optional, Type

from .graph_runtime import (
    AgentNode as RuntimeAgentNode,
    BlueprintTerminalNode,
    GraphDefinition,
    GraphEdge,
)


BLUEPRINT_START_NODE_ID = "blueprint-start"
BLUEPRINT_END_NODE_ID = "blueprint-end"

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
