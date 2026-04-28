import os
from io import BytesIO

from flask import Flask, Response, jsonify, request

from .config_store import load_config
from .reporting import (
    build_raw_csv_text,
    build_raw_xlsx_bytes,
    build_report_index,
    build_statistics_csv_text,
    build_statistics_xlsx_bytes,
    build_summary_csv_text,
    build_summary_xlsx_bytes,
    resolve_report_dir,
)
from .service import build_meter_payload, export_reports_now, get_runtime_health_snapshot, poll_once, start_background_threads, sync_config
from .storage import init_db

app = Flask(__name__)


def _read_build_stamp():
    try:
        stamp_path = "/app/.build_stamp"
        if os.path.exists(stamp_path):
            with open(stamp_path, "r", encoding="utf-8") as f:
                return f.read().strip()
    except Exception:
        pass
    return ""


@app.route("/api/health")
def api_health():
    cfg = load_config()
    meter_statistics = cfg.get("meter_statistics", {}) or {}
    runtime = get_runtime_health_snapshot(window_seconds=600)
    return jsonify({
        "ok": 1,
        "service": "meter_service",
        "meter_count": len(cfg.get("meters", [])),
        "cabinet_meter_count": len(cfg.get("cabinets", [])),
        "auto_export_enabled": bool(meter_statistics.get("auto_export_enabled", True)),
        "report_dir": resolve_report_dir(meter_statistics),
        "build_stamp": _read_build_stamp(),
        "runtime": runtime,
    })


@app.route("/api/meters")
def api_meters():
    target = request.args.get("target", "total")
    period = request.args.get("period", "day")
    days = request.args.get("days", 7, type=int)
    payload = build_meter_payload(target_source_key=target, period=period, days=days)
    payload["data_source"] = "meter_service"
    return jsonify(payload)


@app.route("/api/config")
def api_config():
    return jsonify(load_config())


@app.route("/api/config/sync", methods=["POST"])
def api_config_sync():
    payload = request.get_json(silent=True) or {}
    saved = sync_config(payload)
    poll_once()
    export_result = export_reports_now()
    return jsonify({
        "ok": 1,
        "meter_count": len(saved.get("meters", [])),
        "cabinet_meter_count": len(saved.get("cabinets", [])),
        "export_result": export_result,
    })


def _csv_response(csv_text, filename):
    return Response(
        csv_text.encode("utf-8-sig"),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _xlsx_response(xlsx_bytes, filename):
    return Response(
        xlsx_bytes,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.route("/api/export/meter_statistics")
def api_export_meter_statistics():
    target = request.args.get("target", "total")
    period = request.args.get("period", "day")
    days = request.args.get("days", 35, type=int)
    fmt = str(request.args.get("format", "csv") or "csv").strip().lower()
    payload = build_meter_payload(target_source_key=target, period=period, days=days)
    payload["data_source"] = "meter_service"
    if fmt == "xlsx":
        return _xlsx_response(build_statistics_xlsx_bytes(payload, period), f"meter_statistics_{period}.xlsx")
    return _csv_response(build_statistics_csv_text(payload, period), f"meter_statistics_{period}.csv")


@app.route("/api/export/meter_raw")
def api_export_meter_raw():
    target = request.args.get("target", "total")
    days = request.args.get("days", 35, type=int)
    fmt = str(request.args.get("format", "csv") or "csv").strip().lower()
    payload = build_meter_payload(target_source_key=target, period="day", days=days)
    payload["data_source"] = "meter_service"
    if fmt == "xlsx":
        return _xlsx_response(build_raw_xlsx_bytes(payload.get("meters", [])), "meter_raw.xlsx")
    return _csv_response(build_raw_csv_text(payload.get("meters", [])), "meter_raw.csv")


@app.route("/api/export/meter_summary")
def api_export_meter_summary():
    target = request.args.get("target", "total")
    days = request.args.get("days", 35, type=int)
    fmt = str(request.args.get("format", "csv") or "csv").strip().lower()
    payload = build_meter_payload(target_source_key=target, period="day", days=days)
    payload["data_source"] = "meter_service"
    if fmt == "xlsx":
        return _xlsx_response(build_summary_xlsx_bytes(payload), "meter_summary.xlsx")
    return _csv_response(build_summary_csv_text(payload), "meter_summary.csv")


@app.route("/api/reports")
def api_reports():
    cfg = load_config()
    meter_statistics = cfg.get("meter_statistics", {}) or {}
    payload = build_report_index(meter_statistics)
    payload["ok"] = 1
    return jsonify(payload)


def create_app():
    init_db()
    start_background_threads()
    return app


if __name__ == "__main__":
    init_db()
    start_background_threads()
    app.run(host="0.0.0.0", port=6901, debug=False)
