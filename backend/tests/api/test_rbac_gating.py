"""Phase 4 — permission gating on the profile and outreach routers.

The authed user defaults to OWNER (conftest), so these tests mutate
fake_user.role to exercise denial paths. require_permission runs before the
endpoint body, so most denials need no DB mocking.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from .conftest import make_result

PROFILE_EDIT_ENDPOINTS = [
    ("post", "/profile/ingest", {"url": "https://example.com"}),
    ("post", "/profile/save", {"product_name": "X"}),
    ("put", "/profile/update", {"product_name": "X"}),
]

# save/update touch only the mocked DB; ingest needs the arq pool, so it's
# tested separately (see test_admin_ingest_passes_gate).
PROFILE_EDIT_NO_REDIS = [e for e in PROFILE_EDIT_ENDPOINTS if e[1] != "/profile/ingest"]


class TestProfileGating:
    async def test_viewer_can_read_profile(self, authed_client, fake_user, mock_db):
        fake_user.role = "viewer"  # profile.view granted to all roles
        mock_db.execute.return_value = make_result(scalar=None)
        resp = await authed_client.get("/profile")
        # 404 (no profile) — NOT 403; the read permission is allowed.
        assert resp.status_code == 404

    @pytest.mark.parametrize("method,path,body", PROFILE_EDIT_ENDPOINTS)
    async def test_member_cannot_edit_profile(
        self, authed_client, fake_user, method, path, body
    ):
        fake_user.role = "member"  # lacks profile.edit
        resp = await getattr(authed_client, method)(path, json=body)
        assert resp.status_code == 403
        assert resp.json()["detail"]["code"] == "PERMISSION_DENIED"
        assert resp.json()["detail"]["required_permission"] == "profile.edit"

    @pytest.mark.parametrize("method,path,body", PROFILE_EDIT_NO_REDIS)
    async def test_admin_can_edit_profile(
        self, authed_client, fake_user, mock_db, method, path, body
    ):
        fake_user.role = "admin"  # admins have profile.edit
        # Not a 403 — gate passes (downstream may 4xx for other reasons).
        resp = await getattr(authed_client, method)(path, json=body)
        assert resp.status_code != 403

    async def test_admin_ingest_passes_gate(self, authed_client, fake_user, mock_db):
        fake_user.role = "admin"
        mock_pool = AsyncMock()
        mock_pool.enqueue_job = AsyncMock()
        with (
            patch("app.routers.profile.get_arq_pool", return_value=mock_pool),
            patch(
                "app.routers.profile.check_rate_limit",
                AsyncMock(return_value=(True, 0)),
            ),
        ):
            resp = await authed_client.post(
                "/profile/ingest", json={"url": "https://example.com"}
            )
        assert resp.status_code == 202


class TestOutreachGating:
    async def test_viewer_cannot_generate(self, authed_client, fake_user):
        fake_user.role = "viewer"
        resp = await authed_client.post(
            "/outreach/generate", json={"company_name": "Acme"}
        )
        assert resp.status_code == 403
        assert resp.json()["detail"]["required_permission"] == "outreach.create"

    async def test_viewer_cannot_send(self, authed_client, fake_user):
        fake_user.role = "viewer"
        resp = await authed_client.post(
            "/outreach/send/00000000-0000-0000-0000-000000000003",
            json={"to_email": "x@example.com"},
        )
        assert resp.status_code == 403
        assert resp.json()["detail"]["required_permission"] == "outreach.send"

    async def test_member_can_view_own_history(self, authed_client, fake_user, mock_db):
        fake_user.role = "member"
        mock_db.execute.side_effect = [
            make_result(scalar_one=0),   # count
            make_result(scalars_all=[]), # items
        ]
        resp = await authed_client.get("/outreach/history")
        assert resp.status_code == 200


class TestHistoryScope:
    async def test_member_cannot_request_scope_all(self, authed_client, fake_user):
        fake_user.role = "member"  # lacks outreach.view.all
        resp = await authed_client.get("/outreach/history?scope=all")
        assert resp.status_code == 403
        assert resp.json()["detail"]["required_permission"] == "outreach.view.all"

    async def test_admin_can_request_scope_all(self, authed_client, fake_user, mock_db):
        fake_user.role = "admin"  # has outreach.view.all
        mock_db.execute.side_effect = [
            make_result(scalar_one=0),
            make_result(scalars_all=[]),
        ]
        resp = await authed_client.get("/outreach/history?scope=all")
        assert resp.status_code == 200

    async def test_invalid_scope_422(self, authed_client):
        resp = await authed_client.get("/outreach/history?scope=everything")
        assert resp.status_code == 422
