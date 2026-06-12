"""worker.py — the background worker process (the "kitchen" behind the API).

In plain English:
- This is a SEPARATE program from the web API. You run it with
  ``python worker.py``. It connects to the same Redis and waits for jobs the
  API dropped on the queue, then runs them.
- ``WorkerSettings.functions`` is the allow-list of jobs it knows how to run:
  ingestion, single outreach, and batch. The string names here must match the
  names the API passes to ``enqueue_job(...)``.
- The settings below are the safety rails:
    * ``max_jobs=10``    — run up to 10 jobs at once
    * ``job_timeout=120``— kill a job after 120s (default)
    * ``max_tries=3`` + ``retry_jobs=True`` — auto-retry a failed job up to 3x
- WHY the batch job overrides these (the ``func(...)`` line): a 20-prospect
  batch can take longer than 120s, and retrying a half-finished batch would
  redo/duplicate work — so it gets a 10-minute timeout and NO retries.

Deployment detail: the worker image installs Playwright (a real browser) for
scraping and gets more memory; the API image stays small. See docker-compose.yml.
"""

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
