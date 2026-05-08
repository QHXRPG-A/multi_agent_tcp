"""Public semantic entrypoint for CLI-backed Agent worker execution.

The implementation still lives in ``cluster.py`` for backward compatibility
with older imports, but new code should import ``CLIWorkerBackend`` from this
module or from the package root.
"""

from .cluster import (
    CLIWorkerBackend,
    CodeMakerCluster,
    ParallelResult,
    ReduceResult,
    WorkerConfig,
    WorkerResult,
    extract_final_text,
    is_retryable_error,
    summarize_gather_result,
)

__all__ = (
    "CLIWorkerBackend",
    "CodeMakerCluster",
    "WorkerConfig",
    "WorkerResult",
    "ParallelResult",
    "ReduceResult",
    "extract_final_text",
    "summarize_gather_result",
    "is_retryable_error",
)
