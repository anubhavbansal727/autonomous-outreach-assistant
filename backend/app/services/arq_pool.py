"""services/arq_pool.py — the API's connection to the job queue (Redis/ARQ).

In plain English:
- ARQ is the background job system. The web API never runs the slow AI work
  itself; instead it drops a "please run job X" message into Redis, and a
  separate worker process (worker.py) picks it up and runs it.
- This file gives routers a shared handle to that Redis queue. They call
  ``pool = await get_arq_pool()`` and then ``pool.enqueue_job("run_outreach_job",
  ...)`` to schedule work.
- We cache the pool in a module-level variable so we open the connection once
  and reuse it, instead of reconnecting on every request.
- Bonus: this same Redis handle is also used by the rate limiter
  (services/rate_limiter.py), which is why an ArqRedis object gets passed there.
"""

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from app.config import settings

_arq_pool: ArqRedis | None = None


async def get_arq_pool() -> ArqRedis:
    global _arq_pool
    if _arq_pool is None:
        _arq_pool = await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))
    return _arq_pool
