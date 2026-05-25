#!/usr/bin/env bash
set -euo pipefail

echo "[EB][pdf-libs] Installing system libraries for WeasyPrint/Playwright..."

run_as_root() {
  if [ "$(id -u)" -eq 0 ]; then
    "$@"
  else
    sudo "$@"
  fi
}

if command -v dnf >/dev/null 2>&1; then
  run_as_root dnf -y install \
    pango \
    cairo \
    gdk-pixbuf2 \
    glib2 \
    libffi \
    harfbuzz \
    fontconfig \
    freetype
elif command -v yum >/dev/null 2>&1; then
  run_as_root yum -y install \
    pango \
    cairo \
    gdk-pixbuf2 \
    glib2 \
    libffi \
    harfbuzz \
    fontconfig \
    freetype
elif command -v apt-get >/dev/null 2>&1; then
  run_as_root apt-get update -y
  run_as_root apt-get install -y \
    libpango-1.0-0 \
    libcairo2 \
    libgdk-pixbuf-2.0-0 \
    libglib2.0-0 \
    libffi8 \
    libharfbuzz0b \
    fontconfig \
    libfreetype6
else
  echo "[EB][pdf-libs] Unsupported package manager. Install libs manually."
  exit 1
fi

echo "[EB][pdf-libs] System library install complete."

