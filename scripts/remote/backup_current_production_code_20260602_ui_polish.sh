#!/usr/bin/env bash
set -euo pipefail

# AI_MODULE: remote_production_code_backup
# AI_PURPOSE: Back up the current Smart Center production code before the 1080p/wide UI polish.
# AI_BOUNDARY: Read /srv/smart-center/current and write /srv/smart-center/backups only.
# AI_RUNTIME: Run through scripts/ssh_exec.sh; production root paths use sudo -n.

APP_ROOT="/srv/smart-center"
CURRENT="$APP_ROOT/current"
BACKUP_ROOT="$APP_ROOT/backups"
TS="$(date +%Y%m%d_%H%M%S)"
REVISION="unknown"

if [ -f "$CURRENT/REVISION" ]; then
  REVISION="$(sudo -n cat "$CURRENT/REVISION" | tr -d '[:space:]' || true)"
fi
if [ -z "$REVISION" ]; then
  REVISION="unknown"
fi

SHORT="${REVISION:0:7}"
BACKUP_DIR="$BACKUP_ROOT/pre-ui-wide-1080-polish-${TS}-${SHORT}"
ARCHIVE="$BACKUP_DIR/current-code.tar.gz"
MANIFEST="$BACKUP_DIR/MANIFEST.json"

echo "host=$(hostname)"
echo "time=$(date -Iseconds)"
echo "current=$CURRENT"
echo "backup_dir=$BACKUP_DIR"
echo "archive=$ARCHIVE"

if [ ! -e "$CURRENT" ]; then
  echo "current path missing: $CURRENT" >&2
  exit 1
fi

sudo -n mkdir -p "$BACKUP_DIR"
sudo -n tar \
  --exclude='./__pycache__' \
  --exclude='./.venv' \
  --exclude='./runtime' \
  --exclude='./reports' \
  --exclude='./training' \
  -C "$CURRENT" \
  -czf "$ARCHIVE" \
  .

SIZE_BYTES="$(sudo -n stat -c '%s' "$ARCHIVE")"
SHA256="$(sudo -n sha256sum "$ARCHIVE" | awk '{print $1}')"
SERVICE_STATE="$(sudo -n systemctl is-active smart-center.service 2>/dev/null || true)"

cat <<EOF_MANIFEST | sudo -n tee "$MANIFEST" >/dev/null
{
  "schema": "smart_center.production_code_backup.v1",
  "created_at": "$(date -Iseconds)",
  "created_by": "scripts/remote/backup_current_production_code_20260602_ui_polish.sh",
  "current": "$CURRENT",
  "current_realpath": "$(readlink -f "$CURRENT")",
  "revision": "$REVISION",
  "backup_dir": "$BACKUP_DIR",
  "archive": "$ARCHIVE",
  "size_bytes": $SIZE_BYTES,
  "sha256": "$SHA256",
  "service_state": "$SERVICE_STATE"
}
EOF_MANIFEST

echo "backup_manifest=$MANIFEST"
echo "backup_size_bytes=$SIZE_BYTES"
echo "backup_sha256=$SHA256"
echo "service_state=$SERVICE_STATE"
