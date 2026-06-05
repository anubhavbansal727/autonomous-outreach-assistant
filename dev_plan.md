# Development Plan: Mini CRM AI Crew

**Author:** Anubhav Bansal  
**Version:** 2.0  
**Date:** June 5, 2026  
**References:** `prd_mini_crm_ai_crew_v2.md` (v2.1) · `technical_spec.md` (v1.0)

---

## Status Summary

| Phase | Status | Completed |
|---|---|---|
| Phase 0 — Operational Setup | ✅ Done | API keys in place, repo created |
| Week 1 — LangGraph Outreach Graph | ✅ Done | Graph runs end-to-end |
| Week 2 — Ingestion Graph + DB Schema | ✅ Done | Migrations applied, ingestion works |
| Week 3 — FastAPI Backend + ARQ Worker | ✅ Done | All endpoints live |
| Week 4 — React Frontend | ✅ Done | All pages built and wired |
| Week 5 — Email Send + Mock Mode | ✅ Done | Send flow verified end-to-end |
| Week 6 — Hardening, Testing, Deployment | ✅ Done | Tests pass, Docker working locally |
| Post-launch bug fixes | ✅ Done | See Bug Fix Log below |

**The project is feature-complete and locally verified.** Railway + Vercel deployment is the remaining step.

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

| # | Status | Task | Notes |
|---|---|---|---|
| 0.1 | ✅ | Create GitHub repository | [autonomous-outreach-assistant](https://github.com/anubhavbansal727/autonomous-outreach-assistant) |
| 0.2 | ✅ | Sign up for OpenAI | API key in `.env` |
| 0.3 | ✅ | Sign up for Serper | API key in `.env` |
| 0.4 | ✅ | Sign up for Resend | API key in `.env`; domain verification pending (using test domain for now) |
| 0.5 | ☐ | Sign up for LangSmith | Optional — `LANGCHAIN_TRACING_V2=false` currently |
| 0.6 | ☐ | Sign up for Railway | Needed for production deployment |
| 0.7 | ☐ | Sign up for Vercel | Needed for frontend deployment |

---

## Week 1 — LangGraph Outreach Graph ✅

**Goal:** End-to-end outreach graph runs in CLI.

| # | Status | Task |
|---|---|---|
| 1.1 | ✅ | Project scaffold — `pyproject.toml`, `uv sync`, Playwright install |
| 1.2 | ✅ | `OutreachState` TypedDict |
| 1.3 | ✅ | Tool functions — `scrape_website`, `web_search`, `get_crm_pipeline` |
| 1.4 | ✅ | Research node + ReAct loop |
| 1.5 | ✅ | Personalize node with `with_structured_output` |
| 1.6 | ✅ | Schedule node + ReAct loop |
| 1.7 | ✅ | Graph assembly + CLI smoke test |

---

## Week 2 — Ingestion Graph + DB Schema ✅

| # | Status | Task |
|---|---|---|
| 2.1 | ✅ | `IngestionState` TypedDict |
| 2.2 | ✅ | Scrape node (Playwright, 5 paths, best-effort) |
| 2.3 | ✅ | Extract node (GPT-4o, structured output) |
| 2.4 | ✅ | IngestionGraph assembly + CLI test |
| 2.5 | ✅ | DB models + Alembic setup + initial migration |
| 2.6 | ✅ | Async session factory + `get_db` dependency |

---

## Week 3 — FastAPI Backend + ARQ Worker ✅

| # | Status | Task |
|---|---|---|
| 3.1 | ✅ | FastAPI app factory + lifespan |
| 3.2 | ✅ | Auth endpoints (`/auth/*`) |
| 3.3 | ✅ | Profile endpoints (`/profile/*`) |
| 3.4 | ✅ | Outreach endpoints (`/outreach/*`) |
| 3.5 | ✅ | CRM + health endpoints |
| 3.6 | ✅ | ARQ worker + job functions (ingestion + outreach) |
| 3.7 | ✅ | Rate limiter (Redis sliding window) |
| 3.8 | ✅ | API tests |

---

## Week 4 — React Frontend ✅

| # | Status | Task |
|---|---|---|
| 4.1 | ✅ | Vite + React + TypeScript scaffold |
| 4.2 | ✅ | Auth infrastructure (apiFetch, AuthContext, silent refresh) |
| 4.3 | ✅ | Login + Register pages |
| 4.4 | ✅ | App shell + routing |
| 4.5 | ✅ | Onboarding page (URL ingest + profile review form) |
| 4.6 | ✅ | Generate + Result pages (polling, edit mode, approve & send) |
| 4.7 | ✅ | History + Settings pages |
| 4.8 | ✅ | `useJobPolling` hook |

---

## Week 5 — Resend Integration + Mock Mode ✅

| # | Status | Task |
|---|---|---|
| 5.1 | ✅ | `resend.py` service — CAN-SPAM headers, plain text + HTML |
| 5.2 | ✅ | `POST /outreach/{job_id}/send` endpoint |
| 5.3 | ✅ | Approve & Send dialog in frontend |
| 5.4 | ✅ | Mock mode with fixture loading and 2s step delays |
| 5.5 | ✅ | Seed demo script (`demo@datapulse.io` / `Demo1234!`, 5 jobs) |

---

## Week 6 — Hardening, Observability, Testing, Deployment ✅

| # | Status | Task | Notes |
|---|---|---|---|
| 6.1 | ☐ | LangSmith tracing | Disabled (`LANGCHAIN_TRACING_V2=false`); enable when ready |
| 6.2 | ✅ | ARQ retry logic (max 3, exponential backoff) | |
| 6.3 | ✅ | Unit tests — schemas, rate limiter, JWT (32 tests) | All passing |
| 6.4 | ☐ | Integration test (real GPT-4o-mini run) | Scaffolded; not run in CI |
| 6.5 | ✅ | Docker Compose (5 services, non-conflicting ports 5433/6380) | Working locally |
| 6.6 | ☐ | Railway deployment | Config files ready (`railway.toml`, `railway.worker.toml`); not deployed yet |
| 6.7 | ☐ | Vercel deployment | Config ready (`vercel.json`); not deployed yet |
| 6.8 | ☐ | End-to-end smoke test (production) | Blocked on 6.6 + 6.7 |

---

## Bug Fix Log (post-Week 6, during local verification)

All bugs found and fixed during the first real end-to-end run. All fixes are committed and pushed.

| Commit | Bug | Root Cause | Fix |
|---|---|---|---|
| `ddf1e96` | Login 500 error | `passlib` incompatible with `bcrypt>=4.0` — missing `__about__` module | Replaced `passlib` entirely with raw `bcrypt` library (`hashpw`/`checkpw`/`gensalt`) |
| `b3ff189` | Ingestion enqueue 500 | `pool.client` AttributeError — ARQ 0.25 pool IS the Redis client, no `.client` attribute | Changed `pool.client` → `pool` in `profile.py` and `outreach.py` |
| `3d8136d` | Ingestion job OpenAI error | `langchain-openai` reads `OPENAI_API_KEY` from `os.environ`; pydantic-settings doesn't export to env | Passed `api_key=settings.OPENAI_API_KEY` explicitly to all 5 `ChatOpenAI()` constructors |
| `6a30824` | Profile save 422 | GPT-4o returned 9 case studies; `SaveProfileRequest` had `max_length=5` on list fields | Raised all list field limits to 20 |
| `4e94f88` | Outreach `GraphRecursionError` | `recursion_limit=10` too tight for full graph path; LLM was batching 2 tool calls per turn | Raised limit to 25; tightened research prompt to "ONE tool at a time, web_search at most ONCE" |
| `1c114da` | Email/LinkedIn draft empty after job completes | `final_state` was read from last event only (`extract_schedule_node` output); personalize fields not included | Accumulate all node outputs across the `astream` loop into `accumulated_state` |
| `1fa1b45` | Send button POSTed to `/outreach/send/undefined` | `OutreachResultResponse` returned `job_id` but TS type `OutreachJob` expected `id` | Renamed field to `id` in schema + router constructor |
| `a48dc2c` | Send returned 400 `NO_RESEND_DOMAIN` | User has no verified domain; endpoint hard-rejected instead of falling back | Fall back to `resend.dev`; add `PATCH /auth/me` endpoint; fix Settings page to call correct endpoint |
| `403e902` | Send returned 502 | `outreach@resend.dev` is not a permitted sender on Resend's test domain | Use `onboarding@resend.dev` when domain is `resend.dev`; log real exception before 502 |

---

## Definition of Done (v1)

- [x] All 6 weeks built
- [x] `pytest tests/unit tests/api` — all passing
- [x] `MOCK_MODE=true` — full flow works without real API keys
- [x] Real API keys — full flow verified end-to-end (ingest → generate → approve & send)
- [x] Email delivered via Resend (verified locally)
- [x] Seed script produces demo-ready data
- [x] README documents setup, env vars, architecture, and how to run
- [ ] Railway deployment live — backend health check green
- [ ] Vercel deployment live — frontend accessible at public URL
- [ ] LangSmith traces visible for at least one production run

---

## Remaining To-Do

### Deployment (next priority)

| # | Task | Notes |
|---|---|---|
| D1 | Create Railway project, add Postgres + Redis plugins | |
| D2 | Create `backend` service — set env vars, deploy from GitHub | RAM: 256 MB |
| D3 | Run `alembic upgrade head` via Railway shell | One-time, after first deploy |
| D4 | Create `worker` service — set `INSTALL_PLAYWRIGHT=true`, `CMD=python worker.py` | RAM: 512 MB |
| D5 | Create Vercel project — connect frontend dir, set `VITE_API_URL` to Railway URL | |
| D6 | Run `python scripts/seed_demo.py` against production DB | |
| D7 | End-to-end smoke test on live URLs | Register → ingest → generate → send |

### Optional / v2 Backlog

| # | Task | Notes |
|---|---|---|
| O1 | Enable LangSmith tracing | Set `LANGCHAIN_TRACING_V2=true` + add `LANGCHAIN_API_KEY` |
| O2 | Resend custom domain setup | Verify DNS records in Resend dashboard; update `resend_domain` in Settings |
| O3 | Add integration test to CI | `test_outreach_graph.py` with GPT-4o-mini |
| O4 | v2 — Low-confidence research pause | `interrupt()` + human-in-the-loop mid-graph |
| O5 | v2 — Draft quality self-critique loop | Conditional exit edges |
| O6 | v2 — Resumable runs after failure | Postgres checkpointer |
| O7 | v2 — Batch multi-prospect processing | `Send()` fan-out API |

---

## v2 Roadmap Reference

See `prd_mini_crm_ai_crew_v2.md` → v2 Roadmap for the 4 LangGraph-specific features planned after v1 ships:

1. Low-Confidence Research Pause — `interrupt()` + conditional edges
2. Draft Quality Self-Critique Loop — cycles with conditional exit edges
3. Resumable Runs After Failure — Postgres checkpointer
4. Batch Multi-Prospect Processing — `Send()` fan-out API
