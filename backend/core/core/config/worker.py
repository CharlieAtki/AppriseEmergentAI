from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class WorkerConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="WORKER__")

    # Task types for which a dedicated LangGraph is compiled at startup.
    # Unknown task_types at runtime fall back to the "general" graph (see execute_task.py).
    # "general" must always be present — it is the fallback graph.
    task_types: list[str] = ["general", "code", "research", "coordination"]

    max_jobs: int = 10
    # Ceiling for LangGraph graph execution. Long-running graphs will be killed
    # by ARQ and retried if this is exceeded — set above the p99 graph latency.
    job_timeout: int = 300
    # How long ARQ retains job results in Redis. Only used for observability;
    # no business logic reads these results.
    keep_result: int = 3600
    max_tries: int = 3
    # Cron frequencies in seconds / minutes — tune per environment.
    metrics_sample_interval_seconds: int = 15   # WORKER__METRICS_SAMPLE_INTERVAL_SECONDS
    sweep_interval_minutes: int = 5             # WORKER__SWEEP_INTERVAL_MINUTES
    curate_memory_hour: int = 0                 # WORKER__CURATE_MEMORY_HOUR (midnight UTC)
