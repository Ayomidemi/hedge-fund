<!-- This file is purely for developer note and human read allowed only -->

cd root
./scripts/dev-backend.sh
./scripts/stop-backend.sh

cd backend
.venv/bin/alembic upgrade head
.venv/bin/python -m app.scripts.sync_invest_fixed_income --force

Optional FMDQ fixed-income feed:
HF_FMDQ_API_KEY=
HF_FMDQ_FIXED_INCOME_PATH=
HF_FMDQ_API_KEY_HEADER=Authorization

cd frontend
npm run dev -- --hostname 127.0.0.1 --port 3000
