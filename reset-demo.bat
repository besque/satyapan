@echo off
REM Reset the demo (fresh test data, dates relative to today) and start the website.  Takes about a minute.
cd /d "%~dp0"
echo Stopping the website...
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }"
set PYTHONIOENCODING=utf-8
set HF_HUB_DISABLE_SYMLINKS_WARNING=1
echo Loading test data...
.venv\Scripts\python -W ignore scripts\seed.py
call "%~dp0start.bat"
