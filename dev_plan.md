# Development Plan: Mini CRM AI Crew

**Author:** Anubhav Bansal  
**Version:** 1.0  
**Date:** May 28, 2026  
**References:** `prd_mini_crm_ai_crew_v2.md` (v2.1) · `technical_spec.md` (v1.0)

---

## Overview

Six-week build plan, preceded by a one-time operational setup phase. Each week targets a vertical slice: agents first (CLI-validated), then backend, then frontend, then integrations, then hardening and deployment.

```
Phase 0 — Operational Setup       (before any code)
Week 1  — LangGraph Outreach Graph (CLI)
Week 2  — Ingestion Graph + DB Schema
Week 3  — FastAPI Backend + ARQ Worker
Week 4  — React Frontend
Week 5  — Email Send + Mock Mode
Week 6  — Auth Hardening, Observability, Testing, Deployment
```

---

## Phase 0 — Operational Setup

One-time account and API key setup. Must be complete before Week 1.

| # | Status | Task | Notes |
|---|---|---|---|
| 0.1 | ☐ | Create GitHub repository | Public repo (portfolio); add `.gitignore` for Python + Node |
| 0.2 | ☐ | Sign up for OpenAI | [platform.openai.com](https://platform.openai.com) → create project → generate API key → add $5–10 credit |
| 0.3 | ☐ | Sign up for Serper | [serper.dev](https://serper.dev) → free tier (100 searches/month) → copy API key |
| 0.4 | ☐ | Sign up for Resend | [resend.com](https://resend.com) → free tier → add + verify sending domain → copy API key |
| 0.5 | ☐ | Sign up for LangSmith | [smith.langchain.com](https://smith.langchain.com) → free tier → create project → copy API key |
| 0.6 | ☐ | Sign up for Railway | [railway.app](https://railway.app) → Hobby plan ($5/month) → create project |
| 0.7 | ☐ | Sign up for Vercel | [vercel.com](https://vercel.com) → free tier → connect GitHub account |

**Output:** `.env.example` filled with real key names (not values); keys stored in a password manager.

---

## Week 1 — LangGraph Outreach Graph (CLI)

**Goal:** End-to-end outreach graph runs in CLI. Research → Personalise → Schedule. All three agents validate LangGraph state-passing and structured output contracts.

**PRD milestone:** *"Working 3-agent outreach crew in CLI; sequential flow validated; LangGraph context-passing confirmed"*

### Tasks

#### 1.1 Project Scaffold
- Initialise `mini-crm-ai-crew/` monorepo directory
- Create `backend/pyproject.toml` with all dependencies (pinned to versions in `technical_spec.md` Section 3)
- Run `uv sync` to generate `uv.lock`
- Run `python -m playwright install chromium`
- Create `.env.example` with all variable names from Section 11

#### 1.2 OutreachState TypedDict
- Create `backend/app/graphs/outreach/state.py`
- Define `OutreachState` with all fields from `technical_spec.md` Section 6
- Annotators: use `Annotated[list, operator.add]` for message accumulation; plain assignment for scalar fields

#### 1.3 Tool Functions
- Create `backend/app/tools/scrape.py` — `scrape_website(url: str) -> str` using Playwright (15s timeout, `page.content()`)
- Create `backend/app/tools/search.py` — `web_search(query: str) -> str` via Serper `POST /search` (httpx, `SERPER_API_KEY`)
- Create `backend/app/tools/crm.py` — `get_crm_pipeline() -> str` returning hardcoded mock pipeline JSON (direct Python call, no HTTP)
- Decorate all three with `@tool`

#### 1.4 Research Node
- Create `backend/app/graphs/outreach/graph.py`
- `research_node`: GPT-4o, temp=0.5, bound with `[web_search, scrape_website]`
- `research_tools_node`: `ToolNode([web_search, scrape_website])`
- Conditional edge: `should_continue_research` — routes back to `research_node` if last message has tool calls, else → `personalize_node`

#### 1.5 Personalize Node
- `personalize_node`: GPT-4o, temp=0.7, `with_structured_output(OutreachDraftOutput)` — see Section 7 for field table
- Reads `research_output` from state; writes `email_subject`, `email_body`, `linkedin_note`, `data_confidence`, `personalization_signals`

#### 1.6 Schedule Node
- `schedule_node`: GPT-4o, temp=0.2, bound with `[get_crm_pipeline]`
- `schedule_tools_node`: `ToolNode([get_crm_pipeline])`
- Conditional edge: `should_continue_schedule` — same ReAct loop pattern as research
- Final node writes `schedule_output` to state

#### 1.7 Graph Assembly + CLI Smoke Test
- Wire up `StateGraph(OutreachState)` with all nodes and edges
- Compile with `recursion_limit=10`
- Write `scripts/test_outreach_cli.py` — hardcode a test company + contact, invoke `graph.ainvoke(state)`, print structured results
- Verify: research populates company data, personalisation references it, schedule output has `send_at` and `channel`

**Exit criteria:** CLI script runs to completion; `OutreachDraftOutput` and `ScheduleOutput` schemas validate; no `ValidationError`.

---

## Week 2 — Ingestion Graph + DB Schema

**Goal:** Ingestion graph (Scraper + Extractor) runs end-to-end. All 4 DB tables created via Alembic migration.

**PRD milestone:** *"Ingestion crew (scraper + extractor); onboarding flow with editable pre-fill form"*

### Tasks

#### 2.1 IngestionState TypedDict
- Create `backend/app/graphs/ingestion/state.py`
- Fields: `url`, `raw_html`, `product_profile_output`, `error`

#### 2.2 Scrape Node
- `scrape_node` in `backend/app/graphs/ingestion/graph.py`
- Playwright: fetch homepage + `/pricing` + `/about` + `/customers` + `/case-studies` (best-effort, skip 404s)
- Concatenate raw HTML strings; write to `state["raw_html"]`
- No LLM — pure Python

#### 2.3 Extract Node
- `extract_node`: GPT-4o, temp=0.2, `with_structured_output(ProductProfileOutput)`
- Input: `raw_html` from state + system prompt instructing field extraction
- Output schema: all fields in `product_profiles` table (see `technical_spec.md` Section 7)
- On parse failure: retry once; if still fails, set `state["error"]` and write partial output

#### 2.4 IngestionGraph Assembly + CLI Test
- Wire up linear `scrape_node → extract_node`
- Write `scripts/test_ingestion_cli.py` — test against a real product URL (e.g. `https://linear.app`)
- Verify: `ProductProfileOutput` validates; key fields populated

#### 2.5 DB Models + Alembic Setup
- Create `backend/app/models/db.py` — SQLAlchemy ORM models for all 4 tables (`users`, `product_profiles`, `ingestion_jobs`, `outreach_jobs`) — columns exactly as in `technical_spec.md` Section 4
- Set up `backend/alembic.ini` + `backend/app/db/migrations/env.py`
- Generate initial migration: `alembic revision --autogenerate -m "initial schema"`
- Verify migration SQL matches the Section 4 table spec

#### 2.6 DB Session Factory
- Create `backend/app/db/session.py` — async engine, `AsyncSession` factory, `get_db` FastAPI dependency

**Exit criteria:** `alembic upgrade head` runs cleanly; all 4 tables created; ingestion CLI script produces valid `ProductProfileOutput`.

---

## Week 3 — FastAPI Backend + ARQ Worker

**Goal:** All 17 API endpoints live and tested via TestClient. ARQ worker enqueues and executes both graph jobs.

**PRD milestone:** *"FastAPI backend — all endpoints, ARQ job queue, PostgreSQL + Redis integration"*

### Tasks

#### 3.1 FastAPI App Factory
- Create `backend/app/main.py` — `create_app()`, lifespan (DB pool open/close + Redis open/close), CORS config
- Register all routers: auth, profile, outreach, crm, health

#### 3.2 Auth Endpoints (`/auth/*`)
- Implement `POST /auth/register` — bcrypt hash password, create user row, issue access + refresh tokens
- Implement `POST /auth/login` — verify password hash, issue tokens; same 401 message for wrong email or password
- Implement `POST /auth/refresh` — read `httpOnly` cookie, validate refresh JWT, issue new access token
- Implement `POST /auth/logout` — clear refresh cookie
- Implement `GET /auth/me` — return user row for current Bearer token
- Create `backend/app/auth/dependencies.py` — `get_current_user` FastAPI dependency

#### 3.3 Profile Endpoints (`/profile/*`)
- `GET /profile` — return active profile or 404
- `PUT /profile` — upsert active profile fields
- `DELETE /profile` — deactivate profile (`is_active = false`)
- `POST /profile/ingest` — enqueue `run_ingestion_job` via ARQ; return `{ job_id }`
- `GET /profile/ingest/status/{job_id}` — return `{ status, current_step }` from `ingestion_jobs`

#### 3.4 Outreach Endpoints (`/outreach/*`)
- `POST /outreach/generate` — validate active profile exists, enqueue `run_outreach_job`; return `{ job_id }`
- `GET /outreach/status/{job_id}` — return `{ status, current_step }` from `outreach_jobs`
- `GET /outreach/result/{job_id}` — return full result payload (only if `status == done`)
- `POST /outreach/{job_id}/send` — call Resend SDK, update `send_status = sent`, store `resend_message_id`
- `GET /outreach/history` — paginated list (page + page_size query params), filter by `user_id`

#### 3.5 CRM + Health Endpoints
- `GET /crm/pipeline` — return hardcoded mock pipeline JSON (list of 5 companies with stage + last_contact)
- `GET /health` — ping DB + Redis; return `{ status: ok, db: ok, redis: ok }`

#### 3.6 ARQ Worker + Job Functions
- Create `backend/worker.py` — ARQ `WorkerSettings` with `redis_settings`, `functions` list, `max_jobs=10`
- Create `backend/app/jobs/ingestion_job.py` — `run_ingestion_job(ctx, user_id, url, job_id)` — streams `IngestionGraph`, updates `ingestion_jobs` step by step
- Create `backend/app/jobs/outreach_job.py` — `run_outreach_job(ctx, user_id, company_name, contact_name, job_id, product_profile_id)` — streams `OutreachGraph`, updates `outreach_jobs` step by step
- Both functions: check `MOCK_MODE` at top and short-circuit to fixture loading if true

#### 3.7 Rate Limiter
- Create `backend/app/services/rate_limiter.py` — Redis sliding window; `check_rate_limit(user_id, limit=10, window=3600)`
- Apply to `POST /outreach/generate` and `POST /profile/ingest`
- Return HTTP 429 with `{ error, code: RATE_LIMIT, retry_after }` on breach

#### 3.8 API Tests
- Write `backend/tests/api/` tests for all 17 endpoints using `httpx.AsyncClient` + `TestClient`
- Mock ARQ enqueue; mock DB with test database (SQLite or Postgres test schema)
- Cover: happy path + main error paths (401, 404, 409, 422, 429)

**Exit criteria:** `pytest tests/api/` passes; all 17 endpoints return correct status codes; ARQ worker processes a mock job end-to-end.

---

## Week 4 — React Frontend

**Goal:** All 7 pages built and wired to the real backend API. Auth flow, polling, and edit-in-place all work.

**PRD milestone:** *"React frontend — onboarding, generate, result display (with edit mode), history tab"*

### Tasks

#### 4.1 Project Scaffold
- `npm create vite@latest frontend -- --template react-ts`
- Install all dependencies from `technical_spec.md` Section 3
- Set up Tailwind CSS 3, shadcn/ui (init), React Router v6, TanStack Query v5
- Configure `vite.config.ts` proxy: `/api → http://localhost:8000`

#### 4.2 Auth Infrastructure
- Create `src/api/client.ts` — `apiFetch` with Bearer injection, silent 401 refresh retry, redirect on second 401
- Create `AuthContext` + `AuthProvider` — stores `{ user, accessToken }`; calls `/auth/refresh` on mount
- Create `useAuth` hook — reads `AuthContext`
- Wrap `App.tsx` Router inside `AuthProvider` > `QueryClientProvider`
- Create `ProtectedRoute` component — redirects unauthenticated users to `/login`

#### 4.3 Auth Pages
- `LoginPage` — email + password form; calls `POST /auth/login`; stores access token in context on success
- `RegisterPage` — same form + confirm password; calls `POST /auth/register`

#### 4.4 App Shell + Routing
- `AppShell.tsx` — sidebar navigation + main content area
- `Sidebar.tsx` — links to Onboarding, Generate, History, Settings; shows logged-in user email
- Routes: `/login`, `/register`, `/` (Onboarding), `/generate`, `/result/:jobId`, `/history`, `/settings`

#### 4.5 Onboarding Page
- `UrlIngestForm` — URL input; on submit, calls `POST /profile/ingest`, navigates to progress view
- `IngestProgress` — polls `/profile/ingest/status/:id` every 3s via `useJobPolling`; shows `Scraping → Extracting → Done` stepper
- `ProfileReviewForm` — editable form pre-filled with agent-extracted data; save calls `PUT /profile`

#### 4.6 Generate Page + Result Page
- `GenerateForm` — `company_name` + `contact_name` inputs; submit calls `POST /outreach/generate`
- `JobProgressStepper` — polls `/outreach/status/:id`; shows `Research → Personalizing → Scheduling → Done`
- `ResultCard` — renders `EmailEditor` + `LinkedInEditor` + `ScheduleCard` once status is done
- `EmailEditor` — inline-editable subject + body; save calls `PUT /outreach/:id` (subject + body fields)
- `LinkedInEditor` — inline-editable note; same save pattern
- `ScheduleCard` — shows `send_at`, `channel`, `recommended_window`; shows warning banner if `flag_for_human = true`

#### 4.7 History Page + Settings Page
- `HistoryTable` — shadcn Table; columns: company, status, send_status, created_at, actions; pagination via query params
- `PaginationControls` — prev/next; shows current page / total
- `SettingsPage` — shows `resend_domain` input (save calls `PUT /profile`); shows current user email; logout button

#### 4.8 useJobPolling Hook
- `useJobPolling(jobId, endpoint)` — `useQuery` wrapper with `refetchInterval: 3000`; disables refetch when `status === 'done' || status === 'failed'`
- Used by both `IngestProgress` and `JobProgressStepper`

**Exit criteria:** Full user flow works against local backend — register → onboard → generate → view result → history; no TypeScript errors; all pages render without console errors.

---

## Week 5 — Resend Integration + Mock Mode

**Goal:** Approve & send flow works end-to-end. Mock mode works in isolation without real API keys.

**PRD milestone:** *"Resend integration, Approve & Send flow, CAN-SPAM headers, mock mode + seed script"*

### Tasks

#### 5.1 Resend Email Send
- Create `backend/app/services/resend.py` — wraps `resend.Emails.send()`
- Required fields: `from` (`{user_name} <outreach@{resend_domain}>`), `to`, `subject`, `html`
- Headers: `List-Unsubscribe` (CAN-SPAM); `X-Entity-Ref-ID` (dedup)
- Captures and returns `resend_message_id`

#### 5.2 POST `/outreach/{job_id}/send` Endpoint
- Validates: job belongs to user; `status == done`; `send_status == draft` (no double-send)
- Calls `resend.py` with current `email_subject` + `email_body` (post-edit values)
- On success: updates `send_status = sent`, `resend_message_id`, `sent_at`
- On Resend error: returns HTTP 502 with `{ error, code: SEND_FAILED }`

#### 5.3 Approve & Send in Frontend
- `ScheduleCard` — "Approve & Send" button calls `POST /outreach/{id}/send` mutation via TanStack Query `useMutation`
- Confirmation dialog (shadcn `AlertDialog`) before send
- On success: update UI to show `send_status: sent`; disable send button

#### 5.4 Mock Mode
- Add `MOCK_MODE` env var check at top of `run_ingestion_job` and `run_outreach_job`
- Create fixture files:
  - `backend/fixtures/research_output.json` — mock `ProspectResearchOutput`
  - `backend/fixtures/outreach_draft.json` — mock `OutreachDraftOutput`
  - `backend/fixtures/schedule_output.json` — mock `ScheduleOutput`
  - `backend/fixtures/product_profile.json` — mock `ProductProfileOutput`
- Mock jobs: load fixture, write step updates with `asyncio.sleep(2)` delays, write `status=done`

#### 5.5 Seed Demo Script
- `backend/scripts/seed_demo.py`:
  - Creates demo user (`demo@example.com` / `demo1234`)
  - Creates active product profile from `product_profile.json`
  - Creates 5 outreach jobs with varied `status` and `send_status` (2 sent, 1 draft, 1 failed, 1 running)
  - Uses fixture data for `email_draft`, `linkedin_draft`, `schedule_json`
- Run with: `python scripts/seed_demo.py`

**Exit criteria:** With real Resend key, email lands in inbox. With `MOCK_MODE=true`, full flow works with zero real API keys. Seed script populates DB in <5 seconds.

---

## Week 6 — Hardening, Observability, Testing, Deployment

**Goal:** Production-ready: LangSmith traces, retry logic, full test suite, Docker packaging, Railway + Vercel live.

**PRD milestone:** *"Auth, rate limiting, retry logic, LangSmith observability, Docker packaging, Railway + Vercel deployment, test suite"*

### Tasks

#### 6.1 LangSmith Tracing
- Set `LANGCHAIN_TRACING_V2=true`, `LANGCHAIN_API_KEY`, `LANGCHAIN_PROJECT` in `.env`
- Verify: every graph run appears in LangSmith dashboard with node-level traces
- PII audit: confirm `contact_name` + prospect email are not in run name, tags, or metadata

#### 6.2 ARQ Retry Logic
- In `run_outreach_job`: wrap graph invocation in try/except; on exception, increment `retry_count`, set `error_message`
- Configure ARQ retry: `max_tries=3`, backoff: 1s → 2s → 4s
- On final failure: set `status=failed`

#### 6.3 Unit Tests
- `backend/tests/unit/test_schemas.py` — validate all Pydantic output schemas with valid + invalid data
- `backend/tests/unit/test_rate_limiter.py` — test sliding window logic with mock Redis
- `backend/tests/unit/test_jwt.py` — test token creation, validation, expiry, wrong type

#### 6.4 Integration Test (1 run)
- `backend/tests/integration/test_outreach_graph.py`
- Uses GPT-4o-mini (cheaper) + real Serper key + sandboxed test DB
- Verifies full `OutreachGraph` run produces a `status=done` job with all output fields populated
- Mark with `@pytest.mark.integration` so it's skipped in fast test runs

#### 6.5 Docker Compose
- Write `docker-compose.yml` with 5 services: `backend` (256MB), `worker` (512MB), `frontend`, `postgres`, `redis`
- Backend + worker: same image, different `CMD`
- Frontend: Vite dev server in dev; nginx static in prod
- Volume: named `postgres_data`
- Health check: `backend` waits for postgres + redis; `worker` waits for `backend` healthy

#### 6.6 Railway Deployment
- Create 4 Railway services in the project: `backend`, `worker`, `postgres` (plugin), `redis` (plugin)
- Set all env vars from Section 11 in Railway service config
- Set `worker` service start command: `python worker.py`
- Set `backend` RAM: 256MB; `worker` RAM: 512MB
- Verify: `GET /health` returns `{ status: ok, db: ok, redis: ok }`
- Run `alembic upgrade head` via Railway shell (one-time)

#### 6.7 Vercel Deployment
- Connect frontend directory to Vercel project
- Add `vercel.json` SPA rewrite rule: `{ "rewrites": [{ "source": "/(.*)", "destination": "/index.html" }] }`
- Set `VITE_API_URL` env var to Railway backend URL
- Verify: frontend loads; login and generate flows work against production backend

#### 6.8 End-to-End Smoke Test (Production)
- Register new user on live URL
- Submit product URL → verify ingestion completes
- Generate outreach for a test company → verify result loads
- Approve & send → verify email received

**Exit criteria:** `pytest tests/unit tests/api` passes (no integration tests in CI). Railway backend + worker running. Vercel frontend accessible at public URL. LangSmith shows live traces.

---

## Definition of Done (v1)

- [ ] All 6 weeks complete
- [ ] `pytest tests/unit tests/api` — all passing
- [ ] `MOCK_MODE=true` — full flow works without real API keys
- [ ] Railway deployment live — backend health check green
- [ ] Vercel deployment live — frontend accessible
- [ ] LangSmith traces visible for at least one production run
- [ ] Seed script produces demo-ready data
- [ ] README documents setup, env vars, and how to run

---

## v2 Roadmap Reference

See `prd_mini_crm_ai_crew_v2.md` → v2 Roadmap for the 4 LangGraph-specific features planned after v1 ships:

1. Low-Confidence Research Pause — `interrupt()` + conditional edges
2. Draft Quality Self-Critique Loop — cycles with conditional exit edges
3. Resumable Runs After Failure — Postgres checkpointer
4. Batch Multi-Prospect Processing — `Send()` fan-out API
