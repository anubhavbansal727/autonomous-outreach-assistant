"""services/rate_limiter.py — stops one user from hammering expensive endpoints.

In plain English:
- Each AI run costs money (LLM + scraping), so we cap how many a user may start
  per hour. Generate = 10/hour, ingest = 10/hour, batch = 2/hour. Different
  buckets per action.
- The technique is a "sliding window" counter stored in Redis:
    * We keep a sorted set per user where each past request is one entry,
      scored by its timestamp.
    * On a new request we delete entries older than the window, count what's
      left, and allow the request only if the count is under the limit.
- Returns ``(allowed, retry_after_seconds)`` so the router can return a 429 with
  a helpful "try again in N seconds" message.
"""

import time

from redis.asyncio import Redis


async def check_rate_limit(
    redis: Redis,
    user_id: str,
    limit: int = 10,
    window: int = 3600,
) -> tuple[bool, int]:
    """Sliding window rate limiter using a Redis sorted set.

    Returns (allowed: bool, retry_after: int seconds).
    The sorted set key is ``rate:{user_id}``. Each member is the request
    timestamp (as a string); its score is the same timestamp value so that
    ZREMRANGEBYSCORE can prune expired entries efficiently.
    """
    key = f"rate:{user_id}"
    now = time.time()
    window_start = now - window

    pipe = redis.pipeline()
    # 1. Remove entries older than the window
    pipe.zremrangebyscore(key, 0, window_start)
    # 2. Count remaining entries
    pipe.zcard(key)
    results = await pipe.execute()

    count: int = results[1]

    if count >= limit:
        return False, window

    # 3. Record the current request (score = member = timestamp string)
    member = str(now)
    await redis.zadd(key, {member: now})
    await redis.expire(key, window)

    return True, 0
