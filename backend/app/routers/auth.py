"""routers/auth.py — signup / login / logout endpoints (URLs under /auth).

In plain English:
- ``/register`` creates an account. Passwords are never stored as-is — bcrypt
  hashes them (one-way, salted) so a database leak doesn't expose passwords.
- ``/login`` checks the password and, on success, returns an access token plus
  sets the refresh token as a secure http-only cookie (JavaScript can't read
  it, which limits theft).
- ``/refresh`` swaps a valid refresh cookie for a fresh access token.
- ``/me`` (GET) returns the logged-in user; ``/me`` (PATCH) lets them set their
  email sending domain.
The token-minting/checking helpers live in app/auth/dependencies.py.
"""

import uuid

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import (
    create_access_token,
    create_refresh_token,
    get_current_user,
)
from app.config import settings
from app.db.session import get_db
from app.models.db import User
from app.models.schemas import (
    LoginRequest,
    LogoutResponse,
    MeResponse,
    RefreshResponse,
    RegisterRequest,
    TokenResponse,
    UpdateMeRequest,
)

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE = "refresh_token"
COOKIE_OPTS = dict(
    httponly=True,
    secure=True,
    samesite="strict",
    max_age=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 86400,
)


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    # Check email uniqueness
    result = await db.execute(select(User).where(User.email == body.email))
    if result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "Email already registered", "code": "EMAIL_EXISTS"},
        )

    user = User(
        email=body.email,
        password_hash=bcrypt.hashpw(body.password.encode(), bcrypt.gensalt()).decode(),
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    await db.commit()

    access_token = create_access_token(str(user.id))
    refresh_token = create_refresh_token(str(user.id))

    response.set_cookie(REFRESH_COOKIE, refresh_token, **COOKIE_OPTS)
    return TokenResponse(access_token=access_token, user_id=str(user.id))


@router.post("/login", response_model=TokenResponse, status_code=status.HTTP_200_OK)
async def login(
    body: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    if user is None or not bcrypt.checkpw(body.password.encode(), user.password_hash.encode()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "Invalid email or password", "code": "INVALID_CREDENTIALS"},
        )

    access_token = create_access_token(str(user.id))
    refresh_token = create_refresh_token(str(user.id))

    response.set_cookie(REFRESH_COOKIE, refresh_token, **COOKIE_OPTS)
    return TokenResponse(access_token=access_token, user_id=str(user.id))


@router.post("/refresh", response_model=RefreshResponse, status_code=status.HTTP_200_OK)
async def refresh(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> RefreshResponse:
    token = request.cookies.get(REFRESH_COOKIE)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "Missing refresh token", "code": "MISSING_REFRESH_TOKEN"},
        )

    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        if payload.get("type") != "refresh":
            raise JWTError("wrong token type")
        user_id: str | None = payload.get("sub")
        if user_id is None:
            raise JWTError("missing sub")
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "Invalid refresh token", "code": "INVALID_REFRESH_TOKEN"},
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "User not found", "code": "USER_NOT_FOUND"},
        )

    return RefreshResponse(access_token=create_access_token(str(user.id)))


@router.post("/logout", response_model=LogoutResponse, status_code=status.HTTP_200_OK)
async def logout(response: Response) -> LogoutResponse:
    response.delete_cookie(REFRESH_COOKIE)
    return LogoutResponse()


@router.get("/me", response_model=MeResponse, status_code=status.HTTP_200_OK)
async def me(current_user: User = Depends(get_current_user)) -> MeResponse:
    return MeResponse(
        user_id=current_user.id,
        email=current_user.email,
        resend_domain=current_user.resend_domain,
        created_at=current_user.created_at,
    )


@router.patch("/me", response_model=MeResponse, status_code=status.HTTP_200_OK)
async def update_me(
    body: UpdateMeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MeResponse:
    if body.resend_domain is not None:
        current_user.resend_domain = body.resend_domain or None
    await db.commit()
    await db.refresh(current_user)
    return MeResponse(
        user_id=current_user.id,
        email=current_user.email,
        resend_domain=current_user.resend_domain,
        created_at=current_user.created_at,
    )
