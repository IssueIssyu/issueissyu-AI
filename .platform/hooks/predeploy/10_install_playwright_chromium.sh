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

run_as_root() {
  if [ "$(id -u)" -eq 0 ]; then
    "$@"
  else
    sudo "$@"
  fi
}

# AL2023에는 xorg-x11-libs 메타 패키지가 없으므로 개별 libX* 패키지로 설치한다.
_CHROMIUM_RPM_PACKAGES=(
  atk at-spi2-atk at-spi2-core
  cups-libs libdrm
  libXcomposite libXcursor libXdamage libXext libXfixes libXi libXrandr libXScrnSaver libXtst
  mesa-libgbm pango cairo alsa-lib libxkbcommon
  nss nspr gtk3
)

echo "[EB][playwright] Installing Chromium system dependencies (root)..."
if command -v dnf >/dev/null 2>&1; then
  run_as_root dnf -y install "${_CHROMIUM_RPM_PACKAGES[@]}"
elif command -v yum >/dev/null 2>&1; then
  run_as_root yum -y install "${_CHROMIUM_RPM_PACKAGES[@]}"
else
  "${PYTHON_BIN}" -m playwright install-deps chromium
fi

WEBAPP_USER="webapp"
if ! id "${WEBAPP_USER}" >/dev/null 2>&1; then
  echo "[EB][playwright] ${WEBAPP_USER} user not found, installing as current user..."
  "${PYTHON_BIN}" -m playwright install chromium
else
  echo "[EB][playwright] Installing Chromium browser as ${WEBAPP_USER}..."
  sudo -u "${WEBAPP_USER}" -H "${PYTHON_BIN}" -m playwright install chromium
fi

echo "[EB][playwright] Chromium install complete."

