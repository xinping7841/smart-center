import csv
import io
import json
import os
from datetime import datetime, timedelta
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Font

from .config_store import DATA_DIR


def resolve_report_dir(meter_statistics):
    configured = str((meter_statistics or {}).get("report_dir") or "").strip()
    if not configured:
        configured = os.path.join(DATA_DIR, "reports", "energy")
    configured = os.path.expandvars(os.path.expanduser(configured))
    if not os.path.isabs(configured):
        configured = os.path.join(DATA_DIR, configured)
    return os.path.normpath(configured)


def _to_cell(value):
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _render_csv(headers, rows):
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(headers)
    for row in rows:
        writer.writerow([_to_cell(item) for item in row])
    return buffer.getvalue()


def _render_xlsx(sheet_name, headers, rows):
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = str(sheet_name or "Sheet1")[:31]
    worksheet.append(list(headers or []))
    for cell in worksheet[1]:
        cell.font = Font(bold=True)
    for row in rows or []:
        worksheet.append([_to_cell(item) for item in row])
    for column_cells in worksheet.columns:
        max_len = 0
        column_letter = column_cells[0].column_letter
        for cell in column_cells:
            value = "" if cell.value is None else str(cell.value)
            max_len = max(max_len, len(value))
        worksheet.column_dimensions[column_letter].width = min(max(max_len + 2, 12), 40)
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _build_summary_rows(payload):
    payload = payload or {}
    summary = payload.get("summary", {}) or {}
    compare = summary.get("comparison_day", {}) or {}
    dashboard = payload.get("dashboard_summary", {}) or {}
    exported_at = datetime.now().isoformat(timespec="seconds")
    headers = [
        "exported_at",
        "target",
        "target_label",
        "total_meters",
        "online_meters",
        "offline_meters",
        "total_power_kw",
        "total_daily_energy_kwh",
        "total_monthly_energy_kwh",
        "total_energy_kwh",
        "display_total_energy_kwh",
        "effective_total_energy_kwh",
        "energy_display_mode",
        "comparison_delta_kwh",
        "comparison_delta_pct",
        "comparison_trend",
    ]
    rows = [[
        exported_at,
        payload.get("trend_target") or "total",
        payload.get("trend_target_label") or "全部统计电表",
        summary.get("total", 0),
        summary.get("online", 0),
        summary.get("offline", 0),
        dashboard.get("power", summary.get("total_realtime_power", 0)),
        dashboard.get("daily_energy", summary.get("total_daily_energy", 0)),
        dashboard.get("monthly_energy", summary.get("total_monthly_energy", 0)),
        summary.get("total_electric_energy", 0),
        summary.get("display_total_electric_energy", 0),
        summary.get("effective_total_electric_energy", 0),
        summary.get("energy_display_mode", "display"),
        compare.get("delta", 0),
        compare.get("delta_pct", ""),
        compare.get("trend", "flat"),
    ]]
    return headers, rows


def build_summary_csv_text(payload):
    headers, rows = _build_summary_rows(payload)
    return _render_csv(headers, rows)


def build_summary_xlsx_bytes(payload):
    headers, rows = _build_summary_rows(payload)
    return _render_xlsx("summary", headers, rows)


def _build_statistics_rows(payload, period="day"):
    payload = payload or {}
    period_key = {"day": "daily", "week": "weekly", "month": "monthly"}.get(str(period or "day"), "daily")
    trend_breakdown = payload.get("trend_breakdown", {}) or {}
    source_rows = list(trend_breakdown.get(period_key, []) or [])
    summary = payload.get("summary", {}) or {}
    compare = summary.get("comparison_day", {}) or {}
    exported_at = datetime.now().isoformat(timespec="seconds")
    headers = [
        "exported_at",
        "period_mode",
        "target",
        "target_label",
        "period",
        "consume_kwh",
        "is_current_period",
        "total_power_kw",
        "total_daily_energy_kwh",
        "total_monthly_energy_kwh",
        "effective_total_energy_kwh",
        "comparison_delta_kwh",
        "comparison_delta_pct",
        "comparison_trend",
    ]
    rows = []
    last_index = max(len(source_rows) - 1, 0)
    for index, row in enumerate(source_rows):
        rows.append([
            exported_at,
            period,
            payload.get("trend_target") or "total",
            payload.get("trend_target_label") or "全部统计电表",
            row.get("period") or row.get("date") or "",
            row.get("consume", 0),
            1 if bool(row.get("is_today")) or index == last_index else 0,
            summary.get("total_realtime_power", 0),
            summary.get("total_daily_energy", 0),
            summary.get("total_monthly_energy", 0),
            summary.get("effective_total_electric_energy", 0),
            compare.get("delta", 0),
            compare.get("delta_pct", ""),
            compare.get("trend", "flat"),
        ])
    return headers, rows


def build_statistics_csv_text(payload, period="day"):
    headers, rows = _build_statistics_rows(payload, period=period)
    return _render_csv(headers, rows)


def build_statistics_xlsx_bytes(payload, period="day"):
    headers, rows = _build_statistics_rows(payload, period=period)
    return _render_xlsx(f"statistics_{period}", headers, rows)


def _build_raw_rows(rows):
    exported_at = datetime.now().isoformat(timespec="seconds")
    headers = [
        "exported_at",
        "meter_id",
        "display_name",
        "area_name",
        "online",
        "meter_mode",
        "protocol",
        "comm_mode",
        "realtime_power_kw",
        "raw_electric_energy_kwh",
        "display_electric_energy_kwh",
        "effective_electric_energy_kwh",
        "daily_energy_kwh",
        "monthly_energy_kwh",
        "voltage_a_v",
        "voltage_b_v",
        "voltage_c_v",
        "current_a_a",
        "current_b_a",
        "current_c_a",
        "power_factor",
        "frequency_hz",
        "updated_at",
        "error",
    ]
    result_rows = []
    for row in list(rows or []):
        result_rows.append([
            exported_at,
            row.get("id") or row.get("meter_id") or "",
            row.get("display_name") or row.get("name") or "",
            row.get("area_name") or "",
            1 if bool(row.get("online", False)) else 0,
            row.get("meter_mode") or "",
            row.get("protocol") or "",
            row.get("comm_mode") or "",
            row.get("realtime_power", 0),
            row.get("raw_electric_energy", row.get("electric_energy", 0)),
            row.get("display_electric_energy", row.get("electric_energy", 0)),
            row.get("effective_electric_energy", row.get("electric_energy", 0)),
            row.get("daily_energy", 0),
            row.get("monthly_energy", 0),
            row.get("voltage_a", 0),
            row.get("voltage_b", 0),
            row.get("voltage_c", 0),
            row.get("current_a", 0),
            row.get("current_b", 0),
            row.get("current_c", 0),
            row.get("power_factor", 0),
            row.get("frequency", 0),
            row.get("updated_at") or "",
            row.get("error") or "",
        ])
    return headers, result_rows


def build_raw_csv_text(rows):
    headers, result_rows = _build_raw_rows(rows)
    return _render_csv(headers, result_rows)


def build_raw_xlsx_bytes(rows):
    headers, result_rows = _build_raw_rows(rows)
    return _render_xlsx("raw", headers, result_rows)


def _write_text(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        f.write(text)


def _write_bytes(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(content)


def _cleanup_old_reports(report_dir, keep_days):
    keep_days = max(int(keep_days or 90), 1)
    cutoff = datetime.now() - timedelta(days=keep_days)
    for folder_name in ("daily", "weekly", "monthly", "raw", "summary"):
        folder_path = os.path.join(report_dir, folder_name)
        if not os.path.isdir(folder_path):
            continue
        for file_name in os.listdir(folder_path):
            if not (file_name.lower().endswith(".csv") or file_name.lower().endswith(".xlsx")):
                continue
            full_path = os.path.join(folder_path, file_name)
            try:
                modified = datetime.fromtimestamp(os.path.getmtime(full_path))
                if modified < cutoff:
                    os.remove(full_path)
            except Exception:
                continue


def export_reports_snapshot(payload, meter_statistics):
    meter_statistics = meter_statistics or {}
    if not bool(meter_statistics.get("auto_export_enabled", True)):
        return None
    report_dir = resolve_report_dir(meter_statistics)
    os.makedirs(report_dir, exist_ok=True)
    now = datetime.now()
    week_id = f"{now.isocalendar().year}-W{now.isocalendar().week:02d}"
    month_id = now.strftime("%Y-%m")
    date_id = now.strftime("%Y-%m-%d")

    summary_csv = build_summary_csv_text(payload)
    daily_csv = build_statistics_csv_text(payload, "day")
    weekly_csv = build_statistics_csv_text(payload, "week")
    monthly_csv = build_statistics_csv_text(payload, "month")
    raw_csv = build_raw_csv_text((payload or {}).get("meters", []))

    summary_xlsx = build_summary_xlsx_bytes(payload)
    daily_xlsx = build_statistics_xlsx_bytes(payload, "day")
    weekly_xlsx = build_statistics_xlsx_bytes(payload, "week")
    monthly_xlsx = build_statistics_xlsx_bytes(payload, "month")
    raw_xlsx = build_raw_xlsx_bytes((payload or {}).get("meters", []))

    text_files = {
        os.path.join(report_dir, "latest_summary.csv"): summary_csv,
        os.path.join(report_dir, "latest_daily.csv"): daily_csv,
        os.path.join(report_dir, "latest_weekly.csv"): weekly_csv,
        os.path.join(report_dir, "latest_monthly.csv"): monthly_csv,
        os.path.join(report_dir, "latest_raw.csv"): raw_csv,
        os.path.join(report_dir, "summary", f"{date_id}.csv"): summary_csv,
        os.path.join(report_dir, "daily", f"{date_id}.csv"): daily_csv,
        os.path.join(report_dir, "weekly", f"{week_id}.csv"): weekly_csv,
        os.path.join(report_dir, "monthly", f"{month_id}.csv"): monthly_csv,
        os.path.join(report_dir, "raw", f"{date_id}.csv"): raw_csv,
    }
    binary_files = {
        os.path.join(report_dir, "latest_summary.xlsx"): summary_xlsx,
        os.path.join(report_dir, "latest_daily.xlsx"): daily_xlsx,
        os.path.join(report_dir, "latest_weekly.xlsx"): weekly_xlsx,
        os.path.join(report_dir, "latest_monthly.xlsx"): monthly_xlsx,
        os.path.join(report_dir, "latest_raw.xlsx"): raw_xlsx,
        os.path.join(report_dir, "summary", f"{date_id}.xlsx"): summary_xlsx,
        os.path.join(report_dir, "daily", f"{date_id}.xlsx"): daily_xlsx,
        os.path.join(report_dir, "weekly", f"{week_id}.xlsx"): weekly_xlsx,
        os.path.join(report_dir, "monthly", f"{month_id}.xlsx"): monthly_xlsx,
        os.path.join(report_dir, "raw", f"{date_id}.xlsx"): raw_xlsx,
    }

    for path, text in text_files.items():
        _write_text(path, text)
    for path, content in binary_files.items():
        _write_bytes(path, content)
    _cleanup_old_reports(report_dir, meter_statistics.get("history_keep_days", 90))

    return {
        "report_dir": report_dir,
        "exported_at": now.isoformat(timespec="seconds"),
        "file_count": len(text_files) + len(binary_files),
    }


def build_report_index(meter_statistics):
    report_dir = resolve_report_dir(meter_statistics or {})
    items = []
    for category in ("summary", "daily", "weekly", "monthly", "raw"):
        for ext in ("csv", "xlsx"):
            path = os.path.join(report_dir, f"latest_{category}.{ext}")
            exists = os.path.exists(path)
            items.append({
                "key": f"{category}_{ext}",
                "category": category,
                "format": ext,
                "path": path,
                "exists": exists,
                "updated_at": datetime.fromtimestamp(os.path.getmtime(path)).isoformat(timespec="seconds") if exists else "",
                "size": os.path.getsize(path) if exists else 0,
            })
    return {"report_dir": report_dir, "items": items}
