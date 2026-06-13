"""API tests for /auth endpoints.

Tests in this module use anon_client (get_db mocked, get_current_user real)
for register/login/refresh/logout, and authed_client for me/patch_me where
authentication is required.

bcrypt is patched at the router level (app.routers.auth.bcrypt) to avoid
depending on the system bcrypt installation in this test environment.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.auth.dependencies import create_refresh_token

from .conftest import CREATED_AT, TENANT_ID, USER_ID, make_result


def _db_user(
    user_id=None,
    email="test@example.com",
    must_change_password=False,
):
    """Build a MagicMock representing a User row fetched from the DB."""
    u = MagicMock()
    u.id = user_id or USER_ID
    u.email = email
    u.password_hash = "fake_bcrypt_hash"  # bcrypt.checkpw is always patched
    u.must_change_password = must_change_password
    u.created_at = CREATED_AT
    return u


def _db_membership(role="owner", status="active"):
    """Build a MagicMock representing the user's Membership row."""
    m = MagicMock()
    m.tenant_id = TENANT_ID
    m.user_id = USER_ID
    m.role = role
    m.status = status
    return m


def _login_results(user, membership=None):
    """Execute side-effects for a login/refresh: user lookup, GUC bind, membership."""
    return [
        make_result(scalar=user),         # user lookup by email / id
        make_result(),                    # bind_tenant_context(user_id) — ignored
        make_result(scalar=membership),   # membership lookup
    ]


# ---------------------------------------------------------------------------
# POST /auth/register
# ---------------------------------------------------------------------------


class TestRegister:
    async def test_register_new_user_returns_201(self, anon_client, mock_db):
        mock_db.execute.return_value = make_result(scalar=None)  # email not taken

        with patch("app.routers.auth.bcrypt") as mock_bcrypt:
            mock_bcrypt.hashpw.return_value = b"fake_hash"
            mock_bcrypt.gensalt.return_value = b"fake_salt"

            resp = await anon_client.post(
                "/auth/register",
                json={"email": "new@example.com", "password": "securepassword"},
            )

        assert resp.status_code == 201
        body = resp.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"
        assert "user_id" in body

    async def test_register_sets_refresh_cookie(self, anon_client, mock_db):
        mock_db.execute.return_value = make_result(scalar=None)

        with patch("app.routers.auth.bcrypt") as mock_bcrypt:
            mock_bcrypt.hashpw.return_value = b"fake_hash"
            mock_bcrypt.gensalt.return_value = b"fake_salt"

            resp = await anon_client.post(
                "/auth/register",
                json={"email": "new@example.com", "password": "securepassword"},
            )

        assert resp.status_code == 201
        assert "refresh_token" in resp.cookies

    async def test_register_duplicate_email_returns_409(self, anon_client, mock_db):
        # Email uniqueness check finds an existing user
        mock_db.execute.return_value = make_result(scalar=_db_user())

        with patch("app.routers.auth.bcrypt"):
            resp = await anon_client.post(
                "/auth/register",
                json={"email": "taken@example.com", "password": "securepassword"},
            )

        assert resp.status_code == 409
        assert resp.json()["detail"]["code"] == "EMAIL_EXISTS"

    async def test_register_short_password_returns_422(self, anon_client):
        resp = await anon_client.post(
            "/auth/register",
            json={"email": "new@example.com", "password": "short"},
        )
        assert resp.status_code == 422

    async def test_register_invalid_email_returns_422(self, anon_client):
        resp = await anon_client.post(
            "/auth/register",
            json={"email": "not-an-email", "password": "securepassword"},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /auth/login
# ---------------------------------------------------------------------------


class TestLogin:
    async def test_login_valid_credentials_returns_200(self, anon_client, mock_db):
        mock_db.execute.side_effect = _login_results(_db_user(), _db_membership())

        with patch("app.routers.auth.bcrypt") as mock_bcrypt:
            mock_bcrypt.checkpw.return_value = True  # password matches

            resp = await anon_client.post(
                "/auth/login",
                json={"email": "test@example.com", "password": "correctpassword"},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"
        assert body["role"] == "owner"
        assert body["tenant_id"] == str(TENANT_ID)
        assert body["must_change_password"] is False

    async def test_login_surfaces_must_change_password(self, anon_client, mock_db):
        mock_db.execute.side_effect = _login_results(
            _db_user(must_change_password=True), _db_membership(role="member")
        )

        with patch("app.routers.auth.bcrypt") as mock_bcrypt:
            mock_bcrypt.checkpw.return_value = True

            resp = await anon_client.post(
                "/auth/login",
                json={"email": "test@example.com", "password": "temp"},
            )

        assert resp.status_code == 200
        assert resp.json()["must_change_password"] is True
        assert resp.json()["role"] == "member"

    async def test_login_sets_refresh_cookie(self, anon_client, mock_db):
        mock_db.execute.side_effect = _login_results(_db_user(), _db_membership())

        with patch("app.routers.auth.bcrypt") as mock_bcrypt:
            mock_bcrypt.checkpw.return_value = True

            resp = await anon_client.post(
                "/auth/login",
                json={"email": "test@example.com", "password": "correctpassword"},
            )

        assert "refresh_token" in resp.cookies

    async def test_login_wrong_password_returns_401(self, anon_client, mock_db):
        mock_db.execute.return_value = make_result(scalar=_db_user())

        with patch("app.routers.auth.bcrypt") as mock_bcrypt:
            mock_bcrypt.checkpw.return_value = False  # password mismatch

            resp = await anon_client.post(
                "/auth/login",
                json={"email": "test@example.com", "password": "wrongpassword"},
            )

        assert resp.status_code == 401
        assert resp.json()["detail"]["code"] == "INVALID_CREDENTIALS"

    async def test_login_unknown_email_returns_401(self, anon_client, mock_db):
        # User not found in DB → scalar_one_or_none returns None
        mock_db.execute.return_value = make_result(scalar=None)

        with patch("app.routers.auth.bcrypt") as mock_bcrypt:
            mock_bcrypt.checkpw.return_value = False

            resp = await anon_client.post(
                "/auth/login",
                json={"email": "ghost@example.com", "password": "anypassword"},
            )

        assert resp.status_code == 401
        assert resp.json()["detail"]["code"] == "INVALID_CREDENTIALS"


# ---------------------------------------------------------------------------
# POST /auth/refresh
# ---------------------------------------------------------------------------


class TestRefresh:
    async def test_refresh_with_valid_cookie_returns_200(self, anon_client, mock_db):
        refresh_token = create_refresh_token(str(USER_ID))
        mock_db.execute.side_effect = _login_results(_db_user(), _db_membership())

        resp = await anon_client.post(
            "/auth/refresh",
            cookies={"refresh_token": refresh_token},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"

    async def test_refresh_without_cookie_returns_401(self, anon_client):
        resp = await anon_client.post("/auth/refresh")

        assert resp.status_code == 401
        assert resp.json()["detail"]["code"] == "MISSING_REFRESH_TOKEN"

    async def test_refresh_with_garbage_token_returns_401(self, anon_client):
        resp = await anon_client.post(
            "/auth/refresh",
            cookies={"refresh_token": "not.a.valid.jwt"},
        )

        assert resp.status_code == 401
        assert resp.json()["detail"]["code"] == "INVALID_REFRESH_TOKEN"


# ---------------------------------------------------------------------------
# POST /auth/logout
# ---------------------------------------------------------------------------


class TestLogout:
    async def test_logout_returns_200(self, anon_client):
        resp = await anon_client.post("/auth/logout")

        assert resp.status_code == 200
        assert resp.json() == {"logged_out": True}


# ---------------------------------------------------------------------------
# GET /auth/me
# ---------------------------------------------------------------------------


class TestMe:
    async def test_me_returns_user_info(self, authed_client, fake_user):
        resp = await authed_client.get("/auth/me")

        assert resp.status_code == 200
        body = resp.json()
        assert body["email"] == fake_user.email
        assert body["user_id"] == str(fake_user.id)
        assert body["resend_domain"] is None

    async def test_me_returns_role_and_permissions(self, authed_client, fake_user):
        # fake_user is an owner (see conftest) → full permission set.
        resp = await authed_client.get("/auth/me")

        assert resp.status_code == 200
        body = resp.json()
        assert body["role"] == "owner"
        assert "tenant.manage" in body["permissions"]
        assert "outreach.send" in body["permissions"]
        assert body["tenant"]["id"] == str(fake_user.tenant.id)
        assert body["must_change_password"] is False

    async def test_me_without_auth_returns_403(self, anon_client):
        # No Authorization header → HTTPBearer returns 403
        resp = await anon_client.get("/auth/me")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# PATCH /auth/me
# ---------------------------------------------------------------------------


class TestUpdateMe:
    async def test_patch_me_sets_resend_domain(self, authed_client, fake_tenant, mock_db):
        # resend_domain lives on the tenant (shared sending config) in v3.
        resp = await authed_client.patch(
            "/auth/me",
            json={"resend_domain": "mycompany.com"},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["resend_domain"] == "mycompany.com"
        assert fake_tenant.resend_domain == "mycompany.com"
        mock_db.commit.assert_awaited_once()

    async def test_patch_me_clears_resend_domain(self, authed_client, fake_tenant, mock_db):
        # Empty string → router sets the tenant's resend_domain = None
        fake_tenant.resend_domain = "old.com"

        resp = await authed_client.patch(
            "/auth/me",
            json={"resend_domain": ""},
        )

        assert resp.status_code == 200
        assert resp.json()["resend_domain"] is None
        assert fake_tenant.resend_domain is None

    async def test_patch_me_without_auth_returns_403(self, anon_client):
        resp = await anon_client.patch("/auth/me", json={"resend_domain": "x.com"})
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /auth/change-password
# ---------------------------------------------------------------------------


class TestChangePassword:
    async def test_change_password_clears_flag(self, authed_client, fake_user, mock_db):
        fake_user.must_change_password = True
        with patch("app.routers.auth.bcrypt") as mock_bcrypt:
            mock_bcrypt.checkpw.return_value = True
            mock_bcrypt.hashpw.return_value = b"newhash"
            mock_bcrypt.gensalt.return_value = b"salt"
            resp = await authed_client.post(
                "/auth/change-password",
                json={"current_password": "temp1234", "new_password": "brandnew123"},
            )
        assert resp.status_code == 200
        assert resp.json()["changed"] is True
        assert fake_user.must_change_password is False
        mock_db.commit.assert_awaited_once()

    async def test_change_password_wrong_current_401(self, authed_client, fake_user):
        with patch("app.routers.auth.bcrypt") as mock_bcrypt:
            mock_bcrypt.checkpw.return_value = False
            resp = await authed_client.post(
                "/auth/change-password",
                json={"current_password": "wrong", "new_password": "brandnew123"},
            )
        assert resp.status_code == 401

    async def test_change_password_short_new_422(self, authed_client):
        resp = await authed_client.post(
            "/auth/change-password",
            json={"current_password": "temp1234", "new_password": "short"},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Forced-reset guard (require_password_changed)
# ---------------------------------------------------------------------------


class TestForcedResetGuard:
    async def test_protected_route_blocked_until_reset(self, authed_client, fake_user):
        fake_user.must_change_password = True
        resp = await authed_client.get("/profile")
        assert resp.status_code == 403
        assert resp.json()["detail"]["code"] == "PASSWORD_CHANGE_REQUIRED"

    async def test_auth_me_still_reachable_during_forced_reset(self, authed_client, fake_user):
        # /auth is exempt from the guard so the user can still see who they are.
        fake_user.must_change_password = True
        resp = await authed_client.get("/auth/me")
        assert resp.status_code == 200
        assert resp.json()["must_change_password"] is True
