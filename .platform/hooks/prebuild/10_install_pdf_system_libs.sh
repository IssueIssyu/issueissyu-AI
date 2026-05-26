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
    pango-devel \
    cairo \
    cairo-devel \
    cairo-gobject-devel \
    gdk-pixbuf2 \
    glib2 \
    glib2-devel \
    libffi \
    libffi-devel \
    harfbuzz \
    fontconfig \
    freetype \
    gcc \
    pkgconfig \
    python3-devel \
    google-noto-sans-cjk-fonts
elif command -v yum >/dev/null 2>&1; then
  run_as_root yum -y install \
    pango \
    pango-devel \
    cairo \
    cairo-devel \
    cairo-gobject-devel \
    gdk-pixbuf2 \
    glib2 \
    glib2-devel \
    libffi \
    libffi-devel \
    harfbuzz \
    fontconfig \
    freetype \
    gcc \
    pkgconfig \
    python3-devel \
    google-noto-sans-cjk-fonts
elif command -v apt-get >/dev/null 2>&1; then
  run_as_root apt-get update -y
  run_as_root apt-get install -y \
    libpango-1.0-0 \
    libpango1.0-dev \
    libcairo2 \
    libcairo2-dev \
    libgdk-pixbuf-2.0-0 \
    libglib2.0-0 \
    libglib2.0-dev \
    libffi8 \
    libffi-dev \
    libharfbuzz0b \
    fontconfig \
    libfreetype6 \
    gcc \
    pkg-config \
    python3-dev \
    fonts-nanum
else
  echo "[EB][pdf-libs] Unsupported package manager. Install libs manually."
  exit 1
fi

echo "[EB][pdf-libs] System library install complete."

