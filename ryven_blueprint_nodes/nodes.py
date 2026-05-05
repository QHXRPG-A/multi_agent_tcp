from __future__ import annotations

from typing import Any, Dict

from ryvencore import Data, Node, NodeInputType, NodeOutputType
from ryven.node_env import export_nodes, on_gui_load

from multi_agent_tcp.graph_runtime import AgentNode as RuntimeAgentNode
from multi_agent_tcp.ryven_blueprint import (
    BLUEPRINT_END_NODE_ID,
    BLUEPRINT_START_NODE_ID,
    install_blueprint_hooks,
)


def _default_agent_config() -> Dict[str, Any]:
    return RuntimeAgentNode.from_dict({"cwd": "."}).to_dict()


def _normalize_agent_config(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict) and "agent_node" in value:
        value = value["agent_node"]
    if not isinstance(value, dict):
        value = {}
    return RuntimeAgentNode.from_dict(value).to_dict()


class BlueprintStart(Node):
    """Required entry point for runnable blueprints."""

    version = "v0.1"
    title = "Start"
    identifier = "BlueprintStart"
    tags = ["blueprint", "start", "entry"]
    blueprint_terminal_kind = "start"
    blueprint_protected = True
    hide_from_node_list = True
    init_outputs = [NodeOutputType(label="next", type_="exec")]

    def get_state(self) -> Dict[str, Any]:
        return {"node_id": BLUEPRINT_START_NODE_ID}


class BlueprintEnd(Node):
    """Required terminal point for runnable blueprints."""

    version = "v0.1"
    title = "End"
    identifier = "BlueprintEnd"
    tags = ["blueprint", "end", "terminal"]
    blueprint_terminal_kind = "end"
    blueprint_protected = True
    hide_from_node_list = True
    init_inputs = [NodeInputType(label="done", type_="exec")]

    def get_state(self) -> Dict[str, Any]:
        return {"node_id": BLUEPRINT_END_NODE_ID}


class AgentNode(Node):
    """A visual wrapper around multi_agent_tcp.graph_runtime.AgentNode."""

    version = "v0.1"
    title = "AgentNode"
    identifier = "AgentNode"
    tags = ["agent", "codemaker", "codex", "blueprint"]
    init_inputs = [
        NodeInputType(label="in", type_="exec"),
        NodeInputType(label="prompt", type_="data"),
    ]
    init_outputs = [
        NodeOutputType(label="out", type_="exec"),
        NodeOutputType(label="result", type_="data"),
    ]

    def __init__(self, params):
        super().__init__(params)
        self.agent_config = _default_agent_config()

    def runtime_node(self) -> RuntimeAgentNode:
        return RuntimeAgentNode.from_dict(self.agent_config)

    def set_agent_config(self, value: Dict[str, Any]) -> None:
        self.agent_config = _normalize_agent_config(value)

    def get_state(self) -> Dict[str, Any]:
        return {"agent_node": dict(self.agent_config)}

    def set_state(self, data: Dict[str, Any], version):
        self.agent_config = _normalize_agent_config(data)

    def update_event(self, input_called=-1):
        if input_called == 1 and self.input(1) is not None:
            self.set_output_val(1, self.input(1))
        if input_called in {-1, 0}:
            self.exec_output(0)


install_blueprint_hooks()

export_nodes([
    BlueprintStart,
    BlueprintEnd,
    AgentNode,
])


@on_gui_load
def load_gui():
    from . import gui
