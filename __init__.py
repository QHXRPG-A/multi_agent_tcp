"""Orchestrate multiple CLI-backed Agent workers via TCP.

Quick start::

    from multi_agent_tcp import CLIWorkerBackend, WorkerConfig

    backend = await CLIWorkerBackend.create(
        workers=[WorkerConfig("cm1", cwd=Path(".")), WorkerConfig("cm2", cwd=Path("."))],
    )
    result = await backend.run_parallel([("cm1", {"prompt": "A"}), ("cm2", {"prompt": "B"})])
    for wr in result.succeeded:
        print(wr.worker, wr.answer[:200])
    await backend.stop()
"""

from .broker import Broker
from .client import AgentTCPClient
from .cli_worker_backend import (
    CLIWorkerBackend,
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
    AgentRing,
    AgentSkillSelection,
    BlueprintTerminalNode,
    BrokerAgentRuntime,
    GuLiCodeTopAgentProfile,
    GraphDefinition,
    GraphEdge,
    GraphEvent,
    GraphExecutor,
    GraphJob,
    GraphRuntime,
    JoinBarrier,
    JoinContribution,
    MultiModalEnvelope,
    OutgoingMessageBatch,
    PendingAgentMessage,
    RouteNode,
    RunEndResult,
    StagedOutgoingMessage,
    TopAgentPlanValidation,
    TopAgentStartPlan,
    TopAgentTask,
    WorkdirAssignmentResult,
    WorkspaceManifest,
    normalize_envelope,
)
from .ryven_blueprint import RyvenFlowCompileError, compile_ryven_flow
from .ryven_blueprint import BlueprintRunController, BlueprintRunResult
from .graph_control import (
    GraphControlResponse,
    GraphRuntimeControlPlane,
    GraphRuntimeRPCServer,
    graph_definition_from_dict,
    inject_framework_context,
    load_graph_definition,
    load_top_agent_profile,
    ordinary_agent_framework_context,
    scoped_organization_view,
)
from .desktop_blueprint_service import (
    DEFAULT_BLUEPRINT_ID,
    DEFAULT_BLUEPRINT_NAME,
    DesktopBlueprintHTTPServer,
    DesktopBlueprintService,
)
from .workspace_manager import (
    AgentCheckout,
    ChangesetSubmitResult,
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
    "CLIWorkerBackend",
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
    "AgentRing",
    "AgentSkillSelection",
    "GuLiCodeTopAgentProfile",
    "TopAgentTask",
    "TopAgentStartPlan",
    "TopAgentPlanValidation",
    "BlueprintTerminalNode",
    "AgentInstance",
    "GraphRuntime",
    "BrokerAgentRuntime",
    "JoinBarrier",
    "JoinContribution",
    "RunEndResult",
    "WorkdirAssignmentResult",
    "PendingAgentMessage",
    "OutgoingMessageBatch",
    "StagedOutgoingMessage",
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
    "BlueprintRunController",
    "BlueprintRunResult",
    "GraphControlResponse",
    "GraphRuntimeControlPlane",
    "GraphRuntimeRPCServer",
    "graph_definition_from_dict",
    "inject_framework_context",
    "load_graph_definition",
    "load_top_agent_profile",
    "ordinary_agent_framework_context",
    "scoped_organization_view",
    "DEFAULT_BLUEPRINT_ID",
    "DEFAULT_BLUEPRINT_NAME",
    "DesktopBlueprintHTTPServer",
    "DesktopBlueprintService",
    "DulwichWorkspaceManager",
    "ProjectWorkspace",
    "RunWorkspace",
    "AgentCheckout",
    "ChangesetSubmitResult",
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
