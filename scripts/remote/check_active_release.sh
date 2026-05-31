#!/usr/bin/env bash
set -euo pipefail

echo "service_active=$(sudo -n systemctl is-active smart-center.service)"
echo "current=$(sudo -n readlink -f /srv/smart-center/current)"
if [ -f /srv/smart-center/current/.codex_deploy_ts.txt ]; then
  echo "deploy_ts=$(sudo -n cat /srv/smart-center/current/.codex_deploy_ts.txt)"
fi
if [ -d /srv/smart-center/current/.git ]; then
  echo "revision=$(sudo -n git -C /srv/smart-center/current rev-parse HEAD)"
fi
