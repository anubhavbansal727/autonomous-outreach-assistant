"""API tests for GET /health.

The health endpoint is a simple liveness probe — no DB or Redis checks.
"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app


async def _client():
    """Return a fresh client for the vanilla app (no dep overrides needed)."""
    app = create_app()
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


class TestHealth:
    async def test_returns_ok(self):
        async with await _client() as client:
            resp = await client.get("/health")

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["db"] == "ok"
        assert body["redis"] == "ok"

    async def test_no_auth_required(self):
        """Health endpoint is public — no Authorization header needed."""
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
