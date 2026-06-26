"""Fixtures for REAL-database integration tests (RLS isolation + migration).

These tests exercise the things mocks can't: Postgres Row-Level Security and the
v3 backfill migration. They are SKIPPED unless ``TEST_DATABASE_URL`` is set to a
superuser/owner async URL, e.g.::

    TEST_DATABASE_URL=postgresql+asyncpg://crm:crm@localhost:5433/crm \
        python -m pytest tests/integration -m integration

How it works:
- A session-scoped step runs ``alembic upgrade head`` against that DB.
- ``owner_engine`` connects as the migration owner (superuser) — it BYPASSES RLS,
  so it's used to seed data and to assert ground truth.
- ``app_engine`` connects as the dedicated non-owner ``crm_app`` role, which RLS
  is actually enforced against — this is what the app uses in production.
- Both the role and its grants are (re)provisioned per test, so the suite is
  robust even after the migration test downgrades/upgrades the schema.
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

# backend/tests/integration/conftest.py -> backend/
BACKEND_DIR = pathlib.Path(__file__).resolve().parents[2]
TEST_DB_URL = os.environ.get("TEST_DATABASE_URL")
APP_ROLE = "crm_app"
APP_PASSWORD = "apppass"

# Every test in this package needs a real DB.
pytestmark = pytest.mark.integration


def _require_db() -> str:
    if not TEST_DB_URL:
        pytest.skip("set TEST_DATABASE_URL to run integration tests")
    return TEST_DB_URL


def _app_url() -> str:
    """Same DB as TEST_DATABASE_URL but authenticating as the non-owner role."""
    return make_url(_require_db()).set(
        username=APP_ROLE, password=APP_PASSWORD
    ).render_as_string(hide_password=False)


def run_alembic(*args: str) -> None:
    """Run an alembic command against the test DB (env drives settings.DATABASE_URL)."""
    env = {**os.environ, "DATABASE_URL": _require_db()}
    subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=str(BACKEND_DIR),
        env=env,
        check=True,
        capture_output=True,
    )


@pytest.fixture(scope="session", autouse=True)
def _migrate_to_head():
    """Bring the test DB to head once per session (no-op if already there)."""
    if TEST_DB_URL:
        run_alembic("upgrade", "head")
    yield


@pytest_asyncio.fixture
async def owner_engine():
    """Superuser/owner engine — bypasses RLS. Also (re)provisions the app role."""
    url = _require_db()
    engine = create_async_engine(url, poolclass=NullPool)
    async with engine.begin() as conn:
        # APP_ROLE / APP_PASSWORD are trusted constants — a DO block can't take
        # bind parameters, so they're inlined.
        await conn.execute(
            text(
                f"DO $$ BEGIN "
                f"IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN "
                f"CREATE ROLE {APP_ROLE} LOGIN PASSWORD '{APP_PASSWORD}'; "
                f"END IF; END $$;"
            )
        )
        # Re-apply grants every time so the suite survives the migration test's
        # downgrade/upgrade (new tables would otherwise have no grants).
        await conn.execute(text(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}"))
        await conn.execute(
            text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {APP_ROLE}")
        )
        await conn.execute(
            text(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}")
        )
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def app_engine(owner_engine):
    """Non-owner engine that RLS is enforced against (NullPool: no GUC leakage)."""
    engine = create_async_engine(_app_url(), poolclass=NullPool)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def two_tenants(owner_engine):
    """Seed two isolated tenants, each with an owner + one outreach job.

    Seeded via the owner connection (bypasses RLS). Returns the ids for tests.
    Cleans up afterwards.
    """
    a_tenant, a_user, a_job = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    b_tenant, b_user, b_job = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    async with owner_engine.begin() as conn:
        for t, name in ((a_tenant, "Acme"), (b_tenant, "Globex")):
            await conn.execute(
                text("INSERT INTO tenants (id, name) VALUES (:id, :n)"),
                {"id": t, "n": name},
            )
        for u, email in ((a_user, "a@acme.test"), (b_user, "b@globex.test")):
            await conn.execute(
                text("INSERT INTO users (id, email, password_hash) VALUES (:id, :e, 'x')"),
                {"id": u, "e": email},
            )
        for t, u in ((a_tenant, a_user), (b_tenant, b_user)):
            await conn.execute(
                text(
                    "INSERT INTO memberships (tenant_id, user_id, role) "
                    "VALUES (:t, :u, 'owner')"
                ),
                {"t": t, "u": u},
            )
        for j, t, u, company in (
            (a_job, a_tenant, a_user, "Acme Prospect"),
            (b_job, b_tenant, b_user, "Globex Prospect"),
        ):
            await conn.execute(
                text(
                    "INSERT INTO outreach_jobs (id, tenant_id, user_id, company_name, status) "
                    "VALUES (:j, :t, :u, :c, 'done')"
                ),
                {"j": j, "t": t, "u": u, "c": company},
            )

    yield {
        "a": {"tenant": a_tenant, "user": a_user, "job": a_job},
        "b": {"tenant": b_tenant, "user": b_user, "job": b_job},
    }

    async with owner_engine.begin() as conn:
        await conn.execute(
            text("DELETE FROM tenants WHERE id = ANY(:ids)"),
            {"ids": [a_tenant, b_tenant]},  # cascades memberships + jobs
        )
        await conn.execute(
            text("DELETE FROM users WHERE id = ANY(:ids)"),
            {"ids": [a_user, b_user]},
        )
