#!/usr/bin/env bash
set -euo pipefail

# AI_MODULE: remote_verify_node123_music_route_context
# AI_PURPOSE: Verify node-123 local-model knowledge routes music status questions to dashboard summary.
# AI_BOUNDARY: Read-only probe through /api/local-model/chat; never calls playback, queue, volume, or device-control APIs.
# AI_RUNTIME: Run via scripts/ssh_exec.sh on node-120 after applying the compact knowledge context.
# AI_RISK: Low. The prompt explicitly asks for routing guidance only, not current playback control.

python3 - <<'PY'
import json
import sys
import urllib.request

payload = json.dumps(
    {
        "messages": [
            {
                "role": "user",
                "content": (
                    "用户问：主界面音乐播放器现在什么状态、当前歌曲、播放模式、音量和队列是什么？"
                    "请只说明应该优先调用哪个只读接口和字段，不要执行播放控制。"
                ),
            }
        ]
    },
    ensure_ascii=False,
).encode("utf-8")
req = urllib.request.Request(
    "http://127.0.0.1:6899/api/local-model/chat",
    data=payload,
    headers={"Content-Type": "application/json"},
    method="POST",
)
data = json.loads(urllib.request.urlopen(req, timeout=80).read().decode("utf-8"))
answer = str(data.get("answer") or data.get("reply") or "")
checks = {
    "mentions_dashboard_summary": "/api/dashboard/summary" in answer,
    "mentions_modules_apple_audio": "modules.apple_audio" in answer,
    "avoids_library_route": "/api/apple-audio/library" not in answer,
    "mentions_read_only": "只读" in answer,
}
print(json.dumps(
    {
        "ok": data.get("ok"),
        "elapsed_ms": data.get("elapsed_ms"),
        "checks": checks,
        "answer": answer[:1800],
    },
    ensure_ascii=False,
    indent=2,
))
if not data.get("ok") or not all(checks.values()):
    sys.exit(1)
PY
