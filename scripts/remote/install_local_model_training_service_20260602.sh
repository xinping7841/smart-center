#!/usr/bin/env bash
set -euo pipefail

# AI_MODULE: remote_install_local_model_training_service
# AI_PURPOSE: 将当前 release 中的本地模型训练 systemd service 同步到 /etc，并重载 systemd。
# AI_BOUNDARY: 只安装 smart-center-local-model-training.service/timer，不切换主服务 release，不调用设备控制接口。
# AI_RUNTIME: 通过 scripts/ssh_exec.sh 上传执行；/etc 写入使用 sudo -n。

SOURCE="/srv/smart-center/current/deploy/linux/smart-center-local-model-training.service"
TIMER_SOURCE="/srv/smart-center/current/deploy/linux/smart-center-local-model-training.timer"
TARGET="/etc/systemd/system/smart-center-local-model-training.service"
TIMER_TARGET="/etc/systemd/system/smart-center-local-model-training.timer"
TS="$(date +%Y%m%d_%H%M%S)"

echo "source=$SOURCE"
echo "target=$TARGET"
if [ ! -f "$SOURCE" ]; then
  echo "missing source service: $SOURCE" >&2
  exit 1
fi

if [ -f "$TARGET" ]; then
  sudo -n cp -a "$TARGET" "${TARGET}.bak-${TS}"
  echo "service_backup=${TARGET}.bak-${TS}"
fi
sudo -n install -m 0644 "$SOURCE" "$TARGET"

if [ -f "$TIMER_SOURCE" ]; then
  if [ -f "$TIMER_TARGET" ]; then
    sudo -n cp -a "$TIMER_TARGET" "${TIMER_TARGET}.bak-${TS}"
    echo "timer_backup=${TIMER_TARGET}.bak-${TS}"
  fi
  sudo -n install -m 0644 "$TIMER_SOURCE" "$TIMER_TARGET"
fi

sudo -n systemctl daemon-reload
sudo -n systemctl enable smart-center-local-model-training.timer >/dev/null 2>&1 || true
echo "installed_service="
sudo -n systemctl cat smart-center-local-model-training.service
