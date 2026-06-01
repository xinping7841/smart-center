#!/usr/bin/env bash
set -euo pipefail

# AI_MODULE: remote_production_code_backup
# AI_PURPOSE: 在 node-120 上备份当前生产代码 current 目录，供飞书/模型知识库改造前保留现场。
# AI_BOUNDARY: 只读取 /srv/smart-center/current 并写入 /srv/smart-center/backups，不切换 release、不重启服务、不触发设备控制。
# AI_RUNTIME: 通过 scripts/ssh_exec.sh 上传执行；生产 root 路径统一使用 sudo -n。
# AI_RISK: 中，备份生产代码但不修改运行服务。

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
BACKUP_DIR="$BACKUP_ROOT/pre-feishu-nl-knowledge-${TS}-${SHORT}"
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
  "created_by": "scripts/remote/backup_current_production_code_20260601.sh",
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
