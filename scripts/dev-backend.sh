#!/usr/bin/env bash
# Start the full backend stack: Redis, API, Celery worker + beat.
# Ctrl+C stops everything cleanly.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"
VENV="$BACKEND/.venv"
API_HOST="${HF_API_HOST:-127.0.0.1}"
API_PORT="${HF_API_PORT:-8001}"

if [[ ! -x "$VENV/bin/uvicorn" ]]; then
  echo "Missing backend venv. Run:"
  echo "  cd backend && python -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 1
fi

cd "$ROOT"
echo "→ Starting Redis (docker)..."
docker compose up -d redis

echo "→ Waiting for Redis..."
for _ in {1..30}; do
  if docker compose exec -T redis redis-cli ping 2>/dev/null | grep -q PONG; then
    break
  fi
  sleep 0.5
done

PIDS=()
cleanup() {
  echo
  echo "→ Stopping backend processes..."
  for pid in "${PIDS[@]}"; do
    kill "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

cd "$BACKEND"

echo "→ Starting Celery worker + beat..."
"$VENV/bin/celery" -A app.workers.celery_app worker --beat -l info &
PIDS+=($!)

echo "→ Starting API at http://${API_HOST}:${API_PORT}"
"$VENV/bin/uvicorn" app.main:app --host "$API_HOST" --port "$API_PORT" &
PIDS+=($!)

echo
echo "Backend is up. Press Ctrl+C to stop."
wait
