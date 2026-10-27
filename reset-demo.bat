@echo off
REM Reset the demo and start the website.   reset-demo        = quick (seconds)
REM                                          reset-demo full   = full (about 15 minutes)
cd /d "%~dp0"
echo Stopping the website...
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }"
set PYTHONIOENCODING=utf-8
echo Resetting the demo...
.venv\Scripts\python -W ignore scripts\reset_demo.py %1
call "%~dp0start.bat"
