#!/usr/bin/env python3
import json
import os
import sys
import urllib.request


def _env(name: str, default: str = "") -> str:
    return str(os.environ.get(name, default) or default).strip()


def _status_text(status: str) -> str:
    normalized = status.lower()
    if normalized in {"success", "ok", "done"}:
        return "\u6210\u529f"
    if normalized in {"failed", "fail", "error"}:
        return "\u5931\u8d25"
    return status or "\u672a\u77e5"


def _message_text(message: str) -> str:
    mapping = {
        "backup_completed": "\u5907\u4efd\u5df2\u5b8c\u6210\uff0clatest \u6307\u9488\u5df2\u66f4\u65b0",
        "backup_failed": "\u5907\u4efd\u811a\u672c\u6267\u884c\u5931\u8d25",
    }
    return mapping.get(message, message)


def main() -> int:
    webhook = _env("SMART_CENTER_BACKUP_WEBHOOK")
    if not webhook:
        return 0

    title = _env("SMART_CENTER_BACKUP_NOTIFY_TITLE", "Smart Center \u5907\u4efd\u901a\u77e5")
    status = _status_text(_env("BACKUP_STATUS", "unknown"))
    host = _env("BACKUP_HOST")
    target = _env("BACKUP_TARGET")
    target_name = _env("BACKUP_TARGET_NAME")
    duration = _env("BACKUP_DURATION_TEXT") or _env("BACKUP_DURATION_SEC")
    app_size = _env("BACKUP_APP_SIZE")
    data_size = _env("BACKUP_DATA_SIZE")
    message = _message_text(_env("BACKUP_MESSAGE"))
    error_summary = _env("BACKUP_ERROR_SUMMARY")
    keep_count = _env("BACKUP_KEEP_COUNT")
    restore_hint = _env("BACKUP_RESTORE_HINT")

    lines = [f"{title} [{status}]"]
    if host:
        lines.append(f"\u4e3b\u673a\uff1a{host}")
    if target_name:
        lines.append(f"\u5907\u4efd\u76ee\u5f55\uff1a{target_name}")
    if target:
        lines.append(f"\u76ee\u6807\u8def\u5f84\uff1a{target}")
    if duration:
        lines.append(f"\u8017\u65f6\uff1a{duration}")
    if app_size:
        lines.append(f"\u4ee3\u7801\u5927\u5c0f\uff1a{app_size}")
    if data_size:
        lines.append(f"\u6570\u636e\u5927\u5c0f\uff1a{data_size}")
    if keep_count:
        lines.append(f"\u4fdd\u7559\u4efd\u6570\uff1a\u6700\u8fd1 {keep_count} \u4efd")
    if message:
        lines.append(f"\u8be6\u60c5\uff1a{message}")
    if error_summary:
        lines.append(f"\u9519\u8bef\u6458\u8981\uff1a{error_summary}")
    if restore_hint and status == "\u6210\u529f":
        lines.append(f"\u6062\u590d\u53c2\u8003\uff1a{restore_hint}")

    payload = {
        "msgtype": "text",
        "text": {
            "content": "\n".join(lines),
        },
    }
    request = urllib.request.Request(
        webhook,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        response.read()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"notify failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
