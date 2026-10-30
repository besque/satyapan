#!/usr/bin/env bash
# Reload the demo (real data + a fresh simulated cycle), refresh the test results, and start the website.
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

echo "Stopping the website..."
lsof -ti:8000 | xargs kill -9 2>/dev/null || true

export PYTHONIOENCODING=utf-8
echo "Loading the demo..."
"$DIR/.venv/bin/python" -W ignore scripts/seed.py > /dev/null
"$DIR/.venv/bin/python" -W ignore scripts/evaluate.py
exec "$DIR/start.sh"
