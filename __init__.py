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
    "AgentsRegistry",
    "AgentProfile",
    "AgentSession",
    "SkillInfo",
    "show_registry_response",
    "__version__",
)
__version__ = "0.5.0"
