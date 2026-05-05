"""Orchestrate multiple CodeMaker CLI instances via TCP.

Quick start::

    from multi_agent_tcp import CodeMakerCluster, WorkerConfig

    cluster = await CodeMakerCluster.create(
        workers=[WorkerConfig("cm1", cwd=Path(".")), WorkerConfig("cm2", cwd=Path("."))],
    )
    result = await cluster.run_parallel([("cm1", {"prompt": "A"}), ("cm2", {"prompt": "B"})])
    for wr in result.succeeded:
        print(wr.worker, wr.answer[:200])
    await cluster.stop()
"""

from .broker import Broker
from .client import AgentTCPClient
from .cluster import (
    CodeMakerCluster,
    ParallelResult,
    ReduceResult,
    WorkerConfig,
    WorkerResult,
    is_retryable_error,
)
from .codemaker_bridge import codemaker_run, load_codemaker_runtime
from .codex_bridge import codex_run, extract_codex_final_text, load_codex_runtime
from .adapters import (
    AdapterResult,
    AgentMessage,
    CLIAdapter,
    CodexAdapter,
    CodeMakerAdapter,
    adapter_from_agent_config,
    body_to_agent_message,
)
from .graph_runtime import (
    AgentInstance,
    AgentNode,
    AgentSkillSelection,
    BlueprintTerminalNode,
    BrokerAgentRuntime,
    GraphDefinition,
    GraphEdge,
    GraphEvent,
    GraphExecutor,
    GraphJob,
    GraphRuntime,
    MultiModalEnvelope,
    RouteNode,
    WorkspaceManifest,
    normalize_envelope,
)
from .ryven_blueprint import RyvenFlowCompileError, compile_ryven_flow
from .workspace_manager import (
    DulwichWorkspaceManager,
    FileChange,
    JobWorkspace,
    MergeResult,
    ProjectWorkspace,
    RunWorkspace,
    describe_dulwich_backend,
)
from .skill_space import (
    AgentSkillView,
    SkillRecord,
    SkillSpace,
    SuperAgentProfile,
)
from .registry import AgentsRegistry, AgentProfile, AgentSession, SkillInfo, show_registry_response

__all__ = (
    "CodeMakerCluster",
    "WorkerConfig",
    "WorkerResult",
    "ParallelResult",
    "ReduceResult",
    "is_retryable_error",
    "AgentTCPClient",
    "Broker",
    "codemaker_run",
    "load_codemaker_runtime",
    "codex_run",
    "extract_codex_final_text",
    "load_codex_runtime",
    "AgentMessage",
    "AdapterResult",
    "CLIAdapter",
    "CodexAdapter",
    "CodeMakerAdapter",
    "adapter_from_agent_config",
    "body_to_agent_message",
    "AgentNode",
    "AgentSkillSelection",
    "BlueprintTerminalNode",
    "AgentInstance",
    "GraphRuntime",
    "BrokerAgentRuntime",
    "MultiModalEnvelope",
    "normalize_envelope",
    "GraphEvent",
    "GraphJob",
    "WorkspaceManifest",
    "RouteNode",
    "GraphEdge",
    "GraphDefinition",
    "GraphExecutor",
    "RyvenFlowCompileError",
    "compile_ryven_flow",
    "DulwichWorkspaceManager",
    "ProjectWorkspace",
    "RunWorkspace",
    "JobWorkspace",
    "FileChange",
    "MergeResult",
    "describe_dulwich_backend",
    "SkillSpace",
    "SkillRecord",
    "AgentSkillView",
    "SuperAgentProfile",
    "AgentsRegistry",
    "AgentProfile",
    "AgentSession",
    "SkillInfo",
    "show_registry_response",
    "__version__",
)
__version__ = "0.5.0"
