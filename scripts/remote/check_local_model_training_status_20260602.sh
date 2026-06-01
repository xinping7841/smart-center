#!/usr/bin/env bash
set -euo pipefail

# AI_MODULE: remote_local_model_training_status
# AI_PURPOSE: 查看 node-120 本地模型知识导出 systemd 服务状态和最近日志。
# AI_BOUNDARY: 只读 systemd 状态与导出日志，不调用设备控制接口。

echo "training_service_active=$(sudo -n systemctl is-active smart-center-local-model-training.service 2>/dev/null || true)"
echo "training_service_result=$(sudo -n systemctl show smart-center-local-model-training.service -p Result --value)"
echo "training_service_exec_status=$(sudo -n systemctl show smart-center-local-model-training.service -p ExecMainStatus --value)"
echo "training_service_exec_code=$(sudo -n systemctl show smart-center-local-model-training.service -p ExecMainCode --value)"
echo "training_service_finished_at=$(sudo -n systemctl show smart-center-local-model-training.service -p ActiveExitTimestamp --value)"
echo "latest_training_files="
sudo -n find /srv/smart-center-data/training/local_model -maxdepth 1 -type f -printf '%TY-%Tm-%TdT%TH:%TM:%TS %f\n' | sort | tail -n 24
echo "training_log_tail="
sudo -n tail -n 60 /srv/smart-center-data/runtime/local_model_training_export.log 2>/dev/null || true
