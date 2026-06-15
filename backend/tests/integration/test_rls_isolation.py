"""Postgres Row-Level Security isolation — the hard tenant boundary.

Run as the non-owner crm_app role (RLS-enforced). These prove that even a query
with NO WHERE clause cannot cross tenants, which is the whole point of RLS as a
defense-in-depth backstop behind the app's explicit tenant filters.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.integration


async def _set_tenant(conn, tenant_id):
    await conn.execute(
        text("SELECT set_config('app.current_tenant_id', :v, true)"),
        {"v": str(tenant_id)},
    )


async def _set_user(conn, user_id):
    await conn.execute(
        text("SELECT set_config('app.current_user_id', :v, true)"),
        {"v": str(user_id)},
    )


class TestReadIsolation:
    async def test_unbound_session_sees_nothing(self, app_engine, two_tenants):
        async with app_engine.connect() as conn:
            jobs = (await conn.execute(text("SELECT count(*) FROM outreach_jobs"))).scalar()
            tenants = (await conn.execute(text("SELECT count(*) FROM tenants"))).scalar()
        assert jobs == 0
        assert tenants == 0

    async def test_tenant_sees_only_its_own_rows(self, app_engine, two_tenants):
        a, b = two_tenants["a"], two_tenants["b"]
        async with app_engine.connect() as conn:
            await _set_tenant(conn, a["tenant"])
            names = (
                await conn.execute(text("SELECT company_name FROM outreach_jobs"))
            ).scalars().all()
        assert names == ["Acme Prospect"]
        assert "Globex Prospect" not in names


class TestWriteIsolation:
    async def test_cross_tenant_update_affects_zero_rows(self, app_engine, owner_engine, two_tenants):
        a, b = two_tenants["a"], two_tenants["b"]
        async with app_engine.connect() as conn:
            await _set_tenant(conn, a["tenant"])
            result = await conn.execute(
                text("UPDATE outreach_jobs SET company_name = 'HACKED' WHERE id = :id"),
                {"id": str(b["job"])},
            )
            await conn.commit()
            assert result.rowcount == 0

        # Ground truth via owner (bypasses RLS): B's row is untouched.
        async with owner_engine.connect() as conn:
            name = (
                await conn.execute(
                    text("SELECT company_name FROM outreach_jobs WHERE id = :id"),
                    {"id": str(b["job"])},
                )
            ).scalar()
        assert name == "Globex Prospect"

    async def test_cross_tenant_insert_is_rejected(self, app_engine, two_tenants):
        a, b = two_tenants["a"], two_tenants["b"]
        with pytest.raises(Exception) as exc_info:
            async with app_engine.connect() as conn:
                await _set_tenant(conn, a["tenant"])
                await conn.execute(
                    text(
                        "INSERT INTO outreach_jobs (tenant_id, user_id, company_name) "
                        "VALUES (:t, :u, 'Sneaky')"
                    ),
                    {"t": str(b["tenant"]), "u": str(b["user"])},
                )
                await conn.commit()
        assert "row-level security" in str(exc_info.value).lower()


class TestMembershipBootstrap:
    async def test_membership_readable_by_user_guc_before_tenant(self, app_engine, two_tenants):
        # A freshly-authenticated request knows its user_id but not yet its tenant;
        # the memberships policy must let it read its OWN membership to resolve one.
        a = two_tenants["a"]
        async with app_engine.connect() as conn:
            await _set_user(conn, a["user"])
            count = (
                await conn.execute(text("SELECT count(*) FROM memberships"))
            ).scalar()
        assert count == 1


class TestGucRevert:
    async def test_reverted_guc_fails_closed_without_erroring(self, app_engine, two_tenants):
        # After commit the transaction-local GUC reverts to '' on a pooled
        # connection. NULLIF(...,'') must fold that to NULL so the policy matches
        # nothing — instead of erroring on ''::uuid.
        a = two_tenants["a"]
        async with app_engine.connect() as conn:
            await _set_tenant(conn, a["tenant"])
            await conn.execute(text("SELECT 1"))
            await conn.commit()  # GUC reverts here

            # New transaction, no GUC: must return 0 rows, NOT raise.
            count = (
                await conn.execute(text("SELECT count(*) FROM outreach_jobs"))
            ).scalar()
        assert count == 0
