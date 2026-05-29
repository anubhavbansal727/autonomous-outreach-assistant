"""Unit tests for the Redis sliding-window rate limiter."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_redis(zcard_count: int = 0) -> AsyncMock:
    """Return a mock Redis client whose pipeline returns zcard_count.

    The pipeline's zremrangebyscore/zcard are called without await in the real
    code (they queue commands, not execute them), so we use plain MagicMock for
    those methods to avoid unawaited-coroutine warnings.
    """
    pipe = MagicMock()  # sync mock for the pipeline object
    pipe.zremrangebyscore = MagicMock(return_value=None)
    pipe.zcard = MagicMock(return_value=None)
    pipe.execute = AsyncMock(return_value=[None, zcard_count])

    redis = AsyncMock()
    redis.pipeline = MagicMock(return_value=pipe)
    redis.zadd = AsyncMock()
    redis.expire = AsyncMock()
    return redis


class TestCheckRateLimit:
    @pytest.mark.asyncio
    async def test_first_request_is_allowed(self):
        from app.services.rate_limiter import check_rate_limit
        redis = _make_redis(zcard_count=0)
        allowed, retry_after = await check_rate_limit(redis, "user:1", limit=10, window=3600)
        assert allowed is True
        assert retry_after == 0

    @pytest.mark.asyncio
    async def test_request_recorded_on_allow(self):
        from app.services.rate_limiter import check_rate_limit
        redis = _make_redis(zcard_count=5)
        await check_rate_limit(redis, "user:1", limit=10, window=3600)
        redis.zadd.assert_awaited_once()
        redis.expire.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_at_limit_is_denied(self):
        from app.services.rate_limiter import check_rate_limit
        redis = _make_redis(zcard_count=10)
        allowed, retry_after = await check_rate_limit(redis, "user:1", limit=10, window=3600)
        assert allowed is False
        assert retry_after == 3600

    @pytest.mark.asyncio
    async def test_over_limit_is_denied(self):
        from app.services.rate_limiter import check_rate_limit
        redis = _make_redis(zcard_count=99)
        allowed, _ = await check_rate_limit(redis, "user:1", limit=10, window=3600)
        assert allowed is False

    @pytest.mark.asyncio
    async def test_denied_does_not_record_request(self):
        from app.services.rate_limiter import check_rate_limit
        redis = _make_redis(zcard_count=10)
        await check_rate_limit(redis, "user:1", limit=10, window=3600)
        redis.zadd.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_uses_correct_key_prefix(self):
        from app.services.rate_limiter import check_rate_limit
        redis = _make_redis(zcard_count=0)
        await check_rate_limit(redis, "user:abc", limit=10, window=3600)
        call_kwargs = redis.zadd.call_args
        # First positional arg to zadd is the key
        assert call_kwargs[0][0] == "rate:user:abc"
