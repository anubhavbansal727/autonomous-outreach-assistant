# Technical Specification: Mini CRM AI Crew

**Project:** Mini CRM AI Crew — Autonomous B2B Outreach Assistant  
**Author:** Anubhav Bansal  
**Version:** 1.0  
**Date:** May 28, 2026  
**PRD Reference:** `prd_mini_crm_ai_crew_v2.md` (v2.1)

---

## Table of Contents

1. [Overview & Scope](#1-overview--scope)
2. [Project Structure](#2-project-structure)
3. [Technology Stack](#3-technology-stack)
4. [Database Schema](#4-database-schema)
5. [API Specification](#5-api-specification)
6. [Agent & Crew Specification](#6-agent--crew-specification)
7. [Agent Output Schemas](#7-agent-output-schemas)
8. [ARQ Worker Configuration](#8-arq-worker-configuration)
9. [Frontend Architecture](#9-frontend-architecture)
10. [Integration Specifications](#10-integration-specifications)
11. [Environment Variables](#11-environment-variables)
12. [Docker & Deployment](#12-docker--deployment)
13. [Mock Mode Architecture](#13-mock-mode-architecture)

---

## 1. Overview & Scope

This document defines the technical architecture and contracts for the Mini CRM AI Crew system. It is implementation-facing — specifying what gets built and how components connect — without prescribing exact code. For product-level requirements, user stories, and design decisions, see the PRD.

### What this document covers

- Directory and module structure
- All third-party dependency versions
- PostgreSQL schema: tables, columns, types, constraints, indexes
- REST API: every endpoint's request/response shape and error codes
- LangGraph graph definitions: state schemas, nodes, edges, conditional routing, tool functions
- ARQ worker: job functions, retry policy, step-update mechanism
- React frontend: route map, component hierarchy, state management pattern, TypeScript interface contracts
- External integrations: Resend, LangSmith, Serper, Playwright
- Environment variables and Docker service topology
- Mock mode end-to-end behaviour

### What this document defers to the PRD

- User stories and acceptance criteria
- Product design decisions and their rationale
- Success metrics and SLAs
- Risk register and mitigations
- Project milestones

### Stack Summary

| Layer | Technology | Version | Purpose |
| --- | --- | --- | --- |
| API server | FastAPI | 0.115.x | REST endpoints, dependency injection, request validation |
| Data validation | Pydantic | v2.x | Request/response schemas, agent output schemas |
| ORM / migrations | SQLAlchemy (async) + Alembic | 2.x / 1.13.x | DB models, schema migrations |
| DB driver | asyncpg | 0.29.x | Async PostgreSQL driver |
| Job queue | ARQ | 0.25.x | Async Redis-backed job queue for crew runs |
| Agent framework | LangGraph | 0.2.x | Graph-based agent orchestration (nodes, state, edges) |
| Scraping | Playwright | 1.x | Headless browser scraping via custom `@tool` function |
| Search | Serper API | REST | Web search via custom `@tool` function; no wrapper library |
| LLM | OpenAI GPT-4o | via openai SDK 1.x | All agents |
| Email delivery | Resend | 2.x Python SDK | Sending approved outreach emails |
| Observability | LangSmith | via langchain | Agent trace logging |
| Auth | python-jose + passlib[bcrypt] | 3.x / 1.7.x | JWT creation/validation; bcrypt password hashing |
| Package manager | uv | latest | Python 3.12 virtual env and dependency management |
| Frontend framework | React | 18.x | UI |
| Language | TypeScript | 5.x | Type safety across frontend |
| Build tool | Vite | 5.x | Frontend dev server and production bundler |
| Styling | Tailwind CSS | 3.x | Utility-first CSS |
| UI components | shadcn/ui (Radix UI) | latest | Accessible, unstyled component primitives |
| Server state | TanStack Query | v5.x | API fetching, polling, mutation, caching |
| Routing | React Router | v6.x | Client-side navigation |
| Database | PostgreSQL | 16 | Primary data store |
| Cache / queue backend | Redis | 7 | ARQ job queue + rate-limit counters |
| Container | Docker + Compose | 24.x / 2.x | Local dev and production packaging |

---

## 2. Project Structure

```
mini-crm-ai-crew/
├── backend/
│   ├── app/
│   │   ├── main.py                      # FastAPI app factory, router registration, lifespan
│   │   ├── auth/
│   │   │   ├── __init__.py
│   │   │   └── dependencies.py          # get_current_user dependency; X-API-Key validation
│   │   ├── routers/
│   │   │   ├── auth.py                  # POST /auth/register, /auth/login, /auth/refresh, /auth/logout, GET /auth/me
│   │   │   ├── profile.py               # /profile/* endpoints
│   │   │   ├── outreach.py              # /outreach/* endpoints
│   │   │   ├── crm.py                   # GET /crm/pipeline (mock data)
│   │   │   └── health.py                # GET /health
│   │   ├── models/
│   │   │   ├── db.py                    # SQLAlchemy ORM table definitions
│   │   │   └── schemas.py               # Pydantic request/response models
│   │   ├── graphs/
│   │   │   ├── ingestion/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── graph.py             # IngestionGraph: StateGraph definition, nodes, edges
│   │   │   │   └── state.py             # IngestionState TypedDict
│   │   │   └── outreach/
│   │   │       ├── __init__.py
│   │   │       ├── graph.py             # OutreachGraph: StateGraph definition, nodes, edges
│   │   │       └── state.py             # OutreachState TypedDict
│   │   ├── tools/
│   │   │   ├── scrape.py                # @tool: scrape_website(url) → str via Playwright
│   │   │   ├── search.py                # @tool: web_search(query) → str via Serper REST API
│   │   │   └── crm.py                   # @tool: get_crm_pipeline() → str via /crm/pipeline
│   │   ├── jobs/
│   │   │   ├── ingestion_job.py         # ARQ job function: run_ingestion_job
│   │   │   └── outreach_job.py          # ARQ job function: run_outreach_job
│   │   ├── services/
│   │   │   ├── resend.py                # Resend API client wrapper
│   │   │   └── rate_limiter.py          # Redis sliding-window rate limiter
│   │   └── db/
│   │       ├── session.py               # asyncpg session factory + get_db dependency
│   │       └── migrations/              # Alembic env.py + revision files
│   ├── fixtures/
│   │   ├── research_output.json         # Mock ProspectResearchOutput
│   │   ├── outreach_draft.json          # Mock OutreachDraftOutput
│   │   ├── schedule_output.json         # Mock ScheduleOutput
│   │   └── product_profile.json         # Mock ProductProfileOutput
│   ├── scripts/
│   │   └── seed_demo.py                 # Populates DB with demo user + 5 fixture jobs
│   ├── tests/
│   │   ├── unit/                        # Pydantic schema tests, utility tests
│   │   ├── api/                         # httpx TestClient endpoint tests
│   │   └── integration/                 # Full crew run (GPT-4o-mini, sandboxed DB)
│   ├── worker.py                        # ARQ worker entry point
│   ├── alembic.ini
│   └── pyproject.toml
│
├── frontend/
│   ├── src/
│   │   ├── main.tsx                     # React root, QueryClientProvider, Router
│   │   ├── App.tsx                      # Route definitions
│   │   ├── api/
│   │   │   └── client.ts                # apiFetch wrapper; Bearer token injection; 401 auto-refresh; typed errors
│   │   ├── pages/
│   │   │   ├── Onboarding.tsx
│   │   │   ├── Generate.tsx
│   │   │   ├── Result.tsx               # /result/:jobId
│   │   │   ├── History.tsx
│   │   │   └── Settings.tsx
│   │   ├── components/
│   │   │   ├── ui/                      # shadcn/ui primitives (Button, Input, Badge, Table…)
│   │   │   ├── layout/
│   │   │   │   ├── AppShell.tsx         # Sidebar + main content wrapper
│   │   │   │   └── Sidebar.tsx          # Nav links, API key status indicator
│   │   │   ├── onboarding/
│   │   │   │   ├── UrlIngestForm.tsx    # URL input + submit
│   │   │   │   ├── IngestProgress.tsx   # Scraping → Extracting → Done stepper
│   │   │   │   └── ProfileReviewForm.tsx # Editable profile form post-ingestion
│   │   │   ├── outreach/
│   │   │   │   ├── GenerateForm.tsx     # Company + contact inputs + generate button
│   │   │   │   ├── JobProgressStepper.tsx # Research → Personalizing → Scheduling → Done
│   │   │   │   ├── ResultCard.tsx       # Container for email + LinkedIn + schedule
│   │   │   │   ├── EmailEditor.tsx      # Inline-editable subject + body
│   │   │   │   ├── LinkedInEditor.tsx   # Inline-editable LinkedIn note
│   │   │   │   └── ScheduleCard.tsx     # Send timing + flag_for_human alert
│   │   │   └── history/
│   │   │       ├── HistoryTable.tsx     # shadcn Table with job rows
│   │   │       └── PaginationControls.tsx
│   │   ├── hooks/
│   │   │   ├── useJobPolling.ts         # useQuery wrapper; refetchInterval=3000; auto-stops on done/failed
│   │   │   └── useAuth.ts               # Reads AuthContext; exposes { user, accessToken, login, logout }
│   │   ├── types/
│   │   │   └── index.ts                 # All TypeScript interfaces (see Section 9)
│   │   └── lib/
│   │       └── utils.ts                 # cn() class merge helper, date formatting
│   ├── public/
│   ├── index.html
│   ├── vite.config.ts
│   ├── tailwind.config.ts
│   ├── tsconfig.json
│   └── package.json
│
├── docker-compose.yml                   # Local dev (5 services)
├── vercel.json                          # SPA rewrite rule: all paths → index.html
├── .env.example
└── README.md
```

---

## 3. Technology Stack

### Backend Dependencies (`pyproject.toml`)

| Package | Version | Purpose |
| --- | --- | --- |
| `fastapi` | 0.115.x | ASGI web framework |
| `pydantic` | 2.x | Data validation, settings, agent output schemas |
| `uvicorn[standard]` | 0.30.x | ASGI server |
| `sqlalchemy[asyncio]` | 2.x | Async ORM |
| `asyncpg` | 0.29.x | PostgreSQL async driver |
| `alembic` | 1.13.x | Database migrations |
| `arq` | 0.25.x | Async Redis job queue |
| `redis` | 5.x | Redis client (rate limiter) |
| `langgraph` | 0.2.x | Graph-based agent orchestration |
| `langchain-core` | 0.3.x | Base tool/message types used by LangGraph |
| `langchain-openai` | 0.2.x | OpenAI LLM + `with_structured_output()` integration |
| `playwright` | 1.x | Headless browser for JS-heavy scraping (used in `tools/scrape.py`) |
| `httpx` | 0.27.x | Async HTTP — Serper REST calls in `tools/search.py`; test client |
| `openai` | 1.x | GPT-4o API client (used via langchain-openai) |
| `resend` | 2.x | Resend email API client |
| `langsmith` | 0.1.x | LangSmith tracing (auto-enabled via env vars with LangGraph) |
| `python-jose[cryptography]` | 3.x | JWT creation and validation |
| `passlib[bcrypt]` | 1.7.x | Password hashing (bcrypt) |
| `httpx` | 0.27.x | Async HTTP (test client) |
| `pytest` | 8.x | Test runner |
| `pytest-asyncio` | 0.23.x | Async test support |
| `pytest-recording` | 0.13.x | VCR cassette recording for LLM mocks |

**Python version:** 3.12  
**Package manager:** `uv` — `uv sync --frozen` installs from `uv.lock`

### Frontend Dependencies (`package.json`)

| Package | Version | Purpose |
| --- | --- | --- |
| `react` | 18.x | UI framework |
| `react-dom` | 18.x | DOM rendering |
| `typescript` | 5.x | Type safety |
| `vite` | 5.x | Dev server + bundler |
| `@vitejs/plugin-react` | 4.x | React Fast Refresh |
| `@tanstack/react-query` | 5.x | Server state, polling, mutations |
| `react-router-dom` | 6.x | Client-side routing |
| `tailwindcss` | 3.x | Utility CSS |
| `@radix-ui/react-*` | latest | Accessible UI primitives (via shadcn/ui) |
| `class-variance-authority` | 0.7.x | Variant-based component styling |
| `clsx` | 2.x | Conditional class merging |
| `lucide-react` | 0.400.x | Icon library |
| `@tailwindcss/typography` | 0.5.x | Prose styling for email body preview |

**Node version:** 20.x LTS

---

## 4. Database Schema

**Migration strategy:** Alembic with `--autogenerate`. Run `alembic upgrade head` on every deploy (Docker entrypoint for `backend` service). All timestamps stored as `TIMESTAMPTZ` (UTC with offset).

---

### Table: `users`

| Column | Type | Nullable | Default | Constraints |
| --- | --- | --- | --- | --- |
| `id` | UUID | NO | `gen_random_uuid()` | PRIMARY KEY |
| `email` | TEXT | NO | — | UNIQUE |
| `password_hash` | TEXT | NO | — | bcrypt hash; raw password never stored |
| `resend_domain` | TEXT | YES | NULL | Verified sending domain for Resend |
| `created_at` | TIMESTAMPTZ | NO | `NOW()` | — |

**Indexes:**
- `UNIQUE` on `email` — login lookup; must be O(1)

**Notes:** Multi-user, no tenants. All queries for profiles and jobs are scoped to `user_id`. Deleting a user cascades to all their profiles and jobs.

---

### Table: `product_profiles`

| Column | Type | Nullable | Default | Constraints |
| --- | --- | --- | --- | --- |
| `id` | UUID | NO | `gen_random_uuid()` | PRIMARY KEY |
| `user_id` | UUID | NO | — | FK → `users(id)` ON DELETE CASCADE |
| `source_url` | TEXT | YES | NULL | — |
| `product_name` | TEXT | NO | — | — |
| `one_liner` | TEXT | YES | NULL | — |
| `target_customer` | TEXT | YES | NULL | — |
| `pain_points` | TEXT[] | NO | `'{}'` | — |
| `differentiators` | TEXT[] | NO | `'{}'` | — |
| `case_studies` | TEXT[] | NO | `'{}'` | — |
| `cta` | TEXT | YES | NULL | — |
| `icp` | TEXT | YES | NULL | — |
| `avoid_messaging` | TEXT | YES | NULL | Always manually entered; never agent-inferred |
| `is_active` | BOOLEAN | NO | `true` | — |
| `created_at` | TIMESTAMPTZ | NO | `NOW()` | — |
| `updated_at` | TIMESTAMPTZ | NO | `NOW()` | Updated via trigger or application logic |

**Indexes:**
- INDEX on `user_id` — list all profiles per user
- `UNIQUE PARTIAL INDEX` on `(user_id) WHERE is_active = true` — enforces at most one active profile per user; fast lookup for "get my active profile"

---

### Table: `ingestion_jobs`

Tracks the background Ingestion Crew runs initiated by `POST /profile/ingest`.

| Column | Type | Nullable | Default | Constraints |
| --- | --- | --- | --- | --- |
| `id` | UUID | NO | `gen_random_uuid()` | PRIMARY KEY |
| `user_id` | UUID | NO | — | FK → `users(id)` ON DELETE CASCADE |
| `url` | TEXT | NO | — | The URL submitted for ingestion |
| `status` | TEXT | NO | `'running'` | CHECK IN `('running', 'done', 'failed')` |
| `current_step` | TEXT | YES | NULL | CHECK IN `('scraping', 'extracting', 'complete')` |
| `result_json` | JSONB | YES | NULL | Serialised `ProductProfileOutput`; populated on success |
| `error_message` | TEXT | YES | NULL | Populated on failure |
| `created_at` | TIMESTAMPTZ | NO | `NOW()` | — |
| `completed_at` | TIMESTAMPTZ | YES | NULL | — |

**Indexes:**
- INDEX on `user_id` — look up a user's most recent ingestion job

---

### Table: `outreach_jobs`

| Column | Type | Nullable | Default | Constraints |
| --- | --- | --- | --- | --- |
| `id` | UUID | NO | `gen_random_uuid()` | PRIMARY KEY |
| `user_id` | UUID | NO | — | FK → `users(id)` ON DELETE CASCADE |
| `product_profile_id` | UUID | YES | NULL | FK → `product_profiles(id)` ON DELETE SET NULL |
| `company_name` | TEXT | NO | — | — |
| `contact_name` | TEXT | YES | NULL | — |
| `status` | TEXT | NO | `'running'` | CHECK IN `('running', 'done', 'failed')` |
| `current_step` | TEXT | YES | NULL | CHECK IN `('researching', 'personalizing', 'scheduling', 'complete')` |
| `send_status` | TEXT | NO | `'draft'` | CHECK IN `('draft', 'approved', 'sent', 'bounced', 'replied')` |
| `data_confidence` | TEXT | YES | NULL | CHECK IN `('low', 'medium', 'high')` |
| `email_subject` | TEXT | YES | NULL | — |
| `email_draft` | TEXT | YES | NULL | — |
| `linkedin_draft` | TEXT | YES | NULL | — |
| `schedule_json` | JSONB | YES | NULL | Shape: `ScheduleOutput` (see Section 7) |
| `resend_message_id` | TEXT | YES | NULL | Populated after successful Resend send |
| `sent_at` | TIMESTAMPTZ | YES | NULL | — |
| `error_message` | TEXT | YES | NULL | Shown in UI on failure |
| `retry_count` | INTEGER | NO | `0` | Incremented on each retry attempt |
| `token_usage` | INTEGER | YES | NULL | Total tokens across all agents in this run |
| `created_at` | TIMESTAMPTZ | NO | `NOW()` | — |
| `completed_at` | TIMESTAMPTZ | YES | NULL | — |

**Indexes:**
- INDEX on `user_id` — all history queries filter by user
- INDEX on `(user_id, created_at DESC)` — paginated history table (primary sort)
- PARTIAL INDEX on `status WHERE status = 'running'` — job monitoring / health check queries

---

## 5. API Specification

### Authentication

All protected endpoints require the header:
```
Authorization: Bearer <access_token>
```

**Token types:**

| Token | Lifetime | Storage | Purpose |
|---|---|---|---|
| Access token | 30 minutes | Frontend memory (React context) | Authenticates every API request |
| Refresh token | 7 days | `httpOnly; Secure; SameSite=Strict` cookie | Issues new access tokens silently |

**Access token payload (JWT claims):**

| Claim | Value |
|---|---|
| `sub` | `user_id` (UUID string) |
| `exp` | Expiry timestamp |
| `type` | `"access"` |

The backend dependency `get_current_user`:
1. Reads the `Authorization: Bearer` header
2. Decodes and validates the JWT using `JWT_SECRET_KEY`
3. Checks `type == "access"` and `exp` not expired
4. Returns the user row (looked up by `sub`) or raises HTTP 401

**Why access token in memory (not localStorage):** localStorage is readable by any JavaScript on the page (XSS risk). Keeping the access token in React context means it's lost on page refresh — the frontend silently calls `POST /auth/refresh` on mount to restore it using the `httpOnly` cookie, which JS cannot read.

### Standard Error Response Shape

All error responses use:
```
{ "error": "<human-readable message>", "code": "<SNAKE_CASE_CODE>" }
```

Rate limit errors (HTTP 429) additionally include:
```
{ "error": "Rate limit exceeded", "code": "RATE_LIMIT", "retry_after": 3600 }
```

---

### POST `/auth/register` — Register

**Auth:** None (public)

**Request body:**

| Field | Type | Required | Constraints |
| --- | --- | --- | --- |
| `email` | string | YES | Valid email format; max 254 chars |
| `password` | string | YES | Min 8 chars |

**Response (HTTP 201):**

| Field | Type | Description |
| --- | --- | --- |
| `access_token` | string | Short-lived JWT (30 min) |
| `token_type` | string | `"bearer"` |
| `user_id` | string (UUID) | — |

Sets `httpOnly; Secure; SameSite=Strict` cookie containing the refresh token (7 days).

**Errors:** `409 CONFLICT` if email already registered; `422 VALIDATION_ERROR`

---

### POST `/auth/login` — Login

**Auth:** None (public)

**Request body:**

| Field | Type | Required |
| --- | --- | --- |
| `email` | string | YES |
| `password` | string | YES |

**Response (HTTP 200):**

| Field | Type |
| --- | --- |
| `access_token` | string |
| `token_type` | string (`"bearer"`) |
| `user_id` | string (UUID) |

Sets refresh token cookie (same as `/auth/register`).

**Errors:** `401 UNAUTHORIZED` — same message whether email or password is wrong (prevents user enumeration)

---

### POST `/auth/refresh` — Refresh Access Token

**Auth:** Refresh token cookie (no Bearer header)  
**Purpose:** Called silently by the frontend on app load and when the access token nears expiry.

**Response (HTTP 200):**

| Field | Type |
| --- | --- |
| `access_token` | string |
| `token_type` | string (`"bearer"`) |

**Errors:** `401 UNAUTHORIZED` if refresh token is missing, expired, or invalid

---

### POST `/auth/logout` — Logout

**Auth:** Bearer token

**Response (HTTP 200):**

| Field | Type |
| --- | --- |
| `logged_out` | boolean (`true`) |

Clears the refresh token cookie by setting it with `max-age=0`.

---

### GET `/auth/me` — Current User

**Auth:** Bearer token

**Response (HTTP 200):**

| Field | Type |
| --- | --- |
| `user_id` | string (UUID) |
| `email` | string |
| `resend_domain` | string \| null |
| `created_at` | string (ISO 8601) |

**Errors:** `401 UNAUTHORIZED`

---

### POST `/profile/ingest` — Start Ingestion Job

**Auth:** Bearer token

**Request body:**

| Field | Type | Required | Constraints |
| --- | --- | --- | --- |
| `url` | string | YES | Valid `http://` or `https://` URL; max 2048 chars |

**Response (HTTP 202):**

| Field | Type |
| --- | --- |
| `job_id` | string (UUID) |

**Errors:** `422 VALIDATION_ERROR` if URL invalid; `429 RATE_LIMIT` if exceeded.

---

### GET `/profile/result/:id` — Get Ingestion Job Result

**Auth:** Bearer token

**Path param:** `id` — ingestion job UUID

**Response (HTTP 200):**

| Field | Type | Notes |
| --- | --- | --- |
| `job_id` | string | — |
| `status` | string | `running` / `done` / `failed` |
| `current_step` | string \ | null | `scraping` / `extracting` / `complete` |
| `profile` | object \ | null | `ProductProfileOutput` shape (see Section 7); populated when `done` |
| `error_message` | string \ | null | Populated when `failed` |

**Errors:** `404 NOT_FOUND` if job doesn't exist or belongs to another user.

---

### POST `/profile/save` — Save Product Profile

**Auth:** Bearer token  
**Purpose:** Saves a confirmed (user-reviewed) product profile.

**Request body:**

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `product_name` | string | YES | Max 200 chars |
| `one_liner` | string | NO | Max 500 chars |
| `target_customer` | string | NO | Max 500 chars |
| `pain_points` | string[] | NO | Max 10 items, each max 300 chars |
| `differentiators` | string[] | NO | Max 10 items |
| `case_studies` | string[] | NO | Max 5 items |
| `cta` | string | NO | Max 300 chars |
| `icp` | string | NO | Max 500 chars |
| `avoid_messaging` | string | NO | Max 1000 chars; always user-entered |
| `source_url` | string | NO | Original ingestion URL |

**Response (HTTP 201):**

| Field | Type |
| --- | --- |
| `profile_id` | string (UUID) |

**Notes:** Sets `is_active = true` on this profile; deactivates any previous active profile for the user (via the partial unique index constraint).

**Errors:** `422 VALIDATION_ERROR`

---

### PUT `/profile/update` — Update Active Product Profile

**Auth:** Bearer token

**Request body:** Any subset of `POST /profile/save` fields (all optional; at least one required).

**Response (HTTP 200):**

| Field | Type |
| --- | --- |
| `profile_id` | string (UUID) |
| `updated_at` | string (ISO 8601) |

**Errors:** `404 NOT_FOUND` if no active profile exists; `422 VALIDATION_ERROR`

---

### POST `/outreach/generate` — Start Outreach Job

**Auth:** Bearer token

**Request body:**

| Field | Type | Required | Constraints |
| --- | --- | --- | --- |
| `company_name` | string | YES | Max 100 chars; pattern `^[a-zA-Z0-9 \-]+$` |
| `contact_name` | string | NO | Max 100 chars; same pattern |

**Response (HTTP 202):**

| Field | Type |
| --- | --- |
| `job_id` | string (UUID) |

**Errors:**
- `400 NO_ACTIVE_PROFILE` if the user has no active product profile
- `422 VALIDATION_ERROR` on constraint violation
- `429 RATE_LIMIT` if > 10 outreach jobs within the past hour

---

### GET `/outreach/status/:id` — Poll Job Status

**Auth:** Bearer token

**Response (HTTP 200):**

| Field | Type | Notes |
| --- | --- | --- |
| `job_id` | string | — |
| `status` | string | `running` / `done` / `failed` |
| `current_step` | string \ | null | `researching` / `personalizing` / `scheduling` / `complete` |
| `created_at` | string (ISO 8601) | — |

**Errors:** `404 NOT_FOUND`

---

### GET `/outreach/result/:id` — Get Full Outreach Result

**Auth:** Bearer token

**Response (HTTP 200):** Full `OutreachJob` shape (see TypeScript interfaces in Section 9).

Key fields:
| Field | Type | Notes |
| --- | --- | --- |
| `job_id` | string | — |
| `company_name` | string | — |
| `contact_name` | string \ | null | — |
| `status` | string | `done` or `failed` |
| `send_status` | string | `draft` / `approved` / `sent` / `bounced` / `replied` |
| `data_confidence` | string | `low` / `medium` / `high` |
| `email_subject` | string \ | null | — |
| `email_draft` | string \ | null | — |
| `linkedin_draft` | string \ | null | — |
| `schedule_json` | object \ | null | `ScheduleOutput` shape |
| `error_message` | string \ | null | — |
| `token_usage` | integer \ | null | — |
| `created_at` | string (ISO 8601) | — |
| `completed_at` | string (ISO 8601) \ | null | — |

**Errors:** `404 NOT_FOUND`; `409 CONFLICT` if `status = 'running'` (result not ready yet)

---

### PUT `/outreach/result/:id` — Edit Draft In-Place

**Auth:** Bearer token  
**Purpose:** User edits the AI-generated email/LinkedIn content before approving.

**Request body** (all optional; at least one required):

| Field | Type | Notes |
| --- | --- | --- |
| `email_subject` | string | Max 500 chars |
| `email_draft` | string | Max 10,000 chars |
| `linkedin_draft` | string | Max 300 chars |

**Response (HTTP 200):**

| Field | Type |
| --- | --- |
| `updated` | boolean (`true`) |
| `updated_at` | string (ISO 8601) |

**Errors:** `404 NOT_FOUND`; `409 CONFLICT` if `send_status = 'sent'` (cannot edit after send)

---

### POST `/outreach/send/:id` — Approve & Send

**Auth:** Bearer token  
**Purpose:** Human-approved send; calls Resend API; updates job to `sent`.

**Request body:**

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `to_email` | string | YES | Valid email address; prospect's email |

**Response (HTTP 200):**

| Field | Type |
| --- | --- |
| `sent` | boolean (`true`) |
| `resend_message_id` | string |
| `sent_at` | string (ISO 8601) |

**Errors:** `404 NOT_FOUND`; `409 CONFLICT` if `send_status` is already `sent`; `502 UPSTREAM_ERROR` if Resend API call fails (send_status stays `approved`)

---

### POST `/outreach/retry/:id` — Retry Failed Job

**Auth:** Bearer token

**Response (HTTP 202):**

| Field | Type |
| --- | --- |
| `job_id` | string |
| `retry_count` | integer |

**Errors:** `404 NOT_FOUND`; `409 CONFLICT` if `status != 'failed'`; `429 RATE_LIMIT`

---

### GET `/outreach/history` — List Past Runs

**Auth:** Bearer token

**Query params:**

| Param | Type | Default | Max |
| --- | --- | --- | --- |
| `page` | integer | 1 | — |
| `per_page` | integer | 20 | 100 |

**Response (HTTP 200):**

| Field | Type |
| --- | --- |
| `items` | `HistoryItem[]` |
| `total` | integer |
| `page` | integer |
| `per_page` | integer |

Each `HistoryItem` includes: `id`, `company_name`, `contact_name`, `status`, `send_status`, `data_confidence`, `token_usage`, `created_at`, `sent_at`.

Ordered by `created_at DESC`.

---

### DELETE `/outreach/:id` — Delete Job (GDPR)

**Auth:** Bearer token  
**Purpose:** Hard-deletes the job row and all its draft content.

**Response (HTTP 200):**

| Field | Type |
| --- | --- |
| `deleted` | boolean (`true`) |

**Errors:** `404 NOT_FOUND`

---

### GET `/crm/pipeline` — Mock CRM Records

**Auth:** Bearer token  
**Purpose:** Used by the Scheduler Agent as a tool to check pipeline status.

**Response (HTTP 200):**

| Field | Type |
| --- | --- |
| `records` | `CRMRecord[]` |

Each `CRMRecord`:

| Field | Type | Notes |
| --- | --- | --- |
| `company_name` | string | — |
| `contact_name` | string \ | null | — |
| `stage` | string | `exploring` / `demo_booked` / `negotiating` / `closed_won` / `closed_lost` |
| `last_contacted` | string (YYYY-MM-DD) | — |

---

### GET `/health` — Health Check

**Auth:** None

**Response (HTTP 200):**

| Field | Type | Notes |
| --- | --- | --- |
| `status` | string | `ok` |
| `db` | string | `ok` / `error` |
| `redis` | string | `ok` / `error` |

Returns HTTP 200 even if `db` or `redis` is `error` — callers should check sub-fields.

---

## 6. Agent Graph Specification

LangGraph represents each pipeline as a `StateGraph` — a directed graph of Python nodes connected by edges. All nodes share a typed state object; each node reads fields it needs and writes its results back to state. No YAML config files; all logic is explicit Python.

**Graph compile option:** `recursion_limit=10` on both graphs — caps the Research Agent's ReAct loop and prevents infinite tool-call cycles.

**Source file locations:**

```
backend/app/graphs/ingestion/state.py   # IngestionState TypedDict
backend/app/graphs/ingestion/graph.py   # IngestionGraph: nodes + edges compiled into StateGraph
backend/app/graphs/outreach/state.py    # OutreachState TypedDict
backend/app/graphs/outreach/graph.py    # OutreachGraph: nodes + edges compiled into StateGraph
backend/app/tools/scrape.py             # @tool: scrape_website
backend/app/tools/search.py             # @tool: web_search
backend/app/tools/crm.py                # @tool: get_crm_pipeline
```

---

### Graph 1: Ingestion Graph

**Purpose:** Scrapes the seller's product website and extracts a structured product profile.  
**Triggered by:** `run_ingestion_job` ARQ job.  
**Inputs:** `{ url: str }`

#### `IngestionState` fields

| Field | Type | Set by |
|---|---|---|
| `url` | `str` | Input |
| `scraped_pages` | `list[ScrapedPage]` | `scrape_node` |
| `product_profile` | `ProductProfileOutput \| None` | `extract_node` |
| `error` | `str \| None` | Either node on failure |

#### Nodes

**`scrape_node`** — Pure Python (no LLM)
- Calls `scrape_website` tool for each target path: homepage, `/pricing`, `/about`, `/customers`, `/case-studies`
- Runs all page scrapes concurrently (`asyncio.gather`)
- Writes `scraped_pages` to state; records failed URLs in each `ScrapedPage.scraped = false`
- No LLM involved — direct Playwright calls

**`extract_node`** — LLM node
| Property | Value |
|---|---|
| LLM | GPT-4o via `langchain-openai` |
| Temperature | 0.2 |
| Output binding | `llm.with_structured_output(ProductProfileOutput)` |
| System prompt intent | B2B SaaS product positioning expert; infer ICP, pain points, differentiators, CTAs from scraped marketing copy |
| Missing fields | Populate `missing_fields[]` with field names that could not be inferred; never hallucinate |
| Input from state | `scraped_pages` (all page content concatenated into context) |

#### Edges

```
START → scrape_node → extract_node → END
```

Linear — no conditional routing needed.

---

### Graph 2: Outreach Graph

**Purpose:** Researches a prospect company, writes personalised outreach, and recommends send timing.  
**Triggered by:** `run_outreach_job` ARQ job.  
**Inputs:** `{ company_name, contact_name, product_profile, avoid_messaging }`

#### `OutreachState` fields

| Field | Type | Set by |
|---|---|---|
| `company_name` | `str` | Input |
| `contact_name` | `str \| None` | Input |
| `product_profile` | `dict` | Input (serialised `ProductProfileOutput`) |
| `avoid_messaging` | `str` | Input |
| `research_messages` | `list[BaseMessage]` | `research_node` / `research_tools_node` (ReAct loop) |
| `research_output` | `ProspectResearchOutput \| None` | `research_node` (on loop completion) |
| `outreach_draft` | `OutreachDraftOutput \| None` | `personalize_node` |
| `schedule_messages` | `list[BaseMessage]` | `schedule_node` / `schedule_tools_node` |
| `schedule_output` | `ScheduleOutput \| None` | `schedule_node` (on loop completion) |
| `error` | `str \| None` | Any node on failure |

#### Nodes

**`research_node`** — ReAct agent (LLM with tools)
| Property | Value |
|---|---|
| LLM | GPT-4o, temperature 0.1, tools bound: `[web_search, scrape_website]` |
| Pattern | ReAct loop: LLM decides whether to call a tool or return final answer |
| System prompt intent | B2B research analyst; uncover firmographics, tech stack, recent signals |
| Serper queries | (1) `"{company_name}" company B2B overview industry employees` (2) `"{company_name}" funding news product launch 2025 2026` |
| On completion | Parses final message into `ProspectResearchOutput` via `with_structured_output()`; writes to state |

**`research_tools_node`** — `ToolNode([web_search, scrape_website])`
- Executes whichever tool the Research Agent called
- Appends tool result to `research_messages`
- Returns to `research_node`

**`personalize_node`** — LLM node (no tools)
| Property | Value |
|---|---|
| LLM | GPT-4o, temperature 0.7 |
| Output binding | `with_structured_output(OutreachDraftOutput)` |
| System prompt intent | B2B copywriter; connect prospect pain points to product capabilities; feel researched, not templated |
| Negative constraint | System prompt includes: *"Do not mention or imply: {avoid_messaging}. This is a strict constraint."* |
| Degraded-state instruction | *"If research data is sparse, write a strong semi-personalised email from industry and size alone. Do not hallucinate specifics."* |
| Input from state | `research_output`, `product_profile`, `avoid_messaging` |

**`schedule_node`** — ReAct agent (LLM with one tool)
| Property | Value |
|---|---|
| LLM | GPT-4o, temperature 0.1, tools bound: `[get_crm_pipeline]` |
| System prompt intent | Outbound sales timing expert; infer time zone from HQ location; flag pipeline conflicts |
| Decision signals | (1) HQ timezone → Tue–Thu 9–11am local; (2) funding/launch news → `priority: high`; (3) CRM match → `flag_for_human: true` |
| On completion | Parses final message into `ScheduleOutput`; writes to state |

**`schedule_tools_node`** — `ToolNode([get_crm_pipeline])`

#### Edges

```
START → research_node
research_node ──(has tool calls?)──► research_tools_node → research_node  (loop)
research_node ──(no tool calls)───► personalize_node
personalize_node → schedule_node
schedule_node ──(has tool calls?)──► schedule_tools_node → schedule_node  (loop)
schedule_node ──(no tool calls)───► END
```

Both loops use a conditional edge function that inspects the last message in the respective `messages` list: if it contains tool call requests, route to the tool node; otherwise continue forward.

---

### Tool Definitions

All tools are plain Python functions decorated with `@tool` from `langchain-core`. No wrapper libraries.

#### `scrape_website(url: str) -> str`
- File: `backend/app/tools/scrape.py`
- Uses `async_playwright()` to launch Chromium (headless), navigate to `url`, wait for `networkidle`, extract `page.inner_text("body")`
- Timeout: 15,000ms
- On error: returns `"SCRAPE_FAILED: {url}"` string (agent sees this and adjusts)

#### `web_search(query: str, n_results: int = 5) -> str`
- File: `backend/app/tools/search.py`
- Makes `POST https://google.serper.dev/search` with `{ q: query, num: n_results }`
- Auth: `X-API-Key: {SERPER_API_KEY}` header
- Returns JSON string of search results (organic + news items)

#### `get_crm_pipeline() -> str`
- File: `backend/app/tools/crm.py`
- Direct Python function call — imports and calls the CRM data service function directly (no HTTP, no auth token needed)
- The ARQ worker runs in the same Python process as the app; calling internal functions is simpler and more reliable than looping back through HTTP
- Returns JSON string of `CRMRecord[]`

---

## 7. Agent Output Schemas

These are Pydantic model contracts. All `output_pydantic` fields in CrewAI tasks map to one of these shapes.

---

### `ScrapeOutput`

| Field | Type | Notes |
| --- | --- | --- |
| `raw_pages` | `ScrapedPage[]` | One entry per URL attempted |
| `scrape_success` | boolean | `true` if at least homepage returned content |
| `failed_pages` | string[] | URLs that returned empty or error |

**`ScrapedPage`:**

| Field | Type |
| --- | --- |
| `url` | string |
| `content` | string (raw text) |
| `scraped` | boolean |

---

### `ProductProfileOutput`

| Field | Type | Notes |
| --- | --- | --- |
| `product_name` | string | — |
| `one_liner` | string \ | null | One sentence value prop |
| `target_customer` | string \ | null | — |
| `pain_points` | string[] | Max 8 items |
| `differentiators` | string[] | Max 8 items |
| `case_studies` | string[] | Short summaries; max 5 items |
| `cta` | string \ | null | Primary call to action |
| `icp` | string \ | null | Ideal customer profile description |
| `extraction_confidence` | string | `low` / `medium` / `high` |
| `missing_fields` | string[] | Field names that could not be inferred |

---

### `ProspectResearchOutput`

| Field | Type | Notes |
| --- | --- | --- |
| `company_name` | string | Normalised/confirmed name |
| `industry` | string \ | null | e.g., "B2B SaaS / HR Tech" |
| `size` | string \ | null | e.g., "50–200 employees" |
| `hq_location` | string \ | null | "City, Country" |
| `hq_timezone` | string \ | null | IANA tz string, e.g., `"America/Chicago"` |
| `pain_points` | string[] | Inferred from website + news |
| `tech_stack` | string[] | Inferred from job postings, integrations pages |
| `recent_news` | `NewsItem[]` | Funding, launches, partnerships |
| `website_url` | string \ | null | Canonical company website |
| `scrape_success` | boolean | Whether website scraping returned useful data |

**`NewsItem`:**

| Field | Type | Notes |
| --- | --- | --- |
| `headline` | string | — |
| `date` | string | YYYY-MM-DD or year only |
| `signal_type` | string | `funding` / `launch` / `partnership` / `other` |

---

### `OutreachDraftOutput`

| Field | Type | Notes |
| --- | --- | --- |
| `email_subject` | string | Max 100 chars; no emojis |
| `email_body` | string | Plain text; ~150–200 words; no HTML |
| `linkedin_note` | string | Plain text; max 300 chars |
| `data_confidence` | string | `low` / `medium` / `high`; agent self-assessment |
| `personalization_signals` | string[] | Specific details used, e.g., "Series B funding", "uses Salesforce" |

---

### `ScheduleOutput`

| Field | Type | Notes |
| --- | --- | --- |
| `send_at` | string | ISO 8601 with tz offset, e.g., `"2026-06-03T09:30:00-05:00"` |
| `channel` | string | Always `"email"` in v1 |
| `recommended_window` | string | Human-readable, e.g., `"Tue–Thu 9–11am CT"` |
| `priority` | string | `"high"` / `"normal"` |
| `flag_for_human` | boolean | `true` if prospect is in CRM pipeline |
| `flag_reason` | string \ | null | e.g., `"Prospect in pipeline at 'negotiating' stage"` |

---

## 8. ARQ Worker Configuration

### Worker Entry Point: `backend/worker.py`

The worker process connects to Redis and listens for jobs enqueued by the FastAPI backend.

**Worker settings:**

| Setting | Value | Notes |
| --- | --- | --- |
| `max_jobs` | 10 | Max concurrent jobs |
| `job_timeout` | 120 seconds | Per-job hard timeout; job marked `failed` on breach |
| `keep_result` | 3600 seconds | Result kept in Redis for 1 hour (for deduplication) |
| `retry_jobs` | `true` | Enable automatic retries |
| `max_tries` | 3 | Total attempts (1 original + 2 retries) |

**Retry backoff:** Exponential — attempt 1 immediate, attempt 2 after 1s, attempt 3 after 2s. After 3 failed attempts, job is marked `failed` and `error_message` is written to DB.

### Job: `run_ingestion_job`

| Property | Value |
| --- | --- |
| Parameters | `ctx`, `job_id: str`, `user_id: str`, `url: str` |
| Returns | `None` (writes results directly to DB) |
| Step updates | Writes `current_step` to `ingestion_jobs` row at: `"scraping"` → `"extracting"` → `"complete"` |
| On success | Writes `result_json`, sets `status="done"`, `completed_at=now()` |
| On failure | Writes `error_message`, sets `status="failed"`; ARQ retries up to `max_tries` |
| Mock mode | Loads `fixtures/product_profile.json`; simulates step progression with 2s delays |

### Job: `run_outreach_job`

| Property | Value |
| --- | --- |
| Parameters | `ctx`, `job_id: str`, `user_id: str`, `company_name: str`, `contact_name: str \ | None`,` product_profile: dict` |
| Returns | `None` |
| Step updates | Writes `current_step` to `outreach_jobs` between tasks: `"researching"` → `"personalizing"` → `"scheduling"` → `"complete"` |
| On success | Writes `email_subject`, `email_draft`, `linkedin_draft`, `schedule_json`, `data_confidence`, `token_usage`; sets `status="done"` |
| On failure | Writes `error_message`; increments `retry_count`; sets `status="failed"` |
| Mock mode | Loads fixture JSONs; simulates step progression with 2s delays between steps |

**Step-update mechanism:** The ARQ job function calls `graph.astream(initial_state)` and iterates over the stream of node-completion events. Each event carries the node name that just finished; the job function maps node names to `current_step` values and writes to DB:

| Node event | `current_step` written |
|---|---|
| `research_node` completes | `"researching"` |
| `personalize_node` completes | `"personalizing"` |
| `schedule_node` completes | `"scheduling"` |
| Graph reaches END | `"complete"` |

This is cleaner than manual writes between calls — the stream naturally delivers one event per node completion with no extra instrumentation.

---

## 9. Frontend Architecture

### Routes (React Router v6)

| Path | Component | Auth Guard | Notes |
| --- | --- | --- | --- |
| `/login` | `Login` | None | Redirects to `/` if already logged in |
| `/register` | `Register` | None | Redirects to `/` if already logged in |
| `/` | `Onboarding` | `<RequireAuth>` | Redirects to `/generate` if active profile exists |
| `/generate` | `Generate` | `<RequireAuth>` | Redirects to `/` if no profile |
| `/result/:jobId` | `Result` | `<RequireAuth>` | — |
| `/history` | `History` | `<RequireAuth>` | — |
| `/settings` | `Settings` | `<RequireAuth>` | — |

**Auth guard pattern:** `<RequireAuth>` reads the access token from `AuthContext`. If absent, redirects to `/login`. On every app load, the root component silently calls `POST /auth/refresh` using the `httpOnly` cookie — success restores the access token in context; failure (expired/missing cookie) sends the user to `/login`.

### Component Hierarchy

```
App.tsx
└── QueryClientProvider
    └── AuthProvider                     — holds access token in context; exposes login/logout/refresh
        └── Router
            └── AppShell
                ├── Sidebar (nav links, user email, logout button)
                └── <Outlet> (page content)
                    ├── LoginPage            — email + password form; calls POST /auth/login
                    ├── RegisterPage         — email + password form; calls POST /auth/register
                    ├── OnboardingPage
                    │   ├── UrlIngestForm        — URL input + submit; triggers POST /profile/ingest
                │   ├── IngestProgress       — polls /profile/result/:id; Scraping→Extracting→Done stepper
                │   └── ProfileReviewForm    — editable fields for all profile properties
                │       └── ProfileFieldArray — reusable list-of-strings editor (pain_points, etc.)
                │
                ├── GeneratePage
                │   ├── GenerateForm         — company name + contact; submit triggers POST /outreach/generate
                │   └── JobProgressStepper   — Research→Personalizing→Scheduling→Done; polls /status/:id
                │
                ├── ResultPage
                │   ├── DataConfidenceBadge  — low/medium/high colour pill
                │   ├── EmailResultCard
                │   │   ├── SubjectLine      — inline editable (edit mode)
                │   │   ├── EmailBody        — inline editable (edit mode), typography prose styles
                │   │   ├── EditToggleButton
                │   │   └── ApproveSendButton → opens SendDialog
                │   │       └── SendDialog   — email input, confirm send, calls POST /outreach/send/:id
                │   ├── LinkedInCard         — inline editable; char counter (max 300)
                │   ├── ScheduleCard         — send_at, recommended_window, priority badge
                │   │   └── FlagAlert        — amber banner if flag_for_human = true
                │   └── RetryButton          — visible only when status = 'failed'
                │
                ├── HistoryPage
                │   ├── HistoryTable         — shadcn Table
                │   │   └── HistoryTableRow  — per-job row with status/send_status badges
                │   └── PaginationControls
                │
                └── SettingsPage
                    ├── AccountSection       — email display, change password (v2), logout
                    └── ActiveProfileCard    — profile summary, edit button
```

### State Management

**TanStack Query is the single source of truth for all server state.**

| Query Key | Endpoint | `staleTime` | Notes |
| --- | --- | --- | --- |
| `['profile', 'active']` | `GET /profile/result/active` | 5 minutes | Active product profile |
| `['outreach', 'status', jobId]` | `GET /outreach/status/:id` | 0 | Polling; `refetchInterval: 3000`; disabled when `status !== 'running'` |
| `['outreach', 'result', jobId]` | `GET /outreach/result/:id` | 30 seconds | Fetched once on ResultPage mount |
| `['outreach', 'history']` | `GET /outreach/history` | 60 seconds | Paginated |
| `['crm', 'pipeline']` | Internal — not fetched by frontend | — | Backend only |

**`useJobPolling` hook:**
- Wraps `useQuery` with `refetchInterval: (data) => data?.status === 'running' ? 3000 : false`
- Automatically stops polling once `status` is `done` or `failed`
- Optionally accepts an `onComplete(result)` callback

**Mutations:**
- `POST /outreach/generate` → `useMutation`; on success, navigate to `/result/:jobId`
- `PUT /outreach/result/:id` → `useMutation`; on success, invalidate `['outreach', 'result', jobId]`
- `POST /outreach/send/:id` → `useMutation`; on success, invalidate result query
- `POST /outreach/retry/:id` → `useMutation`; on success, restart polling
- `POST /profile/save` → `useMutation`; on success, navigate to `/generate`

**Local `useState` only for:**
- Edit mode toggle on `EmailResultCard` / `LinkedInCard`
- `SendDialog` open/closed
- `ProfileFieldArray` add/remove interactions

### TypeScript Interface Contracts

Defined in `src/types/index.ts`. All date fields are ISO 8601 strings.

**`User`**

| Field | Type |
| --- | --- |
| `id` | string |
| `email` | string |
| `resend_domain` | string \ | null |
| `created_at` | string |

**`ProductProfile`**

| Field | Type |
| --- | --- |
| `id` | string |
| `user_id` | string |
| `source_url` | string \ | null |
| `product_name` | string |
| `one_liner` | string \ | null |
| `target_customer` | string \ | null |
| `pain_points` | string[] |
| `differentiators` | string[] |
| `case_studies` | string[] |
| `cta` | string \ | null |
| `icp` | string \ | null |
| `avoid_messaging` | string \ | null |
| `is_active` | boolean |
| `created_at` | string |
| `updated_at` | string |

**`ScheduleOutput`**

| Field | Type |
| --- | --- |
| `send_at` | string |
| `channel` | `'email'` |
| `recommended_window` | string |
| `priority` | `'high' \ | 'normal'` |
| `flag_for_human` | boolean |
| `flag_reason` | string \ | null |

**`OutreachJob`**

| Field | Type |
| --- | --- |
| `id` | string |
| `user_id` | string |
| `product_profile_id` | string \ | null |
| `company_name` | string |
| `contact_name` | string \ | null |
| `status` | `'running' \ | 'done' \ | 'failed'` |
| `current_step` | `'researching' \ | 'personalizing' \ | 'scheduling' \ | 'complete' \ | null` |
| `send_status` | `'draft' \ | 'approved' \ | 'sent' \ | 'bounced' \ | 'replied'` |
| `data_confidence` | `'low' \ | 'medium' \ | 'high' \ | null` |
| `email_subject` | string \ | null |
| `email_draft` | string \ | null |
| `linkedin_draft` | string \ | null |
| `schedule_json` | `ScheduleOutput \ | null` |
| `resend_message_id` | string \ | null |
| `sent_at` | string \ | null |
| `error_message` | string \ | null |
| `retry_count` | number |
| `token_usage` | number \ | null |
| `created_at` | string |
| `completed_at` | string \ | null |

**`HistoryItem`** (subset of `OutreachJob` for list views)

| Field | Type |
| --- | --- |
| `id` | string |
| `company_name` | string |
| `contact_name` | string \ | null |
| `status` | string |
| `send_status` | string |
| `data_confidence` | string \ | null |
| `token_usage` | number \ | null |
| `created_at` | string |
| `sent_at` | string \ | null |

**`JobStatusResponse`**

| Field | Type |
| --- | --- |
| `job_id` | string |
| `status` | `'running' \ | 'done' \ | 'failed'` |
| `current_step` | string \ | null |
| `created_at` | string |

**`CRMRecord`**

| Field | Type |
| --- | --- |
| `company_name` | string |
| `contact_name` | string \ | null |
| `stage` | `'exploring' \ | 'demo_booked' \ | 'negotiating' \ | 'closed_won' \ | 'closed_lost'` |
| `last_contacted` | string |

**`ApiError`**

| Field | Type |
| --- | --- |
| `error` | string |
| `code` | string |
| `retry_after` | number \ | undefined |

### API Client (`src/api/client.ts`)

- Single `apiFetch(path: string, options?: RequestInit): Promise<T>` function
- Prepends `VITE_API_BASE_URL` to every path
- Injects `Authorization: Bearer <accessToken>` header; reads token from `AuthContext` via a module-level setter (context sets the token on login; client reads it on each call)
- On `401` response: triggers silent token refresh via `POST /auth/refresh`, then retries the original request once
- On non-2xx response after retry: parses body as `ApiError` and throws it; if refresh also fails, clears auth context and redirects to `/login`
- All API hooks/mutations import and call this function — never use `fetch` directly in components

---

## 10. Integration Specifications

### Resend API

**Endpoint:** `POST `https://api.resend.com/emails`  
**Auth:** `Authorization: Bearer {RESEND_API_KEY}`  
**SDK:** `resend` Python SDK v2.x (wraps the REST call)

**Request payload fields:**

| Field | Value | Notes |
| --- | --- | --- |
| `from` | `{product_name} <outreach@{resend_domain}>` | `product_name` from active profile; `resend_domain` from `users.resend_domain` |
| `to` | `["<prospect_email>"]` | Single recipient in v1 |
| `subject` | `outreach_jobs.email_subject` | — |
| `html` | HTML-wrapped `outreach_jobs.email_draft` | Convert newlines to `<br>`, wrap in `<p>` |
| `headers` | `{ "List-Unsubscribe": "<mailto:unsubscribe@{resend_domain}>" }` | CAN-SPAM compliance |

**Success:** Returns `{ id: string }` → stored as `outreach_jobs.resend_message_id`

**Failure handling:**  
If Resend returns a non-2xx response, the backend returns HTTP 502 to the frontend. The job's `send_status` remains `approved` (not `sent`) — user can retry the send. The error details are logged but not stored on the job row (transient send failure, not a data failure).

**Pre-condition:** `users.resend_domain` must be non-null. If null, `POST /outreach/send/:id` returns HTTP 400 `DOMAIN_NOT_CONFIGURED` before calling Resend.

---

### LangSmith

**Setup (environment variables):**

| Variable | Value |
| --- | --- |
| `LANGCHAIN_TRACING_V2` | `"true"` |
| `LANGCHAIN_API_KEY` | Smith API key from `smith.langchain.com` |
| `LANGCHAIN_PROJECT` | `"mini-crm-ai-crew"` |

**Integration mechanism:** LangGraph has native LangSmith tracing. Setting the three environment variables is sufficient — every `graph.astream()` / `graph.ainvoke()` call is automatically traced as a LangGraph run. Each node appears as a child span with its inputs, outputs, and latency. No explicit callback registration needed.

**Run naming convention:** Each crew run is named `{crew_name}/{job_id}` (e.g., `outreach/3f4a...`). This is set via the `name` parameter in `crew.kickoff()` or via `LANGCHAIN_RUN_NAME`.

**PII exclusion policy:**
- Do NOT pass `contact_name` or prospect email addresses as crew inputs, metadata tags, or run names
- Use `job_id` as the identifier in all trace labels
- `company_name` may appear in traces (it is not PII)

---

### Serper API (Research Agent)

**Tool:** `SerperDevTool(n_results=5)` from `crewai_tools`  
**Auth:** Tool reads `SERPER_API_KEY` from environment automatically  
**Free tier:** 2,500 queries/month — documented in `.env.example`

**Search query structure used by Research Agent:**

| Query | Purpose |
| --- | --- |
| `"{company_name}" company B2B overview industry employees` | Firmographics |
| `"{company_name}" funding news product launch 2025 2026` | Recent signals |

The Research Agent executes these searches via tool calls during its task execution. The tool returns JSON search results which the agent parses into `ProspectResearchOutput`.

---

### ScrapeWebsiteTool (Playwright)

**Tool:** `ScrapeWebsiteTool` from `crewai_tools`  
**Browser:** Playwright Chromium, headless  
**Timeout:** 15,000ms per page load  
**Playwright install:** Run `playwright install chromium` during Docker image build

**Usage in Ingestion Crew (Scraper Agent):**  
Called once per target URL path. Target paths: homepage, `/pricing`, `/about`, `/customers`, `/case-studies`. If a path returns a 404 or empty content, it is recorded in `ScrapeOutput.failed_pages[]` and execution continues.

**Usage in Outreach Crew (Research Agent):**  
Called on the prospect's homepage URL (obtained from Serper search results). One call only.

---

## 11. Environment Variables

All variables defined in `.env` at the project root. `.env.example` is committed to the repository with descriptions but no values.

| Variable | Required | Description | Where to obtain |
| --- | --- | --- | --- |
| `OPENAI_API_KEY` | YES | OpenAI API key for all agent LLM calls | platform.openai.com → API Keys |
| `SERPER_API_KEY` | YES | Serper web search API key (2,500 free queries/month) | serper.dev → Dashboard → API Key |
| `DATABASE_URL` | YES | PostgreSQL async connection string | Format: `postgresql+asyncpg://user:pass@host:5432/dbname` |
| `REDIS_URL` | YES | Redis connection string | Format: `redis://localhost:6379` |
| `JWT_SECRET_KEY` | YES | Secret used to sign all JWTs | Generate with `openssl rand -hex 32`; rotating this invalidates all active sessions |
| `JWT_ALGORITHM` | NO | JWT signing algorithm | Default: `HS256` |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | NO | Access token lifetime in minutes | Default: `30` |
| `JWT_REFRESH_TOKEN_EXPIRE_DAYS` | NO | Refresh token lifetime in days | Default: `7` |
| `RESEND_API_KEY` | YES (for send flow) | Resend API key; domain must be verified before sends work | resend.com → API Keys |
| `LANGCHAIN_API_KEY` | NO | LangSmith tracing API key | smith.langchain.com → Settings → API Keys |
| `LANGCHAIN_TRACING_V2` | NO | Set to `"true"` to enable LangSmith tracing | — |
| `LANGCHAIN_PROJECT` | NO | LangSmith project name | Default: `"mini-crm-ai-crew"` |
| `MOCK_MODE` | NO | Set to `"true"` to bypass all LLM/API calls | Dev/demo use only |
| `VITE_API_BASE_URL` | YES (frontend) | Backend URL for API client | Dev: `http://localhost:8000`; Prod: deployed backend URL |

**Note on `JWT_SECRET_KEY`:** Rotating this key invalidates all existing access and refresh tokens — every user gets logged out immediately. For planned rotation, implement a grace period by temporarily accepting both old and new keys.

---

## 12. Docker & Deployment

### `docker-compose.yml` — Local Development (5 services)

#### Service: `postgres`

| Setting | Value |
| --- | --- |
| Image | `postgres:16-alpine` |
| Port | `5432:5432` |
| Volume | `postgres_data:/var/lib/postgresql/data` |
| Env vars | `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` |
| Health check | `pg_isready -U ${POSTGRES_USER}` every 5s |

#### Service: `redis`

| Setting | Value |
| --- | --- |
| Image | `redis:7-alpine` |
| Port | `6379:6379` |
| Volume | `redis_data:/data` |
| Command | `redis-server --appendonly yes` (AOF persistence — jobs survive Redis restart) |
| Health check | `redis-cli ping` every 5s |

#### Service: `backend`

| Setting | Value |
| --- | --- |
| Build context | `./backend` |
| Port | `8000:8000` |
| Depends on | `postgres` (healthy), `redis` (healthy) |
| Command | `sh -c "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"` |
| Env | All variables from `.env` |
| Health check | `GET http://localhost:8000/health` every 10s |

#### Service: `worker`

| Setting | Value |
| --- | --- |
| Build context | `./backend` (same image as `backend`) |
| Port | None |
| Depends on | `postgres` (healthy), `redis` (healthy) |
| Command | `python worker.py` |
| Env | All variables from `.env` |

#### Service: `frontend`

| Setting | Value |
| --- | --- |
| Build context | `./frontend` |
| Port | `5173:5173` |
| Depends on | `backend` |
| Command | `npm run dev -- --host` (Vite dev server, LAN-accessible) |

---

### Dockerfiles

#### `backend/Dockerfile` (multi-stage)

| Stage | Base image | Key actions |
| --- | --- | --- |
| `builder` | `python:3.12-slim` | Install `uv`; copy `pyproject.toml` + `uv.lock`; run `uv sync --frozen`; install Playwright Chromium |
| `runtime` | `python:3.12-slim` | Copy virtual env from builder; copy app code; create non-root user `appuser`; expose port 8000 |

#### `frontend/Dockerfile` (multi-stage)

| Stage | Base image | Key actions |
| --- | --- | --- |
| `builder` | `node:20-alpine` | `npm ci`; `npm run build` |
| `runtime` | `nginx:alpine` | Copy `dist/` from builder; add `nginx.conf` routing all paths to `index.html` (SPA fallback) |

---

### Health Check Endpoint

`GET /health` is used by:
- Docker `HEALTHCHECK` directive for the `backend` service
- Load balancer readiness probes on Cloud Run

Returns HTTP 200 with `{ "status": "ok", "db": "ok"|"error", "redis": "ok"|"error" }`. Always returns 200 — callers must inspect sub-fields. The `/health` endpoint itself runs a lightweight `SELECT 1` on the DB and a `PING` on Redis.

---

### Production Deployment: Railway + Vercel

All backend services (API, worker, Postgres, Redis) deploy to Railway under a single Hobby plan ($5/month, includes $5 usage credit). The frontend deploys to Vercel on the free Hobby tier.

#### Railway Services

| Service | Type | Memory | Notes |
| --- | --- | --- | --- |
| `backend` | Web service (Docker) | 256MB | FastAPI; Railway auto-assigns a public HTTPS URL; `HEALTHCHECK` hits `/health` |
| `worker` | Worker service (Docker) | 512MB | ARQ worker; needs more RAM for Playwright browser instances; no public port |
| `postgres` | Railway Postgres plugin | — | Managed PostgreSQL 16; `DATABASE_URL` injected automatically into all services |
| `redis` | Railway Redis plugin | — | Managed Redis 7; `REDIS_URL` injected automatically into all services |

**Why 512MB for the worker:** Playwright spawns a Chromium browser process per scrape call (~400MB peak). The API server never runs Playwright directly — only the worker does — so the API can stay at 256MB.

#### Vercel (Frontend)

| Setting | Value |
| --- | --- |
| Framework preset | Vite |
| Build command | `npm run build` |
| Output directory | `dist` |
| SPA rewrite | All paths → `index.html` (configured in `vercel.json`) |
| Env var | `VITE_API_BASE_URL` → Railway backend public URL |

#### Environment Variables

Railway injects `DATABASE_URL` and `REDIS_URL` automatically when Postgres and Redis plugins are attached to a service. All other variables (`OPENAI_API_KEY`, `SERPER_API_KEY`, `RESEND_API_KEY`, `JWT_SECRET_KEY`, etc.) are set manually in Railway's Variables UI per service. The `backend` and `worker` services share the same variable set — set them on one service and use Railway's "shared variables" or duplicate them on both.

#### Deployment Workflow

1. Push to `main` branch on GitHub
2. Railway auto-deploys `backend` and `worker` from the connected repo (separate Railway services pointing to `./backend` with different start commands)
3. Vercel auto-deploys `frontend` from the same repo (root set to `./frontend`)
4. Run `alembic upgrade head` once after first deploy — Railway allows one-off commands via the CLI: `railway run alembic upgrade head`

#### Estimated Monthly Cost

| Service | Estimated usage cost |
| --- | --- |
| `backend` (256MB, low traffic) | ~$0.50–1.00 |
| `worker` (512MB, low traffic) | ~$1.00–2.00 |
| `postgres` (~50MB data) | ~$0.50 |
| `redis` (~5MB data) | ~$0.10 |
| **Total Railway** | **\~$2–4/month** (within $5 credit) |
| Vercel frontend | $0 |

---

## 13. Mock Mode Architecture

Mock mode allows the full application to be demonstrated and developed without any paid API keys (OpenAI, Serper, Resend) or email domain configuration.

### Activation

Set `MOCK_MODE=true` in the environment before starting the backend and worker services.

### Backend Behaviour

#### `run_ingestion_job` in mock mode

1. Immediately writes `current_step = "scraping"` to `ingestion_jobs`
2. `await asyncio.sleep(2)`
3. Writes `current_step = "extracting"`
4. `await asyncio.sleep(2)`
5. Loads `backend/fixtures/product_profile.json` as `ProductProfileOutput`
6. Writes `result_json`, sets `status = "done"`, `current_step = "complete"`, `completed_at = now()`

#### `run_outreach_job` in mock mode

1. Writes `current_step = "researching"` to `outreach_jobs`
2. `await asyncio.sleep(2)`
3. Writes `current_step = "personalizing"`
4. `await asyncio.sleep(2)`
5. Writes `current_step = "scheduling"`
6. `await asyncio.sleep(2)`
7. Loads `fixtures/outreach_draft.json` + `fixtures/schedule_output.json`
8. Writes `email_subject`, `email_draft`, `linkedin_draft`, `schedule_json`, `data_confidence`, sets `status = "done"`, `current_step = "complete"`, `token_usage = 0`

### Fixture Files

Located at `backend/fixtures/`. Each file contains a valid JSON document matching its corresponding agent output schema.

| File | Schema | Contents |
| --- | --- | --- |
| `product_profile.json` | `ProductProfileOutput` | Sample B2B SaaS product (fictional "DataPulse" analytics platform) |
| `research_output.json` | `ProspectResearchOutput` | Sample prospect company (fictional "Acme Corp", fintech, 100–250 employees, Chicago) |
| `outreach_draft.json` | `OutreachDraftOutput` | Sample email + LinkedIn note with `data_confidence: high` |
| `schedule_output.json` | `ScheduleOutput` | Sample schedule for following Tuesday 10am CT, `priority: normal`, `flag_for_human: false` |

### Seed Script (`scripts/seed_demo.py`)

Creates demo data for portfolio showcasing. Run once against a fresh or existing database.

**Creates:**
- 1 user with API key `DEMO-KEY-12345678` (unhashed for easy demo access; salt still applied)
- 1 active `ProductProfileOutput` from `fixtures/product_profile.json`
- 5 `outreach_jobs` rows:

| # | Company | Status | Send Status | Notes |
| --- | --- | --- | --- | --- |
| 1 | Acme Corp | `done` | `draft` | Awaiting approval |
| 2 | GlobalTech Inc | `done` | `approved` | Approved, not yet sent |
| 3 | Nexus Payments | `done` | `sent` | Has `resend_message_id`, `sent_at` |
| 4 | Vortex Labs | `done` | `bounced` | Has `resend_message_id`, bounced |
| 5 | Prism Analytics | `failed` | `draft` | Has `error_message: "Research Agent: Serper returned no results"` |

- 3 mock CRM pipeline records (returned by `GET /crm/pipeline`)

### Frontend Behaviour in Mock Mode

The frontend has **no knowledge of mock mode** — it calls the same API endpoints and receives real-looking responses. The full UI flow is exercisable:
- Polling with step progression
- Result display with email + LinkedIn + schedule
- Approve & Send flow (Resend is still called unless `RESEND_API_KEY` is unset — guard in `services/resend.py` returns a mock `resend_message_id` when the key is absent in mock mode)
- History table with all status variants

This means a reviewer can run `docker-compose up` with only `MOCK_MODE=true`, `DATABASE_URL`, and `REDIS_URL` set — no paid API keys required.
