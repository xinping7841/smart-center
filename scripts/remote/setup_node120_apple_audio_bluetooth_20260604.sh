#!/usr/bin/env bash
set -euo pipefail

# AI_MODULE: remote_node120_apple_audio_bluetooth_setup
# AI_PURPOSE: Diagnose and optionally prepare node-120 for Smart Center local Bluetooth music playback.
# AI_BOUNDARY: Default mode is read-only. Mount/config changes require explicit environment variables.
# AI_DATA_FLOW: NAS SMB/NFS or existing local mount -> Smart Center apple_audio config -> node-120 ffplay -> Bluetooth audio sink.
# AI_RUNTIME: Run via scripts/ssh_exec.sh on node-120.
# AI_RISK: Medium. Mounting NAS paths and restarting smart-center can affect music library availability.
# AI_SEARCH_KEYWORDS: node120, apple audio, bluetooth speaker, ffplay, cifs, /mnt/fnnas-audio.

NAS_HOST="${NAS_HOST:-192.168.50.254}"
NAS_SHARE="${NAS_SHARE:-}"
NAS_AUDIO_PATH="${NAS_AUDIO_PATH:-/vol2/1000/Audio}"
LOCAL_AUDIO_ROOT="${LOCAL_AUDIO_ROOT:-/mnt/fnnas-audio}"
ENV_FILE="${ENV_FILE:-/etc/smart-center.env}"
MOUNT_CIFS="${MOUNT_CIFS:-0}"
CIFS_USERNAME="${CIFS_USERNAME:-}"
CIFS_PASSWORD="${CIFS_PASSWORD:-}"
CIFS_DOMAIN="${CIFS_DOMAIN:-WORKGROUP}"

echo "== node120 apple audio bluetooth setup check =="
hostname || true
date -Is || true

echo "nas_host=$NAS_HOST"
echo "nas_audio_path=$NAS_AUDIO_PATH"
echo "local_audio_root=$LOCAL_AUDIO_ROOT"
echo "mount_cifs=$MOUNT_CIFS"

echo "== required tools =="
for cmd in bluetoothctl ffplay pactl wpctl mount.cifs; do
  if command -v "$cmd" >/dev/null 2>&1; then
    echo "$cmd=$(command -v "$cmd")"
  else
    echo "$cmd=missing"
  fi
done

echo "== bluetooth =="
bluetoothctl list || true
bluetoothctl devices Connected || true

echo "== local audio root =="
if [ -e "$LOCAL_AUDIO_ROOT" ]; then
  ls -ld "$LOCAL_AUDIO_ROOT" || true
  find "$LOCAL_AUDIO_ROOT" -maxdepth 2 -type f \( -iname '*.mp3' -o -iname '*.flac' -o -iname '*.m4a' -o -iname '*.wav' -o -iname '*.aac' -o -iname '*.ogg' \) 2>/dev/null | head -20 || true
else
  echo "missing=$LOCAL_AUDIO_ROOT"
fi

if [ "$MOUNT_CIFS" = "1" ]; then
  if [ -z "$NAS_SHARE" ] || [ -z "$CIFS_USERNAME" ] || [ -z "$CIFS_PASSWORD" ]; then
    echo "MOUNT_CIFS=1 requires NAS_SHARE, CIFS_USERNAME, CIFS_PASSWORD" >&2
    exit 2
  fi
  CREDS="/etc/smart-center-fnnas-audio.credentials"
  sudo -n install -d -m 0755 "$LOCAL_AUDIO_ROOT"
  {
    printf 'username=%s\n' "$CIFS_USERNAME"
    printf 'password=%s\n' "$CIFS_PASSWORD"
    printf 'domain=%s\n' "$CIFS_DOMAIN"
  } | sudo -n tee "$CREDS" >/dev/null
  sudo -n chmod 0600 "$CREDS"
  if ! mountpoint -q "$LOCAL_AUDIO_ROOT"; then
    sudo -n mount -t cifs "//$NAS_HOST/$NAS_SHARE" "$LOCAL_AUDIO_ROOT" \
      -o "credentials=$CREDS,iocharset=utf8,vers=3.0,ro,noserverino"
  fi
fi

echo "== audio sinks =="
pactl list short sinks 2>/dev/null || true
wpctl status 2>/dev/null | sed -n '1,120p' || true

echo "done"
echo "next_config_hint=POST /api/apple-audio/config with nas_music_roots=[\"$LOCAL_AUDIO_ROOT\"], player_mode=node120_bluetooth, local_player_enabled=true"
