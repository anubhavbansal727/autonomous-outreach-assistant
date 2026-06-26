"""routers/tenant.py — workspace settings and the audit log (URLs under /tenant, /audit).

In plain English:
- ``GET /tenant`` returns the current workspace (any member may read it).
- ``PATCH /tenant`` renames the workspace and sets the shared sending domain
  (``resend_domain`` moved here from the user in v3). Owner-only via the
  ``tenant.manage`` permission.
- ``GET /audit`` returns the recent audit trail (owners + admins).

All reads/writes are tenant-scoped by Row-Level Security, so these endpoints
can only ever touch the caller's own workspace.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import RequestContext, require_context, require_permission
from app.auth.permissions import Permission
from app.db.session import get_db
from app.models.db import AuditLog, Tenant
from app.models.schemas import (
    AuditLogEntry,
    AuditLogResponse,
    TenantResponse,
    UpdateTenantRequest,
)
from app.services.audit import record_audit

router = APIRouter(tags=["tenant"])


async def _get_tenant(db: AsyncSession, tenant_id) -> Tenant:
    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "Tenant not found", "code": "TENANT_NOT_FOUND"},
        )
    return tenant


@router.get("/tenant", response_model=TenantResponse, status_code=status.HTTP_200_OK)
async def get_tenant(
    ctx: RequestContext = Depends(require_context),
    db: AsyncSession = Depends(get_db),
) -> TenantResponse:
    tenant = await _get_tenant(db, ctx.tenant_id)
    return TenantResponse.model_validate(tenant)


@router.patch("/tenant", response_model=TenantResponse, status_code=status.HTTP_200_OK)
async def update_tenant(
    body: UpdateTenantRequest,
    ctx: RequestContext = Depends(require_permission(Permission.TENANT_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> TenantResponse:
    tenant = await _get_tenant(db, ctx.tenant_id)

    changes: dict = {}
    if body.name is not None and body.name != tenant.name:
        changes["name"] = {"from": tenant.name, "to": body.name}
        tenant.name = body.name
    if body.resend_domain is not None:
        new_domain = body.resend_domain or None
        if new_domain != tenant.resend_domain:
            changes["resend_domain"] = {"from": tenant.resend_domain, "to": new_domain}
            tenant.resend_domain = new_domain

    if changes:
        await record_audit(
            db,
            tenant_id=ctx.tenant_id,
            actor_user_id=ctx.user.id,
            action="tenant.updated",
            target=str(tenant.id),
            meta=changes,
        )
    await db.commit()
    # No refresh after commit: the transaction-local RLS GUC has reverted, so a
    # re-SELECT would see zero rows. expire_on_commit=False keeps the in-memory
    # object (with the values we just set) valid for the response.
    return TenantResponse.model_validate(tenant)


@router.get("/audit", response_model=AuditLogResponse, status_code=status.HTTP_200_OK)
async def get_audit_log(
    limit: int = Query(50, ge=1, le=200),
    ctx: RequestContext = Depends(require_permission(Permission.AUDIT_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> AuditLogResponse:
    rows = (
        (
            await db.execute(
                select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return AuditLogResponse(items=[AuditLogEntry.model_validate(r) for r in rows])
