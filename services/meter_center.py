from datetime import datetime, timedelta

from config import CONFIG, DEVICE_STATUS, METER_STATUS, get_default_status
from data_logger import apply_display_reset, calculate_display_reset_delta, compare_with_previous, get_generic_energy_history_data, summarize_period_rows

from .meter_payloads import apply_reference_comparison, build_reference_meter_payload, find_meter_row_by_source
from .meter_remote import safe_float


def decorate_meter_rows(rows, energy_display_mode="display"):
    decorated = []
    for row in rows or []:
        item = dict(row)
        raw_energy = safe_float(item.get("electric_energy"), 0.0)
        source_type = str(item.get("source_type") or "").strip().lower()
        item["power_is_estimated"] = source_type in {"cabinet_meter", "calculated_meter"}
        item["display_electric_energy"] = round(raw_energy, 4)
        item["raw_electric_energy"] = round(raw_energy, 4)
        item["effective_electric_energy"] = round(
            item["display_electric_energy"] if str(energy_display_mode or "display").lower() != "raw" else item["raw_electric_energy"],
            4,
        )
        decorated.append(item)
    return decorated


def build_meter_row(cab_idx, cab_cfg, status):
    status = status or get_default_status()
    meter_mode = str(cab_cfg.get("meter_mode", "type1") or "type1")
    comm_ok = bool(status.get("comm_status", False))
    channel_count = int(cab_cfg.get("channel_count", 0) or 0)
    channel_states = list(status.get("channels_1_4", []) or [])[:channel_count]
    channel_on_count = sum(1 for item in channel_states if item)
    return {
        "id": f"cabinet_meter_{cab_idx}",
        "meter_id": f"cabinet_meter_{cab_idx}",
        "source_type": "cabinet_meter",
        "cabinet_idx": cab_idx,
        "source_key": f"cabinet:{cab_idx}",
        "cabinet_name": cab_cfg.get("cabinet_name", f"电柜 {cab_idx + 1}"),
        "display_name": cab_cfg.get("meter_display_name") or cab_cfg.get("cabinet_name", f"电柜 {cab_idx + 1}"),
        "meter_mode": meter_mode,
        "meter_mode_name": {"type1": "电表类型 1", "type4": "电表类型 4"}.get(meter_mode, meter_mode),
        "meter_kind": "柜内电表",
        "protocol": cab_cfg.get("plc_type", "AV-100"),
        "area_name": cab_cfg.get("meter_area_name", ""),
        "meter_sort_order": int(cab_cfg.get("meter_sort_order", cab_idx + 1) or (cab_idx + 1)),
        "visible_in_meter_center": bool(cab_cfg.get("meter_visible_in_center", True)),
        "include_in_totals": bool(cab_cfg.get("meter_include_in_totals", True)),
        "include_in_reports": bool(cab_cfg.get("meter_include_in_reports", True)),
        "online": comm_ok,
        "comm_status": comm_ok,
        "ip": cab_cfg.get("ip", ""),
        "port": cab_cfg.get("port", ""),
        "station_id": cab_cfg.get("station_id", ""),
        "ct_ratio": safe_float(cab_cfg.get("ct_ratio", 1), 1.0),
        "channel_count": channel_count,
        "channel_on_count": channel_on_count,
        "work_mode": status.get("work_mode", "未知"),
        "voltage_a": safe_float(status.get("voltage_a")),
        "voltage_b": safe_float(status.get("voltage_b")),
        "voltage_c": safe_float(status.get("voltage_c")),
        "voltage_ab": safe_float(status.get("voltage_ab")),
        "voltage_bc": safe_float(status.get("voltage_bc")),
        "voltage_ca": safe_float(status.get("voltage_ca")),
        "current_a": safe_float(status.get("current_a")),
        "current_b": safe_float(status.get("current_b")),
        "current_c": safe_float(status.get("current_c")),
        "realtime_power": safe_float(status.get("realtime_power")),
        "reactive_power": safe_float(status.get("reactive_power")),
        "apparent_power": safe_float(status.get("apparent_power")),
        "power_factor": safe_float(status.get("power_factor")),
        "frequency": safe_float(status.get("frequency")),
        "electric_energy": safe_float(status.get("electric_energy")),
        "daily_energy": safe_float(status.get("daily_energy")),
        "monthly_energy": safe_float(status.get("monthly_energy")),
        "cabinet_temp": safe_float(status.get("cabinet_temp")),
        "cabinet_humidity": safe_float(status.get("cabinet_humidity")),
        "energy_format_preset": cab_cfg.get("energy_format_preset", "cabinet_builtin"),
    }


def build_standalone_meter_row(meter_cfg, meter_status):
    meter_id = str(meter_cfg.get("id", "")).strip()
    bind_cabinet_idx = int(meter_cfg.get("bind_cabinet_idx", -1) or -1)
    return {
        "id": meter_id,
        "meter_id": meter_id,
        "source_type": "standalone_meter",
        "source_key": f"meter:{meter_id}",
        "cabinet_idx": bind_cabinet_idx,
        "cabinet_name": meter_status.get("bound_cabinet_name") or meter_cfg.get("name", meter_id),
        "display_name": meter_cfg.get("name", meter_id),
        "meter_mode": meter_cfg.get("meter_type", "direct"),
        "meter_mode_name": meter_cfg.get("meter_type", "direct"),
        "meter_kind": meter_cfg.get("meter_kind", "独立电表"),
        "protocol": meter_cfg.get("protocol", "Modbus-RTU/TCP"),
        "online": bool(meter_status.get("online", False)),
        "comm_status": bool(meter_status.get("online", False)),
        "ip": meter_cfg.get("ip", ""),
        "port": meter_cfg.get("port", ""),
        "station_id": meter_cfg.get("station_id", ""),
        "ct_ratio": safe_float(meter_cfg.get("ct_ratio", 1), 1.0),
        "channel_count": 0,
        "channel_on_count": 0,
        "work_mode": meter_status.get("work_mode", "独立电表"),
        "voltage_a": safe_float(meter_status.get("voltage_a")),
        "voltage_b": safe_float(meter_status.get("voltage_b")),
        "voltage_c": safe_float(meter_status.get("voltage_c")),
        "voltage_ab": safe_float(meter_status.get("voltage_ab")),
        "voltage_bc": safe_float(meter_status.get("voltage_bc")),
        "voltage_ca": safe_float(meter_status.get("voltage_ca")),
        "current_a": safe_float(meter_status.get("current_a")),
        "current_b": safe_float(meter_status.get("current_b")),
        "current_c": safe_float(meter_status.get("current_c")),
        "realtime_power": safe_float(meter_status.get("realtime_power")),
        "reactive_power": safe_float(meter_status.get("reactive_power")),
        "apparent_power": safe_float(meter_status.get("apparent_power")),
        "power_factor": safe_float(meter_status.get("power_factor")),
        "frequency": safe_float(meter_status.get("frequency")),
        "electric_energy": safe_float(meter_status.get("electric_energy")),
        "daily_energy": safe_float(meter_status.get("daily_energy")),
        "monthly_energy": safe_float(meter_status.get("monthly_energy")),
        "cabinet_temp": meter_status.get("cabinet_temp"),
        "cabinet_humidity": meter_status.get("cabinet_humidity"),
        "brand": meter_cfg.get("brand", ""),
        "model": meter_cfg.get("model", ""),
        "sort_order": int(meter_cfg.get("sort_order", 999) or 999),
        "source_mode": meter_cfg.get("source_mode", "standalone"),
        "energy_format_preset": meter_cfg.get("energy_format_preset", "custom"),
        "error": meter_status.get("error", ""),
        "area_name": meter_cfg.get("area_name", ""),
        "visible_in_meter_center": bool(meter_cfg.get("visible_in_meter_center", meter_cfg.get("visible", True))),
        "include_in_totals": bool(meter_cfg.get("include_in_totals", True)),
        "include_in_reports": bool(meter_cfg.get("include_in_reports", True)),
    }


def get_all_meter_rows():
    rows = []
    for idx, cab_cfg in enumerate(CONFIG.get("cabinets", [])):
        rows.append(build_meter_row(idx, cab_cfg, DEVICE_STATUS.get(idx)))
    for meter_cfg in CONFIG.get("meters", []):
        meter_id = str(meter_cfg.get("id", "")).strip()
        if not meter_id:
            continue
        meter_status = METER_STATUS.get(meter_id, {})
        bind_cabinet_idx = int(meter_cfg.get("bind_cabinet_idx", -1) or -1)
        if str(meter_cfg.get("source_mode", "standalone")) == "cabinet_linked" and bind_cabinet_idx >= 0:
            continue
        rows.append(build_standalone_meter_row(meter_cfg, meter_status))
    return rows


def filter_summary_rows(rows):
    meter_statistics = CONFIG.get("meter_statistics", {}) or {}
    mode = str(meter_statistics.get("summary_mode", "include_flag") or "include_flag")
    filtered = []
    for row in rows:
        include = bool(row.get("include_in_totals", True))
        visible = bool(row.get("visible_in_meter_center", True))
        if not visible:
            continue
        if mode == "visible_only":
            if include:
                filtered.append(row)
        elif include:
            filtered.append(row)
    return filtered


def serialize_type_counts(rows):
    type_counts = {}
    for row in rows:
        meter_mode = str(row.get("meter_mode") or "other")
        type_counts[meter_mode] = type_counts.get(meter_mode, 0) + 1
    return type_counts


def meter_sort_value(row):
    try:
        return int(row.get("sort_order", row.get("meter_sort_order", 999)) or 999)
    except Exception:
        return 999


def sort_meter_rows(rows):
    return sorted(
        rows,
        key=lambda row: (
            meter_sort_value(row),
            str(row.get("display_name") or row.get("cabinet_name") or row.get("id") or ""),
        ),
    )


def build_area_groups(rows):
    groups = {}
    for row in rows:
        area_name = str(row.get("area_name") or "").strip()
        if not area_name:
            continue
        groups.setdefault(area_name, []).append(row)
    return groups


def build_target_rows(rows):
    targets = [{"source_key": "total", "label": "全部统计电表", "type": "total"}]
    for area_name in sorted(build_area_groups(rows).keys()):
        targets.append({
            "source_key": f"area:{area_name}",
            "label": f"{area_name}（区域）",
            "type": "area",
            "area_name": area_name,
        })
    targets.extend(
        {
            "source_key": row.get("source_key"),
            "label": row.get("display_name") or row.get("cabinet_name") or row.get("id"),
            "type": row.get("source_type"),
            "area_name": row.get("area_name", ""),
        }
        for row in rows
    )
    return targets


def aggregate_history_rows(rows, days):
    days = max(2, int(days or 7))
    start_date = datetime.now().date() - timedelta(days=days - 1)
    consume_map = {}
    for offset in range(days):
        day_text = (start_date + timedelta(days=offset)).strftime("%Y-%m-%d")
        consume_map[day_text] = 0.0

    for row in rows:
        if not row.get("include_in_reports", True):
            continue
        source_type = "cabinet" if row.get("source_type") == "cabinet_meter" else "meter"
        source_id = row.get("cabinet_idx") if source_type == "cabinet" else row.get("id")
        history = get_generic_energy_history_data(source_type, source_id, row.get("daily_energy", 0.0), days=days)
        for item in history:
            day_text = str(item.get("date") or "")
            if day_text in consume_map:
                consume_map[day_text] += safe_float(item.get("consume"), 0.0)

    today_text = datetime.now().strftime("%Y-%m-%d")
    return [
        {"date": day_text, "consume": round(consume_map[day_text], 4), "is_today": day_text == today_text}
        for day_text in sorted(consume_map.keys())
    ]


def resolve_trend_target(rows, target_source_key):
    target_key = str(target_source_key or "total")
    if target_key == "total":
        return {"target": "total", "label": "全部统计电表", "type": "total", "rows": rows}
    if target_key.startswith("area:"):
        area_name = target_key.split(":", 1)[1].strip()
        area_rows = [row for row in rows if str(row.get("area_name") or "").strip() == area_name]
        return {"target": target_key, "label": f"{area_name}（区域）", "type": "area", "rows": area_rows}
    target_row = next((row for row in rows if str(row.get("source_key")) == target_key), None)
    if not target_row:
        return None
    return {
        "target": target_key,
        "label": target_row.get("display_name") or target_row.get("cabinet_name") or target_row.get("id"),
        "type": target_row.get("source_type"),
        "rows": [target_row],
    }


def build_trend_rows(rows, target_source_key="total", period="day", days=7):
    days = max(2, int(days or 7))
    resolved = resolve_trend_target(rows, target_source_key)
    if not resolved or not resolved.get("rows"):
        return {
            "target": None,
            "target_label": "",
            "target_type": "",
            "daily_rows": [],
            "period_rows": {"daily": [], "weekly": [], "monthly": []},
            "comparison": compare_with_previous([]),
        }
    if resolved.get("type") in ("total", "area"):
        daily_rows = aggregate_history_rows(resolved.get("rows", []), days)
    else:
        target = resolved["rows"][0]
        source_type = "cabinet" if target.get("source_type") == "cabinet_meter" else "meter"
        source_id = target.get("cabinet_idx") if source_type == "cabinet" else target.get("id")
        daily_rows = get_generic_energy_history_data(source_type, source_id, target.get("daily_energy", 0.0), days=days)
    period_rows = summarize_period_rows(daily_rows)
    period_key = "weekly" if str(period) == "week" else ("monthly" if str(period) == "month" else "daily")
    comparison = compare_with_previous(period_rows.get(period_key, []))
    return {
        "target": resolved.get("target"),
        "target_label": resolved.get("label", ""),
        "target_type": resolved.get("type", ""),
        "daily_rows": daily_rows,
        "period_rows": period_rows,
        "comparison": comparison,
    }


def build_meter_center_payload(target_source_key="total", period="day", days=7):
    meter_statistics = CONFIG.get("meter_statistics", {}) or {}
    energy_display_mode = str(meter_statistics.get("energy_display_mode", "display") or "display")
    all_rows = decorate_meter_rows(sort_meter_rows(get_all_meter_rows()), energy_display_mode=energy_display_mode)
    summary_rows = filter_summary_rows(all_rows)
    total_power = sum(safe_float(row.get("realtime_power")) for row in summary_rows if not bool(row.get("power_is_estimated", False)))
    estimated_total_power = sum(safe_float(row.get("realtime_power")) for row in summary_rows)
    raw_total_daily_energy = sum(safe_float(row.get("daily_energy")) for row in summary_rows)
    total_monthly_energy = sum(safe_float(row.get("monthly_energy")) for row in summary_rows)
    total_energy = sum(safe_float(row.get("electric_energy")) for row in summary_rows)
    meters = [row for row in all_rows if bool(row.get("visible_in_meter_center", True))]
    trend_bundle = build_trend_rows(summary_rows, target_source_key=target_source_key, period=period, days=days)
    visible_online_count = sum(1 for row in meters if bool(row.get("online", False)))
    display_total_energy = calculate_display_reset_delta(total_energy)
    reset_from = str((meter_statistics.get("display_reset", {}) or {}).get("from") or meter_statistics.get("display_reset_from") or "").strip()
    reset_is_today = bool(reset_from) and reset_from[:10] == datetime.now().strftime("%Y-%m-%d")
    total_daily_energy = display_total_energy if reset_is_today else raw_total_daily_energy
    summary_energy_value = display_total_energy if energy_display_mode != "raw" else total_energy
    payload = {
        "summary": {
            "total": len(meters),
            "online": visible_online_count,
            "offline": max(len(meters) - visible_online_count, 0),
            "total_realtime_power": round(total_power, 2),
            "estimated_total_realtime_power": round(estimated_total_power, 2),
            "total_daily_energy": round(total_daily_energy, 1),
            "raw_total_daily_energy": round(raw_total_daily_energy, 1),
            "total_monthly_energy": round(total_monthly_energy, 1),
            "total_electric_energy": round(total_energy, 1),
            "display_total_electric_energy": round(display_total_energy, 1),
            "effective_total_electric_energy": round(summary_energy_value, 1),
            "energy_display_mode": energy_display_mode,
            "type_counts": serialize_type_counts(meters),
            "comparison_day": trend_bundle["comparison"],
        },
        "meters": meters,
        "trend": trend_bundle.get("daily_rows", []),
        "trend_breakdown": trend_bundle.get("period_rows", {}),
        "trend_target": trend_bundle.get("target"),
        "trend_target_label": trend_bundle.get("target_label", ""),
        "trend_target_type": trend_bundle.get("target_type", ""),
        "trend_period": period,
        "trend_days": days,
        "trend_targets": build_target_rows(meters),
        "dashboard_summary": {
            "power": round(total_power, 2),
            "estimated_power": round(estimated_total_power, 2),
            "daily_energy": round(total_daily_energy, 1),
            "raw_daily_energy": round(raw_total_daily_energy, 1),
            "monthly_energy": round(total_monthly_energy, 1),
            "electric_energy": round(total_energy, 1),
            "display_electric_energy": round(display_total_energy, 1),
            "effective_electric_energy": round(summary_energy_value, 1),
            "energy_display_mode": energy_display_mode,
            "comparison_day": trend_bundle["comparison"],
        },
    }
    fallback_reference_row = find_meter_row_by_source(
        all_rows,
        str(meter_statistics.get("reference_total_meter_source_key", "") or "").strip(),
    )
    payload = apply_reference_comparison(payload, build_reference_meter_payload(fallback_reference_row))
    reference_key = str((payload.get("summary", {}) or {}).get("reference_total_meter_source_key") or "").strip()
    if reference_key:
        for item in payload.get("meters", []) or []:
            item["is_reference_meter"] = meter_source_keys_match(item.get("source_key"), reference_key) or meter_source_keys_match(item.get("meter_id") or item.get("id"), reference_key)
    return payload
