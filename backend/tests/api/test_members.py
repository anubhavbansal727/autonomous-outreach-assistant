"""API tests for /members (RBAC team management).

Uses authed_client (get_current_user + get_db overridden). The authenticated
user is an OWNER by default (see conftest fake_user); tests that exercise
permission denial or admin-vs-owner rules mutate fake_user.role first.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from .conftest import CREATED_AT, TENANT_ID, USER_ID, make_result

OTHER_USER_ID = uuid.UUID("00000000-0000-0000-0000-0000000000aa")
MEMBER_ID = uuid.UUID("00000000-0000-0000-0000-0000000000bb")


def _membership(role="member", status="active", user_id=OTHER_USER_ID, mid=MEMBER_ID):
    m = MagicMock()
    m.id = mid
    m.user_id = user_id
    m.role = role
    m.status = status
    m.created_at = CREATED_AT
    return m


def _user_row(user_id=OTHER_USER_ID, email="colleague@example.com"):
    u = MagicMock()
    u.id = user_id
    u.email = email
    return u


# ---------------------------------------------------------------------------
# GET /members
# ---------------------------------------------------------------------------


class TestListMembers:
    async def test_lists_roster(self, authed_client, mock_db):
        mock_db.execute.side_effect = [
            make_result(scalars_all=[_membership(role="owner", user_id=USER_ID)]),
            make_result(scalars_all=[_user_row(USER_ID, "owner@example.com")]),
        ]
        resp = await authed_client.get("/members")
        assert resp.status_code == 200
        members = resp.json()["members"]
        assert len(members) == 1
        assert members[0]["role"] == "owner"
        assert members[0]["email"] == "owner@example.com"

    async def test_viewer_can_list(self, authed_client, fake_user, mock_db):
        fake_user.role = "viewer"  # members.view is granted to everyone
        mock_db.execute.side_effect = [
            make_result(scalars_all=[]),
            make_result(scalars_all=[]),
        ]
        resp = await authed_client.get("/members")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# POST /members
# ---------------------------------------------------------------------------


class TestCreateMember:
    async def test_owner_creates_member_returns_temp_password(self, authed_client, mock_db):
        mock_db.execute.return_value = make_result(scalar=None)  # email free
        with patch("app.routers.members.bcrypt") as mock_bcrypt:
            mock_bcrypt.hashpw.return_value = b"hashed"
            mock_bcrypt.gensalt.return_value = b"salt"
            resp = await authed_client.post(
                "/members", json={"email": "new@example.com", "role": "member"}
            )
        assert resp.status_code == 201
        body = resp.json()
        assert body["email"] == "new@example.com"
        assert body["role"] == "member"
        assert body["temporary_password"]  # present and non-empty

    async def test_duplicate_email_409(self, authed_client, mock_db):
        mock_db.execute.return_value = make_result(scalar=_user_row())
        resp = await authed_client.post(
            "/members", json={"email": "taken@example.com", "role": "member"}
        )
        assert resp.status_code == 409
        assert resp.json()["detail"]["code"] == "EMAIL_EXISTS"

    async def test_cannot_create_owner_role_422(self, authed_client):
        resp = await authed_client.post(
            "/members", json={"email": "x@example.com", "role": "owner"}
        )
        assert resp.status_code == 422  # 'owner' not in AssignableRole

    async def test_member_role_forbidden(self, authed_client, fake_user):
        fake_user.role = "member"  # lacks members.manage
        resp = await authed_client.post(
            "/members", json={"email": "x@example.com", "role": "member"}
        )
        assert resp.status_code == 403
        assert resp.json()["detail"]["code"] == "PERMISSION_DENIED"


# ---------------------------------------------------------------------------
# PATCH /members/{id}
# ---------------------------------------------------------------------------


class TestUpdateMember:
    async def test_owner_changes_role(self, authed_client, mock_db):
        mock_db.execute.side_effect = [
            make_result(scalar=_membership(role="member")),  # target
            make_result(scalar=_user_row()),                 # user for response
        ]
        resp = await authed_client.patch(
            f"/members/{MEMBER_ID}", json={"role": "admin"}
        )
        assert resp.status_code == 200
        assert resp.json()["role"] == "admin"

    async def test_no_changes_400(self, authed_client):
        resp = await authed_client.patch(f"/members/{MEMBER_ID}", json={})
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "NO_CHANGES"

    async def test_cannot_modify_self(self, authed_client, mock_db):
        mock_db.execute.side_effect = [
            make_result(scalar=_membership(role="owner", user_id=USER_ID)),
        ]
        resp = await authed_client.patch(
            f"/members/{MEMBER_ID}", json={"role": "admin"}
        )
        assert resp.status_code == 403
        assert resp.json()["detail"]["code"] == "CANNOT_MODIFY_SELF"

    async def test_admin_cannot_modify_owner(self, authed_client, fake_user, mock_db):
        fake_user.role = "admin"
        mock_db.execute.side_effect = [
            make_result(scalar=_membership(role="owner")),
        ]
        resp = await authed_client.patch(
            f"/members/{MEMBER_ID}", json={"status": "suspended"}
        )
        assert resp.status_code == 403
        assert resp.json()["detail"]["code"] == "ADMIN_CANNOT_MODIFY_OWNER"

    async def test_last_owner_cannot_be_demoted(self, authed_client, mock_db):
        mock_db.execute.side_effect = [
            make_result(scalar=_membership(role="owner")),  # target is an owner
            make_result(scalar_one=1),                      # only 1 active owner
        ]
        resp = await authed_client.patch(
            f"/members/{MEMBER_ID}", json={"role": "admin"}
        )
        assert resp.status_code == 403
        assert resp.json()["detail"]["code"] == "LAST_OWNER"


# ---------------------------------------------------------------------------
# DELETE /members/{id}
# ---------------------------------------------------------------------------


class TestRemoveMember:
    async def test_owner_removes_member(self, authed_client, mock_db):
        mock_db.execute.side_effect = [
            make_result(scalar=_membership(role="member")),
            make_result(scalar=_user_row()),
        ]
        resp = await authed_client.delete(f"/members/{MEMBER_ID}")
        assert resp.status_code == 200
        assert resp.json()["removed"] is True
        mock_db.delete.assert_awaited_once()

    async def test_member_not_found_404(self, authed_client, mock_db):
        mock_db.execute.return_value = make_result(scalar=None)
        resp = await authed_client.delete(f"/members/{MEMBER_ID}")
        assert resp.status_code == 404

    async def test_member_role_forbidden(self, authed_client, fake_user):
        fake_user.role = "viewer"
        resp = await authed_client.delete(f"/members/{MEMBER_ID}")
        assert resp.status_code == 403
        assert resp.json()["detail"]["code"] == "PERMISSION_DENIED"
