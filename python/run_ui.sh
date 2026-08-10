#!/usr/bin/env bash
# Launch the Streamlit UI on the local network (accessible from other devices
# on the same Wi-Fi/LAN via the "Network URL" that Streamlit prints).
set -euo pipefail
cd "$(dirname "$0")/.."   # repo root (this launcher lives in python/)
# Prefer the project virtualenv (modern Streamlit); fall back to PYTHON or python3.
if [ -n "${PYTHON:-}" ]; then PY="$PYTHON"
elif [ -x ".venv/bin/python" ]; then PY=".venv/bin/python"
else PY="python3"; fi
exec "$PY" -m streamlit run python/app.py --server.address=0.0.0.0 --server.port "${PORT:-8501}"
