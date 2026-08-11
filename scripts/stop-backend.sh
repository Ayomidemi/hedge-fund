#!/usr/bin/env bash
# Stop backend processes started by dev-backend.sh (or run manually).
set -euo pipefail

echo "→ Stopping API and Celery..."
pkill -f "uvicorn app.main:app" 2>/dev/null || true
pkill -f "celery -A app.workers.celery_app" 2>/dev/null || true

if lsof -ti tcp:8001 >/dev/null 2>&1; then
  lsof -ti tcp:8001 | xargs kill -9 2>/dev/null || true
fi

echo "Done. Redis container left running (docker compose stop redis to stop it)."
