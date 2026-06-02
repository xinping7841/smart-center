#!/usr/bin/env bash
set -euo pipefail

# AI_MODULE: remote_local_model_summary_refresh_once
# AI_PURPOSE: 在 node-120 生产环境手动生成一次本地模型系统摘要。
# AI_BOUNDARY: 只读取知识包并调用本地模型 chat/completions 生成摘要，不调用任何设备控制接口。

APP_ROOT="/srv/smart-center"
CURRENT="$APP_ROOT/current"
PYTHON="$APP_ROOT/.venv/bin/python"
DATA_DIR="/srv/smart-center-data"

cd "$CURRENT"
echo "current=$(sudo -n readlink -f "$CURRENT")"
echo "revision=$(sudo -n cat "$CURRENT/REVISION")"
MAX_INPUT_CHARS="${SMART_CENTER_SUMMARY_MAX_INPUT_CHARS:-20000}"

echo "summary_start=$(date -Iseconds)"
echo "max_input_chars=$MAX_INPUT_CHARS"
sudo -n SMART_CENTER_DATA_DIR="$DATA_DIR" "$PYTHON" "$CURRENT/scripts/refresh_local_model_system_summary.py" --max-input-chars "$MAX_INPUT_CHARS"
echo "summary_done=$(date -Iseconds)"
echo "summary_files="
sudo -n find "$DATA_DIR/training/local_model" -maxdepth 1 -type f -name 'system_summary_*' -printf '%TY-%Tm-%TdT%TH:%TM:%TS %f\n' | sort | tail -n 8
