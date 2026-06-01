#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="/srv/smart-center"
REPO_URL="/srv/git/smart-center-clean.git"
REVISION="$(sudo -n git --git-dir "$REPO_URL" rev-parse refs/heads/main)"
STAMP="$(date +%Y%m%d_%H%M%S)"
SHORT_REV="$(printf '%s' "$REVISION" | cut -c1-7)"
RELEASE_DIR="$APP_ROOT/releases/smart-center-release-${STAMP}-main-${SHORT_REV}"
BACKUP_DIR="$APP_ROOT/backups/pre-main-release-${STAMP}-main-${SHORT_REV}"
CURRENT_LINK="$APP_ROOT/current"

echo "deploy_revision=$REVISION"
echo "release_dir=$RELEASE_DIR"
echo "backup_dir=$BACKUP_DIR"

sudo -n mkdir -p "$APP_ROOT/releases" "$APP_ROOT/backups"

if [ -e "$CURRENT_LINK" ]; then
  CURRENT_TARGET="$(sudo -n readlink -f "$CURRENT_LINK" || true)"
  if [ -n "${CURRENT_TARGET:-}" ] && [ -d "$CURRENT_TARGET" ]; then
    sudo -n cp -a "$CURRENT_TARGET" "$BACKUP_DIR"
  else
    sudo -n cp -a "$CURRENT_LINK" "$BACKUP_DIR"
  fi
else
  sudo -n mkdir -p "$BACKUP_DIR"
fi

TMP_RELEASE="${RELEASE_DIR}.tmp"
sudo -n rm -rf "$TMP_RELEASE"
sudo -n git clone --quiet "$REPO_URL" "$TMP_RELEASE"
sudo -n git -C "$TMP_RELEASE" checkout --quiet "$REVISION"
printf '%s\n' "$REVISION" | sudo -n tee "$TMP_RELEASE/REVISION" >/dev/null
sudo -n mv "$TMP_RELEASE" "$RELEASE_DIR"

sudo -n APP_ROOT="$APP_ROOT" bash "$RELEASE_DIR/deploy/linux/remote_release.sh" "$RELEASE_DIR"
sudo -n systemctl restart smart-center.service
sleep 2

echo "service_active=$(sudo -n systemctl is-active smart-center.service)"
echo "current=$(sudo -n readlink -f "$CURRENT_LINK")"
if [ -f "$CURRENT_LINK/REVISION" ]; then
  echo "revision=$(sudo -n cat "$CURRENT_LINK/REVISION")"
fi
if [ -f "$CURRENT_LINK/RELEASE_INFO.json" ]; then
  echo "release_info=$(sudo -n tr -d '\n' < "$CURRENT_LINK/RELEASE_INFO.json")"
fi
