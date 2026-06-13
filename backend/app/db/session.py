"""db/session.py — how the app talks to PostgreSQL.

In plain English:
- ``engine`` is the connection pool to the database (created once, shared).
- ``AsyncSessionLocal`` is a factory: call it to get a fresh "session"
  (a unit of DB work you read/write through, then commit).
- ``get_db()`` is the FastAPI dependency used inside routers — it hands each
  request its own session and cleans it up afterwards.
- ``bind_tenant_context()`` tells Postgres WHICH tenant (and user) the current
  transaction belongs to. The Row-Level Security policies (see the rbac
  migration) only reveal rows matching these values — without this call, a
  non-superuser connection sees zero tenant-scoped rows.

Note: the background jobs (app/jobs/* and the batch graph nodes) do NOT use
``get_db``; they run in the worker process outside any web request, so they
open ``tenant_session(tenant_id)`` blocks — which bind the RLS GUC up front so
their reads/writes are scoped to the right tenant (and not silently blocked).
"""

import uuid
from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncSession:  # type: ignore[override]
    async with AsyncSessionLocal() as session:
        yield session


@asynccontextmanager
async def tenant_session(
    tenant_id: uuid.UUID | str,
    user_id: uuid.UUID | str | None = None,
) -> AsyncIterator[AsyncSession]:
    """Open a worker session already bound to a tenant's RLS context.

    Replaces a bare ``AsyncSessionLocal()`` for background work. The GUC is set
    via ``SET LOCAL`` (transaction-scoped), which is correct for the workers'
    single-commit-per-block pattern: bind → query/update → commit. If a caller
    needs more work after a commit in the same block, re-open the context.
    """
    async with AsyncSessionLocal() as session:
        await bind_tenant_context(session, tenant_id=tenant_id, user_id=user_id)
        yield session


async def bind_tenant_context(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID | str | None = None,
    user_id: uuid.UUID | str | None = None,
) -> None:
    """Bind the RLS context GUCs to the session's current transaction.

    ``set_config(..., is_local := true)`` scopes the value to the transaction,
    so it resets automatically at COMMIT/ROLLBACK — call this again after a
    commit if more tenant-scoped queries follow in the same session.
    """
    if user_id is not None:
        await db.execute(
            text("SELECT set_config('app.current_user_id', :v, true)"),
            {"v": str(user_id)},
        )
    if tenant_id is not None:
        await db.execute(
            text("SELECT set_config('app.current_tenant_id', :v, true)"),
            {"v": str(tenant_id)},
        )
