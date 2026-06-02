"""Public semantic entrypoint for CLI-backed Agent worker execution."""

from .cluster import (
    CLIWorkerBackend,
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
    "WorkerConfig",
    "WorkerResult",
    "ParallelResult",
    "ReduceResult",
    "extract_final_text",
    "summarize_gather_result",
    "is_retryable_error",
)
