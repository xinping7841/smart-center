#!/usr/bin/env bash
set -euo pipefail

# AI_MODULE: remote_apply_ark_cloud_model
# AI_PURPOSE: Read a temporary Ark key file on node-120 and apply cloud_model runtime config.
# AI_BOUNDARY: Writes only /srv/smart-center-data/config.json through the Python config script; does not call control APIs.
# AI_RUNTIME: Run through scripts/ssh_exec.sh after uploading /tmp/smart-center-ark-api-key; root paths use sudo -n.
# AI_RISK: Medium, handles a model API secret and restarts smart-center.service.

KEY_FILE="${ARK_API_KEY_FILE:-/tmp/smart-center-ark-api-key}"
PYTHON="${PYTHON:-/srv/smart-center/.venv/bin/python}"
SCRIPT="/srv/smart-center/current/scripts/remote/configure_ark_cloud_model_20260602.py"

if [ ! -f "$KEY_FILE" ]; then
  echo "missing_key_file=$KEY_FILE" >&2
  exit 1
fi
if [ ! -f "$SCRIPT" ]; then
  echo "missing_script=$SCRIPT" >&2
  exit 1
fi

ARK_API_KEY="$(tr -d '\r\n' < "$KEY_FILE")"
if [ -z "$ARK_API_KEY" ]; then
  echo "empty_key_file=$KEY_FILE" >&2
  exit 1
fi

sudo -n env \
  ARK_API_KEY="$ARK_API_KEY" \
  SMART_CENTER_CONFIG_FILE=/srv/smart-center-data/config.json \
  "$PYTHON" "$SCRIPT"

rm -f "$KEY_FILE"
sudo -n systemctl restart smart-center.service
sleep 2
echo "service_active=$(sudo -n systemctl is-active smart-center.service)"
