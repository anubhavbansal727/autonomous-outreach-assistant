"""API tests for /tenant and /audit."""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock

from .conftest import CREATED_AT, TENANT_ID, USER_ID, make_result, make_tenant


def _audit_row(action="member.created"):
    a = MagicMock()
    a.id = uuid.uuid4()
    a.action = action
    a.target = str(USER_ID)
    a.actor_user_id = USER_ID
    a.meta = {"role": "member"}
    a.created_at = CREATED_AT
    return a


# ---------------------------------------------------------------------------
# GET/PATCH /tenant
# ---------------------------------------------------------------------------


class TestGetTenant:
    async def test_any_member_reads_tenant(self, authed_client, fake_user, mock_db):
        fake_user.role = "viewer"
        mock_db.execute.return_value = make_result(scalar=make_tenant(name="Acme"))
        resp = await authed_client.get("/tenant")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Acme"
        assert resp.json()["id"] == str(TENANT_ID)


class TestUpdateTenant:
    async def test_owner_updates_name_and_domain(self, authed_client, mock_db):
        mock_db.execute.return_value = make_result(scalar=make_tenant(name="Old"))
        resp = await authed_client.patch(
            "/tenant", json={"name": "NewCo", "resend_domain": "newco.com"}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "NewCo"
        assert body["resend_domain"] == "newco.com"

    async def test_admin_cannot_manage_tenant(self, authed_client, fake_user):
        fake_user.role = "admin"  # tenant.manage is owner-only
        resp = await authed_client.patch("/tenant", json={"name": "NewCo"})
        assert resp.status_code == 403
        assert resp.json()["detail"]["code"] == "PERMISSION_DENIED"


# ---------------------------------------------------------------------------
# GET /audit
# ---------------------------------------------------------------------------


class TestAuditLog:
    async def test_admin_reads_audit_log(self, authed_client, fake_user, mock_db):
        fake_user.role = "admin"
        mock_db.execute.return_value = make_result(
            scalars_all=[_audit_row(), _audit_row("tenant.updated")]
        )
        resp = await authed_client.get("/audit")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 2
        assert items[0]["action"] == "member.created"
        assert items[0]["meta"] == {"role": "member"}

    async def test_member_cannot_read_audit_log(self, authed_client, fake_user):
        fake_user.role = "member"
        resp = await authed_client.get("/audit")
        assert resp.status_code == 403
        assert resp.json()["detail"]["code"] == "PERMISSION_DENIED"
