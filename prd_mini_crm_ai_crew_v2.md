# PRD: Mini CRM AI Crew — Autonomous B2B Outreach Assistant

**Product:** Mini CRM AI Crew  
**Type:** Internal Tool / Developer Portfolio Project  
**Author:** Anubhav Bansal  
**Version:** 2.2  
**Status:** v1 Shipped  
**Date:** June 5, 2026  
**Changelog:** v2.1 — Added async queue spec, Scheduler Agent contract, Testing Strategy, Demo & Portfolio section, Privacy & Data Retention, prompt injection mitigation, data model gaps, WebSocket vs polling tradeoff, `avoid_messaging` injection mechanism, API key lifecycle, edit flow spec. v2.2 — Corrected stack: implementation uses LangGraph natively (not CrewAI); updated Goal, Agent Architecture, and Milestones accordingly. Marked v1 as shipped.

---

## Problem Statement

Sales reps and SDRs spend 2–3 hours per prospect manually researching companies, writing personalised outreach, and deciding when to send it. This is repetitive, context-heavy work that degrades in quality at scale — the exact class of task that enterprise agent platforms like Agentforce, Breeze AI, and Fin AI are productising for large sales teams.

This project builds a production-grade autonomous agent system that mirrors those platforms' core mechanics: multi-agent orchestration, URL-based product context ingestion, tool-use, handoff logic, human-in-the-loop approval, and async job execution — packaged as a usable web application.

---

## Goal

Build a **deployable B2B outreach automation tool** powered by a multi-agent LangGraph system, exposed via a FastAPI backend and a minimal React frontend — demonstrating real-world agentic AI patterns including onboarding ingestion, outreach generation, and human-approved email delivery.

---

## Target User

A **solo founder, SDR, or sales engineer** at a B2B SaaS company who needs personalised outreach prepared for 10–50 prospects per week but lacks the bandwidth to research each one manually.

---

## User Stories

- As a new user, I want to paste my product website URL and have my product profile auto-filled, so I don't have to manually describe my product.
- As a sales rep, I want to enter a company name and get a personalised cold email + LinkedIn note within 2 minutes, so I can send outreach without manual research.
- As a sales rep, I want to review the drafted email before it is sent, so I stay in control of what goes out under my name.
- As a sales rep, I want to know if a prospect is already in the pipeline before sending, so I don't send duplicate or conflicting messages.
- As a power user, I want to review my outreach history per company, so I can track what was sent and when.
- As a user, I want to register with my email and password and log in securely, so I can access my own outreach data privately.

---

## Agent Architecture

### Crew 1 — Product Profile Ingestion (runs once at onboarding)

| Agent | Role | Tools |
|---|---|---|
| Scraper Agent | Fetches homepage, /pricing, /customers, /about, /case-studies | ScrapeWebsiteTool (Playwright for JS-heavy SPAs) |
| Extractor Agent | Parses raw content into structured product profile JSON | LLM only (GPT-4o) |

**Context passing:** Scraper node output is stored in graph state and automatically available to the Extract node.

**Fallback:** If scraping fails (auth-gated, SPA rendering issues, vague copy), user is shown a manual form pre-filled with whatever was extracted. "Avoid messaging" field is always manual — the agent cannot infer what the company does *not* want to say.

### Crew 2 — Outreach Generation (runs per prospect)

| Agent | Role | Tools |
|---|---|---|
| Research Agent | Builds prospect company profile: industry, size, pain points, tech stack, news signals | SerperDevTool, ScrapeWebsiteTool |
| Personalization Agent | Cross-references prospect profile against seller's product profile; writes cold email + LinkedIn note | LLM only (GPT-4o) |
| Scheduler Agent | Decides send timing based on defined signals; flags if prospect is already in CRM pipeline | Mock CRM API (custom FastAPI endpoint) |

**Context passing:** All nodes share a typed graph state object. Research output, product profile, and `avoid_messaging` are fields on that state — each node reads what it needs and writes its result back. No explicit wiring syntax required.

`avoid_messaging` is injected as a hard negative constraint in the Personalization node's system prompt: *"Do not mention or imply: {avoid_messaging}. This is a strict constraint — violating it invalidates the output."* Enforcement is prompt-level.

#### Scheduler Agent — Full Specification

**Inputs (via task context):**
- Research Agent output (prospect JSON)
- Result of `/crm/pipeline` tool call

**Decision signals:**
1. Prospect time zone (inferred from company HQ location in research output)
2. Day of week / time of day (targets Tuesday–Thursday, 9–11am prospect local time)
3. Recent company news signal (if a funding round or product launch was found, flag as high priority)
4. CRM pipeline check (if prospect company name matches an existing record, `flag_for_human: true`)

**Output schema (`schedule_json`):**
```json
{
  "send_at": "2026-06-03T09:30:00-05:00",  // ISO 8601 with tz offset
  "channel": "email",                        // always "email" in v1
  "recommended_window": "Tue-Thu 9–11am CT",
  "priority": "high | normal",
  "flag_for_human": true,
  "flag_reason": "Prospect already in CRM pipeline as 'exploring' stage"
}
```

**Mock CRM API contract (`/crm/pipeline` GET):**
```json
{
  "records": [
    {
      "company_name": "Acme Corp",
      "contact_name": "Jane Smith",
      "stage": "exploring | demo_booked | negotiating | closed_won | closed_lost",
      "last_contacted": "2026-04-12"
    }
  ]
}
```

**Degraded-state behaviour:** If the Research Agent returns sparse data (company has minimal web presence), the Personalization Agent still runs but the task prompt instructs it to acknowledge the gap: *"If prospect data is insufficient to write a highly personalised email, write a strong semi-personalised email based on industry and company size alone. Do not hallucinate specific details."* The job completes with status `done`; the result card shows a `data_confidence: low | medium | high` indicator.

The Personalization Agent receives both the **Research Agent's prospect JSON** and the **seller's stored product profile** as context, enabling it to connect specific prospect pain points to specific product capabilities.

---

## Functional Requirements

### Onboarding Flow

1. User registers with email + password (or logs in if returning) → JWT issued
2. User pastes product website URL
3. Ingestion Crew runs in the background (~30 seconds)
4. Pre-filled product profile form shown for review and edit
5. User confirms → profile saved to `product_profiles` table
6. Profile is automatically injected into every future outreach crew run

### Outreach Generation Flow

1. User inputs: company name (max 100 chars, alphanumeric + spaces + hyphens only), contact name (optional, same constraints)
2. Outreach Crew runs asynchronously → returns `job_id` immediately
3. Frontend polls `/outreach/status/:id` every **3 seconds** with a progress indicator showing current agent step
4. On completion, result displayed: formatted email, LinkedIn note, schedule card, `data_confidence` badge
5. User reviews → may edit email subject, email body, or LinkedIn note in-place (edits saved via `PUT /outreach/result/:id`; editing does not create a new job or invalidate the existing one)
6. User clicks **"Approve & Send"**
7. Backend calls Resend API → email delivered from user's verified domain
8. Job status updated to `sent`; `sent_at` and `resend_message_id` stored

**Failed job UX:** If a job reaches `status: failed`, the UI shows `error_message` (e.g., "Research Agent: all scraping attempts returned empty results") and a **"Retry"** button that re-triggers the crew run for the same inputs, incrementing `retry_count`.

### API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/auth/register` | POST | Accepts `{ email, password }`, creates user, returns access token + sets refresh cookie |
| `/auth/login` | POST | Accepts `{ email, password }`, returns access token + sets refresh cookie |
| `/auth/refresh` | POST | Uses `httpOnly` refresh cookie to issue a new access token |
| `/auth/logout` | POST | Clears the refresh cookie |
| `/auth/me` | GET | Returns current authenticated user's profile |
| `/profile/ingest` | POST | Accepts `{ url }`, triggers ingestion crew, returns `{ job_id }` |
| `/profile/result/:id` | GET | Returns extracted product profile JSON for user review |
| `/profile/save` | POST | Saves confirmed product profile to DB |
| `/profile/update` | PUT | Updates existing product profile |
| `/outreach/generate` | POST | Accepts `{ company_name, contact_name? }`, returns `{ job_id }` |
| `/outreach/status/:id` | GET | Returns `{ status: running \| done \| failed, current_step: string }` |
| `/outreach/result/:id` | GET | Returns full outreach package (email, LinkedIn note, schedule JSON, data_confidence) |
| `/outreach/result/:id` | PUT | Updates email/LinkedIn draft in place (post-generation edits) |
| `/outreach/send/:id` | POST | Human-approved send — calls Resend API, updates job to `sent` |
| `/outreach/retry/:id` | POST | Re-runs crew for a failed job |
| `/outreach/history` | GET | Returns past runs for the authenticated user |
| `/crm/pipeline` | GET | Returns mock CRM records (used by Scheduler Agent as a tool) |

**Error responses:** All endpoints return `{ error: string, code: string }` on failure. Rate limit exceeded returns HTTP 429 with `{ error: "Rate limit exceeded", code: "RATE_LIMIT", retry_after: 3600 }`.

### Frontend

- **Onboarding:** URL input → progress indicator → editable pre-filled profile form → confirm
- **Generate:** Company name (validated: max 100 chars) + optional contact → polling every 3s with step label (Research → Personalizing → Scheduling → Done)
- **Result:** Formatted email with subject, LinkedIn note, schedule card, `data_confidence` badge. Inline-editable email subject, email body, LinkedIn note. **"Approve & Send"** and **"Edit"** (toggles edit mode, saves on blur). Failed state shows `error_message` + Retry button.
- **History:** Table of past runs — company, status (`draft` / `approved` / `sent` / `bounced`), sent date, token usage, `data_confidence`

---

## Non-Functional Requirements

- **Latency:** Outreach job completion under 90 seconds (p95); ingestion job under 60 seconds (p95)
- **Rate limiting:** Max 10 outreach crew runs per API key per hour; token budget of 100K tokens per user per month
- **Reliability:** Retry failed agent tasks up to 3 times with exponential backoff before marking job as `failed`. Jobs persist across server restarts (queue-backed, not in-memory).
- **Async queue:** ARQ (async Redis queue) — chosen over FastAPI BackgroundTasks for job persistence on restart, and over Celery for async-native simplicity. Redis also serves as the rate-limit counter store.
- **Deliverability:** All sends include `List-Unsubscribe` header (CAN-SPAM compliance); sent from user's verified custom domain via Resend
- **Observability:** All agent decisions and tool calls logged to LangSmith; structured JSON logs for all API events
- **Auth:** Email + password registration and login. Passwords hashed with bcrypt. Short-lived JWT access token (30 min) returned in response body; long-lived refresh token (7 days) in `httpOnly` `Secure` cookie. All protected endpoints require `Authorization: Bearer <access_token>`. Multi-user, no tenants — each user's data is isolated by `user_id`.
- **Input security:** `company_name` and `contact_name` are user-supplied strings that flow into agent prompts. Sanitize to max 100 chars, alphanumeric + spaces + hyphens only, before use. Treat as untrusted in all prompt interpolations.
- **Deployment:** Dockerised; backend (API + worker + Postgres + Redis) on Railway (Hobby plan); frontend on Vercel (free tier)

---

## Architecture Overview

```
React Frontend
     │ HTTPS / polling (3s interval)
FastAPI Backend  ←→  PostgreSQL (jobs, results, users, product_profiles)
     │               Redis (ARQ job queue + rate-limit counters)
     ├── Ingestion Crew (ARQ background job — onboarding)
     │     ├─ Scraper Agent  →  Playwright + ScrapeWebsiteTool
     │     └─ Extractor Agent  →  GPT-4o
     │          context=[scrape_task]
     │
     ├── Outreach Crew (ARQ background job — per prospect)
     │     ├─ Research Agent  →  SerperDev + ScrapeWebsite
     │     ├─ Personalization Agent  →  GPT-4o + context=[research_task] + product_profile input
     │     └─ Scheduler Agent  →  Mock CRM API + context=[research_task]
     │
     └── Send Layer (on human approval)
           └─ Resend API  →  email delivered to prospect
                │
           LangSmith (Observability — all agent traces)
```

---

## Data Model

**`users`**

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | Primary key |
| `api_key_hash` | TEXT | SHA-256 hash of the user's API key |
| `email` | TEXT | Optional — for Resend sender verification |
| `resend_domain` | TEXT | Verified sending domain |
| `created_at` | TIMESTAMP | |

**`product_profiles`**

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | Primary key |
| `user_id` | UUID | FK to `users.id` |
| `source_url` | TEXT | URL used for ingestion |
| `product_name` | TEXT | |
| `one_liner` | TEXT | |
| `target_customer` | TEXT | |
| `pain_points` | TEXT[] | Array of strings |
| `differentiators` | TEXT[] | Array of strings |
| `case_studies` | TEXT[] | Array of strings |
| `cta` | TEXT | |
| `icp` | TEXT | Ideal customer profile |
| `avoid_messaging` | TEXT | Always manually entered |
| `is_active` | BOOLEAN | Only one active profile per user; toggling activates and deactivates others |
| `created_at` | TIMESTAMP | |
| `updated_at` | TIMESTAMP | |

**`outreach_jobs`**

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | Primary key |
| `user_id` | UUID | FK to `users.id` |
| `product_profile_id` | UUID | FK — snapshot of profile used for this run |
| `company_name` | TEXT | |
| `contact_name` | TEXT | Optional |
| `status` | TEXT | `running`, `done`, `failed` |
| `current_step` | TEXT | `researching \| personalizing \| scheduling \| complete` |
| `send_status` | TEXT | `draft`, `approved`, `sent`, `bounced`, `replied` |
| `data_confidence` | TEXT | `low \| medium \| high` — set by Personalization Agent |
| `email_subject` | TEXT | |
| `email_draft` | TEXT | |
| `linkedin_draft` | TEXT | |
| `schedule_json` | JSONB | `{ send_at, channel, recommended_window, priority, flag_for_human, flag_reason }` |
| `resend_message_id` | TEXT | Populated after send |
| `sent_at` | TIMESTAMP | |
| `error_message` | TEXT | Populated on failure — shown to user |
| `retry_count` | INTEGER | Default 0; incremented on each retry attempt |
| `token_usage` | INTEGER | Total tokens consumed |
| `created_at` | TIMESTAMP | |
| `completed_at` | TIMESTAMP | |

---

## Testing Strategy

| Layer | Approach |
|---|---|
| **Unit tests** | Pytest — Pydantic schema validation, API request/response shapes, utility functions |
| **API tests** | `httpx.AsyncClient` with FastAPI `TestClient` — all endpoints, including error and 429 cases |
| **Agent tests** | LLM calls mocked with `pytest-recording` (VCR cassettes) — record one real run per agent, replay in CI without burning tokens |
| **Integration test** | One full crew run per crew using `GPT-4o-mini` (cost-reduced) against a live but sandboxed DB — golden path only |
| **Dev environment** | `MOCK_MODE=true` env var bypasses all LLM and external tool calls, returns fixture JSON — enables rapid frontend iteration without API keys |

CI runs unit + API tests on every commit; integration tests run nightly.

---

## Demo & Portfolio

For showcasing the project to reviewers and recruiters:

- **`MOCK_MODE=true`**: When set, crew runs return pre-recorded fixture results instantly (no OpenAI/Serper keys needed). The UI behaves identically — polling, progress steps, result display, approve flow all work.
- **Seed script** (`scripts/seed_demo.py`): Populates a sample product profile, 5 completed outreach jobs (mix of `draft`, `sent`, `bounced` statuses), and mock CRM records. Run with `python scripts/seed_demo.py`.
- **`.env.example`**: Committed to repo. Documents all required environment variables with descriptions and links to where keys are obtained.
- **README**: Covers project purpose, architecture diagram, local setup (Docker Compose), mock mode instructions, and screenshots of the key flows.

---

## Privacy & Data Retention

- **Scraped prospect data** is stored implicitly in `email_draft` and research context. Under GDPR Article 17, if a prospect requests erasure, the relevant `outreach_jobs` rows must be deleted. The app is a single-user tool in v1 — users are responsible for their own compliance.
- **Data retention**: `outreach_jobs` rows older than 12 months are eligible for purge. No automated purge in v1 — documented as a manual admin operation.
- **Right-to-delete endpoint**: `DELETE /outreach/:id` — hard deletes the job row and its draft content. Not exposed in the UI in v1 but available via API.
- **No third-party analytics** on the frontend. LangSmith receives agent traces — ensure no PII (prospect email addresses, contact names) flows into trace metadata.

---

## Success Metrics

| Metric | Target |
|---|---|
| Outreach job completion time (p95) | < 90 seconds |
| Ingestion job completion time (p95) | < 60 seconds |
| Agent task failure rate | < 5% |
| Email draft quality score (self-rated, 1–5) | ≥ 4.0 avg |
| Human-review flag accuracy (no false negatives on in-pipeline prospects) | 100% |
| Token cost per outreach run | < $0.15 (~2 GPT-4o calls at ~15K tokens each) |
| Email deliverability (inbox placement rate) | > 90% |

---

## Out of Scope (v1)

- Fully autonomous sending without human approval (intentional — see Design Decisions)
- LinkedIn message sending (LinkedIn API terms prohibit automated messaging)
- CRM sync (Salesforce, HubSpot connectors)
- Multi-language outreach
- Reply detection and follow-up sequencing (→ v2, see below)
- Team management / multi-seat billing
- WebSocket-based real-time agent streaming (v2 — polling at 3s interval is sufficient for current p95 latency target)
- Batch multi-prospect processing (→ v2, see below)

---

## v2 Roadmap

The four features below are intentionally deferred to v2. Each one requires a LangGraph capability that is not used in v1 — they are the primary reason the v1 graph architecture is built on LangGraph rather than plain sequential function calls.

---

### Feature 1 — Low-Confidence Research Pause
**LangGraph capability required:** Conditional edges + `interrupt()` for human-in-the-loop within the graph

**Problem:** When the Research Agent returns `data_confidence: low` (obscure company, minimal web presence), v1 silently degrades to a generic semi-personalised email. The user only discovers this after reading the draft.

**v2 behaviour:** After the research node completes, a conditional edge checks `data_confidence`. If `low`, the graph pauses mid-run and surfaces a clarification card in the UI: *"I couldn't find enough about Acme Corp to personalise this well. Can you fill in any of these gaps?"* — with pre-populated fields for tech stack, pain points, and recent news. The user submits their additions; the graph resumes from the research node with the enriched context, then proceeds to personalisation.

**Why it requires LangGraph:** The graph must pause, wait for external input of unknown duration, and resume from its saved state. LangGraph's `interrupt()` + Postgres checkpointer handles this natively. A plain function sequence has no concept of suspending mid-execution and resuming with new inputs.

---

### Feature 2 — Draft Quality Self-Critique Loop
**LangGraph capability required:** Cycles with conditional exit edges

**Problem:** The Personalization Agent produces variable quality drafts. v1 has no quality gate — every draft goes straight to the user regardless of how generic or weak it is.

**v2 behaviour:** After the personalization node writes the draft, a **Critic node** scores it against four criteria: personalisation depth, relevance of product-prospect fit, clarity of CTA, and tone appropriateness. Each criterion is scored 1–5 by the LLM. If the aggregate score is below 3.5, the graph loops back to the personalization node with the critique as feedback: *"The email doesn't reference Acme Corp's recent Series B. The CTA is too vague."* The loop runs a maximum of 2 revision cycles before proceeding regardless of score.

**Why it requires LangGraph:** This is a true cycle in the execution graph, not a linear sequence. `personalize_node → critic_node → (score ≥ 3.5 OR attempts ≥ 2?) → schedule_node | personalize_node`. Implementing a conditional loopback cleanly in a plain function sequence requires bespoke retry logic that becomes messy with state; LangGraph makes the cycle a first-class construct.

---

### Feature 3 — Resumable Runs After Failure
**LangGraph capability required:** Persistent graph checkpointing (Postgres checkpointer)

**Problem:** v1 retries a failed job from scratch. If the Research Agent ran successfully (15–20 seconds, 2–3 Serper queries, 1 Playwright scrape) but the Personalization Agent failed due to an OpenAI timeout, the retry wastes time and tokens re-running research on the same company.

**v2 behaviour:** LangGraph's Postgres checkpointer saves graph state after every node completes. On retry, the graph detects the last successful checkpoint and resumes from the next node — skipping completed work. A job that failed at personalization resumes at personalisation; research output is already in the checkpoint. Users see the job progress indicator jump straight to "Personalizing…" on retry rather than restarting from "Researching…".

**Why it requires LangGraph:** LangGraph's checkpointer persists the full `OutreachState` to Postgres at each node boundary. No other part of the stack (ARQ, FastAPI) has visibility into graph-level state. Replicating this manually would mean serialising and storing intermediate agent outputs explicitly — which is reinventing the checkpointer.

---

### Feature 4 — Batch Multi-Prospect Processing
**LangGraph capability required:** Dynamic fan-out with the `Send()` API

**Status:** ✅ **Shipped** (PR #3) — implemented as specified below: CSV upload (≤20 rows), `Send()` parallel research with fan-in, sequential personalization, and a live "Research X/N · Personalizing Y/N" progress view. Each prospect reuses the existing Result page for review/send.

**Problem:** v1 processes one prospect at a time. A user with 20 prospects to reach out to this week submits 20 individual generate requests and waits for each to complete sequentially.

**v2 behaviour:** User uploads a CSV of prospect companies (up to 20 rows). A single batch job fans out: the Research Agent runs in parallel across all prospects simultaneously using LangGraph's `Send()` API. Once all research tasks complete (fan-in), personalisation runs sequentially for each prospect — sequential because the OpenAI API has rate limits and personalisation benefits from focused context. The user sees a batch progress view: "Research: 18/20 complete. Personalizing: 6/20."

**Why it requires LangGraph:** `Send()` enables dynamic fan-out where the number of parallel branches is determined at runtime (by the number of rows in the CSV), not hardcoded at graph definition time. Parallelising this with plain `asyncio.gather()` is possible but produces no structured state, no per-branch checkpointing, and no clean fan-in. LangGraph's map-reduce pattern handles this as a native construct.

---

## Design Decisions

**Human-in-the-loop before send (mandatory):** Autonomous sending without review risks CAN-SPAM/GDPR violations, sender domain blacklisting, and hallucinated content reaching real prospects. The "Approve & Send" checkpoint retains 95% of the automation value while keeping the user in control — consistent with how Agentforce and Fin AI position human oversight as a trust feature, not a limitation.

**URL ingestion over manual form (primary onboarding path):** A pre-filled, editable profile reduces onboarding drop-off and produces higher-quality agent context than user self-description. Manual form remains as fallback when scraping fails.

**Product profile stored per user, injected per run:** Decoupling the seller's context from the per-run input means users only describe their product once. Storing `product_profile_id` on each job creates an audit trail of which messaging version generated which outreach.

**Polling over WebSockets:** Frontend polls `/outreach/status/:id` at 3-second intervals rather than maintaining a WebSocket connection. Rationale: simpler infra (no connection state on server), acceptable for p95 latency of 90s (30 polling cycles max), and easier to deploy on serverless platforms. WebSocket streaming of per-agent-step events is a v2 enhancement once the core flow is validated.

**ARQ over FastAPI BackgroundTasks:** BackgroundTasks cannot reliably implement retries with backoff or survive server restarts. ARQ provides job persistence in Redis, native async support, and retry semantics — without the operational weight of Celery. Redis is already in the stack for rate limiting.

**Prompt injection mitigation:** `company_name` and `contact_name` are user-controlled inputs that flow into agent prompts. Input is sanitised (max 100 chars, restricted character set) before use. Agent task descriptions treat these fields as data, not as instruction carriers: *"Research the company named: {company_name}"* — not interpolated into system-level instructions.

---

## Milestones

| Week | Deliverable |
|---|---|
| 1 | Working 3-node LangGraph outreach graph in CLI; ReAct research loop, structured personalisation, schedule extraction validated |
| 2 | Ingestion crew (scraper + extractor); onboarding flow with editable pre-fill form |
| 3 | FastAPI backend — all endpoints, ARQ job queue, PostgreSQL + Redis integration |
| 4 | React frontend — onboarding, generate, result display (with edit mode), history tab |
| 5 | Resend integration, "Approve & Send" flow, CAN-SPAM headers, mock mode + seed script |
| 6 | Auth, rate limiting, retry logic, LangSmith observability, Docker packaging, Railway + Vercel deployment, test suite |

---

## Risks & Mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| Prospect website is a React SPA — standard scraper returns blank HTML | High | Upgrade Research Agent scraping to Playwright for JS rendering |
| Seller's product website is auth-gated or sparse | Medium | Graceful fallback to manual form; show which fields could not be extracted |
| LLM returns malformed JSON (breaks downstream agents) | Medium | Use `with_structured_output(PydanticModel)` on all LLM nodes; retry on parse failure |
| Resend domain verification not completed by user | Medium | Block send flow with inline setup guide; test send to user's own address first |
| Token costs exceed budget per user | Low | Hard-cap token budget; surface usage meter in dashboard |
| Graph exceeds max iterations and hangs | Low | Set `recursion_limit=10` on graph compile; ARQ job timeout of 120s |
| Cold email flagged as spam due to domain reputation | Low | Require custom domain (no free Gmail/Outlook); document warmup best practices |
| Prompt injection via company name input | Low | Input sanitisation (max 100 chars, restricted charset); inputs treated as data not instructions in prompts |
| Obscure prospect — Research Agent returns near-empty output | Medium | Personalization Agent degrades gracefully to semi-personalised email; `data_confidence: low` surfaced to user |
| ARQ/Redis unavailable on server restart | Low | Docker Compose includes Redis service; Railway/Render managed Redis add-on documented in deployment guide |
