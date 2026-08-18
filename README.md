# Hedge Fund Platform

Monorepo for a quantitative trading and portfolio operations platform.

- **Backend:** Python + FastAPI
- **Frontend:** Next.js (App Router, TypeScript, Tailwind)

## Project structure

```
hedge-fund/
├── backend/          # FastAPI API, services, strategies
├── frontend/         # Next.js web app
└── docker-compose.yml
```

## Prerequisites

- Python 3.11+
- Node.js 20+
- Docker (optional, for Postgres + Redis)

## Quick start

### 1. Infrastructure (optional)

```bash
docker compose up -d
```

### 2. Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

API docs: http://localhost:8000/docs

Database health: http://localhost:8000/api/health/db

For Supabase, set `HF_SUPABASE_DATABASE_URL` in the root `.env` or `backend/.env` to the Supabase Postgres pooler connection string. The backend accepts `postgresql://`, `postgres://`, or `postgresql+asyncpg://`, normalizes Postgres URLs for async SQLAlchemy, and applies Supabase pooler-safe connection options.

### 3. Live price platform (Celery worker)

Prices are refreshed centrally by a Celery beat schedule, written to
`instrument_quotes`, applied to every open position (mark-to-market), and
pushed to the frontend over WebSocket (`/api/ws`) via Redis pub/sub.

Start the full backend stack (Redis + API + Celery) with one command:

```bash
./scripts/dev-backend.sh
```

Stop API and Celery:

```bash
./scripts/stop-backend.sh
```

The key timing and News Centre knobs are in the root `.env`:

```env
HF_PRICE_REFRESH_INTERVAL_SECONDS=300   # 5 min on free API tiers; 10 for penny-stock testing
HF_NEWS_POLL_INTERVAL_SECONDS=600       # 10 min default cadence for News Centre polling
HF_NEWS_POLL_JURISDICTIONS=US           # Scheduled News Centre scope; use US,NG only when desired
HF_NEWS_TICKER_REFRESH_TTL_SECONDS=1800 # 30 min cache guard for selected-ticker news refreshes
```

All other tuning (batch size, market-hours gating, staleness threshold,
benchmark tickers, news provider caps) lives in backend constants/services.
Each refresh cycle is audited in `price_refresh_runs` and surfaced on the
Administration page.

### 4. Frontend

```bash
cd frontend
npm install
cp .env.local.example .env.local
npm run dev
```

App: http://localhost:3000

## Backend layout

```
backend/app/
├── api/           # HTTP routes
├── core/          # Config, shared utilities
├── db/            # SQLAlchemy engine/session setup
├── models/        # Database models
├── services/      # Business logic
└── strategies/    # Quant / signal logic
```

## Initial data model

The first database migration establishes the system-of-record tables the fund will build on:

- instruments
- portfolios
- cash ledger entries
- positions
- trades
- model versions
- model recommendations
- risk limits and checks
- evidence snapshots
- ticker memos
- human-versus-model decisions

## Frontend layout

```
frontend/src/
├── app/           # Next.js pages & layouts
├── components/    # UI components
└── lib/           # API client, helpers
```
