# Integration tests (real Postgres)

These exercise what mocks can't: Postgres **Row-Level Security** isolation and
the **v3 RBAC backfill migration**. They are skipped unless `TEST_DATABASE_URL`
points at a reachable superuser/owner Postgres.

## Run

Start a Postgres (the project's compose file exposes one on `localhost:5433`):

```bash
docker compose up -d postgres
```

Then, from `backend/`:

```bash
# PowerShell
$env:TEST_DATABASE_URL='postgresql+asyncpg://crm:crm@localhost:5433/crm'
python -m pytest tests/integration -m integration

# bash
TEST_DATABASE_URL=postgresql+asyncpg://crm:crm@localhost:5433/crm \
  python -m pytest tests/integration -m integration
```

The harness ([conftest.py](conftest.py)) self-provisions:

- runs `alembic upgrade head` on the target DB,
- creates the dedicated non-owner `crm_app` role (password `apppass`) and grants,
- exposes `owner_engine` (superuser, **bypasses** RLS — used to seed + assert
  ground truth) and `app_engine` (connects as `crm_app`, **RLS-enforced** — what
  the app uses in production).

`TEST_DATABASE_URL` must be a superuser/owner connection: the suite needs to
`CREATE ROLE`, run migrations, and seed rows that bypass RLS.

## What's covered

- **test_rls_isolation.py** — unbound session sees nothing; a tenant sees only
  its own rows; cross-tenant UPDATE touches 0 rows and INSERT is rejected by the
  `WITH CHECK` policy; a membership is readable by `app.current_user_id` before a
  tenant is resolved; a reverted GUC fails closed (0 rows) instead of erroring.
- **test_migration.py** — downgrades to the v2 schema, seeds v2-shaped data,
  upgrades to head, and asserts each legacy user became the Owner of their own
  tenant with `resend_domain` moved and all `tenant_id`s backfilled. Restores
  head afterward.

> Note: the migration test downgrades/upgrades the target DB, so point
> `TEST_DATABASE_URL` at a disposable/dev database, never production.
