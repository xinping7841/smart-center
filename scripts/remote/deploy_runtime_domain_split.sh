#!/usr/bin/env bash
set -euo pipefail

# AI_MODULE: remote_deploy_main_release
# AI_PURPOSE: 在 node-120 上从 clean Git main 生成生产 release，并保留切换前备份。
# AI_BOUNDARY: 只操作 /srv/smart-center release/current/backups，不修改运行数据 /srv/smart-center-data。
# AI_RUNTIME: 通过 scripts/ssh_exec.sh 上传执行；远端 root 路径统一使用 sudo -n。
# AI_RISK: 高，生产切换脚本；修改前必须确认备份、编译检查和 systemd 状态检查仍在。

APP_ROOT="/srv/smart-center"
BARE_REPO="/srv/git/smart-center-clean.git"
BRANCH="main"
TS="$(date +%Y%m%d_%H%M%S)"
REV="$(git --git-dir="$BARE_REPO" rev-parse "$BRANCH")"
SHORT="${REV:0:7}"
RELEASE="$APP_ROOT/releases/smart-center-release-${TS}-${BRANCH}-${SHORT}"
BACKUP="$APP_ROOT/backups/pre-main-release-${TS}-${BRANCH}-${SHORT}"
CURRENT="$APP_ROOT/current"

echo "rev=$REV"
echo "backup=$BACKUP"
echo "release=$RELEASE"

sudo -n mkdir -p "$APP_ROOT/releases" "$APP_ROOT/backups"
if [ -e "$CURRENT" ]; then
  sudo -n cp -a "$(readlink -f "$CURRENT")" "$BACKUP"
fi
sudo -n mkdir -p "$RELEASE"
sudo -n git --git-dir="$BARE_REPO" archive "$REV" | sudo -n tar -x -C "$RELEASE"
printf '%s\n' "$REV" | sudo -n tee "$RELEASE/REVISION" >/dev/null
if [ -f "$RELEASE/requirements.txt" ]; then
  sudo -n python3 -m compileall "$RELEASE/app.py" "$RELEASE/api" "$RELEASE/services" "$RELEASE/runtime" "$RELEASE/config.py" "$RELEASE/background.py" "$RELEASE/power.py" "$RELEASE/snmp_core.py" >/tmp/smart-center-release-compile.log 2>&1 || {
    cat /tmp/smart-center-release-compile.log
    exit 1
  }
fi
sudo -n ln -sfn "$RELEASE" "$CURRENT"
sudo -n systemctl restart smart-center.service
sleep 2
sudo -n systemctl is-active smart-center.service
printf 'current_revision='
cat "$CURRENT/REVISION"
printf 'service_status=' 
sudo -n systemctl --no-pager --plain status smart-center.service | sed -n '1,6p'
