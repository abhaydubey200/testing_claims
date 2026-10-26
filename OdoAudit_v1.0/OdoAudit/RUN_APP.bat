@echo off
title Odometer Photo Audit
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" call SETUP.bat
if not exist "web\dist\index.html" call SETUP.bat
echo Starting... the app opens in your browser. Keep this window open while you use it.
set "ODOAUDIT_OPEN_BROWSER=1"
".venv\Scripts\python.exe" -m uvicorn server:app --host 127.0.0.1 --port 8501
pause
