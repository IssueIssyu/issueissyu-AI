#!/usr/bin/env bash
set -euo pipefail

echo "[EB][playwright] Resolving Python runtime..."

PYTHON_BIN=""
if compgen -G "/var/app/venv/*/bin/python" > /dev/null; then
  PYTHON_BIN="$(ls -1 /var/app/venv/*/bin/python | head -n 1)"
elif [ -x "/opt/python/run/venv/bin/python" ]; then
  PYTHON_BIN="/opt/python/run/venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3)"
else
  echo "[EB][playwright] python3 not found"
  exit 1
fi

echo "[EB][playwright] Using Python: ${PYTHON_BIN}"

if ! "${PYTHON_BIN}" -m pip show playwright >/dev/null 2>&1; then
  echo "[EB][playwright] playwright package missing, installing..."
  "${PYTHON_BIN}" -m pip install --no-cache-dir playwright
fi

echo "[EB][playwright] Installing chromium browser..."
"${PYTHON_BIN}" -m playwright install chromium
echo "[EB][playwright] Chromium install complete."

