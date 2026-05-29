import logging

from arq.connections import RedisSettings

from app.config import settings
from app.jobs.ingestion_job import run_ingestion_job
from app.jobs.outreach_job import run_outreach_job

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)


class WorkerSettings:
    functions = [run_ingestion_job, run_outreach_job]
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
    max_jobs = 10
    job_timeout = 120
    keep_result = 3600
    retry_jobs = True
    max_tries = 3


if __name__ == "__main__":
    from arq.worker import run_worker

    run_worker(WorkerSettings)
