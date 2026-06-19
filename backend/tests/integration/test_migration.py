"""The v3 backfill migration must not break shipped v1/v2 data.

Downgrade to the v2 schema (pre-RBAC), seed v2-shaped rows, then upgrade head
and assert every legacy user became the Owner of their own tenant with all data
re-homed under it. Always restores head afterwards.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from .conftest import run_alembic

pytestmark = pytest.mark.integration

V2_REVISION = "b1f2c3d4e5a6"


async def _columns(conn, table: str) -> set[str]:
    rows = await conn.execute(
        text("SELECT column_name FROM information_schema.columns WHERE table_name = :t"),
        {"t": table},
    )
    return {r[0] for r in rows}


class TestBackfillMigration:
    async def test_v2_data_migrates_to_tenants(self, owner_engine):
        ua, ub = uuid.uuid4(), uuid.uuid4()
        try:
            # --- back to the v2 schema (user_id-scoped, resend_domain on users) ---
            run_alembic("downgrade", V2_REVISION)

            async with owner_engine.begin() as conn:
                pp_cols = await _columns(conn, "product_profiles")
                assert "user_id" in pp_cols and "tenant_id" not in pp_cols
                user_cols = await _columns(conn, "users")
                assert "resend_domain" in user_cols

                # Seed two v2 users with their own profiles + jobs.
                await conn.execute(
                    text(
                        "INSERT INTO users (id, email, password_hash, resend_domain) "
                        "VALUES (:a, 'miguser-a@test', 'x', 'acme.com'), "
                        "(:b, 'miguser-b@test', 'x', NULL)"
                    ),
                    {"a": ua, "b": ub},
                )
                await conn.execute(
                    text(
                        "INSERT INTO product_profiles (user_id, product_name, is_active) "
                        "VALUES (:a, 'Acme Widget', true)"
                    ),
                    {"a": ua},
                )
                await conn.execute(
                    text(
                        "INSERT INTO outreach_jobs (user_id, company_name, status) "
                        "VALUES (:a, 'Prospect A', 'done'), (:b, 'Prospect B', 'done')"
                    ),
                    {"a": ua, "b": ub},
                )

            # --- apply the v3 RBAC migration ---
            run_alembic("upgrade", "head")

            async with owner_engine.begin() as conn:
                # Each legacy user → Owner of a tenant whose id reuses the user id.
                for uid, domain in ((ua, "acme.com"), (ub, None)):
                    role, status, tenant_id = (
                        await conn.execute(
                            text(
                                "SELECT role, status, tenant_id FROM memberships WHERE user_id = :u"
                            ),
                            {"u": uid},
                        )
                    ).one()
                    assert role == "owner"
                    assert status == "active"
                    assert tenant_id == uid  # backfill reuses the user id

                    resend = (
                        await conn.execute(
                            text("SELECT resend_domain FROM tenants WHERE id = :t"),
                            {"t": uid},
                        )
                    ).scalar()
                    assert resend == domain  # resend_domain moved users -> tenants

                # Profile re-homed onto the tenant, audit-only creator preserved.
                prof = (
                    await conn.execute(
                        text(
                            "SELECT tenant_id, created_by_user_id, is_active "
                            "FROM product_profiles WHERE created_by_user_id = :u"
                        ),
                        {"u": ua},
                    )
                ).one()
                assert prof[0] == ua and prof[1] == ua and prof[2] is True

                # No NULL tenant_id left on any tenant-scoped table.
                for table in ("product_profiles", "outreach_jobs"):
                    nulls = (
                        await conn.execute(
                            text(f"SELECT count(*) FROM {table} WHERE tenant_id IS NULL")
                        )
                    ).scalar()
                    assert nulls == 0, f"{table} has NULL tenant_id after backfill"

                # Schema shape flipped over to v3.
                user_cols = await _columns(conn, "users")
                assert "resend_domain" not in user_cols
                assert "must_change_password" in user_cols
                pp_cols = await _columns(conn, "product_profiles")
                assert "tenant_id" in pp_cols and "user_id" not in pp_cols
        finally:
            # Restoring head must NOT be swallowed: if it fails, later RLS tests
            # would silently run against the v2 schema. Let it raise.
            run_alembic("upgrade", "head")
            # Row cleanup is best-effort (the schema is already restored).
            try:
                async with owner_engine.begin() as conn:
                    # Deleting the tenants cascades profiles/jobs/memberships.
                    await conn.execute(
                        text("DELETE FROM tenants WHERE id = ANY(:ids)"),
                        {"ids": [ua, ub]},
                    )
                    await conn.execute(
                        text("DELETE FROM users WHERE id = ANY(:ids)"),
                        {"ids": [ua, ub]},
                    )
            except Exception:
                pass
