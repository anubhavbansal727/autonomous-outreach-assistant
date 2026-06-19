"""rbac: tenants, memberships, audit_logs, tenant_id everywhere, RLS

The v3 multi-tenancy migration. In plain English, four things happen, in order:

1. CREATE — new ``tenants``, ``memberships`` and ``audit_logs`` tables, plus
   nullable ``tenant_id`` columns on every tenant-scoped table.
2. BACKFILL — every existing user becomes the Owner of their own brand-new
   single-member tenant. The backfilled tenant deliberately REUSES the user's
   UUID as its own id, which makes the data backfill a trivial
   ``tenant_id = user_id`` (new tenants created after this migration get
   random ids as normal — there is no meaning to the overlap).
3. TIGHTEN — flip ``tenant_id`` to NOT NULL, swap the one-active-profile
   unique index from per-user to per-tenant, move ``resend_domain`` from
   users to tenants, drop ``product_profiles.user_id`` (replaced by
   ``tenant_id`` + audit-only ``created_by_user_id``).
4. LOCK — enable Row-Level Security with FORCE on all tenant-scoped tables.
   Policies allow access only when the transaction has set
   ``app.current_tenant_id`` (see app/db/session.py::bind_tenant_context).
   Even a query that forgets a WHERE clause cannot cross tenants.

NOTE: superusers and the table owner WITHOUT force would bypass RLS; FORCE
makes the policies apply to the table owner too. For real isolation the app
must connect as a dedicated non-owner role — see scripts/create_app_db_role.sql.

Revision ID: d4e5f6a7b8c9
Revises: b1f2c3d4e5a6
Create Date: 2026-06-12 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'b1f2c3d4e5a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Tables that carry a tenant_id and get the standard tenant-isolation policy.
TENANT_SCOPED_TABLES = (
    'product_profiles',
    'ingestion_jobs',
    'outreach_jobs',
    'batch_jobs',
    'audit_logs',
)


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. CREATE — new tables and nullable columns
    # ------------------------------------------------------------------
    op.create_table(
        'tenants',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('name', sa.TEXT(), nullable=False),
        sa.Column('slug', sa.TEXT(), nullable=True),
        sa.Column('resend_domain', sa.TEXT(), nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('slug'),
    )

    op.create_table(
        'memberships',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('role', sa.TEXT(), nullable=False),
        sa.Column('status', sa.TEXT(), server_default=sa.text("'active'"), nullable=False),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.CheckConstraint("role IN ('owner', 'admin', 'member', 'viewer')", name='ck_memberships_role'),
        sa.CheckConstraint("status IN ('active', 'suspended')", name='ck_memberships_status'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('uq_memberships_user_id', 'memberships', ['user_id'], unique=True)
    op.create_index('ix_memberships_tenant_id', 'memberships', ['tenant_id'], unique=False)

    op.create_table(
        'audit_logs',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('actor_user_id', sa.UUID(), nullable=True),
        sa.Column('action', sa.TEXT(), nullable=False),
        sa.Column('target', sa.TEXT(), nullable=True),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['actor_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_audit_logs_tenant_id_created_at', 'audit_logs', ['tenant_id', 'created_at'], unique=False)

    op.add_column('users', sa.Column('must_change_password', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    op.add_column('product_profiles', sa.Column('tenant_id', sa.UUID(), nullable=True))
    op.add_column('product_profiles', sa.Column('created_by_user_id', sa.UUID(), nullable=True))
    op.add_column('ingestion_jobs', sa.Column('tenant_id', sa.UUID(), nullable=True))
    op.add_column('outreach_jobs', sa.Column('tenant_id', sa.UUID(), nullable=True))
    op.add_column('batch_jobs', sa.Column('tenant_id', sa.UUID(), nullable=True))

    # ------------------------------------------------------------------
    # 2. BACKFILL — one personal tenant per existing user
    # ------------------------------------------------------------------
    # Tenant id = user id makes every child-table backfill a simple
    # tenant_id := user_id. The user's resend_domain moves to their tenant.
    op.execute(
        """
        INSERT INTO tenants (id, name, resend_domain, created_at)
        SELECT id,
               split_part(email, '@', 1) || '''s workspace',
               resend_domain,
               created_at
        FROM users
        """
    )
    op.execute(
        """
        INSERT INTO memberships (tenant_id, user_id, role, status)
        SELECT id, id, 'owner', 'active' FROM users
        """
    )
    op.execute("UPDATE product_profiles SET tenant_id = user_id, created_by_user_id = user_id")
    op.execute("UPDATE ingestion_jobs SET tenant_id = user_id")
    op.execute("UPDATE outreach_jobs SET tenant_id = user_id")
    op.execute("UPDATE batch_jobs SET tenant_id = user_id")

    # ------------------------------------------------------------------
    # 3. TIGHTEN — NOT NULL, FKs, index swaps, column moves
    # ------------------------------------------------------------------
    for table in ('product_profiles', 'ingestion_jobs', 'outreach_jobs', 'batch_jobs'):
        op.alter_column(table, 'tenant_id', nullable=False)
        op.create_foreign_key(
            f'fk_{table}_tenant_id', table, 'tenants',
            ['tenant_id'], ['id'], ondelete='CASCADE',
        )
    op.create_foreign_key(
        'fk_product_profiles_created_by_user_id', 'product_profiles', 'users',
        ['created_by_user_id'], ['id'], ondelete='SET NULL',
    )

    op.create_index('ix_product_profiles_tenant_id', 'product_profiles', ['tenant_id'], unique=False)
    op.create_index(
        'uq_product_profiles_tenant_id_active', 'product_profiles', ['tenant_id'],
        unique=True, postgresql_where=sa.text('is_active = true'),
    )
    op.create_index('ix_ingestion_jobs_tenant_id', 'ingestion_jobs', ['tenant_id'], unique=False)
    op.create_index(
        'ix_outreach_jobs_tenant_id_user_id_created_at', 'outreach_jobs',
        ['tenant_id', 'user_id', 'created_at'], unique=False,
    )
    op.create_index('ix_batch_jobs_tenant_id', 'batch_jobs', ['tenant_id'], unique=False)

    # Dropping product_profiles.user_id cascades its FK and the old
    # ix_product_profiles_user_id / uq_product_profiles_user_id_active indexes.
    op.drop_column('product_profiles', 'user_id')
    op.drop_column('users', 'resend_domain')

    # ------------------------------------------------------------------
    # 4. LOCK — Row-Level Security
    # ------------------------------------------------------------------
    # current_setting(..., true) returns NULL when the GUC was never set, but
    # an EMPTY STRING once a transaction-local value has reverted on a pooled
    # connection — NULLIF(..., '') folds both cases to NULL (policy matches
    # nothing) instead of erroring on ''::uuid.
    tenant_guc = "NULLIF(current_setting('app.current_tenant_id', true), '')::uuid"
    user_guc = "NULLIF(current_setting('app.current_user_id', true), '')::uuid"

    for table in TENANT_SCOPED_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation ON {table}
            USING (tenant_id = {tenant_guc})
            """
        )

    # memberships: also visible by user_id, so a freshly authenticated request
    # can resolve its own membership BEFORE the tenant GUC has been set.
    op.execute("ALTER TABLE memberships ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE memberships FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY tenant_isolation ON memberships
        USING (
            tenant_id = {tenant_guc}
            OR user_id = {user_guc}
        )
        """
    )

    op.execute("ALTER TABLE tenants ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE tenants FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY tenant_isolation ON tenants
        USING (id = {tenant_guc})
        """
    )


def downgrade() -> None:
    # Reverse of upgrade. Best-effort: re-derives per-user columns from the
    # backfilled tenant structure (assumes one membership per user, as in v3).
    for table in TENANT_SCOPED_TABLES + ('memberships', 'tenants'):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    op.add_column('users', sa.Column('resend_domain', sa.TEXT(), nullable=True))
    op.execute(
        """
        UPDATE users SET resend_domain = t.resend_domain
        FROM memberships m JOIN tenants t ON t.id = m.tenant_id
        WHERE m.user_id = users.id
        """
    )

    op.add_column('product_profiles', sa.Column('user_id', sa.UUID(), nullable=True))
    # Re-derive the v2 owner column. Prefer the actual creator; fall back to the
    # tenant's earliest-joined owner (deterministic) for profiles whose creator
    # was since removed. A tenant always has >= 1 owner (last-owner protection).
    op.execute(
        """
        UPDATE product_profiles p SET user_id = COALESCE(
            p.created_by_user_id,
            (SELECT m.user_id FROM memberships m
             WHERE m.tenant_id = p.tenant_id AND m.role = 'owner'
             ORDER BY m.created_at, m.user_id
             LIMIT 1)
        )
        """
    )
    op.alter_column('product_profiles', 'user_id', nullable=False)
    op.create_foreign_key(
        'product_profiles_user_id_fkey', 'product_profiles', 'users',
        ['user_id'], ['id'], ondelete='CASCADE',
    )
    op.create_index('ix_product_profiles_user_id', 'product_profiles', ['user_id'], unique=False)
    op.create_index(
        'uq_product_profiles_user_id_active', 'product_profiles', ['user_id'],
        unique=True, postgresql_where=sa.text('is_active = true'),
    )
    op.drop_index('uq_product_profiles_tenant_id_active', table_name='product_profiles')
    op.drop_index('ix_product_profiles_tenant_id', table_name='product_profiles')
    op.drop_constraint('fk_product_profiles_created_by_user_id', 'product_profiles', type_='foreignkey')
    op.drop_column('product_profiles', 'created_by_user_id')

    op.drop_index('ix_batch_jobs_tenant_id', table_name='batch_jobs')
    op.drop_index('ix_outreach_jobs_tenant_id_user_id_created_at', table_name='outreach_jobs')
    op.drop_index('ix_ingestion_jobs_tenant_id', table_name='ingestion_jobs')
    for table in ('product_profiles', 'ingestion_jobs', 'outreach_jobs', 'batch_jobs'):
        op.drop_constraint(f'fk_{table}_tenant_id', table, type_='foreignkey')
        op.drop_column(table, 'tenant_id')

    op.drop_column('users', 'must_change_password')

    op.drop_index('ix_audit_logs_tenant_id_created_at', table_name='audit_logs')
    op.drop_table('audit_logs')
    op.drop_index('ix_memberships_tenant_id', table_name='memberships')
    op.drop_index('uq_memberships_user_id', table_name='memberships')
    op.drop_table('memberships')
    op.drop_table('tenants')
