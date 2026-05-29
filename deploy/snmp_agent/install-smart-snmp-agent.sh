#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${SMART_CENTER_APP_DIR:-/srv/smart-center/current}"
VENV_DIR="${SMART_CENTER_VENV_DIR:-/srv/smart-center/.venv}"
ENV_FILE="${SMART_SNMP_AGENT_ENV_FILE:-/etc/smart-snmp-agent.env}"
SERVICE_FILE="/etc/systemd/system/smart-snmp.service"

if [ ! -d "$APP_DIR" ]; then
  echo "app dir not found: $APP_DIR" >&2
  exit 1
fi

if [ ! -x "$VENV_DIR/bin/python" ]; then
  echo "python venv not found: $VENV_DIR" >&2
  exit 1
fi

"$VENV_DIR/bin/python" -m pip install -q -r "$APP_DIR/deploy/snmp_agent/requirements-snmp-agent.txt"

sudo -n install -m 0644 "$APP_DIR/deploy/snmp_agent/smart-snmp.service" "$SERVICE_FILE"
if [ ! -f "$ENV_FILE" ]; then
  sudo -n tee "$ENV_FILE" >/dev/null <<'EOF_ENV'
SMART_SNMP_AGENT_HOST=0.0.0.0
SMART_SNMP_AGENT_PORT=6916
SMART_SNMP_AGENT_CONFIG=/srv/smart-center-data/config.json
SMART_SNMP_AGENT_MAX_WORKERS=4
SMART_SNMP_AGENT_IDLE_SLEEP_SEC=0.25
SMART_SNMP_AGENT_CONFIG_RELOAD_SEC=30
EOF_ENV
fi

sudo -n systemctl daemon-reload
sudo -n systemctl enable --now smart-snmp.service
sleep 2
systemctl --no-pager status smart-snmp.service
