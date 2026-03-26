"""ARQ worker configuration."""

from __future__ import annotations

import os

from arq.connections import RedisSettings

from app.tasks.smoke import worker_healthcheck
from app.tasks.update_ohlc import update_daily_ohlc


class WorkerSettings:
    """ARQ worker settings for background jobs."""

    redis_settings = RedisSettings.from_dsn(
        os.getenv("REDIS_URL", "redis://localhost:6379/0")
    )
    functions = [update_daily_ohlc, worker_healthcheck]
    max_tries = 3
    retry_jobs = True
    job_timeout = int(os.getenv("ARQ_JOB_TIMEOUT", "600"))
    keep_result = int(os.getenv("ARQ_KEEP_RESULT", "3600"))
