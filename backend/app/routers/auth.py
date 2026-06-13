"""routers/auth.py — signup / login / logout endpoints (URLs under /auth).

In plain English:
- ``/register`` creates an account AND a brand-new tenant (company workspace),
  making the registrant its Owner — this is the only self-service signup path.
  Passwords are never stored as-is — bcrypt hashes them (one-way, salted) so a
  database leak doesn't expose passwords.
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
from app.auth.permissions import permissions_for
from app.config import settings
from app.db.session import bind_tenant_context, get_db
from app.models.db import Membership, Tenant, User
from app.models.schemas import (
    ChangePasswordRequest,
    ChangePasswordResponse,
    LoginRequest,
    LogoutResponse,
    MeResponse,
    RefreshResponse,
    RegisterRequest,
    TenantInfo,
    TokenResponse,
)


async def _resolve_membership(db: AsyncSession, user_id) -> Membership | None:
    """Load a user's membership, binding the user GUC so RLS allows the read."""
    await bind_tenant_context(db, user_id=str(user_id))
    result = await db.execute(select(Membership).where(Membership.user_id == user_id))
    return result.scalar_one_or_none()

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

    # Registering bootstraps a brand-new tenant with this user as its Owner.
    # IDs are generated client-side so the RLS context can be bound before the
    # INSERTs (the policies' WITH CHECK applies to new rows too).
    user_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    await bind_tenant_context(db, tenant_id=tenant_id, user_id=user_id)

    local_part = body.email.split("@", 1)[0]
    db.add(Tenant(id=tenant_id, name=f"{local_part}'s workspace"))
    user = User(
        id=user_id,
        email=body.email,
        password_hash=bcrypt.hashpw(body.password.encode(), bcrypt.gensalt()).decode(),
    )
    db.add(user)
    db.add(Membership(tenant_id=tenant_id, user_id=user_id, role="owner"))
    await db.flush()
    await db.refresh(user)
    await db.commit()

    access_token = create_access_token(
        str(user.id), tenant_id=str(tenant_id), role="owner"
    )
    refresh_token = create_refresh_token(
        str(user.id), tenant_id=str(tenant_id), role="owner"
    )

    response.set_cookie(REFRESH_COOKIE, refresh_token, **COOKIE_OPTS)
    return TokenResponse(
        access_token=access_token,
        user_id=str(user.id),
        tenant_id=str(tenant_id),
        role="owner",
        must_change_password=False,
    )


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

    membership = await _resolve_membership(db, user.id)
    tenant_id = str(membership.tenant_id) if membership else None
    role = membership.role if membership else None

    access_token = create_access_token(str(user.id), tenant_id=tenant_id, role=role)
    refresh_token = create_refresh_token(str(user.id), tenant_id=tenant_id, role=role)

    response.set_cookie(REFRESH_COOKIE, refresh_token, **COOKIE_OPTS)
    return TokenResponse(
        access_token=access_token,
        user_id=str(user.id),
        tenant_id=tenant_id,
        role=role,
        must_change_password=user.must_change_password,
    )


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

    membership = await _resolve_membership(db, user.id)
    tenant_id = str(membership.tenant_id) if membership else None
    role = membership.role if membership else None

    return RefreshResponse(
        access_token=create_access_token(str(user.id), tenant_id=tenant_id, role=role)
    )


@router.post("/logout", response_model=LogoutResponse, status_code=status.HTTP_200_OK)
async def logout(response: Response) -> LogoutResponse:
    response.delete_cookie(REFRESH_COOKIE)
    return LogoutResponse()


@router.post(
    "/change-password",
    response_model=ChangePasswordResponse,
    status_code=status.HTTP_200_OK,
)
async def change_password(
    body: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChangePasswordResponse:
    """Set a new password. Clears the forced-reset flag for admin-created members.

    Deliberately NOT behind require_password_changed, so a member who still owes
    a reset can call it.
    """
    if not bcrypt.checkpw(
        body.current_password.encode(), current_user.password_hash.encode()
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "Current password is incorrect", "code": "INVALID_CREDENTIALS"},
        )

    current_user.password_hash = bcrypt.hashpw(
        body.new_password.encode(), bcrypt.gensalt()
    ).decode()
    current_user.must_change_password = False
    await db.commit()
    return ChangePasswordResponse()


# resend_domain moved from users to tenants in v3 — it is shared sending config.
# Editing it is owner-only and lives on PATCH /tenant (tenant.manage); /me only
# mirrors the tenant's value for read convenience.


def _me_response(current_user: User) -> MeResponse:
    """Build the /me payload from the tenant-enriched User (see get_current_user)."""
    tenant = current_user.tenant
    return MeResponse(
        user_id=current_user.id,
        email=current_user.email,
        resend_domain=tenant.resend_domain if tenant else None,
        created_at=current_user.created_at,
        must_change_password=current_user.must_change_password,
        role=current_user.role,
        permissions=permissions_for(current_user.role),
        tenant=TenantInfo.model_validate(tenant) if tenant else None,
    )


@router.get("/me", response_model=MeResponse, status_code=status.HTTP_200_OK)
async def me(current_user: User = Depends(get_current_user)) -> MeResponse:
    return _me_response(current_user)
