"""routers/members.py — team management within a tenant (URLs under /members).

In plain English: this is the admin console for a workspace. An admin (or owner)
can see the roster, create accounts for colleagues, change their role, suspend
or reactivate them, and remove them.

Access is gated by PERMISSIONS, not roles — every mutating endpoint requires
``members.manage`` (owners + admins). On top of that, a few hard guard-rails
protect the workspace from being broken:
  * New members can never be created as "owner" (ownership is granted only by an
    existing owner via PATCH).
  * An ADMIN may not modify an OWNER, nor promote anyone to owner — only an
    owner can do that.
  * You cannot modify your own membership here (prevents self-lockout).
  * The LAST active owner cannot be demoted, suspended, or removed.

New accounts are created with a one-time temporary password (returned to the
admin exactly once) and ``must_change_password=True`` so the member sets their
own password on first login. Every mutation writes an audit-log row.
"""

from __future__ import annotations

import secrets
import uuid

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import RequestContext, require_permission
from app.auth.permissions import Permission, Role
from app.db.session import get_db
from app.models.db import Membership, User
from app.models.schemas import (
    CreateMemberRequest,
    CreateMemberResponse,
    MemberListResponse,
    MemberResponse,
    RemoveMemberResponse,
    UpdateMemberRequest,
)
from app.services.audit import record_audit

router = APIRouter(prefix="/members", tags=["members"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


async def _get_membership(db: AsyncSession, member_id: uuid.UUID) -> Membership:
    """Load a membership by id. RLS scopes this to the caller's tenant, so a
    member in another tenant simply 404s."""
    result = await db.execute(select(Membership).where(Membership.id == member_id))
    membership = result.scalar_one_or_none()
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "Member not found", "code": "MEMBER_NOT_FOUND"},
        )
    return membership


async def _count_active_owners(db: AsyncSession) -> int:
    result = await db.execute(
        select(func.count())
        .select_from(Membership)
        .where(Membership.role == Role.OWNER.value, Membership.status == "active")
    )
    return result.scalar_one()


def _forbid(message: str, code: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={"error": message, "code": code},
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=MemberListResponse, status_code=status.HTTP_200_OK)
async def list_members(
    ctx: RequestContext = Depends(require_permission(Permission.MEMBERS_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> MemberListResponse:
    memberships = (
        (await db.execute(select(Membership).order_by(Membership.created_at)))
        .scalars()
        .all()
    )
    user_ids = [m.user_id for m in memberships]
    users = (
        (await db.execute(select(User).where(User.id.in_(user_ids)))).scalars().all()
        if user_ids
        else []
    )
    email_by_id = {u.id: u.email for u in users}

    return MemberListResponse(
        members=[
            MemberResponse(
                user_id=m.user_id,
                membership_id=m.id,
                email=email_by_id.get(m.user_id, ""),
                role=m.role,
                status=m.status,
                created_at=m.created_at,
            )
            for m in memberships
        ]
    )


@router.post("", response_model=CreateMemberResponse, status_code=status.HTTP_201_CREATED)
async def create_member(
    body: CreateMemberRequest,
    ctx: RequestContext = Depends(require_permission(Permission.MEMBERS_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> CreateMemberResponse:
    # Email is globally unique — a person can only belong to one tenant in v3.
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "Email already registered", "code": "EMAIL_EXISTS"},
        )

    temp_password = secrets.token_urlsafe(12)
    new_user = User(
        email=body.email,
        password_hash=_hash_password(temp_password),
        must_change_password=True,
    )
    db.add(new_user)
    await db.flush()
    await db.refresh(new_user)

    membership = Membership(
        tenant_id=ctx.tenant_id,
        user_id=new_user.id,
        role=body.role,
        status="active",
    )
    db.add(membership)
    await db.flush()
    await db.refresh(membership)

    await record_audit(
        db,
        tenant_id=ctx.tenant_id,
        actor_user_id=ctx.user.id,
        action="member.created",
        target=str(new_user.id),
        meta={"email": body.email, "role": body.role},
    )
    await db.commit()

    return CreateMemberResponse(
        user_id=new_user.id,
        membership_id=membership.id,
        email=body.email,
        role=body.role,
        temporary_password=temp_password,
    )


@router.patch(
    "/{member_id}", response_model=MemberResponse, status_code=status.HTTP_200_OK
)
async def update_member(
    member_id: uuid.UUID,
    body: UpdateMemberRequest,
    ctx: RequestContext = Depends(require_permission(Permission.MEMBERS_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> MemberResponse:
    if body.role is None and body.status is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "Nothing to update", "code": "NO_CHANGES"},
        )

    membership = await _get_membership(db, member_id)

    # Guard-rails ---------------------------------------------------------
    if membership.user_id == ctx.user.id:
        raise _forbid("You cannot modify your own membership", "CANNOT_MODIFY_SELF")

    actor_is_owner = ctx.role == Role.OWNER.value
    target_is_owner = membership.role == Role.OWNER.value

    if target_is_owner and not actor_is_owner:
        raise _forbid("Only an owner can modify an owner", "ADMIN_CANNOT_MODIFY_OWNER")

    if body.role == Role.OWNER.value and not actor_is_owner:
        raise _forbid("Only an owner can grant the owner role", "OWNER_GRANT_FORBIDDEN")

    # Last-owner protection: block demoting/suspending the final active owner.
    demoting_owner = (
        target_is_owner and body.role is not None and body.role != Role.OWNER.value
    )
    suspending_owner = (
        target_is_owner and body.status == "suspended"
    )
    if demoting_owner or suspending_owner:
        if await _count_active_owners(db) <= 1:
            raise _forbid(
                "The last owner cannot be demoted or suspended", "LAST_OWNER"
            )

    # Apply ---------------------------------------------------------------
    changes: dict = {}
    if body.role is not None and body.role != membership.role:
        changes["role"] = {"from": membership.role, "to": body.role}
        membership.role = body.role
    if body.status is not None and body.status != membership.status:
        changes["status"] = {"from": membership.status, "to": body.status}
        membership.status = body.status

    if changes:
        action = "member.role_changed" if "role" in changes else "member.status_changed"
        await record_audit(
            db,
            tenant_id=ctx.tenant_id,
            actor_user_id=ctx.user.id,
            action=action,
            target=str(membership.user_id),
            meta=changes,
        )
    await db.commit()
    # No refresh after commit: the RLS GUC has reverted (memberships is RLS-
    # protected). expire_on_commit=False keeps the in-memory membership valid;
    # the users table has no RLS so this lookup is safe post-commit.
    user = (
        await db.execute(select(User).where(User.id == membership.user_id))
    ).scalar_one_or_none()
    return MemberResponse(
        user_id=membership.user_id,
        membership_id=membership.id,
        email=user.email if user else "",
        role=membership.role,
        status=membership.status,
        created_at=membership.created_at,
    )


@router.delete(
    "/{member_id}", response_model=RemoveMemberResponse, status_code=status.HTTP_200_OK
)
async def remove_member(
    member_id: uuid.UUID,
    ctx: RequestContext = Depends(require_permission(Permission.MEMBERS_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> RemoveMemberResponse:
    membership = await _get_membership(db, member_id)

    if membership.user_id == ctx.user.id:
        raise _forbid("You cannot remove yourself", "CANNOT_MODIFY_SELF")

    target_is_owner = membership.role == Role.OWNER.value
    if target_is_owner and ctx.role != Role.OWNER.value:
        raise _forbid("Only an owner can remove an owner", "ADMIN_CANNOT_MODIFY_OWNER")
    if target_is_owner and await _count_active_owners(db) <= 1:
        raise _forbid("The last owner cannot be removed", "LAST_OWNER")

    removed_user_id = membership.user_id
    # Removing the user cascades to their membership and all their rows.
    user = (
        await db.execute(select(User).where(User.id == removed_user_id))
    ).scalar_one_or_none()
    if user is not None:
        await db.delete(user)

    await record_audit(
        db,
        tenant_id=ctx.tenant_id,
        actor_user_id=ctx.user.id,
        action="member.removed",
        target=str(removed_user_id),
    )
    await db.commit()
    return RemoveMemberResponse()
