@echo off
REM Reading tracker - local web app launcher
REM (messages kept ASCII so they render in any console codepage)
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [setup] Creating virtual environment...
  py -3 -m venv .venv
  if errorlevel 1 (
    echo [error] Python 3 not found. Install it from python.org and run again.
    pause
    exit /b 1
  )
  echo [setup] Installing dependencies...
  ".venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
  ".venv\Scripts\python.exe" -m pip install --quiet -r requirements.txt
)

echo.
echo   Reading tracker is starting.
echo     This PC : http://127.0.0.1:8765
echo     Phone   : http://^<this-PC-IP^>:8765   (same Wi-Fi, run ipconfig for the IP)
echo.
echo   Press Ctrl+C to stop.
echo.

start "" http://127.0.0.1:8765
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port 8765
