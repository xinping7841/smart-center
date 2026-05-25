#!/usr/bin/env bash
set -euo pipefail

HOST_NAME=""
SCRIPT_PATH=""
REMOTE_WORKDIR=""
REMOTE_TEMP_ROOT_WIN="C:\\Users\\Public\\Temp"
REMOTE_TEMP_ROOT_SCP="/C:/Users/Public/Temp"

usage() {
  cat <<'EOF'
Usage:
  scripts/ssh_exec_windows.sh --host <host> --script <local.ps1> [--remote-workdir <win-path>]

Example:
  bash scripts/ssh_exec_windows.sh \
    --host lk402 \
    --script scripts/remote/check_windows_smart_center.ps1
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host)
      HOST_NAME="${2:-}"
      shift 2
      ;;
    --script)
      SCRIPT_PATH="${2:-}"
      shift 2
      ;;
    --remote-workdir)
      REMOTE_WORKDIR="${2:-}"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -z "$HOST_NAME" || -z "$SCRIPT_PATH" ]]; then
  usage >&2
  exit 2
fi

if [[ ! -f "$SCRIPT_PATH" ]]; then
  echo "script not found: $SCRIPT_PATH" >&2
  exit 1
fi

ps_quote() {
  local value="${1:-}"
  value="${value//\'/\'\'}"
  printf "'%s'" "$value"
}

ABS_SCRIPT="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)/$(basename "$SCRIPT_PATH")"
SCRIPT_NAME="$(basename "$ABS_SCRIPT")"
TMP_NAME="codex_exec_$(python3 - <<'PY'
import uuid
print(uuid.uuid4().hex)
PY
)"
REMOTE_TMP_WIN="${REMOTE_TEMP_ROOT_WIN}\\${TMP_NAME}"
REMOTE_TMP_SCP="${REMOTE_TEMP_ROOT_SCP}/${TMP_NAME}"
REMOTE_SCRIPT_WIN="${REMOTE_TMP_WIN}\\${SCRIPT_NAME}"
REMOTE_SCRIPT_SCP="${REMOTE_TMP_SCP}/${SCRIPT_NAME}"

echo "[ssh_exec_windows] create temp: ${HOST_NAME}:${REMOTE_TMP_WIN}"
ssh "$HOST_NAME" "powershell -NoProfile -Command \"New-Item -ItemType Directory -Force -Path $(ps_quote "$REMOTE_TMP_WIN") | Out-Null\""

cleanup() {
  echo "[ssh_exec_windows] cleanup: ${HOST_NAME}:${REMOTE_TMP_WIN}" >&2
  ssh "$HOST_NAME" "powershell -NoProfile -Command \"Remove-Item -LiteralPath $(ps_quote "$REMOTE_TMP_WIN") -Recurse -Force -ErrorAction SilentlyContinue\"" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "[ssh_exec_windows] upload: ${ABS_SCRIPT} -> ${HOST_NAME}:${REMOTE_SCRIPT_WIN}"
scp -q "$ABS_SCRIPT" "${HOST_NAME}:${REMOTE_SCRIPT_SCP}"

echo "[ssh_exec_windows] run on $HOST_NAME"
if [[ -n "$REMOTE_WORKDIR" ]]; then
  REMOTE_COMMAND="Set-Location -Path $(ps_quote "$REMOTE_WORKDIR"); & $(ps_quote "$REMOTE_SCRIPT_WIN")"
  ssh "$HOST_NAME" "powershell -NoProfile -ExecutionPolicy Bypass -Command \"$REMOTE_COMMAND\""
else
  ssh "$HOST_NAME" "powershell -NoProfile -ExecutionPolicy Bypass -File $REMOTE_SCRIPT_WIN"
fi
