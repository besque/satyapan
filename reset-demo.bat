@echo off
REM Reload the demo (real data + a fresh simulated cycle), refresh the test results, and start the website.
cd /d "%~dp0"
echo Stopping the website...
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }"
set PYTHONIOENCODING=utf-8
echo Loading the demo...
.venv\Scripts\python -W ignore scripts\seed.py > nul
.venv\Scripts\python -W ignore scripts\evaluate.py
call "%~dp0start.bat"
