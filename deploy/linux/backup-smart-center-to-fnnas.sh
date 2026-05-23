#!/usr/bin/env bash
set -euo pipefail

ENV_FILE='/etc/smart-center.env'
NAS_HOST='192.168.50.254'
NAS_BASE=''
SSH_KEY='/root/.ssh/id_ed25519_fnnas_backup'
SSH_OPTS="-i ${SSH_KEY} -o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=10"
SERVICE_FILE='/etc/systemd/system/smart-center.service'
NOTIFY_SCRIPT='/usr/local/bin/notify-backup-result.py'
LOG_FILE='/srv/smart-center-data/runtime/backup_to_fnnas.log'
STAMP="$(date +%F_%H%M%S)"
TMP_LATEST_FILE="/tmp/smart-center-latest-${STAMP}.txt"
START_TS="$(date +%s)"

APP_DIR='/srv/smart-center/current'
DATA_DIR='/srv/smart-center-data'
BACKUP_KEEP_COUNT='14'
APP_SIZE_HUMAN=''
DATA_SIZE_HUMAN=''

if [ -f "$ENV_FILE" ]; then
  # shellcheck disable=SC1090
  source "$ENV_FILE"
fi

APP_DIR="${SMART_CENTER_APP_DIR:-$APP_DIR}"
DATA_DIR="${SMART_CENTER_DATA_DIR:-$DATA_DIR}"
BACKUP_KEEP_COUNT="${SMART_CENTER_BACKUP_KEEP_COUNT:-$BACKUP_KEEP_COUNT}"
NAS_HOST="${SMART_CENTER_BACKUP_NAS_HOST:-$NAS_HOST}"
NAS_BASE="${SMART_CENTER_BACKUP_NAS_BASE:-$NAS_BASE}"

if [ -z "$NAS_BASE" ]; then
  echo "backup target path is empty: set SMART_CENTER_BACKUP_NAS_BASE in /etc/smart-center.env"
  exit 1
fi

TARGET="${NAS_BASE}/${STAMP}"
LATEST_TXT="${NAS_BASE}/latest.txt"

mkdir -p "${DATA_DIR}/runtime"
exec >>"$LOG_FILE" 2>&1

format_duration() {
  local total="$1"
  local hours minutes seconds
  hours=$(( total / 3600 ))
  minutes=$(( (total % 3600) / 60 ))
  seconds=$(( total % 60 ))

  if [ "$hours" -gt 0 ]; then
    printf '%dh%02dm%02ds' "$hours" "$minutes" "$seconds"
    return
  fi
  if [ "$minutes" -gt 0 ]; then
    printf '%dm%02ds' "$minutes" "$seconds"
    return
  fi
  printf '%ss' "$seconds"
}

notify() {
  local status="$1"
  local message="$2"
  local error_summary="${3:-}"
  local duration_sec duration_text

  duration_sec="$(( $(date +%s) - START_TS ))"
  duration_text="$(format_duration "$duration_sec")"

  if [ -x "$NOTIFY_SCRIPT" ]; then
    echo "[$(date '+%F %T')] notify -> status=${status} message=${message} target=${TARGET}"
    if BACKUP_STATUS="$status" \
      BACKUP_MESSAGE="$message" \
      BACKUP_TARGET="$TARGET" \
      BACKUP_TARGET_NAME="$STAMP" \
      BACKUP_HOST="$(hostname)" \
      BACKUP_DURATION_SEC="$duration_sec" \
      BACKUP_DURATION_TEXT="$duration_text" \
      BACKUP_APP_SIZE="$APP_SIZE_HUMAN" \
      BACKUP_DATA_SIZE="$DATA_SIZE_HUMAN" \
      BACKUP_ERROR_SUMMARY="$error_summary" \
      BACKUP_KEEP_COUNT="$BACKUP_KEEP_COUNT" \
      BACKUP_RESTORE_HINT="bash /usr/local/bin/restore-smart-center-from-fnnas.sh ${STAMP}" \
      python3 "$NOTIFY_SCRIPT"; then
      echo "[$(date '+%F %T')] notify -> done"
    else
      echo "[$(date '+%F %T')] notify -> failed"
    fi
  fi
}

on_error() {
  local line_no="$1"
  local exit_code="$2"
  local summary="script exited at line ${line_no} with code ${exit_code}"

  echo "[$(date '+%F %T')] backup failed: $summary"
  notify failed backup_failed "$summary"
}

trap 'on_error ${LINENO} $?' ERR

echo "[$(date '+%F %T')] backup start -> $TARGET"
echo "[$(date '+%F %T')] app dir: $APP_DIR"
echo "[$(date '+%F %T')] data dir: $DATA_DIR"

APP_SIZE_HUMAN="$(du -shL "$APP_DIR" 2>/dev/null | awk '{print $1}')"
DATA_SIZE_HUMAN="$(du -sh "$DATA_DIR" 2>/dev/null | awk '{print $1}')"

ssh $SSH_OPTS root@"$NAS_HOST" "mkdir -p \"$TARGET\" \"$TARGET/system\" \"$TARGET/app\" \"$TARGET/data\""

rsync -az --delete -e "ssh $SSH_OPTS" \
  --exclude '.git' \
  --exclude '.venv' \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  "${APP_DIR}/" root@"$NAS_HOST":"$TARGET/app/current/"

rsync -az -e "ssh $SSH_OPTS" \
  --exclude 'runtime/*.log' \
  "${DATA_DIR}/" root@"$NAS_HOST":"$TARGET/data/"

if [ -f "$ENV_FILE" ]; then
  rsync -az -e "ssh $SSH_OPTS" "$ENV_FILE" root@"$NAS_HOST":"$TARGET/system/"
fi

if [ -f "$SERVICE_FILE" ]; then
  rsync -az -e "ssh $SSH_OPTS" "$SERVICE_FILE" root@"$NAS_HOST":"$TARGET/system/"
fi

printf '%s\n' "$TARGET" > "$TMP_LATEST_FILE"
rsync -az -e "ssh $SSH_OPTS" "$TMP_LATEST_FILE" root@"$NAS_HOST":"$LATEST_TXT"
rm -f "$TMP_LATEST_FILE"

ssh $SSH_OPTS root@"$NAS_HOST" \
  "find \"$NAS_BASE\" -mindepth 1 -maxdepth 1 -type d | sort | head -n -${BACKUP_KEEP_COUNT} | xargs -r rm -rf"

echo "[$(date '+%F %T')] backup done"
notify success backup_completed
