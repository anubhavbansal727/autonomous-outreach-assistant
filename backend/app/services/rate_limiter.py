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
