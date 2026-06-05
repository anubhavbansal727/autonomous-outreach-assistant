"""API tests for /outreach endpoints.

Uses authed_client (get_current_user + get_db mocked).
ARQ pool and Resend service are patched inline per-test.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from .conftest import (
    CREATED_AT,
    JOB_ID,
    PROFILE_ID,
    USER_ID,
    make_outreach_job,
    make_profile,
    make_result,
)

# A second job UUID used in "not found" tests to avoid collision with JOB_ID
OTHER_JOB_ID = uuid.UUID("00000000-0000-0000-0000-000000000099")


def _mock_arq_pool():
    pool = AsyncMock()
    pool.enqueue_job = AsyncMock()
    return pool


# ---------------------------------------------------------------------------
# POST /outreach/generate
# ---------------------------------------------------------------------------


class TestGenerate:
    async def test_enqueues_outreach_job(self, authed_client, mock_db):
        profile = make_profile()
        mock_db.execute.return_value = make_result(scalar=profile)
        pool = _mock_arq_pool()

        with (
            patch("app.routers.outreach.get_arq_pool", return_value=pool),
            patch(
                "app.routers.outreach.check_rate_limit",
                return_value=(True, 0),
            ),
        ):
            resp = await authed_client.post(
                "/outreach/generate",
                json={"company_name": "Acme Corp", "contact_name": "Jane Doe"},
            )

        assert resp.status_code == 202
        body = resp.json()
        assert "job_id" in body
        pool.enqueue_job.assert_awaited_once()
        assert pool.enqueue_job.call_args.args[0] == "run_outreach_job"

    async def test_returns_400_when_no_active_profile(self, authed_client, mock_db):
        mock_db.execute.return_value = make_result(scalar=None)
        pool = _mock_arq_pool()

        with (
            patch("app.routers.outreach.get_arq_pool", return_value=pool),
            patch(
                "app.routers.outreach.check_rate_limit",
                return_value=(True, 0),
            ),
        ):
            resp = await authed_client.post(
                "/outreach/generate",
                json={"company_name": "Acme Corp"},
            )

        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "NO_ACTIVE_PROFILE"

    async def test_rejects_invalid_company_name(self, authed_client):
        # company_name pattern: ^[a-zA-Z0-9 \-]+$
        resp = await authed_client.post(
            "/outreach/generate",
            json={"company_name": "Acme & Corp!"},
        )
        assert resp.status_code == 422

    async def test_requires_auth(self, anon_client):
        resp = await anon_client.post(
            "/outreach/generate",
            json={"company_name": "Acme Corp"},
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /outreach/status/{job_id}
# ---------------------------------------------------------------------------


class TestGetStatus:
    async def test_returns_status_for_running_job(self, authed_client, mock_db):
        job = make_outreach_job(status="running", current_step="researching")
        mock_db.execute.return_value = make_result(scalar=job)

        resp = await authed_client.get(f"/outreach/status/{JOB_ID}")

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "running"
        assert body["current_step"] == "researching"
        assert body["job_id"] == str(JOB_ID)

    async def test_returns_404_for_unknown_job(self, authed_client, mock_db):
        mock_db.execute.return_value = make_result(scalar=None)

        resp = await authed_client.get(f"/outreach/status/{OTHER_JOB_ID}")

        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "JOB_NOT_FOUND"

    async def test_requires_auth(self, anon_client):
        resp = await anon_client.get(f"/outreach/status/{JOB_ID}")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /outreach/result/{job_id}
# ---------------------------------------------------------------------------


class TestGetResult:
    async def test_returns_result_for_done_job(self, authed_client, mock_db):
        job = make_outreach_job(
            status="done",
            email_subject="Subject line",
            email_draft="Dear Jane...",
            linkedin_draft="Hi Jane on LI",
        )
        mock_db.execute.return_value = make_result(scalar=job)

        resp = await authed_client.get(f"/outreach/result/{JOB_ID}")

        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == str(JOB_ID)
        assert body["email_subject"] == "Subject line"
        assert body["email_draft"] == "Dear Jane..."
        assert body["linkedin_draft"] == "Hi Jane on LI"
        assert body["status"] == "done"

    async def test_returns_409_for_running_job(self, authed_client, mock_db):
        job = make_outreach_job(status="running")
        mock_db.execute.return_value = make_result(scalar=job)

        resp = await authed_client.get(f"/outreach/result/{JOB_ID}")

        assert resp.status_code == 409
        assert resp.json()["detail"]["code"] == "JOB_RUNNING"

    async def test_returns_404_for_unknown_job(self, authed_client, mock_db):
        mock_db.execute.return_value = make_result(scalar=None)

        resp = await authed_client.get(f"/outreach/result/{OTHER_JOB_ID}")

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PUT /outreach/result/{job_id}  (edit draft)
# ---------------------------------------------------------------------------


class TestEditDraft:
    async def test_edits_draft_fields(self, authed_client, mock_db):
        job = make_outreach_job(send_status="draft")
        mock_db.execute.return_value = make_result(scalar=job)

        resp = await authed_client.put(
            f"/outreach/result/{JOB_ID}",
            json={
                "email_subject": "New subject",
                "email_draft": "New body",
                "linkedin_draft": "New LI note",
            },
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["updated"] is True
        assert "updated_at" in body
        mock_db.commit.assert_awaited_once()

    async def test_rejects_edit_after_send(self, authed_client, mock_db):
        job = make_outreach_job(send_status="sent")
        mock_db.execute.return_value = make_result(scalar=job)

        resp = await authed_client.put(
            f"/outreach/result/{JOB_ID}",
            json={"email_subject": "Updated"},
        )

        assert resp.status_code == 409
        assert resp.json()["detail"]["code"] == "ALREADY_SENT"

    async def test_returns_404_for_unknown_job(self, authed_client, mock_db):
        mock_db.execute.return_value = make_result(scalar=None)

        resp = await authed_client.put(
            f"/outreach/result/{OTHER_JOB_ID}",
            json={"email_subject": "Updated"},
        )

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /outreach/send/{job_id}
# ---------------------------------------------------------------------------


class TestSend:
    async def test_sends_email_successfully(self, authed_client, mock_db, fake_user):
        job = make_outreach_job(send_status="draft")
        profile = make_profile()
        # Two execute calls: get job, then get profile
        mock_db.execute.side_effect = [
            make_result(scalar=job),
            make_result(scalar=profile),
        ]

        with patch(
            "app.routers.outreach.send_email",
            return_value="resend-msg-id-123",
        ):
            resp = await authed_client.post(
                f"/outreach/send/{JOB_ID}",
                json={"to_email": "recipient@example.com"},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["sent"] is True
        assert body["resend_message_id"] == "resend-msg-id-123"
        mock_db.commit.assert_awaited_once()

    async def test_returns_409_if_already_sent(self, authed_client, mock_db):
        job = make_outreach_job(send_status="sent")
        mock_db.execute.return_value = make_result(scalar=job)

        resp = await authed_client.post(
            f"/outreach/send/{JOB_ID}",
            json={"to_email": "recipient@example.com"},
        )

        assert resp.status_code == 409
        assert resp.json()["detail"]["code"] == "ALREADY_SENT"

    async def test_returns_502_on_resend_failure(self, authed_client, mock_db):
        job = make_outreach_job(send_status="draft")
        profile = make_profile()
        mock_db.execute.side_effect = [
            make_result(scalar=job),
            make_result(scalar=profile),
        ]

        with patch(
            "app.routers.outreach.send_email",
            side_effect=Exception("Resend API error"),
        ):
            resp = await authed_client.post(
                f"/outreach/send/{JOB_ID}",
                json={"to_email": "recipient@example.com"},
            )

        assert resp.status_code == 502
        assert resp.json()["detail"]["code"] == "SEND_FAILED"

    async def test_rejects_invalid_email(self, authed_client):
        resp = await authed_client.post(
            f"/outreach/send/{JOB_ID}",
            json={"to_email": "not-an-email"},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /outreach/retry/{job_id}
# ---------------------------------------------------------------------------


class TestRetry:
    async def test_retries_failed_job(self, authed_client, mock_db):
        job = make_outreach_job(status="failed", retry_count=0)
        profile = make_profile()
        mock_db.execute.side_effect = [
            make_result(scalar=job),
            make_result(scalar=profile),
        ]
        pool = _mock_arq_pool()

        with (
            patch("app.routers.outreach.get_arq_pool", return_value=pool),
            patch(
                "app.routers.outreach.check_rate_limit",
                return_value=(True, 0),
            ),
        ):
            resp = await authed_client.post(f"/outreach/retry/{JOB_ID}")

        assert resp.status_code == 202
        body = resp.json()
        assert body["job_id"] == str(JOB_ID)
        pool.enqueue_job.assert_awaited_once()

    async def test_returns_409_when_job_is_not_failed(self, authed_client, mock_db):
        job = make_outreach_job(status="running")
        mock_db.execute.return_value = make_result(scalar=job)

        pool = _mock_arq_pool()
        with patch("app.routers.outreach.get_arq_pool", return_value=pool):
            resp = await authed_client.post(f"/outreach/retry/{JOB_ID}")

        assert resp.status_code == 409
        assert resp.json()["detail"]["code"] == "NOT_FAILED"


# ---------------------------------------------------------------------------
# GET /outreach/history
# ---------------------------------------------------------------------------


class TestHistory:
    async def test_returns_paginated_history(self, authed_client, mock_db):
        jobs = [make_outreach_job(job_id=uuid.uuid4()) for _ in range(3)]
        # history endpoint calls execute twice: COUNT then SELECT
        mock_db.execute.side_effect = [
            make_result(scalar_one=3),           # total count
            make_result(scalars_all=jobs),        # paginated rows
        ]

        resp = await authed_client.get("/outreach/history")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 3
        assert body["page"] == 1
        assert body["per_page"] == 20
        assert len(body["items"]) == 3

    async def test_respects_pagination_params(self, authed_client, mock_db):
        mock_db.execute.side_effect = [
            make_result(scalar_one=50),
            make_result(scalars_all=[]),
        ]

        resp = await authed_client.get("/outreach/history?page=3&per_page=10")

        assert resp.status_code == 200
        body = resp.json()
        assert body["page"] == 3
        assert body["per_page"] == 10

    async def test_empty_history(self, authed_client, mock_db):
        mock_db.execute.side_effect = [
            make_result(scalar_one=0),
            make_result(scalars_all=[]),
        ]

        resp = await authed_client.get("/outreach/history")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 0
        assert body["items"] == []

    async def test_requires_auth(self, anon_client):
        resp = await anon_client.get("/outreach/history")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# DELETE /outreach/{job_id}
# ---------------------------------------------------------------------------


class TestDeleteJob:
    async def test_deletes_job_returns_200(self, authed_client, mock_db):
        job = make_outreach_job()
        mock_db.execute.return_value = make_result(scalar=job)

        resp = await authed_client.delete(f"/outreach/{JOB_ID}")

        assert resp.status_code == 200
        assert resp.json() == {"deleted": True}
        mock_db.delete.assert_awaited_once_with(job)
        mock_db.commit.assert_awaited_once()

    async def test_returns_404_for_unknown_job(self, authed_client, mock_db):
        mock_db.execute.return_value = make_result(scalar=None)

        resp = await authed_client.delete(f"/outreach/{OTHER_JOB_ID}")

        assert resp.status_code == 404

    async def test_requires_auth(self, anon_client):
        resp = await anon_client.delete(f"/outreach/{JOB_ID}")
        assert resp.status_code == 403
