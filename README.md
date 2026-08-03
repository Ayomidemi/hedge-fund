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
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

API docs: http://localhost:8000/docs

### 3. Frontend

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
├── models/        # Database models
├── services/      # Business logic
└── strategies/    # Quant / signal logic
```

## Frontend layout

```
frontend/src/
├── app/           # Next.js pages & layouts
├── components/    # UI components
└── lib/           # API client, helpers
```
