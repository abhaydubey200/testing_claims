@echo off
title Odometer Photo Audit - one-time setup
cd /d "%~dp0"
echo ============================================================
echo   Odometer Photo Audit - one-time setup (needs internet)
echo ============================================================
set "PY="
for %%V in (3.12 3.11 3.10) do (
  if not defined PY ( py -%%V -c "import sys" >nul 2>&1 && set "PY=py -%%V" )
)
if not defined PY (
  python -c "import sys; sys.exit(0 if (3,10) <= sys.version_info[:2] <= (3,12) else 1)" >nul 2>&1 && set "PY=python"
)
if not defined PY (
  echo.
  echo Python 3.10, 3.11 or 3.12 was not found.
  echo Install Python 3.12 from https://www.python.org/downloads/  ^(tick "Add python.exe to PATH"^)
  echo then run SETUP.bat again.
  pause & exit /b 1
)
echo Using: %PY%
if not exist ".venv\Scripts\python.exe" (
  %PY% -m venv .venv || ( echo Could not create the Python environment. & pause & exit /b 1 )
)
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo Installing packages failed. If your office uses a proxy, ask IT for the proxy address and run:
  echo   .venv\Scripts\python.exe -m pip install --proxy http://PROXY:PORT -r requirements.txt
  pause & exit /b 1
)
".venv\Scripts\python.exe" -c "from rapidocr_onnxruntime import RapidOCR; RapidOCR(); print('Photo reader ready')"
echo.
echo Building the screen (one time, needs Node.js)...
call npm --version || (
  echo Node.js was not found. Install it from https://nodejs.org/ then run SETUP.bat again.
  pause & exit /b 1
)
pushd web
if not exist "node_modules" (
  call npm install --no-audit --no-fund
  if errorlevel 1 ( popd & echo Installing the screen packages failed. & pause & exit /b 1 )
)
call npm run build
if errorlevel 1 ( popd & echo Building the screen failed. & pause & exit /b 1 )
popd
echo.
echo Setup finished. Start the app with RUN_APP.bat
pause
