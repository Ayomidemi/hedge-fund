# Frontend

Next.js app for the two paper books: **Invest** and **Capital**.

Invest is the retail account: markets, orders, holdings, cash, and fixed income. Capital is the fund desk: positions, the trade journal, radar, risk, research, and administration. Both talk to the FastAPI backend. Sign-in uses Supabase.

## Prerequisites

- Node.js 20+
- The backend API running. `./scripts/dev-backend.sh` from the repo root serves it at http://127.0.0.1:8001

## Setup

```bash
cd frontend
npm install
cp env.example .env.local
npm run dev
```

App: http://localhost:3000 or http://localhost:3001

`env.example` points `NEXT_PUBLIC_API_URL` at port 8001, which is the port the dev script uses. If that variable is missing, the client falls back to http://localhost:8000. Set the Supabase URL and anon key in `.env.local` before signing in.

## Scripts

```bash
npm run dev     # next dev, webpack
npm run build
npm run start
npm run lint
```

Route and refresh checks live in `tests/` and run with Node’s test runner:

```bash
node --test tests/*.test.mjs
```

## Layout

```
frontend/src/
├── app/
│   ├── invest/          # Invest account
│   ├── capital/         # Capital entry
│   ├── (platform)/      # Capital desk pages
│   ├── login/           # Supabase sign-in
│   └── settings/
├── components/
└── lib/                 # API client and helpers
```

Live quotes and news arrive on the backend WebSocket and refresh the open page. Order entry, mode changes, and account data go through `/api` on `NEXT_PUBLIC_API_URL`.
