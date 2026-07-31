#!/bin/bash
# NEURAL_MESH Memory Service — Production Startup
# Usage: ./start-mesh.sh [--dev]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# ─── Load env ────────────────────────────────────────────────
if [ -f ".env" ]; then
    set -a
    source .env
    set +a
    echo "[mesh] loaded .env"
else
    echo "[mesh] WARNING: no .env found — using defaults (no auth!)"
fi

# ─── Defaults ────────────────────────────────────────────────
PORT="${NEURAL_MESH_PORT:-4021}"
HOST="${NEURAL_MESH_HOST:-127.0.0.1}"
WORKERS="${NEURAL_MESH_WORKERS:-2}"
TIMEOUT="${NEURAL_MESH_TIMEOUT:-120}"

# ─── Ensure runtime dir exists ───────────────────────────────
mkdir -p "${NEURAL_MESH_SAFE_IO_DIR:-./runtime}"
mkdir -p "${NEURAL_MESH_SAFE_IO_DIR:-./runtime}/exports"

# ─── Sanity check ────────────────────────────────────────────
if [ ! -f "server.py" ]; then
    echo "[mesh] FATAL: server.py not found in $SCRIPT_DIR"
    exit 1
fi

if [ ! -d ".venv-server" ]; then
    echo "[mesh] creating venv..."
    python3 -m venv .venv-server
    .venv-server/bin/pip install flask gunicorn 2>&1 | tail -2
fi

# ─── Start ───────────────────────────────────────────────────
if [ "${1:-}" = "--dev" ]; then
    echo "[mesh] DEV MODE — Flask dev server on $HOST:$PORT"
    exec .venv-server/bin/python server.py
else
    echo "[mesh] PRODUCTION — gunicorn ($WORKERS workers) on $HOST:$PORT"
    exec .venv-server/bin/gunicorn \
        --bind "$HOST:$PORT" \
        --workers "$WORKERS" \
        --timeout "$TIMEOUT" \
        --access-logfile - \
        --error-logfile - \
        --log-level info \
        server:app
fi