import logging
import sys

from arq import func
from arq.connections import RedisSettings

from app.config import settings
from app.jobs.batch_job import run_batch_job
from app.jobs.ingestion_job import run_ingestion_job
from app.jobs.outreach_job import run_outreach_job

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)


class WorkerSettings:
    functions = [
        run_ingestion_job,
        run_outreach_job,
        # A batch of up to 20 prospects can exceed the default 120s timeout, and a
        # partially-completed batch must not restart from scratch — so this job
        # gets a longer timeout and no retries (overrides the worker defaults).
        func(run_batch_job, name="run_batch_job", timeout=600, max_tries=1),
    ]
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
    max_jobs = 10
    job_timeout = 120
    keep_result = 3600
    retry_jobs = True
    max_tries = 3


if __name__ == "__main__":
    from arq.worker import run_worker

    run_worker(WorkerSettings)
