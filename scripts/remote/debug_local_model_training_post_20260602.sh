#!/usr/bin/env bash
set -euo pipefail

# AI_MODULE: remote_local_model_training_post_debug
# AI_PURPOSE: 调试本地模型训练 service 和手动摘要刷新链路。
# AI_BOUNDARY: 只读 systemd 日志/文件并可手动运行摘要脚本；不调用设备控制接口。

echo "now=$(date -Iseconds)"
echo "service_cat="
sudo -n systemctl cat smart-center-local-model-training.service
echo "service_show="
sudo -n systemctl show smart-center-local-model-training.service \
  -p ActiveState -p SubState -p Result -p ExecMainCode -p ExecMainStatus \
  -p ExecStart -p ExecStartPost -p ActiveEnterTimestamp -p ActiveExitTimestamp
echo "journal_tail="
sudo -n journalctl -u smart-center-local-model-training.service --no-pager -n 120
echo "summary_files="
sudo -n find /srv/smart-center-data/training/local_model -maxdepth 1 -type f -name 'system_summary_*' -printf '%TY-%Tm-%TdT%TH:%TM:%TS %f\n' | sort | tail -n 12
MAX_INPUT_CHARS="${SMART_CENTER_SUMMARY_MAX_INPUT_CHARS:-8000}"
echo "manual_summary_start=$(date -Iseconds)"
echo "max_input_chars=$MAX_INPUT_CHARS"
cd /srv/smart-center/current
sudo -n SMART_CENTER_DATA_DIR=/srv/smart-center-data /srv/smart-center/.venv/bin/python /srv/smart-center/current/scripts/refresh_local_model_system_summary.py --max-input-chars "$MAX_INPUT_CHARS"
echo "manual_summary_done=$(date -Iseconds)"
echo "summary_files_after="
sudo -n find /srv/smart-center-data/training/local_model -maxdepth 1 -type f -name 'system_summary_*' -printf '%TY-%Tm-%TdT%TH:%TM:%TS %f\n' | sort | tail -n 12
