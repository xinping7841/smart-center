#!/usr/bin/env bash
set -euo pipefail

RELEASE_DIR="${1:?release dir required}"
APP_ROOT="${APP_ROOT:-/srv/smart-center}"
DATA_ROOT="${DATA_ROOT:-/srv/smart-center-data}"
CURRENT_LINK="${CURRENT_LINK:-$APP_ROOT/current}"
ENV_FILE="${ENV_FILE:-/etc/smart-center.env}"
RELEASE_NAME="$(basename "$RELEASE_DIR")"

mkdir -p "$APP_ROOT/releases" "$APP_ROOT/backups" "$DATA_ROOT/runtime" "$DATA_ROOT/reports"
ln -sfn "$RELEASE_DIR" "$CURRENT_LINK"

if [ -f "$CURRENT_LINK/REVISION" ]; then
  REVISION="$(tr -d '\r\n' < "$CURRENT_LINK/REVISION")"
else
  REVISION=""
fi
if echo "$RELEASE_NAME" | grep -Eq '^smart-center-release-[0-9]{8}_[0-9]{6}-'; then
  RELEASE_TS="$(printf '%s\n' "$RELEASE_NAME" | sed -E 's/^smart-center-release-([0-9]{8}_[0-9]{6})-.*/\1/')"
else
  RELEASE_TS="$(date +%Y%m%d_%H%M%S)"
fi
printf '%s\n' "$RELEASE_TS" > "$CURRENT_LINK/.codex_deploy_ts.txt"
cat > "$CURRENT_LINK/RELEASE_INFO.json" <<EOF_RELEASE_INFO
{
  "release": "$RELEASE_NAME",
  "release_dir": "$RELEASE_DIR",
  "revision": "$REVISION",
  "created_at": "$(date -Iseconds)",
  "created_by": "deploy/linux/remote_release.sh"
}
EOF_RELEASE_INFO

if [ ! -f "$ENV_FILE" ]; then
  cp "$CURRENT_LINK/deploy/linux/.env.example" "$ENV_FILE"
fi

sed -i "s#^SMART_CENTER_APP_DIR=.*#SMART_CENTER_APP_DIR=$CURRENT_LINK#" "$ENV_FILE"
sed -i "s#^SMART_CENTER_DATA_DIR=.*#SMART_CENTER_DATA_DIR=$DATA_ROOT#" "$ENV_FILE"
sed -i "s#^SMART_CENTER_RUNTIME_DIR=.*#SMART_CENTER_RUNTIME_DIR=$DATA_ROOT/runtime#" "$ENV_FILE"
sed -i "s#^SMART_CENTER_REPORTS_DIR=.*#SMART_CENTER_REPORTS_DIR=$DATA_ROOT/reports#" "$ENV_FILE"
sed -i "s#^SMART_CENTER_CONFIG_FILE=.*#SMART_CENTER_CONFIG_FILE=$DATA_ROOT/config.json#" "$ENV_FILE"
sed -i "s#^SMART_CENTER_DB_FILE=.*#SMART_CENTER_DB_FILE=$DATA_ROOT/monitor.db#" "$ENV_FILE"
sed -i "s#^SMART_CENTER_ENERGY_LOG_FILE=.*#SMART_CENTER_ENERGY_LOG_FILE=$DATA_ROOT/energy_log.json#" "$ENV_FILE"
sed -i "s#^SMART_CENTER_OPERATION_LOG_FILE=.*#SMART_CENTER_OPERATION_LOG_FILE=$DATA_ROOT/operation_logs.json#" "$ENV_FILE"
sed -i "s#^SMART_CENTER_AUDIT_LOG_FILE=.*#SMART_CENTER_AUDIT_LOG_FILE=$DATA_ROOT/audit_logs.json#" "$ENV_FILE"
sed -i "s#^SMART_CENTER_AUTH_USERS_FILE=.*#SMART_CENTER_AUTH_USERS_FILE=$DATA_ROOT/runtime/auth_users.json#" "$ENV_FILE"
sed -i "s#^SMART_CENTER_PROJECTOR_BRANDS_FILE=.*#SMART_CENTER_PROJECTOR_BRANDS_FILE=$CURRENT_LINK/projector_brands.json#" "$ENV_FILE"

bash "$CURRENT_LINK/deploy/linux/install.sh"
