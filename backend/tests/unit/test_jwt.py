"""Unit tests for JWT token creation and validation helpers."""
from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from jose import jwt

from app.config import settings


class TestCreateAccessToken:
    def test_returns_string(self):
        from app.auth.dependencies import create_access_token
        token = create_access_token("user-123")
        assert isinstance(token, str)
        assert len(token) > 20

    def test_payload_type_is_access(self):
        from app.auth.dependencies import create_access_token
        token = create_access_token("user-abc")
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        assert payload["type"] == "access"
        assert payload["sub"] == "user-abc"

    def test_exp_is_in_future(self):
        from app.auth.dependencies import create_access_token
        token = create_access_token("user-xyz")
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        assert payload["exp"] > time.time()

    def test_different_users_produce_different_tokens(self):
        from app.auth.dependencies import create_access_token
        t1 = create_access_token("user-1")
        t2 = create_access_token("user-2")
        assert t1 != t2


class TestCreateRefreshToken:
    def test_payload_type_is_refresh(self):
        from app.auth.dependencies import create_refresh_token
        token = create_refresh_token("user-abc")
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        assert payload["type"] == "refresh"

    def test_refresh_expires_later_than_access(self):
        from app.auth.dependencies import create_access_token, create_refresh_token
        access = create_access_token("u")
        refresh = create_refresh_token("u")
        access_exp = jwt.decode(access, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])["exp"]
        refresh_exp = jwt.decode(refresh, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])["exp"]
        assert refresh_exp > access_exp


class TestGetCurrentUser:
    @pytest.mark.asyncio
    async def test_valid_access_token_returns_user(self):
        from app.auth.dependencies import create_access_token, get_current_user
        from fastapi.security import HTTPAuthorizationCredentials

        fake_user = MagicMock()
        fake_user.id = "user-123"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = fake_user

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        token = create_access_token("user-123")
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

        user = await get_current_user(credentials=creds, db=mock_db)
        assert user is fake_user

    @pytest.mark.asyncio
    async def test_refresh_token_raises_401(self):
        from app.auth.dependencies import create_refresh_token, get_current_user
        from fastapi import HTTPException
        from fastapi.security import HTTPAuthorizationCredentials

        token = create_refresh_token("user-123")
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(credentials=creds, db=AsyncMock())
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_garbage_token_raises_401(self):
        from app.auth.dependencies import get_current_user
        from fastapi import HTTPException
        from fastapi.security import HTTPAuthorizationCredentials

        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="not.a.token")
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(credentials=creds, db=AsyncMock())
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_unknown_user_raises_401(self):
        from app.auth.dependencies import create_access_token, get_current_user
        from fastapi import HTTPException
        from fastapi.security import HTTPAuthorizationCredentials

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        token = create_access_token("ghost-user")
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(credentials=creds, db=mock_db)
        assert exc_info.value.status_code == 401
