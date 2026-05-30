#!/usr/bin/env python3
# AI_MODULE: perf_baseline_tool
# AI_PURPOSE: 生成中控前端资源大小和可选 HTTP 接口耗时基线，方便优化前后对比。
# AI_BOUNDARY: 只读扫描与探测，不修改生产数据，不触发真实设备控制。
# AI_DATA_FLOW: repo files + optional HTTP GET -> JSON report in .baseline_reports/.
# AI_RUNTIME: 手动执行；可在 Mac/120/12700K/LK402 任一开发机运行。
# AI_RISK: 低，只访问 GET 接口；默认不访问网络，传 --base-url 才测接口。
# AI_SEARCH_KEYWORDS: performance, baseline, frontend size, page load, lazy-load.

from __future__ import annotations

import argparse
import gzip
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_SIZE_PATHS = [
    "templates/index.html",
    "api/server.py",
    "background.py",
    "config.py",
    "snmp_core.py",
    "static/vendor/echarts.min.js",
    "static/smart-center-time-ntp.css",
    "static/smart-center.css",
    "static/smart-center-scene-card3.css",
    "static/js/core/bootstrap.js",
    "static/js/core/utils.js",
    "static/js/views/snmp-summary.js",
    "static/js/views/snmp.js",
    "static/js/views/server-monitor.js",
    "static/js/views/hvac-view.js",
    "static/js/views/automation-view.js",
    "static/js/views/proxy.js",
    "static/js/views/universal.js",
    "static/js/views/apple-audio.js",
    "static/js/views/local-model.js",
    "static/css/views/local-model.css",
]

DEFAULT_ENDPOINTS = [
    "/",
    "/api/dashboard/summary",
    "/api/snmp/status?compact=1",
    "/api/machines",
    "/api/meters",
    "/api/hvac/status",
]


def now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def iso_now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def file_info(root: Path, rel_path: str) -> dict:
    path = root / rel_path
    if not path.exists():
        return {"path": rel_path, "exists": False}
    data = path.read_bytes()
    return {
        "path": rel_path,
        "exists": True,
        "bytes": len(data),
        "gzip_bytes": len(gzip.compress(data, compresslevel=5)) if data else 0,
        "lines": data.count(b"\n") + (1 if data and not data.endswith(b"\n") else 0),
    }


def request_endpoint(base_url: str, endpoint: str, timeout: float) -> dict:
    url = base_url.rstrip("/") + endpoint
    started = time.perf_counter()
    req = Request(url, headers={"Accept-Encoding": "gzip", "Cache-Control": "no-cache"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            elapsed_ms = (time.perf_counter() - started) * 1000
            encoding = resp.headers.get("Content-Encoding", "")
            if encoding.lower() == "gzip":
                decoded = gzip.decompress(body)
            else:
                decoded = body
            return {
                "endpoint": endpoint,
                "url": url,
                "ok": 200 <= int(resp.status) < 400,
                "status": int(resp.status),
                "elapsed_ms": round(elapsed_ms, 1),
                "bytes": len(decoded),
                "wire_bytes": len(body),
                "content_encoding": encoding or "",
                "content_type": resp.headers.get("Content-Type", ""),
            }
    except HTTPError as err:
        elapsed_ms = (time.perf_counter() - started) * 1000
        return {
            "endpoint": endpoint,
            "url": url,
            "ok": False,
            "status": int(err.code),
            "elapsed_ms": round(elapsed_ms, 1),
            "error": str(err),
        }
    except (TimeoutError, URLError, OSError) as err:
        elapsed_ms = (time.perf_counter() - started) * 1000
        return {
            "endpoint": endpoint,
            "url": url,
            "ok": False,
            "status": 0,
            "elapsed_ms": round(elapsed_ms, 1),
            "error": str(err),
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smart Center performance baseline")
    parser.add_argument("--root", default=".", help="repo root, default current directory")
    parser.add_argument("--base-url", default="", help="optional running Smart Center base URL, e.g. http://127.0.0.1:6899")
    parser.add_argument("--timeout", type=float, default=6.0, help="HTTP timeout seconds")
    parser.add_argument("--output-dir", default=".baseline_reports", help="where JSON reports are written")
    parser.add_argument("--endpoint", action="append", default=[], help="extra endpoint to probe; can repeat")
    parser.add_argument("--path", action="append", default=[], help="extra repo-relative file path to measure; can repeat")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    output_dir = (root / args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = list(dict.fromkeys(DEFAULT_SIZE_PATHS + args.path))
    endpoints = list(dict.fromkeys(DEFAULT_ENDPOINTS + args.endpoint))
    report = {
        "generated_at": iso_now(),
        "cwd": os.getcwd(),
        "root": str(root),
        "files": [file_info(root, item) for item in paths],
        "http": [],
    }
    if args.base_url:
        report["base_url"] = args.base_url.rstrip("/")
        report["http"] = [request_endpoint(args.base_url, item, args.timeout) for item in endpoints]
    out_path = output_dir / f"perf-baseline-{now_stamp()}.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(out_path))
    file_total = sum(item.get("bytes", 0) for item in report["files"] if item.get("exists"))
    gzip_total = sum(item.get("gzip_bytes", 0) for item in report["files"] if item.get("exists"))
    print(f"files: {len(report['files'])} tracked, total={file_total} bytes, gzip={gzip_total} bytes")
    if report["http"]:
        slow = sorted(report["http"], key=lambda item: item.get("elapsed_ms", 0), reverse=True)[:3]
        print("slow endpoints: " + ", ".join(f"{item['endpoint']} {item['elapsed_ms']}ms" for item in slow))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
