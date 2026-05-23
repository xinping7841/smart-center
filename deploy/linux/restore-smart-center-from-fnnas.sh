#!/usr/bin/env bash
set -euo pipefail

NAS_HOST='192.168.50.254'
NAS_BASE=''
SSH_OPTS='-i /root/.ssh/id_ed25519_fnnas_backup -o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=10'
RESTORE_NAME="${1:-latest}"
APP_ROOT='/srv/smart-center'
DATA_ROOT='/srv/smart-center-data'
RESTORE_RELEASE_DIR="$APP_ROOT/releases/restore_${RESTORE_NAME}_$(date +%Y%m%d_%H%M%S)"
LOCAL_SNAPSHOT_ROOT="$APP_ROOT/backups/pre_restore"
LOCAL_SNAPSHOT_DIR="$LOCAL_SNAPSHOT_ROOT/$(date +%Y%m%d_%H%M%S)"

if [ -f /etc/smart-center.env ]; then
  # shellcheck disable=SC1091
  source /etc/smart-center.env
fi

NAS_HOST="${SMART_CENTER_BACKUP_NAS_HOST:-$NAS_HOST}"
NAS_BASE="${SMART_CENTER_BACKUP_NAS_BASE:-$NAS_BASE}"

if [ -z "$NAS_BASE" ]; then
  echo "backup target path is empty: set SMART_CENTER_BACKUP_NAS_BASE in /etc/smart-center.env"
  exit 1
fi

if [ "$RESTORE_NAME" = 'latest' ]; then
  SOURCE_DIR="$(ssh $SSH_OPTS root@$NAS_HOST "cat \"$NAS_BASE/latest.txt\"")"
else
  SOURCE_DIR="$NAS_BASE/$RESTORE_NAME"
fi

echo "[restore] source: $SOURCE_DIR"
ssh $SSH_OPTS root@$NAS_HOST "test -d \"$SOURCE_DIR\""

mkdir -p "$RESTORE_RELEASE_DIR" "$DATA_ROOT" "$LOCAL_SNAPSHOT_DIR"

systemctl stop smart-center || true

echo "[restore] snapshot current runtime -> $LOCAL_SNAPSHOT_DIR"
if [ -L "$APP_ROOT/current" ] || [ -d "$APP_ROOT/current" ]; then
  rsync -a --delete \
    --exclude '.git' \
    --exclude '.venv' \
    --exclude '__pycache__' \
    --exclude '*.pyc' \
    "$APP_ROOT/current/" "$LOCAL_SNAPSHOT_DIR/current/"
fi

if [ -d "$DATA_ROOT" ]; then
  rsync -a --delete "$DATA_ROOT/" "$LOCAL_SNAPSHOT_DIR/data/"
fi

if [ -f /etc/smart-center.env ]; then
  cp -a /etc/smart-center.env "$LOCAL_SNAPSHOT_DIR/"
fi

if [ -f /etc/systemd/system/smart-center.service ]; then
  cp -a /etc/systemd/system/smart-center.service "$LOCAL_SNAPSHOT_DIR/"
fi

rsync -az -e "ssh $SSH_OPTS" root@$NAS_HOST:"$SOURCE_DIR/app/current/" "$RESTORE_RELEASE_DIR/"
rsync -az --delete -e "ssh $SSH_OPTS" root@$NAS_HOST:"$SOURCE_DIR/data/" "$DATA_ROOT/"
rsync -az -e "ssh $SSH_OPTS" root@$NAS_HOST:"$SOURCE_DIR/system/smart-center.env" /etc/smart-center.env
rsync -az -e "ssh $SSH_OPTS" root@$NAS_HOST:"$SOURCE_DIR/system/smart-center.service" /etc/systemd/system/smart-center.service

ln -sfn "$RESTORE_RELEASE_DIR" "$APP_ROOT/current"
systemctl daemon-reload
systemctl restart smart-center

echo "[restore] local pre-restore snapshot: $LOCAL_SNAPSHOT_DIR"
systemctl --no-pager --full status smart-center | sed -n '1,30p'
