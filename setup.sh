#!/usr/bin/env bash
set -euo pipefail

echo ""
echo "=========================================="
echo "  Monday BI Agent — Unix/macOS Setup"
echo "=========================================="
echo ""

# ── Check Python ────────────────────────────
if ! command -v python3 &>/dev/null; then
  echo "[ERROR] python3 not found. Please install Python 3.10+."
  exit 1
fi

# ── Check Node ──────────────────────────────
if ! command -v node &>/dev/null; then
  echo "[ERROR] node not found. Please install Node.js 18+ from https://nodejs.org"
  exit 1
fi

# ── .env file ───────────────────────────────
if [ ! -f ".env" ]; then
  cp .env.example .env
  echo "[OK] Created .env from .env.example"
  echo "     > Please edit .env and add your API keys before starting."
  echo ""
else
  echo "[OK] .env already exists — skipping copy."
fi

# ── Backend venv ────────────────────────────
echo "[1/4] Setting up Python virtual environment..."
cd backend

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
  echo "[OK] Virtual environment created at backend/.venv"
else
  echo "[OK] Virtual environment already exists."
fi

# shellcheck disable=SC1091
source .venv/bin/activate
pip install -r requirements.txt --quiet
echo "[OK] Python dependencies installed."
deactivate
cd ..

# ── Frontend deps ────────────────────────────
echo "[3/4] Installing Node.js dependencies..."
cd frontend
npm install --silent
echo "[OK] Node.js dependencies installed."
cd ..

echo ""
echo "=========================================="
echo "  [4/4] Setup Complete!"
echo "=========================================="
echo ""
echo "  NEXT STEPS:"
echo "  1. Edit .env and fill in your API keys"
echo ""
echo "  2. Start the backend (Terminal 1):"
echo "     cd backend && source .venv/bin/activate && python main.py"
echo ""
echo "  3. Start the frontend (Terminal 2):"
echo "     cd frontend && npm run dev"
echo ""
echo "  4. Open http://localhost:5173"
echo ""
