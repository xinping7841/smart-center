#!/usr/bin/env bash
set -euo pipefail

# AI_MODULE: remote_release_metadata
# AI_PURPOSE: Repair metadata files for the currently active production release.
# AI_BOUNDARY: Writes only metadata files inside /srv/smart-center/current's target release.
# AI_RUNTIME: Run through scripts/ssh_exec.sh; root-owned production paths use sudo -n.

APP_ROOT="/srv/smart-center"
BARE_REPO="/srv/git/smart-center-clean.git"
BRANCH="${BRANCH:-main}"
CURRENT="$APP_ROOT/current"

RELEASE="$(sudo -n readlink -f "$CURRENT")"
RELEASE_NAME="$(basename "$RELEASE")"

if [[ "$RELEASE_NAME" =~ smart-center-release-([0-9]{8}_[0-9]{6})-([A-Za-z0-9._/-]+)-([0-9a-fA-F]{7,40})$ ]]; then
  RELEASE_TS="${BASH_REMATCH[1]}"
  RELEASE_BRANCH="${BASH_REMATCH[2]}"
  SHORT="${BASH_REMATCH[3]}"
else
  RELEASE_TS="$(date +%Y%m%d_%H%M%S)"
  RELEASE_BRANCH="$BRANCH"
  SHORT=""
fi

if [ -f "$RELEASE/REVISION" ]; then
  REV="$(sudo -n cat "$RELEASE/REVISION" | tr -d '\r\n')"
elif [ -n "$SHORT" ]; then
  REV="$(git --git-dir="$BARE_REPO" rev-parse "$SHORT")"
else
  REV="$(git --git-dir="$BARE_REPO" rev-parse "$BRANCH")"
fi

if [ -z "$SHORT" ]; then
  SHORT="${REV:0:7}"
fi

CREATED_AT="$(date -Iseconds)"

printf '%s\n' "$REV" | sudo -n tee "$RELEASE/REVISION" >/dev/null
printf '%s\n' "$RELEASE_TS" | sudo -n tee "$RELEASE/.codex_deploy_ts.txt" >/dev/null
cat <<EOF_RELEASE_INFO | sudo -n tee "$RELEASE/RELEASE_INFO.json" >/dev/null
{
  "release": "$RELEASE_NAME",
  "release_dir": "$RELEASE",
  "branch": "$RELEASE_BRANCH",
  "revision": "$REV",
  "short_revision": "$SHORT",
  "metadata_updated_at": "$CREATED_AT",
  "metadata_source": "scripts/remote/stamp_active_release_metadata.sh"
}
EOF_RELEASE_INFO

echo "current=$RELEASE"
echo "release_name=$RELEASE_NAME"
echo "revision=$REV"
echo "deploy_ts=$RELEASE_TS"
