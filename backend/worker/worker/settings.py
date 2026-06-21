from __future__ import annotations

from arq import cron
from arq.connections import RedisSettings
from core.config import settings as core_settings

from worker.jobs import (
    curate_memory,
    deliver_webhook,
    enrich_task,
    execute_task,
    reflect,
    sample_metrics,
    sweep_tasks,
)
from worker.startup import shutdown, startup

_w = core_settings.worker

# Build cron schedule from config so frequencies are tunable per environment.
# WORKER__METRICS_SAMPLE_INTERVAL_SECONDS, WORKER__SWEEP_INTERVAL_MINUTES,
# WORKER__CURATE_MEMORY_HOUR control these without a code change.
if _w.metrics_sample_interval_seconds < 1:
    raise ValueError(
        f"WORKER__METRICS_SAMPLE_INTERVAL_SECONDS must be >= 1, got {_w.metrics_sample_interval_seconds}"
    )
if _w.sweep_interval_minutes < 1:
    raise ValueError(
        f"WORKER__SWEEP_INTERVAL_MINUTES must be >= 1, got {_w.sweep_interval_minutes}"
    )
if not 0 <= _w.curate_memory_hour <= 23:
    raise ValueError(f"WORKER__CURATE_MEMORY_HOUR must be 0-23, got {_w.curate_memory_hour}")
_metrics_seconds = set(range(0, 60, _w.metrics_sample_interval_seconds))
_sweep_minutes = set(range(0, 60, _w.sweep_interval_minutes))


class WorkerSettings:
    """ARQ worker entry point.

    Declare all enqueueable functions in ``functions``. Cron-only jobs (those
    never explicitly enqueued) live only in ``cron_jobs`` — ARQ registers them
    automatically. Runtime tuning (concurrency, timeouts, frequencies) reads from
    ``core_settings.worker`` so each environment can override via env vars without
    touching this file.

    Separation of concerns reminder: this file is pure wiring. Business logic
    belongs in the job functions; startup/shutdown logic belongs in startup.py.
    """

    # Jobs that are explicitly enqueued by handlers at runtime.
    # Cron-only jobs (sample_metrics, sweep_tasks, curate_memory) are NOT listed
    # here — ARQ registers them from cron_jobs automatically.
    functions = [execute_task, reflect, deliver_webhook, enrich_task]

    cron_jobs = [
        cron(sample_metrics, second=_metrics_seconds),  # default: every 15 s
        cron(curate_memory, minute={0}, hour={_w.curate_memory_hour}),  # default: midnight UTC
        cron(sweep_tasks, minute=_sweep_minutes),  # default: every 5 min
    ]

    on_startup = startup
    on_shutdown = shutdown

    redis_settings = RedisSettings.from_dsn(core_settings.redis.url)

    max_jobs = _w.max_jobs
    job_timeout = _w.job_timeout
    keep_result = _w.keep_result
    # All enqueued jobs must be idempotent — ARQ will retry up to max_tries on
    # unhandled exceptions. deliver_webhook is self-managed and should not reach
    # this limit under normal operation.
    max_tries = _w.max_tries
