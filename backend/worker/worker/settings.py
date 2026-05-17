from __future__ import annotations

from arq import cron
from arq.connections import RedisSettings

from core.config import settings as core_settings
from worker.jobs import curate_memory, decay, execute_task, reflect, sample_metrics
from worker.startup import shutdown, startup


class WorkerSettings:
    functions = [execute_task, reflect]
    cron_jobs = [
        cron(decay,          second={0, 30}),          # every 30 seconds
        cron(sample_metrics, second={0, 15, 30, 45}),  # every 15 seconds
        cron(curate_memory,  minute={0}, hour={0}),    # nightly at midnight
    ]
    on_startup  = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(core_settings.redis.url)
    max_jobs    = 10
    job_timeout = 300   # 5 minutes — ceiling for LangGraph graph execution
    keep_result = 3600  # retain job result in Redis for 1 hour
