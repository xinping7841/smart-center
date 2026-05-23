#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${APP_ROOT:-/srv/smart-center}"
DATA_ROOT="${DATA_ROOT:-/srv/smart-center-data}"
RELEASE_DIR="${RELEASE_DIR:-$APP_ROOT/current}"
SERVICE_NAME="${SERVICE_NAME:-smart-center}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${VENV_DIR:-$APP_ROOT/.venv}"
ENV_FILE="${ENV_FILE:-/etc/smart-center.env}"
PIP_INDEX_URL="${PIP_INDEX_URL:-https://pypi.tuna.tsinghua.edu.cn/simple}"

echo "[1/7] install apt packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y \
  python3 \
  python3-venv \
  python3-pip \
  python3-dev \
  build-essential \
  ffmpeg \
  libgl1 \
  libglib2.0-0 \
  libsm6 \
  libxext6 \
  libgomp1

echo "[2/7] ensure directories"
mkdir -p "$APP_ROOT" "$DATA_ROOT" "$DATA_ROOT/runtime" "$DATA_ROOT/reports" "$APP_ROOT/releases" "$APP_ROOT/backups"

echo "[3/7] create venv"
if [ ! -d "$VENV_DIR" ]; then
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

echo "[4/7] install python requirements"
"$VENV_DIR/bin/pip" install --upgrade pip wheel setuptools
"$VENV_DIR/bin/pip" install \
  --index-url "$PIP_INDEX_URL" \
  --retries 3 \
  --timeout 120 \
  -r "$RELEASE_DIR/requirements.txt"

echo "[5/7] create env file if missing"
if [ ! -f "$ENV_FILE" ]; then
  install -m 0644 "$RELEASE_DIR/deploy/linux/.env.example" "$ENV_FILE"
fi

echo "[6/7] install systemd service"
install -m 0644 "$RELEASE_DIR/deploy/linux/smart-center.service" "/etc/systemd/system/${SERVICE_NAME}.service"
systemctl daemon-reload
systemctl enable "$SERVICE_NAME"

echo "[7/7] restart service"
systemctl restart "$SERVICE_NAME"
systemctl --no-pager --full status "$SERVICE_NAME" || true

echo "install complete"
