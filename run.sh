#!/usr/bin/env bash
# One-command dev runner: sets up anything missing, then starts
# the FastAPI backend (:8000) and the Vite frontend (:5173) together.
set -euo pipefail
cd "$(dirname "$0")"

# On macOS, WeasyPrint needs help finding Homebrew's native libraries (pango etc).
for brew_lib in /opt/homebrew/lib /usr/local/lib; do
  if [ -d "$brew_lib" ]; then
    export DYLD_FALLBACK_LIBRARY_PATH="$brew_lib${DYLD_FALLBACK_LIBRARY_PATH:+:$DYLD_FALLBACK_LIBRARY_PATH}"
  fi
done

# --- Backend setup (idempotent) ---
if [ ! -d .venv ]; then
  echo "==> Creating Python virtualenv..."
  python3 -m venv .venv
fi
source .venv/bin/activate

if ! python -c "import fastapi, uvicorn" >/dev/null 2>&1; then
  echo "==> Installing Python dependencies..."
  pip install -r requirements.txt
fi

if ! python -c "import spacy; spacy.load('en_core_web_sm')" >/dev/null 2>&1; then
  echo "==> Downloading spaCy model en_core_web_sm..."
  python -m spacy download en_core_web_sm
fi

if ! python -c "import weasyprint" >/dev/null 2>&1; then
  echo "WARNING: WeasyPrint cannot load its native libraries."
  echo "         On macOS run: brew install pango"
  echo "         PDF generation will fail until this is fixed; continuing anyway."
fi

# --- Frontend setup (idempotent) ---
if [ ! -d frontend/node_modules ]; then
  echo "==> Installing frontend dependencies..."
  (cd frontend && npm install)
fi

# --- Run both, shut both down on Ctrl+C ---
PIDS=()

# Kill a process and all of its descendants (npm -> vite, uvicorn -> reloader).
kill_tree() {
  local pid=$1
  local child
  for child in $(pgrep -P "$pid" 2>/dev/null); do
    kill_tree "$child"
  done
  kill "$pid" >/dev/null 2>&1 || true
}

cleanup() {
  trap - EXIT INT TERM
  echo ""
  echo "==> Shutting down..."
  for pid in "${PIDS[@]}"; do
    kill_tree "$pid"
  done
  # Backstop: make sure the dev ports are actually released (listeners only,
  # so we never kill a process that merely has a connection open to them).
  lsof -ti tcp:8000 -sTCP:LISTEN 2>/dev/null | xargs kill >/dev/null 2>&1 || true
  lsof -ti tcp:5173 -sTCP:LISTEN 2>/dev/null | xargs kill >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

echo "==> Starting backend on http://localhost:8000"
uvicorn backend.main:app --reload --port 8000 &
PIDS+=($!)

echo "==> Starting frontend on http://localhost:5173"
(cd frontend && npm run dev) &
PIDS+=($!)

echo ""
echo "  App:          http://localhost:5173"
echo "  API health:   http://localhost:8000/api/health"
echo "  Press Ctrl+C to stop both."
echo ""

wait
