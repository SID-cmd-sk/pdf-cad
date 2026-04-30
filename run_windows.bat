@echo off
REM CAD Assist — Windows one-shot installer / launcher.
REM This script bootstraps everything a fresh Windows machine needs:
REM   * creates a Python virtual environment (if missing)
REM   * installs the backend requirements
REM   * installs frontend node modules
REM   * generates sample drawings on first run
REM   * starts backend + frontend and opens the browser
REM
REM Usage: double-click this file, or run `run_windows.bat` from a terminal.

setlocal ENABLEEXTENSIONS
cd /d "%~dp0"

echo.
echo ==================================================
echo   CAD Assist  -  bootstrapping local environment
echo ==================================================

REM --- Python ---
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python was not found. Install Python 3.10+ from https://www.python.org/downloads/windows/
    pause
    exit /b 1
)

REM --- venv ---
if not exist ".venv\Scripts\python.exe" (
    echo [setup] creating virtual environment...
    python -m venv .venv
)
call .venv\Scripts\activate

echo [setup] installing backend deps...
python -m pip install --upgrade pip >nul
python -m pip install -r backend\requirements.txt

REM --- Tesseract ---
where tesseract >nul 2>&1
if errorlevel 1 (
    echo [warn] Tesseract not found. OCR will be disabled.
    echo [warn] Install from https://github.com/UB-Mannheim/tesseract/wiki then re-run.
)

REM --- Samples ---
if not exist "samples\mechanical_part.png" (
    echo [setup] generating sample drawings...
    pushd backend
    python sample_gen.py
    popd
)

REM --- Frontend deps ---
where yarn >nul 2>&1
if errorlevel 1 (
    where npm >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] Neither yarn nor npm was found. Install Node.js 18+ from https://nodejs.org
        pause
        exit /b 1
    )
    set PM=npm
) else (
    set PM=yarn
)

if not exist "frontend\node_modules" (
    echo [setup] installing frontend deps with %PM% ...
    pushd frontend
    call %PM% install
    popd
)

REM --- Launch ---
echo.
echo [start] launching backend on :8001 ...
start "cadassist-backend" cmd /c ".venv\Scripts\python -m uvicorn backend.server:app --host 127.0.0.1 --port 8001"

timeout /t 3 /nobreak >nul

echo [start] launching frontend on :3000 ...
set REACT_APP_BACKEND_URL=http://127.0.0.1:8001
pushd frontend
start "cadassist-frontend" cmd /c "%PM% start"
popd

timeout /t 4 /nobreak >nul
start "" "http://localhost:3000"

echo.
echo All set. Close the two console windows to stop the app.
echo.
endlocal
