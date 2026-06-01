#!/usr/bin/env bash
set -euo pipefail

CURRENT="$(sudo -n readlink -f /srv/smart-center/current)"
echo "service_active=$(sudo -n systemctl is-active smart-center.service)"
echo "current=$CURRENT"
echo "release_name=$(basename "$CURRENT")"
if [ -f "$CURRENT/REVISION" ]; then
  echo "revision=$(sudo -n cat "$CURRENT/REVISION")"
fi
if [ -f "$CURRENT/.codex_deploy_ts.txt" ]; then
  DEPLOY_TS="$(sudo -n cat "$CURRENT/.codex_deploy_ts.txt" | tr -d '\r\n')"
  echo "deploy_ts=$DEPLOY_TS"
  if [ -n "$DEPLOY_TS" ] && ! basename "$CURRENT" | grep -q "$DEPLOY_TS"; then
    echo "deploy_ts_status=stale"
  else
    echo "deploy_ts_status=ok"
  fi
else
  echo "deploy_ts_status=missing"
fi
if [ -f "$CURRENT/RELEASE_INFO.json" ]; then
  echo "release_info=$(sudo -n cat "$CURRENT/RELEASE_INFO.json" | tr -d '\n')"
else
  echo "release_info=missing"
fi
if [ -d "$CURRENT/.git" ]; then
  echo "git_revision=$(sudo -n git -C "$CURRENT" rev-parse HEAD)"
fi
