<!-- This file is purely for developer note and human read allowed only -->

cd backend
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8001

cd frontend
npm run dev -- --hostname 127.0.0.1 --port 3000