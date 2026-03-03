@echo off
setlocal enabledelayedexpansion

echo.
echo ==========================================
echo   Monday BI Agent — Windows Setup
echo ==========================================
echo.

REM ── Check Python ──────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.10+ and add it to PATH.
    pause
    exit /b 1
)

REM ── Check Node ────────────────────────────
node --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Node.js not found. Please install Node.js 18+ from https://nodejs.org
    pause
    exit /b 1
)

REM ── .env file ─────────────────────────────
if not exist ".env" (
    copy ".env.example" ".env" >nul
    echo [OK] Created .env from .env.example
    echo      ^> Please edit .env and add your API keys before starting the servers.
    echo.
) else (
    echo [OK] .env already exists — skipping copy.
)

REM ── Backend venv ──────────────────────────
echo [1/4] Setting up Python virtual environment...
cd backend

if not exist ".venv" (
    python -m venv .venv
    echo [OK] Virtual environment created at backend\.venv
) else (
    echo [OK] Virtual environment already exists.
)

echo [2/4] Installing Python dependencies...
call .venv\Scripts\activate.bat
pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo [ERROR] pip install failed. Check your requirements.txt.
    pause
    exit /b 1
)
echo [OK] Python dependencies installed.
cd ..

REM ── Frontend deps ─────────────────────────
echo [3/4] Installing Node.js dependencies...
cd frontend
call npm install --silent
if errorlevel 1 (
    echo [ERROR] npm install failed.
    pause
    exit /b 1
)
echo [OK] Node.js dependencies installed.
cd ..

echo.
echo ==========================================
echo   [4/4] Setup Complete!
echo ==========================================
echo.
echo   NEXT STEPS:
echo   1. Edit .env and fill in your API keys:
echo      - MONDAY_API_TOKEN
echo      - MONDAY_DEALS_BOARD_ID
echo      - MONDAY_WORK_ORDERS_BOARD_ID
echo      - GROK_API_KEY
echo.
echo   2. Start the backend (Terminal 1):
echo      cd backend
echo      .venv\Scripts\activate
echo      python main.py
echo.
echo   3. Start the frontend (Terminal 2):
echo      cd frontend
echo      npm run dev
echo.
echo   4. Open http://localhost:5173
echo.
pause
