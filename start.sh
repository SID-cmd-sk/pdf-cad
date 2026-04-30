#!/usr/bin/env bash
# CAD/Assist — one-command local launcher.
#
# This script is for LOCAL execution on a user's machine (not inside the
# Emergent preview container, which uses supervisor). It auto-detects Python
# and Node, bootstraps a venv, installs deps, seeds the SQLite DB and starts
# both the FastAPI backend and the React UI.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

BACKEND_PORT="${BACKEND_PORT:-8001}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"
DATA_ROOT="$SCRIPT_DIR/backend/data"

log() { printf "\033[36m[cadassist]\033[0m %s\n" "$*"; }
warn() { printf "\033[33m[cadassist]\033[0m %s\n" "$*"; }
err() { printf "\033[31m[cadassist]\033[0m %s\n" "$*"; }

# ---------- Python ----------
if ! command -v python3 >/dev/null 2>&1; then
    err "python3 not found. Install Python 3.10+ from https://www.python.org"
    exit 1
fi

PYV=$(python3 -c 'import sys; print("%d.%d"%sys.version_info[:2])')
log "Using python $PYV"
python3 - <<'PY'
import sys
if sys.version_info < (3, 10):
    print("Python 3.10+ is required.")
    raise SystemExit(1)
PY

# ---------- Tesseract ----------
if ! command -v tesseract >/dev/null 2>&1; then
    warn "Tesseract not found. OCR will be skipped. Install with:"
    warn "  macOS:  brew install tesseract"
    warn "  Debian: sudo apt install -y tesseract-ocr"
    warn "  Windows: https://github.com/UB-Mannheim/tesseract/wiki"
fi

# ---------- venv ----------
VENV_DIR="$SCRIPT_DIR/.venv"
if [ ! -d "$VENV_DIR" ]; then
    log "Creating virtualenv at $VENV_DIR"
    python3 -m venv "$VENV_DIR"
fi
# shellcheck source=/dev/null
source "$VENV_DIR/bin/activate"

log "Installing backend dependencies (first run only)…"
pip install --upgrade pip >/dev/null
pip install -r backend/requirements.txt

# ---------- Data folders ----------
mkdir -p "$DATA_ROOT/uploads" "$DATA_ROOT/previews" "$DATA_ROOT/outputs" "$SCRIPT_DIR/logs"

# ---------- Samples ----------
if [ ! -d "$SCRIPT_DIR/samples" ] || [ -z "$(ls -A "$SCRIPT_DIR/samples" 2>/dev/null)" ]; then
    log "Generating sample drawings…"
    (cd backend && python sample_gen.py)
fi

# ---------- Frontend deps ----------
if command -v yarn >/dev/null 2>&1; then
    PM="yarn"
elif command -v npm >/dev/null 2>&1; then
    PM="npm"
else
    err "Neither yarn nor npm found. Install Node.js 18+ from https://nodejs.org"
    exit 1
fi

if [ ! -d "$SCRIPT_DIR/frontend/node_modules" ]; then
    log "Installing frontend dependencies with $PM…"
    (cd frontend && $PM install)
fi

# ---------- Start ----------
log "Starting backend on :$BACKEND_PORT"
(cd backend && uvicorn server:app --host 0.0.0.0 --port "$BACKEND_PORT") &
BACK_PID=$!

trap 'kill $BACK_PID 2>/dev/null || true' EXIT

for _ in $(seq 1 30); do
    if curl -fsS "http://localhost:$BACKEND_PORT/api/health" >/dev/null 2>&1; then
        break
    fi
    sleep 1
done
if ! curl -fsS "http://localhost:$BACKEND_PORT/api/health" >/dev/null 2>&1; then
    err "Backend failed to start. Check logs and dependencies, then retry."
    exit 1
fi

log "Starting frontend on :$FRONTEND_PORT"
(cd frontend && PORT="$FRONTEND_PORT" REACT_APP_BACKEND_URL="http://localhost:$BACKEND_PORT" $PM start)
