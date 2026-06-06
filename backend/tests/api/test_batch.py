"""API tests for /outreach/batch endpoints.

Uses authed_client (get_current_user + get_db mocked). ARQ pool and rate
limiter are patched inline per-test.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

from .conftest import (
    BATCH_ID,
    make_batch_job,
    make_outreach_job,
    make_profile,
    make_result,
)

OTHER_BATCH_ID = uuid.UUID("00000000-0000-0000-0000-000000000098")

VALID_CSV = b"company_name,contact_name\nAcme Corp,Jane Smith\nGlobex,John Doe\nInitech,\n"


def _mock_arq_pool():
    pool = AsyncMock()
    pool.enqueue_job = AsyncMock()
    return pool


def _csv_file(content: bytes, name: str = "prospects.csv"):
    return {"file": (name, content, "text/csv")}


# ---------------------------------------------------------------------------
# POST /outreach/batch
# ---------------------------------------------------------------------------


class TestCreateBatch:
    async def test_enqueues_batch_job(self, authed_client, mock_db):
        mock_db.execute.return_value = make_result(scalar=make_profile())
        pool = _mock_arq_pool()

        with (
            patch("app.routers.outreach.get_arq_pool", return_value=pool),
            patch("app.routers.outreach.check_rate_limit", return_value=(True, 0)),
        ):
            resp = await authed_client.post("/outreach/batch", files=_csv_file(VALID_CSV))

        assert resp.status_code == 202
        body = resp.json()
        assert body["total"] == 3
        assert "batch_id" in body
        pool.enqueue_job.assert_awaited_once()
        assert pool.enqueue_job.call_args.args[0] == "run_batch_job"
        # 3 child OutreachJob rows + 1 BatchJob added
        assert mock_db.add.call_count == 4

    async def test_rejects_more_than_20_rows(self, authed_client, mock_db):
        rows = b"company_name\n" + b"\n".join(f"Company {i}".encode() for i in range(21))
        mock_db.execute.return_value = make_result(scalar=make_profile())
        pool = _mock_arq_pool()

        with (
            patch("app.routers.outreach.get_arq_pool", return_value=pool),
            patch("app.routers.outreach.check_rate_limit", return_value=(True, 0)),
        ):
            resp = await authed_client.post("/outreach/batch", files=_csv_file(rows))

        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "INVALID_CSV"
        pool.enqueue_job.assert_not_awaited()

    async def test_rejects_missing_company_column(self, authed_client):
        bad = b"name,email\nAcme,foo@bar.com\n"
        resp = await authed_client.post("/outreach/batch", files=_csv_file(bad))
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "INVALID_CSV"

    async def test_rejects_empty_csv(self, authed_client):
        resp = await authed_client.post(
            "/outreach/batch", files=_csv_file(b"company_name,contact_name\n")
        )
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "INVALID_CSV"

    async def test_rejects_invalid_company_name_row(self, authed_client):
        # "Acme & Corp!" violates the GenerateRequest charset pattern.
        bad = b"company_name\nAcme & Corp!\n"
        resp = await authed_client.post("/outreach/batch", files=_csv_file(bad))
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "INVALID_CSV"

    async def test_rate_limited(self, authed_client):
        pool = _mock_arq_pool()
        with (
            patch("app.routers.outreach.get_arq_pool", return_value=pool),
            patch("app.routers.outreach.check_rate_limit", return_value=(False, 1800)),
        ):
            resp = await authed_client.post("/outreach/batch", files=_csv_file(VALID_CSV))

        assert resp.status_code == 429
        assert resp.json()["detail"]["code"] == "RATE_LIMIT_EXCEEDED"
        pool.enqueue_job.assert_not_awaited()

    async def test_requires_auth(self, anon_client):
        resp = await anon_client.post("/outreach/batch", files=_csv_file(VALID_CSV))
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /outreach/batch/{batch_id}
# ---------------------------------------------------------------------------


class TestGetBatchStatus:
    async def test_returns_aggregate_and_prospects(self, authed_client, mock_db):
        batch = make_batch_job(status="running", total=2, research_done=2, personalize_done=1)
        jobs = [
            make_outreach_job(job_id=uuid.uuid4(), company_name="Acme Corp", status="done"),
            make_outreach_job(
                job_id=uuid.uuid4(),
                company_name="Globex",
                status="running",
                current_step="personalizing",
            ),
        ]
        mock_db.execute.side_effect = [
            make_result(scalar=batch),
            make_result(scalars_all=jobs),
        ]

        resp = await authed_client.get(f"/outreach/batch/{BATCH_ID}")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        assert body["research_done"] == 2
        assert body["personalize_done"] == 1
        assert len(body["prospects"]) == 2
        assert body["prospects"][0]["company_name"] == "Acme Corp"
        assert "job_id" in body["prospects"][0]

    async def test_returns_404_for_unknown_batch(self, authed_client, mock_db):
        mock_db.execute.return_value = make_result(scalar=None)

        resp = await authed_client.get(f"/outreach/batch/{OTHER_BATCH_ID}")

        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "BATCH_NOT_FOUND"

    async def test_requires_auth(self, anon_client):
        resp = await anon_client.get(f"/outreach/batch/{BATCH_ID}")
        assert resp.status_code == 403
