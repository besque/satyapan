#!/usr/bin/env bash
# Start (or restart) the website at http://127.0.0.1:8000
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

# Free port 8000 if occupied
lsof -ti:8000 | xargs kill -9 2>/dev/null || true

export PYTHONIOENCODING=utf-8
echo ""
echo "Website starting at http://127.0.0.1:8000"
echo ""

cd backend
exec "$DIR/.venv/bin/python" -W ignore -m uvicorn app.api:app --host 127.0.0.1 --port 8000
