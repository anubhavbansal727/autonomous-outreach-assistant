"""auth/dependencies.py — how we know WHO is making a request (JWT auth).

In plain English:
- ``create_access_token`` / ``create_refresh_token`` mint signed JWTs. A JWT is
  a tamper-proof string that says "this is user X, valid until time Y",
  signed with our secret so nobody can forge one.
- An ACCESS token is short-lived (30 min) and sent on every request. A REFRESH
  token is long-lived (7 days) and only used to get a new access token.
- ``get_current_user`` is the gatekeeper: routers add it as a dependency
  (``Depends(get_current_user)``). It reads the "Authorization: Bearer <token>"
  header, verifies the signature, loads that user from the DB, and either
  returns the User or raises 401. If you see it on an endpoint, that endpoint
  requires login.
- Multi-tenancy (v3): after loading the user it also resolves their tenant
  membership, binds the Row-Level Security context for the request transaction
  (see db/session.py::bind_tenant_context), and attaches ``tenant_id``,
  ``role`` and ``tenant`` onto the returned User for routers to use.
- RBAC (v3): ``require_context`` packages the request's identity + tenant +
  role + resolved permissions into a ``RequestContext``. ``require_permission``
  is a dependency FACTORY — ``Depends(require_permission(Permission.X))`` on an
  endpoint makes it 403 unless the caller's role grants permission X.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.permissions import Permission, permissions_for
from app.config import settings
from app.db.session import bind_tenant_context, get_db
from app.models.db import Membership, Tenant, User

bearer_scheme = HTTPBearer()


def create_access_token(
    user_id: str, *, tenant_id: str | None = None, role: str | None = None
) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {
        "sub": user_id,
        "type": "access",
        "exp": expire,
    }
    # tenant_id / role are informational claims; the authoritative values are
    # re-resolved from the DB on every request (so a role change takes effect
    # immediately rather than waiting for the token to expire).
    if tenant_id is not None:
        payload["tenant_id"] = tenant_id
    if role is not None:
        payload["role"] = role
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(
    user_id: str, *, tenant_id: str | None = None, role: str | None = None
) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS
    )
    payload = {
        "sub": user_id,
        "type": "refresh",
        "exp": expire,
    }
    if tenant_id is not None:
        payload["tenant_id"] = tenant_id
    if role is not None:
        payload["role"] = role
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"error": "Could not validate credentials", "code": "INVALID_TOKEN"},
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        if payload.get("type") != "access":
            raise credentials_exception
        user_id: str | None = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    # Bind the user GUC first: the memberships RLS policy lets a session read
    # its OWN membership row by user_id before any tenant has been resolved.
    await bind_tenant_context(db, user_id=user_id)

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise credentials_exception

    membership_result = await db.execute(
        select(Membership).where(Membership.user_id == user.id)
    )
    membership = membership_result.scalar_one_or_none()
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "User has no tenant membership", "code": "NO_TENANT"},
        )
    if membership.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "Membership is suspended", "code": "MEMBERSHIP_SUSPENDED"},
        )

    await bind_tenant_context(db, tenant_id=membership.tenant_id)

    tenant_result = await db.execute(
        select(Tenant).where(Tenant.id == membership.tenant_id)
    )
    tenant = tenant_result.scalar_one_or_none()

    # Attach tenant context for routers that still depend on get_current_user
    # directly (profile/outreach until Phase 4 retrofits them to RequestContext).
    user.tenant_id = membership.tenant_id
    user.role = membership.role
    user.tenant = tenant
    return user


# ---------------------------------------------------------------------------
# RBAC — request context and permission gating
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RequestContext:
    """Everything an endpoint needs to know about the caller, resolved once.

    ``permissions`` is the flat list of permission strings the caller's role
    grants (see app/auth/permissions.py). Endpoints should gate on permissions
    via ``require_permission`` rather than reading ``role`` directly.
    """

    user: User
    tenant_id: uuid.UUID
    role: str
    permissions: list[str]

    def has(self, permission: Permission | str) -> bool:
        value = permission.value if isinstance(permission, Permission) else permission
        return value in self.permissions


async def require_context(
    current_user: User = Depends(get_current_user),
) -> RequestContext:
    """Resolve the caller into a RequestContext (identity + tenant + role + perms)."""
    return RequestContext(
        user=current_user,
        tenant_id=current_user.tenant_id,
        role=current_user.role,
        permissions=permissions_for(current_user.role),
    )


async def require_password_changed(
    current_user: User = Depends(get_current_user),
) -> User:
    """Block access while the user still owes a forced password reset.

    Applied to all protected routers EXCEPT /auth, so a member created with a
    temporary password can still hit /auth/me, /auth/change-password and
    /auth/logout, but nothing else, until they set their own password.
    """
    if current_user.must_change_password:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "You must change your password before continuing",
                "code": "PASSWORD_CHANGE_REQUIRED",
            },
        )
    return current_user


def require_permission(permission: Permission | str):
    """Build a dependency that 403s unless the caller's role grants ``permission``.

    Usage:
        @router.post(..., dependencies=[Depends(require_permission(Permission.MEMBERS_MANAGE))])
    or take the context as a parameter:
        ctx: RequestContext = Depends(require_permission(Permission.PROFILE_EDIT))
    """
    required = permission.value if isinstance(permission, Permission) else permission

    async def _checker(
        ctx: RequestContext = Depends(require_context),
    ) -> RequestContext:
        if required not in ctx.permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "You do not have permission to perform this action",
                    "code": "PERMISSION_DENIED",
                    "required_permission": required,
                },
            )
        return ctx

    return _checker
