-- create_app_db_role.sql — provision the dedicated NON-OWNER role the app
-- connects as in production.
--
-- Why this matters: Postgres Row-Level Security is bypassed entirely by
-- superusers and roles with BYPASSRLS. The tables here also use FORCE ROW
-- LEVEL SECURITY so even the table owner is subject to the policies — but the
-- clean setup is a separate, unprivileged login role for the application.
--
--   * Migrations (alembic) keep running as the OWNER user (full DDL rights).
--   * The app (API + worker) connects as `crm_app` via DATABASE_URL.
--
-- Usage (as the database owner / admin):
--   psql "$ADMIN_DATABASE_URL" -v app_password="'<strong-password>'" -f scripts/create_app_db_role.sql
-- Then point the app at it:
--   DATABASE_URL=postgresql://crm_app:<strong-password>@host:5432/crm
--
-- Re-running on an existing role fails on CREATE ROLE — drop it first or
-- comment that line out.
--
-- In local dev (docker compose) the app typically connects as the `postgres`
-- superuser, which bypasses RLS — fine for development, but it means RLS is
-- only actually exercised in production or in the RLS isolation tests.

\set ON_ERROR_STOP on

CREATE ROLE crm_app LOGIN PASSWORD :app_password;

GRANT USAGE ON SCHEMA public TO crm_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO crm_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO crm_app;

-- Tables created by FUTURE migrations get the same grants automatically.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO crm_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO crm_app;

-- The app never needs DDL, and must NOT own any tables (an owner role would
-- bypass plain RLS; FORCE closes that hole, but least privilege is cleaner).
