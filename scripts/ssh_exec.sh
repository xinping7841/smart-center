#!/usr/bin/env bash
set -euo pipefail

HOST_NAME=""
SCRIPT_PATH=""
REMOTE_WORKDIR=""
REMOTE_TEMP_ROOT="/tmp"

usage() {
  cat <<'EOF'
Usage:
  scripts/ssh_exec.sh --host <host> --script <local.sh|local.py> [--remote-workdir <path>]

Runs a local script on a Linux/macOS remote host by uploading it first.
Use this instead of complex inline `ssh "..."` commands.

Example:
  bash scripts/ssh_exec.sh \
    --host node-120-ts \
    --script scripts/remote/check_status.sh \
    --remote-workdir /srv/git/smart-center-clean.git
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
    --remote-temp-root)
      REMOTE_TEMP_ROOT="${2:-/tmp}"
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

ABS_SCRIPT="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)/$(basename "$SCRIPT_PATH")"
SCRIPT_NAME="$(basename "$ABS_SCRIPT")"
TMP_NAME="codex_exec_$(python3 - <<'PY'
import uuid
print(uuid.uuid4().hex)
PY
)"
REMOTE_TMP="${REMOTE_TEMP_ROOT%/}/${TMP_NAME}"
LOCAL_WRAPPER="$(mktemp "${TMPDIR:-/tmp}/codex-ssh-wrapper.XXXXXX")"

case "$SCRIPT_NAME" in
  *.py)
    REMOTE_SCRIPT="${REMOTE_TMP}/payload.py"
    REMOTE_RUNNER="python3"
    ;;
  *)
    REMOTE_SCRIPT="${REMOTE_TMP}/payload.sh"
    REMOTE_RUNNER="bash"
    ;;
esac
REMOTE_WRAPPER="${REMOTE_TMP}/run.sh"

write_wrapper() {
  {
    printf '%s\n' '#!/usr/bin/env bash'
    printf '%s\n' 'set -euo pipefail'
    printf 'REMOTE_SCRIPT=%q\n' "$REMOTE_SCRIPT"
    printf 'REMOTE_WORKDIR=%q\n' "$REMOTE_WORKDIR"
    printf 'REMOTE_RUNNER=%q\n' "$REMOTE_RUNNER"
    cat <<'EOF'

chmod +x "$REMOTE_SCRIPT"
if [[ -n "$REMOTE_WORKDIR" ]]; then
  cd "$REMOTE_WORKDIR"
fi

case "$REMOTE_RUNNER" in
  python3)
    exec python3 "$REMOTE_SCRIPT"
    ;;
  bash)
    exec bash "$REMOTE_SCRIPT"
    ;;
  *)
    echo "unsupported remote runner: $REMOTE_RUNNER" >&2
    exit 2
    ;;
esac
EOF
  } >"$LOCAL_WRAPPER"
}

echo "[ssh_exec] create temp: ${HOST_NAME}:${REMOTE_TMP}"
ssh "$HOST_NAME" mkdir -p "$REMOTE_TMP"

cleanup() {
  echo "[ssh_exec] cleanup: ${HOST_NAME}:${REMOTE_TMP}" >&2
  rm -f "$LOCAL_WRAPPER" >/dev/null 2>&1 || true
  ssh "$HOST_NAME" rm -rf "$REMOTE_TMP" >/dev/null 2>&1 || true
}
trap cleanup EXIT

write_wrapper

echo "[ssh_exec] upload: ${ABS_SCRIPT} -> ${HOST_NAME}:${REMOTE_SCRIPT}"
scp -q "$ABS_SCRIPT" "${HOST_NAME}:${REMOTE_SCRIPT}"
echo "[ssh_exec] upload wrapper -> ${HOST_NAME}:${REMOTE_WRAPPER}"
scp -q "$LOCAL_WRAPPER" "${HOST_NAME}:${REMOTE_WRAPPER}"

echo "[ssh_exec] run on $HOST_NAME"
ssh "$HOST_NAME" bash "$REMOTE_WRAPPER"
