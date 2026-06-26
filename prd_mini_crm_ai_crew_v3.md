# PRD: Mini CRM AI Crew — Multi-Tenant RBAC (IAM)

**Product:** Mini CRM AI Crew  
**Type:** Internal Tool / Developer Portfolio Project  
**Author:** Anubhav Bansal  
**Version:** 3.0  
**Status:** Planned  
**Builds on:** v2.2 (single-tenant, multi-user) — see `prd_mini_crm_ai_crew_v2.md`  
**Date:** June 12, 2026  
**Changelog:** v3.0 — Introduces multi-tenancy (shared-schema + `tenant_id` discriminator), fixed-role RBAC (Owner/Admin/Member/Viewer) backed by a static permission matrix, Postgres Row-Level Security for hard tenant isolation, admin-created member accounts with temporary passwords + forced first-login reset, tenant-shared product profiles, admin oversight of all members' outreach, a member-management UI, and an audit log.

---

## Problem Statement

v1/v2 assumes **one human per account** — every row (`product_profiles`, `outreach_jobs`, etc.) is keyed directly to `users.id` and isolation is enforced by manually filtering each query on `user_id`. There is no organization concept and no roles.

Real sales teams don't work that way. Multiple SDRs at the same company share one product positioning, and their managers need oversight of the team's outreach without each rep re-describing the product or working in a silo. v3 turns the single-user tool into a **multi-tenant team workspace** with proper Identity & Access Management.

For the portfolio, this demonstrates the multi-tenancy + RBAC patterns every B2B SaaS needs: a shared-schema tenant model, a role/permission system, and **database-enforced** tenant isolation via Postgres RLS — production-grade access-control design, not just app-level checks.

---

## Goal

Add **multi-tenant RBAC** so several employees of the same company can share one workspace with role-scoped capabilities and strict cross-tenant isolation — **without regressing** the existing single-user outreach flows or losing any shipped v1 data.

---

## Target Users / Personas

| Persona | Who | Capabilities |
|---|---|---|
| **Owner** | The person who signs the company up (creates the tenant) | Full control: tenant settings, member management, edit shared config, run/send own outreach, view all outreach. Cannot be removed. |
| **Admin** | A sales manager | Manage members (except Owners), edit shared product profiles, view **all** members' outreach, run/send own outreach. |
| **Member** | An SDR | Use shared product profiles (read-only on config), create/send/view **their own** outreach. |
| **Viewer** | A read-only stakeholder | See shared config and their own (empty) workspace. Cannot create or send. |

---

## User Stories

- As an Owner, I want to register my company and become its first admin, so my team has a shared workspace.
- As an Admin, I want to create accounts for my reps with an assigned role, so they can log in without a public sign-up.
- As a newly created Member, I want to be forced to set my own password on first login, so the admin never knows my credentials.
- As a Member, I want to reuse the company's shared product profile, so I don't re-describe the product.
- As a Member, I want my outreach drafts and history private to me by default.
- As an Admin, I want to view every member's outreach history, so I can coach and audit.
- As an Owner, I want to change a member's role or suspend them, so access reflects their current responsibilities.
- As any user, I must **never** see another company's data — even if a query filter is accidentally omitted.

---

## Tenancy & Identity Model

- **`users`** = global identity only (email, password hash). One user belongs to **exactly one tenant in v3** (multi-tenant membership + a tenant switcher is deferred — see Out of Scope).
- **`tenants`** = the company workspace; holds shared config (`name`, `resend_domain`).
- **`memberships`** = the (user ↔ tenant) link carrying the **role**. Exactly one active membership per user in v3.
- **JWT access token** carries `sub` (user_id), `tenant_id`, and `role`. The refresh token carries the same, so a refreshed access token re-binds tenant + role.

---

## Role → Permission Matrix

Permissions are string keys defined once in code (`backend/app/auth/permissions.py`) as the **single source of truth**. The server is authoritative; the frontend mirrors the resolved permission list (returned by `/auth/me`) only for UX (hiding buttons), never for enforcement.

| Permission | Owner | Admin | Member | Viewer |
|---|:--:|:--:|:--:|:--:|
| `tenant.manage` (rename, set resend_domain, delete tenant) | ✅ | — | — | — |
| `members.view` (see team roster) | ✅ | ✅ | ✅ | ✅ |
| `members.manage` (create / suspend / role-change) | ✅ | ✅¹ | — | — |
| `profile.view` (read shared product profiles) | ✅ | ✅ | ✅ | ✅ |
| `profile.edit` (ingest / save / update / activate profiles) | ✅ | ✅ | — | — |
| `outreach.create` (generate, batch, retry) | ✅ | ✅ | ✅ | — |
| `outreach.send` (approve & send) | ✅ | ✅ | ✅ | — |
| `outreach.view.own` (own jobs / history) | ✅ | ✅ | ✅ | ✅ |
| `outreach.view.all` (all members' outreach in tenant) | ✅ | ✅ | — | — |
| `audit.view` (read audit log) | ✅ | ✅ | — | — |

¹ Admins can manage Members/Viewers but **cannot** modify Owners or promote anyone to Owner. Only an Owner can grant or transfer the Owner role.

---

## Data Visibility Rules

- **Product profiles & ingestion jobs:** scoped by `tenant_id` only — **shared** across the tenant. Mutations require `profile.edit`. "One active profile per tenant" replaces v2's "one active profile per user."
- **Outreach jobs & batch jobs:** scoped by `tenant_id` **and** owned by `user_id`. A member sees rows where `user_id == me`. A user with `outreach.view.all` sees all rows in their tenant. Send/edit/delete remain **owner-only**; `outreach.view.all` is read-only oversight.
- **Mock CRM pipeline** (`/crm/pipeline`): tenant-scoped conceptually (a shared team pipeline); remains mock data in v3.

---

## Isolation Enforcement (defense-in-depth)

1. **App-level:** a `require_context` dependency resolves `(user, tenant_id, role, permissions)` from the JWT, and every query filters on `tenant_id` (plus ownership where applicable). A `require_permission("...")` dependency factory guards mutating and oversight endpoints.
2. **Postgres Row-Level Security (hard boundary):** every tenant-scoped table has RLS enabled with **`FORCE ROW LEVEL SECURITY`** and a policy `tenant_id = current_setting('app.current_tenant_id')::uuid`. The app issues `SET LOCAL app.current_tenant_id = :tid` at the start of each request transaction (after auth resolves the tenant) and inside every ARQ background job. The application connects as a **non-owner, non-superuser DB role** so RLS is never bypassed. This guarantees that even a query which forgets the explicit `tenant_id` filter cannot cross tenants.

---

## Onboarding & Auth Flows

- **Tenant bootstrap (`POST /auth/register`):** creates a `tenant` + the registrant's `user` + an **Owner** `membership` in one transaction. This is the only self-service entry point.
- **Admin creates a member (`POST /members`):** requires `members.manage`. Body `{ email, role }` (role ≠ owner). The server generates a temporary password, creates the `user` with `must_change_password = true` + a `membership` in the caller's tenant, and returns the temp password **once** for the admin to relay (no email send in v3).
- **Forced reset:** the `/auth/login` response includes `must_change_password`. While true, the frontend routes to a change-password screen and the backend rejects all non-auth protected endpoints with `403 PASSWORD_CHANGE_REQUIRED` until `POST /auth/change-password` succeeds.
- **Role change / suspend / remove (`PATCH` / `DELETE /members/:id`):** require `members.manage`. Admins cannot touch Owners; the **last Owner cannot be removed or demoted**.

---

## Functional Requirements

### API Endpoints (new / changed)

| Endpoint | Method | Permission | Notes |
|---|---|---|---|
| `/auth/register` | POST | public | **Changed:** creates tenant + Owner membership |
| `/auth/login` | POST | public | **Changed:** response adds `must_change_password`, `tenant_id`, `role` |
| `/auth/me` | GET | auth | **Changed:** returns `tenant`, `role`, `permissions[]` |
| `/auth/change-password` | POST | auth | **New:** clears `must_change_password` |
| `/tenant` | GET | auth | **New:** current tenant info |
| `/tenant` | PATCH | `tenant.manage` | **New:** rename, set `resend_domain` (moved off user) |
| `/members` | GET | `members.view` | **New:** roster with roles / status |
| `/members` | POST | `members.manage` | **New:** create member, returns temp password once |
| `/members/:id` | PATCH | `members.manage` | **New:** change role / suspend / reactivate |
| `/members/:id` | DELETE | `members.manage` | **New:** remove member |
| `/profile/*` | * | `profile.view` / `profile.edit` | **Changed:** tenant-scoped; mutations need `profile.edit` |
| `/outreach/generate`, `/outreach/batch`, `/outreach/retry/:id` | POST | `outreach.create` | **Changed:** tenant-scoped, owned by caller |
| `/outreach/send/:id` | POST | `outreach.send` | **Changed:** owner-only |
| `/outreach/history` | GET | `outreach.view.own` | **Changed:** `?scope=mine\|all`; `all` requires `outreach.view.all` |
| `/outreach/result/:id`, `/outreach/status/:id`, result PUT | * | own or `outreach.view.all` | **Changed:** tenant + ownership checks |
| `/audit` | GET | `audit.view` | **New:** tenant audit log |

`resend_domain` moves from `users` to `tenants` (shared sending config); the user-level field is migrated accordingly.

### Frontend

- **`AuthContext`** holds `tenant`, `role`, `permissions[]` (sourced from `/auth/me`) and exposes a `can(permission)` helper.
- **Forced password change:** a `ChangePasswordPage` plus an `AppShell` guard redirecting while `must_change_password` is true.
- **Team page** (`/team`, gated by `members.manage`): roster table, "Create member" modal (email + role → shows the temp password once), role dropdown, suspend/remove actions.
- **Tenant settings:** `resend_domain` moves from the user Settings page to a tenant-settings section gated by `tenant.manage`.
- **History page:** a "Mine / All" toggle, visible only with `outreach.view.all`, passed through as `?scope=`.
- **Generate / Result pages:** hide "Generate" / "Approve & Send" for Viewers.
- **Sidebar:** conditional Team and Tenant-settings entries by permission.

---

## Data Model Changes

### New tables

**`tenants`**

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | Primary key |
| `name` | TEXT | Workspace / company name |
| `slug` | TEXT | Optional, unique |
| `resend_domain` | TEXT | Nullable — moved from `users` (shared sending config) |
| `created_at` | TIMESTAMPTZ | |

**`memberships`**

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | Primary key |
| `tenant_id` | UUID | FK → `tenants.id` (CASCADE) |
| `user_id` | UUID | FK → `users.id` (CASCADE) |
| `role` | TEXT | CHECK in `owner \| admin \| member \| viewer` |
| `status` | TEXT | CHECK in `active \| suspended`, default `active` |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |

Constraints: `UNIQUE(user_id)` in v3 (one membership per user) and `UNIQUE(tenant_id, user_id)`.

**`audit_logs`**

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | Primary key |
| `tenant_id` | UUID | FK → `tenants.id` |
| `actor_user_id` | UUID | FK → `users.id` (SET NULL) |
| `action` | TEXT | e.g. `member.created`, `member.role_changed`, `outreach.sent` |
| `target` | TEXT | Affected entity id / description |
| `metadata` | JSONB | Structured details |
| `created_at` | TIMESTAMPTZ | Indexed `(tenant_id, created_at)` |

### Changed tables

- **`users`**: add `must_change_password` (BOOLEAN, default false); **remove** `resend_domain` (→ tenants). Email stays globally unique in v3.
- **`product_profiles`**: add `tenant_id` (FK → tenants, CASCADE, indexed) as the scoping key; keep a nullable `created_by_user_id` (FK → users, SET NULL) for audit. **Replace** the partial unique index `uq_product_profiles_user_id_active` with `uq_product_profiles_tenant_id_active` (one active profile per tenant).
- **`ingestion_jobs`**: add `tenant_id` (FK, CASCADE, indexed); keep `user_id` as creator.
- **`outreach_jobs`**: add `tenant_id` (FK, CASCADE, indexed); keep `user_id` as owner. Add composite index `(tenant_id, user_id, created_at)`.
- **`batch_jobs`**: add `tenant_id` (FK, CASCADE, indexed); keep `user_id` as owner.

### RLS

Enable RLS + `FORCE ROW LEVEL SECURITY` with the `app.current_tenant_id` policy on `product_profiles`, `ingestion_jobs`, `outreach_jobs`, `batch_jobs`, `audit_logs`, and `memberships` (membership policy scoped to tenant). The `tenants` policy scopes by `id = current_setting('app.current_tenant_id')::uuid`.

---

## Data Migration (must not break shipped v1 data)

A single Alembic migration:

1. Create `tenants`, `memberships`, `audit_logs`; add new columns (`tenant_id` **nullable first**, `must_change_password`, `created_by_user_id`).
2. **Backfill:** for each existing `user`, create one `tenant` (name = email local-part + "'s workspace") and an **Owner** `membership`; copy the user's `resend_domain` onto the tenant; set `tenant_id` on all that user's `product_profiles` / `ingestion_jobs` / `outreach_jobs` / `batch_jobs`.
3. Make `tenant_id` **NOT NULL** after backfill; drop `uq_product_profiles_user_id_active`, create the per-tenant active index; drop `users.resend_domain`.
4. Provision (or document the creation of) the **non-owner app DB role**; enable RLS + policies + FORCE on the listed tables.

Existing users keep all their data and become Owners of their own single-member tenant.

**Caveat — one tenant per existing user:** the backfill treats every pre-v3 user as an independent account and gives each their own solo tenant. If two existing users are *actually* colleagues at the same company, the migration has no way to know that and will place them in **separate** tenants — each a solo Owner, with no shared profiles between them. There is no self-service "join an existing tenant" flow in v3, so consolidating them would require a manual data fix (move one user's membership + re-point their rows' `tenant_id`, then delete the orphaned tenant). For the current handful of demo/seed accounts this is a non-issue; it only matters if real shared-company users predate v3.

---

## Non-Functional Requirements

- **Security:** server-side permission checks are authoritative; Postgres RLS is the hard isolation boundary; the app connects as a non-superuser, non-table-owner role so RLS is enforced. Temporary passwords are single-use, force a reset, and are never logged.
- **Backward compatibility:** no data loss; single-user accounts migrate cleanly to single-member tenants.
- **Rate limiting:** keep the per-user outreach rate limit; add an optional **per-tenant monthly token budget** aggregated across members (Redis key `tenant:{tenant_id}:tokens`).
- **Observability:** member/role/tenant mutations and sends recorded in `audit_logs`; structured logs include `tenant_id`.
- **Performance:** all new FKs indexed; the per-request `SET LOCAL` GUC is negligible overhead.

---

## Testing Strategy (additions)

| Layer | Approach |
|---|---|
| **RLS isolation** | Two tenants; assert tenant A's session cannot read or update tenant B's rows **even with a deliberately unfiltered query**. |
| **Permission matrix** | Table-driven — each role × each guarded endpoint → expect 200 / 403. |
| **Member management** | Create / role-change / suspend / remove; Admin-cannot-touch-Owner; last-Owner protection. |
| **Forced reset** | Login returns the flag; protected endpoints 403 until change-password; then 200. |
| **Migration** | Seed v2-shaped data, run migration, assert tenants/memberships created, `tenant_id` backfilled, `resend_domain` moved. |
| **Mock seed** | Extend `MOCK_MODE` seed to create one tenant with Owner + Admin + Member + Viewer. |

---

## Out of Scope (v3)

- Self-service email invitations / invite links.
- SSO / SAML / OIDC / SCIM provisioning.
- Custom roles or granular per-resource ACLs (the matrix is fixed).
- A single user belonging to multiple tenants + tenant switcher.
- Billing / seat enforcement.
- Sharing or transferring an individual outreach draft between members.

---

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Missed `tenant_id` filter leaks cross-tenant data | Postgres RLS + FORCE as a hard backstop; isolation tests |
| App connects as table owner → RLS silently bypassed | Provision/document a dedicated non-owner app role; CI check |
| ARQ jobs run outside a request → GUC unset → RLS blocks all rows | Jobs explicitly `SET LOCAL app.current_tenant_id` from the job's `tenant_id` |
| Migration backfill wrong on prod data | Idempotent, tested migration; nullable → backfill → NOT NULL ordering; dry-run on a copy |
| Admin locks out the tenant (removes all Owners) | Enforce ≥ 1 Owner; block last-Owner demote/remove |
| Temp password leakage | Shown once, forced reset, excluded from logs/responses thereafter |

---

## Milestones

| Phase | Deliverable |
|---|---|
| 1 | Schema + Alembic migration + RLS (models, non-owner DB role); verify backfill on seeded v2 data |
| 2 | Permissions module + auth changes (tokens carry tenant/role, `require_context`, `require_permission`, register → tenant, `/me`) |
| 3 | Member & tenant routers (admin-create, roles, suspend, tenant settings) + audit log |
| 4 | Retrofit profile/outreach routers to tenant scope + visibility rules + history `scope` |
| 5 | ARQ job tenant context (GUC + `tenant_id` propagation) |
| 6 | Frontend — AuthContext/permissions, forced reset, Team page, conditional UI, history toggle |
| 7 | Tests — RLS isolation, permission matrix, member mgmt, migration; update `seed_demo` |
