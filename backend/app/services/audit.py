"""services/audit.py — append-only record of who-did-what, per tenant.

In plain English: whenever an admin creates/changes/removes a member or edits
tenant settings, we drop a row in ``audit_logs`` so there is a tamper-evident
trail. ``record_audit`` only stages the row (``db.add``) — the caller's existing
transaction commits it, so the audit entry and the action it describes land
atomically (both or neither).
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import AuditLog


async def record_audit(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    action: str,
    target: str | None = None,
    meta: dict | None = None,
) -> None:
    """Stage an audit-log row on ``db`` (committed by the caller's transaction)."""
    db.add(
        AuditLog(
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            action=action,
            target=target,
            meta=meta,
        )
    )
