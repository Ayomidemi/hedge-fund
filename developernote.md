<!-- This file is purely for developer note and human read allowed only -->

cd root
./scripts/dev-backend.sh
./scripts/stop-backend.sh

cd backend
.venv/bin/alembic upgrade head

cd frontend
npm run dev -- --hostname 127.0.0.1 --port 3000