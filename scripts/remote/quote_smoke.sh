#!/usr/bin/env bash
set -euo pipefail

echo "QUOTE_SMOKE_START"

json='{"k":"v with spaces","quote":"'\''","pipe":"a|b|c","brace":"{1,2,3}","unicode":"\u4e2d\u6587"}'
printf 'json=%s\n' "$json"
printf '%s\n' alpha beta | awk '{printf "awk:%s\n", $0}'
printf 'single=%s double=%s\n' "a'b" 'c"d'
printf 'cwd=%s\n' "$(pwd)"
git rev-parse --is-bare-repository 2>/dev/null || true

echo "QUOTE_SMOKE_DONE"
