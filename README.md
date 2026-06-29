# Autonomous Outreach Assistant

A production-grade **autonomous B2B outreach tool** built to demonstrate real-world agentic AI patterns: multi-agent LangGraph orchestration, human-in-the-loop approval, async job queues, and JWT authentication.

Built by [Anubhav Bansal](https://github.com/anubhavbansal727).

---

## What it does

Sales reps spend 2–3 hours per prospect manually researching companies, writing personalised outreach, and deciding when to send it. This tool automates all of that:

1. **Paste your product URL** → AI scrapes and extracts your product profile automatically
2. **Enter a company name + contact** → AI researches the prospect, writes a personalised cold email and LinkedIn note, and recommends the best send time
3. **Review the draft** → You approve before anything is sent
4. **One click to send** → Email delivered via Resend

**Working at scale?** Upload a CSV of up to 20 prospects on the **Batch** page: research runs in parallel across all of them (LangGraph `Send()` fan-out), then personalised drafts are written one by one — with a live progress view ("Research: 18/20 · Personalizing: 6/20"). Each prospect lands in the same Result page for review and send.

---

## Demo

> **Demo credentials:** `demo@datapulse.io` / `Demo1234!`
>
> Run `python scripts/seed_demo.py` from `backend/` to populate 5 sample outreach jobs.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         React Frontend                          │
│  Onboarding → Generate → Result (approve/edit/send) → History  │
└───────────────────────────┬─────────────────────────────────────┘
                            │ REST + JWT
┌───────────────────────────▼─────────────────────────────────────┐
│                      FastAPI Backend                            │
│  /auth  /profile  /outreach  /crm  /health                     │
└──────────────┬──────────────────────────┬───────────────────────┘
               │ ARQ enqueue              │ DB reads
┌──────────────▼──────────────┐  ┌───────▼──────────┐
│       ARQ Worker            │  │   PostgreSQL 16   │
│  (Redis-backed job queue)   │  │   (async ORM)     │
│                             │  └──────────────────┘
│  ┌──────────────────────┐   │
│  │  IngestionGraph      │   │
│  │  scrape → extract    │   │
│  └──────────────────────┘   │
│                             │
│  ┌──────────────────────┐   │
│  │  OutreachGraph       │   │
│  │  research →          │   │
│  │  personalize →       │   │
│  │  schedule →          │   │
│  │  extract_schedule    │   │
│  └──────────────────────┘   │
└─────────────────────────────┘
```

### LangGraph Graphs

**IngestionGraph** — runs once at onboarding
- `scrape_node`: Playwright scrapes homepage, /pricing, /about, /customers, /case-studies
- `extract_node`: GPT-4o with structured output extracts product profile JSON

**OutreachGraph** — runs per prospect
- `research_node` + tools: ReAct loop using Serper web search and Playwright scraper
- `personalize_node`: GPT-4o writes email subject, body, and LinkedIn note
- `schedule_node` + tools: Checks CRM pipeline, recommends optimal send time
- `extract_schedule_node`: Parses scheduling reasoning into structured output

All graphs are pure Python `StateGraph` — no YAML, no CrewAI patterns.

---

## Stack

| Layer | Tech |
|---|---|
| API | FastAPI 0.115 + Python 3.12 |
| Agent framework | LangGraph 0.2 |
| Job queue | ARQ 0.25 (Redis-backed) |
| Database | PostgreSQL 16 via SQLAlchemy async + asyncpg |
| Migrations | Alembic |
| Auth | python-jose (JWT) + bcrypt |
| LLM | OpenAI GPT-4o via langchain-openai |
| Scraping | Playwright (custom `@tool`) |
| Search | Serper REST API (custom `@tool`) |
| Email | Resend Python SDK |
| Observability | LangSmith (zero-config via env vars) |
| Frontend | React 18 + TypeScript 5 + Vite 5 + Tailwind + shadcn/ui |
| State | TanStack Query v5 (polling) |
| Package manager | `uv` (backend), `npm` (frontend) |

---

## Project Structure

```
autonomous-outreach-assistant/
├── backend/
│   ├── app/
│   │   ├── main.py               # FastAPI app factory + lifespan
│   │   ├── auth/                 # JWT dependency (get_current_user)
│   │   ├── routers/              # auth, profile, outreach, crm, health
│   │   ├── models/               # db.py (ORM) + schemas.py (Pydantic)
│   │   ├── graphs/
│   │   │   ├── ingestion/        # IngestionGraph — scrape + extract
│   │   │   └── outreach/         # OutreachGraph — research + personalise + schedule
│   │   ├── tools/                # scrape.py, search.py, crm.py
│   │   ├── jobs/                 # ARQ job functions
│   │   ├── services/             # resend.py, rate_limiter.py
│   │   └── db/                   # session.py + Alembic migrations
│   ├── fixtures/                 # Mock JSON for MOCK_MODE demo
│   ├── scripts/seed_demo.py      # Seed DB with 5 demo outreach jobs
│   ├── tests/                    # unit/, api/, integration/
│   ├── worker.py                 # ARQ worker entry point
│   └── pyproject.toml
└── frontend/
    └── src/
        ├── api/client.ts         # apiFetch — Bearer injection, 401 retry
        ├── pages/                # Onboarding, Generate, Batch, Result, History, Settings
        ├── components/           # ui/, layout/, onboarding/, outreach/, history/
        ├── hooks/
        │   ├── useJobPolling.ts  # TanStack Query polling (3s interval)
        │   └── useAuth.ts
        └── types/index.ts
```

---

## Quick Start

### Prerequisites

- Python 3.12+
- Node 18+
- Docker (for Postgres + Redis)
- API keys: OpenAI, Serper, Resend

### 1. Start infrastructure

```bash
docker compose up -d postgres redis
```

### 2. Backend

```bash
cd backend
uv sync --frozen
python -m playwright install chromium

cp ../.env.example .env   # fill in your API keys

alembic upgrade head       # run DB migrations

uvicorn app.main:app --reload --port 8000   # API server
python worker.py                             # ARQ worker (separate terminal)
```

### 3. Frontend

```bash
cd frontend
npm install
npm run dev    # http://localhost:5173
```

### Full stack with Docker

```bash
docker compose up --build
```

### Seed demo data

```bash
cd backend
python scripts/seed_demo.py
# Creates demo@datapulse.io / Demo1234! with 5 completed outreach jobs
```

---

## Environment Variables

Copy `.env.example` to `backend/.env` and fill in:

| Variable | Required | Notes |
|---|---|---|
| `OPENAI_API_KEY` | YES | GPT-4o |
| `SERPER_API_KEY` | YES | Web search (100 req/month free tier) |
| `RESEND_API_KEY` | YES | Email delivery |
| `DATABASE_URL` | YES | `postgresql+asyncpg://user:pass@host/db` |
| `REDIS_URL` | YES | `redis://host:6379` |
| `JWT_SECRET_KEY` | YES | Random 32+ byte secret |
| `MOCK_MODE` | NO | Set `true` for demo without real API keys |
| `LANGCHAIN_API_KEY` | NO | LangSmith tracing (optional) |

---

## Key Design Decisions

### Human-in-the-loop is intentional
The outreach graph produces a draft — it never auto-sends. Email delivery only happens via `POST /outreach/{job_id}/send` after the user approves. This mirrors how enterprise agent platforms like Agentforce handle high-stakes automated actions.

### ARQ over Celery
ARQ's async-native design fits naturally with FastAPI and LangGraph's async APIs. No need for a synchronous bridge, and the job functions share the same async DB session pattern as the routers.

### Polling over WebSockets
TanStack Query polling at 3s intervals covers the UI feedback need without the added complexity of WebSocket state management. Jobs typically complete in 30–60 seconds.

### No YAML agent configs
Both LangGraph graphs are pure Python `StateGraph` definitions. Config-as-code means the graph topology is type-checked, testable, and co-located with the node functions.

---

## Running Tests

```bash
cd backend
pytest tests/unit tests/api          # fast, no DB/Redis required
pytest                               # full suite including integration tests
```

---

## Deployment

**Target:** Railway (backend + worker + Postgres + Redis) + Vercel (frontend)

- `backend/railway.toml` — API service config
- `backend/railway.worker.toml` — Worker service (needs 512 MB RAM for Playwright)
- `frontend/vercel.json` — SPA rewrite rules

Estimated cost: ~$2–4/month on Railway Hobby + Vercel free tier.

---

## Agentic Patterns Demonstrated

| Pattern | Implementation |
|---|---|
| Multi-agent orchestration | LangGraph `StateGraph` with typed shared state |
| Dynamic fan-out / map-reduce | Batch processing via LangGraph `Send()` — parallel research, fan-in, sequential personalization |
| ReAct tool-use loops | `research_node` + `ToolNode` with conditional edges |
| Structured output | `llm.with_structured_output(PydanticModel)` |
| Human-in-the-loop | Draft review before email send |
| Async job queue | ARQ with Redis, max 3 retries + exponential backoff |
| Silent auth refresh | `httpOnly` refresh cookie + access token in React memory |
| Mock mode | Fixture-based responses for demo/dev without API keys |
| Observability | LangSmith tracing via zero-config env vars |

---

## License

MIT
