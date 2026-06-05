"""API tests for GET /health.

The health endpoint directly instantiates AsyncSessionLocal and aioredis —
both are patched to avoid real network calls.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app


async def _client():
    """Return a fresh client for the vanilla app (no dep overrides needed)."""
    app = create_app()
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


class TestHealth:
    async def test_returns_ok_when_all_services_up(self):
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.execute = AsyncMock()

        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock()
        mock_redis.aclose = AsyncMock()

        with (
            patch("app.routers.health.AsyncSessionLocal", return_value=mock_session),
            patch("app.routers.health.aioredis.from_url", return_value=mock_redis),
        ):
            async with await _client() as client:
                resp = await client.get("/health")

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["db"] == "ok"
        assert body["redis"] == "ok"

    async def test_reports_db_error_when_db_unreachable(self):
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.execute = AsyncMock(side_effect=Exception("connection refused"))

        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock()
        mock_redis.aclose = AsyncMock()

        with (
            patch("app.routers.health.AsyncSessionLocal", return_value=mock_session),
            patch("app.routers.health.aioredis.from_url", return_value=mock_redis),
        ):
            async with await _client() as client:
                resp = await client.get("/health")

        assert resp.status_code == 200  # health always returns 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["db"] == "error"
        assert body["redis"] == "ok"

    async def test_reports_redis_error_when_redis_unreachable(self):
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.execute = AsyncMock()

        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(side_effect=Exception("redis down"))
        mock_redis.aclose = AsyncMock()

        with (
            patch("app.routers.health.AsyncSessionLocal", return_value=mock_session),
            patch("app.routers.health.aioredis.from_url", return_value=mock_redis),
        ):
            async with await _client() as client:
                resp = await client.get("/health")

        assert resp.status_code == 200
        body = resp.json()
        assert body["db"] == "ok"
        assert body["redis"] == "error"

    async def test_no_auth_required(self):
        """Health endpoint is public — no Authorization header needed."""
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.execute = AsyncMock()

        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock()
        mock_redis.aclose = AsyncMock()

        with (
            patch("app.routers.health.AsyncSessionLocal", return_value=mock_session),
            patch("app.routers.health.aioredis.from_url", return_value=mock_redis),
        ):
            async with await _client() as client:
                resp = await client.get("/health")

        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# CRM pipeline (quick smoke test — no DB, returns hardcoded mock data)
# ---------------------------------------------------------------------------


class TestCrmPipeline:
    async def test_returns_pipeline_records(self, authed_client):
        resp = await authed_client.get("/crm/pipeline")

        assert resp.status_code == 200
        body = resp.json()
        assert "records" in body
        assert len(body["records"]) > 0
        # Verify shape of first record
        first = body["records"][0]
        assert "company_name" in first
        assert "stage" in first
        assert "last_contacted" in first

    async def test_requires_auth(self, anon_client):
        resp = await anon_client.get("/crm/pipeline")
        assert resp.status_code == 403
