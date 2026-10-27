@echo off
REM Start (or restart) the website at http://127.0.0.1:8000  - keep this window open, Ctrl+C to stop.
cd /d "%~dp0"
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }"
set PYTHONIOENCODING=utf-8
echo.
echo Website starting at http://127.0.0.1:8000   (keep this window open, press Ctrl+C to stop)
echo.
cd backend
..\.venv\Scripts\python -W ignore -m uvicorn app.api:app --host 127.0.0.1 --port 8000
