# AI_MODULE: meter_payload_service
# AI_PURPOSE: Build reference meter payloads, source matching variants, and overlay comparisons for energy display.
# AI_BOUNDARY: No device polling or control; it only normalizes and compares already-collected meter rows.
# AI_DATA_FLOW: CONFIG meter definitions + data_logger summaries -> reference meter payloads for meter center APIs.
# AI_RUNTIME: Used by services/meter_center.py and power/meter API reads.
# AI_RISK: Medium. Source matching mistakes can attach history or reference values to the wrong meter.
# AI_COMPAT: Preserve normalized source keys and comparison fields used by meter center frontend.
# AI_SEARCH_KEYWORDS: meter payload, source key, reference meter, energy history, overlay.
from datetime import datetime

from config import CONFIG
from data_logger import calculate_display_reset_delta, compare_with_previous, summarize_period_rows

from .meter_remote import index_meter_rows, normalize_meter_source_key, safe_float, should_overlay_with_candidate


def build_meter_source_variants(value):
    text = str(value or "").strip()
    if not text:
        return set()
    variants = {text}
    normalized = normalize_meter_source_key(text)
    if normalized:
        variants.add(normalized)
    if text.startswith("meter:"):
        bare = text.split(":", 1)[1].strip()
        if bare:
            variants.add(bare)
            normalized_bare = normalize_meter_source_key(bare)
            if normalized_bare:
                variants.add(normalized_bare)
    elif not text.startswith("cabinet:"):
        variants.add(f"meter:{text}")
    if text.startswith("cabinet_meter_"):
        suffix = text.split("_")[-1].strip()
        if suffix.isdigit():
            variants.add(f"cabinet:{suffix}")
    return {item for item in variants if item}


def meter_source_keys_match(left, right):
    return bool(build_meter_source_variants(left) & build_meter_source_variants(right))


def find_meter_row_by_source(rows, source_key):
    source_key = str(source_key or "").strip()
    if not source_key:
        return None
    for row in rows or []:
        row_source_key = str(row.get("source_key") or "").strip()
        row_meter_id = str(row.get("meter_id") or row.get("id") or "").strip()
        if meter_source_keys_match(row_source_key, source_key):
            return row
        if meter_source_keys_match(row_meter_id, source_key):
            return row
    return None


def build_reference_metric(current_value, reference_value):
    current = safe_float(current_value, 0.0)
    reference = safe_float(reference_value, 0.0)
    delta = current - reference
    delta_pct = round(delta / reference * 100.0, 2) if reference > 0 else None
    return {
        "current": round(current, 4),
        "reference": round(reference, 4),
        "delta": round(delta, 4),
        "delta_pct": delta_pct,
        "trend": "up" if delta > 0 else ("down" if delta < 0 else "flat"),
    }


def _row_effective_power(row):
    return safe_float(
        (row or {}).get("effective_realtime_power"),
        safe_float((row or {}).get("stable_realtime_power"), safe_float((row or {}).get("realtime_power"), 0.0)),
    )


def _reference_meter_available(payload):
    return bool(payload.get("online")) or any(
        abs(safe_float(payload.get(key), 0.0)) > 0
        for key in ("realtime_power", "daily_energy", "monthly_energy", "electric_energy", "display_electric_energy", "effective_electric_energy")
    )


def build_reference_meter_payload(row):
    if not isinstance(row, dict):
        return None
    payload = {
        "source_key": str(row.get("source_key") or ""),
        "meter_id": str(row.get("meter_id") or row.get("id") or ""),
        "label": row.get("display_name") or row.get("cabinet_name") or row.get("id") or "参考总表",
        "online": bool(row.get("online", False)),
        "realtime_power": round(_row_effective_power(row), 4),
        "daily_energy": round(safe_float(row.get("daily_energy"), 0.0), 4),
        "monthly_energy": round(safe_float(row.get("monthly_energy"), 0.0), 4),
        "electric_energy": round(safe_float(row.get("electric_energy"), 0.0), 4),
        "display_electric_energy": round(safe_float(row.get("display_electric_energy"), safe_float(row.get("electric_energy"), 0.0)), 4),
        "effective_electric_energy": round(safe_float(row.get("effective_electric_energy"), safe_float(row.get("electric_energy"), 0.0)), 4),
    }
    payload["available"] = _reference_meter_available(payload)
    return payload


def _resolve_payload_target_rows(payload):
    rows = list((payload or {}).get("meters", []) or [])
    target_key = str((payload or {}).get("trend_target") or "total").strip() or "total"
    if target_key == "total":
        return [row for row in rows if bool(row.get("include_in_reports", True))]
    if target_key.startswith("area:"):
        area_name = target_key.split(":", 1)[1].strip()
        return [
            row for row in rows
            if bool(row.get("include_in_reports", True)) and str(row.get("area_name") or "").strip() == area_name
        ]
    target_row = find_meter_row_by_source(rows, target_key)
    return [target_row] if isinstance(target_row, dict) else []


def _resolve_payload_energy_cap(payload):
    target_rows = _resolve_payload_target_rows(payload)
    row_cap = sum(
        max(
            safe_float(row.get("raw_electric_energy"), 0.0),
            safe_float(row.get("electric_energy"), 0.0),
            safe_float(row.get("display_electric_energy"), 0.0),
            safe_float(row.get("effective_electric_energy"), 0.0),
        )
        for row in target_rows
    )
    summary = dict((payload or {}).get("summary", {}) or {})
    dashboard = dict((payload or {}).get("dashboard_summary", {}) or {})
    summary_cap = max(
        safe_float(summary.get("total_electric_energy"), 0.0),
        safe_float(summary.get("display_total_electric_energy"), 0.0),
        safe_float(summary.get("effective_total_electric_energy"), 0.0),
        safe_float(dashboard.get("electric_energy"), 0.0),
        safe_float(dashboard.get("display_electric_energy"), 0.0),
        safe_float(dashboard.get("effective_electric_energy"), 0.0),
    )
    return max(row_cap, summary_cap, 0.0)


def _is_unreasonable_history_consume(consume, energy_cap):
    value = safe_float(consume, 0.0)
    cap = safe_float(energy_cap, 0.0)
    if value <= 0 or cap <= 0:
        return False
    return value > (cap * 1.2)


def sanitize_meter_payload_history(payload):
    if not isinstance(payload, dict):
        return payload
    daily_rows = list(payload.get("trend", []) or ((payload.get("trend_breakdown", {}) or {}).get("daily", []) or []))
    if not daily_rows:
        return payload
    energy_cap = _resolve_payload_energy_cap(payload)
    cleaned_daily = []
    outlier_dates = []
    for row in daily_rows:
        item = dict(row)
        consume = safe_float(item.get("consume"), 0.0)
        if _is_unreasonable_history_consume(consume, energy_cap):
            item["consume"] = 0.0
            item["_outlier"] = True
            outlier_dates.append(str(item.get("date") or item.get("period") or ""))
        else:
            item["consume"] = round(max(consume, 0.0), 4)
        if "period" in item and "date" not in item:
            item["date"] = str(item.get("period") or "")
        cleaned_daily.append(item)

    breakdown = summarize_period_rows(cleaned_daily)
    period_key = "weekly" if str(payload.get("trend_period")) == "week" else ("monthly" if str(payload.get("trend_period")) == "month" else "daily")
    comparison = compare_with_previous(breakdown.get(period_key, []))
    comparison["valid"] = not any(bool(item.get("_outlier")) for item in cleaned_daily[-2:])
    if not comparison["valid"]:
        comparison["reason"] = "history_outlier"

    payload["trend"] = cleaned_daily
    payload["trend_breakdown"] = breakdown
    payload["history_outlier_dates"] = outlier_dates
    summary = dict(payload.get("summary", {}) or {})
    dashboard_summary = dict(payload.get("dashboard_summary", {}) or {})
    summary["comparison_day"] = comparison
    dashboard_summary["comparison_day"] = comparison
    payload["summary"] = summary
    payload["dashboard_summary"] = dashboard_summary
    return payload


def apply_reference_comparison(payload, fallback_reference_meter=None):
    if not isinstance(payload, dict):
        return payload
    summary = dict(payload.get("summary", {}) or {})
    dashboard_summary = dict(payload.get("dashboard_summary", {}) or {})
    meter_statistics = CONFIG.get("meter_statistics", {}) or {}
    existing_reference_meter = summary.get("reference_meter")
    existing_compare = summary.get("compare_to_reference")
    reference_source_key = str(
        summary.get("reference_total_meter_source_key")
        or dashboard_summary.get("reference_total_meter_source_key")
        or meter_statistics.get("reference_total_meter_source_key", "")
        or ""
    ).strip()
    reference_meter = None
    if reference_source_key:
        reference_row = find_meter_row_by_source(payload.get("meters", []), reference_source_key)
        if reference_row:
            reference_meter = build_reference_meter_payload(reference_row)
        elif isinstance(existing_reference_meter, dict):
            existing_key = str(existing_reference_meter.get("source_key") or existing_reference_meter.get("meter_id") or "").strip()
            if existing_key and meter_source_keys_match(existing_key, reference_source_key):
                reference_meter = dict(existing_reference_meter)
        elif isinstance(fallback_reference_meter, dict):
            fallback_key = str(fallback_reference_meter.get("source_key") or fallback_reference_meter.get("meter_id") or "").strip()
            if fallback_key and meter_source_keys_match(fallback_key, reference_source_key):
                reference_meter = dict(fallback_reference_meter)
    if isinstance(reference_meter, dict) and "available" not in reference_meter:
        reference_meter = dict(reference_meter)
        reference_meter["available"] = _reference_meter_available(reference_meter)

    reference_compare = {}
    if reference_meter and bool(reference_meter.get("available")):
        reference_compare = {
            "power": {"available": False, "disabled": True, "reason": "power_comparison_disabled"},
            "daily_energy": build_reference_metric(summary.get("total_daily_energy"), reference_meter.get("daily_energy")),
            "monthly_energy": build_reference_metric(summary.get("total_monthly_energy"), reference_meter.get("monthly_energy")),
            "electric_energy": build_reference_metric(
                summary.get("effective_total_electric_energy", summary.get("display_total_electric_energy", summary.get("total_electric_energy"))),
                reference_meter.get("effective_electric_energy", reference_meter.get("electric_energy")),
            ),
        }
        for item in reference_compare.values():
            item["available"] = True
    elif reference_meter:
        reference_compare = {
            "power": {"available": False},
            "daily_energy": {"available": False},
            "monthly_energy": {"available": False},
            "electric_energy": {"available": False},
        }
    elif isinstance(existing_reference_meter, dict):
        reference_meter = dict(existing_reference_meter)
        if isinstance(existing_compare, dict):
            reference_compare = dict(existing_compare)

    summary["reference_total_meter_source_key"] = reference_source_key
    summary["reference_meter"] = reference_meter
    summary["compare_to_reference"] = reference_compare
    reference_realtime_power = safe_float((reference_meter or {}).get("realtime_power"), 0.0)
    summary["reference_total_realtime_power"] = round(reference_realtime_power, 2)
    summary["submeter_total_realtime_power"] = round(safe_float(summary.get("total_realtime_power"), 0.0), 2)
    summary["submeter_estimated_total_realtime_power"] = round(
        safe_float(summary.get("estimated_total_realtime_power"), 0.0),
        2,
    )
    summary["card_total_realtime_power"] = round(
        safe_float(
            summary.get("estimated_total_realtime_power"),
            safe_float(summary.get("total_realtime_power"), 0.0),
        ),
        2,
    )
    dashboard_summary["reference_total_meter_source_key"] = reference_source_key
    dashboard_summary["reference_meter"] = reference_meter
    dashboard_summary["compare_to_reference"] = reference_compare
    dashboard_summary["reference_total_realtime_power"] = round(reference_realtime_power, 2)
    dashboard_summary["submeter_total_realtime_power"] = round(safe_float(summary.get("total_realtime_power"), 0.0), 2)
    dashboard_summary["submeter_estimated_total_realtime_power"] = round(
        safe_float(summary.get("estimated_total_realtime_power"), 0.0),
        2,
    )
    dashboard_summary["card_total_realtime_power"] = round(
        safe_float(
            summary.get("estimated_total_realtime_power"),
            safe_float(summary.get("total_realtime_power"), 0.0),
        ),
        2,
    )
    dashboard_summary["power"] = round(reference_realtime_power, 2) if reference_realtime_power > 0 else round(
        safe_float(summary.get("total_realtime_power"), 0.0),
        2,
    )
    if "comparison_day" in summary:
        dashboard_summary["comparison_day"] = summary.get("comparison_day")
    payload["summary"] = summary
    payload["dashboard_summary"] = dashboard_summary
    return sanitize_meter_payload_history(payload)


def rebuild_meter_summary_from_rows(rows, energy_display_mode="display", filter_summary_rows=None, serialize_type_counts=None):
    visible_rows = [row for row in rows if bool(row.get("visible_in_meter_center", True))]
    summary_rows = filter_summary_rows(visible_rows) if callable(filter_summary_rows) else visible_rows
    total_power = sum(
        _row_effective_power(row)
        for row in summary_rows
        if not bool(row.get("power_is_estimated", False))
    )
    estimated_total_power = sum(_row_effective_power(row) for row in summary_rows)
    raw_total_daily_energy = sum(safe_float(row.get("daily_energy"), 0.0) for row in summary_rows)
    total_monthly_energy = sum(safe_float(row.get("monthly_energy"), 0.0) for row in summary_rows)
    total_energy = sum(safe_float(row.get("electric_energy"), 0.0) for row in summary_rows)
    display_total_energy = calculate_display_reset_delta(total_energy)
    meter_statistics = CONFIG.get("meter_statistics", {}) or {}
    display_reset = meter_statistics.get("display_reset", {})
    if not isinstance(display_reset, dict):
        display_reset = {}
    reset_from = str(display_reset.get("from") or meter_statistics.get("display_reset_from") or "").strip()
    reset_is_today = bool(reset_from) and reset_from[:10] == datetime.now().strftime("%Y-%m-%d")
    total_daily_energy = display_total_energy if reset_is_today else raw_total_daily_energy
    effective_total_energy = display_total_energy if energy_display_mode != "raw" else total_energy
    online_count = sum(1 for row in visible_rows if bool(row.get("online", False)))
    type_counts = serialize_type_counts(visible_rows) if callable(serialize_type_counts) else {}
    return {
        "summary": {
            "total": len(visible_rows),
            "online": online_count,
            "offline": max(len(visible_rows) - online_count, 0),
            "total_realtime_power": round(total_power, 2),
            "estimated_total_realtime_power": round(estimated_total_power, 2),
            "total_daily_energy": round(total_daily_energy, 1),
            "raw_total_daily_energy": round(raw_total_daily_energy, 1),
            "total_monthly_energy": round(total_monthly_energy, 1),
            "total_electric_energy": round(total_energy, 1),
            "display_total_electric_energy": round(display_total_energy, 1),
            "effective_total_electric_energy": round(effective_total_energy, 1),
            "energy_display_mode": energy_display_mode,
            "type_counts": type_counts,
        },
        "dashboard_summary": {
            "power": round(total_power, 2),
            "estimated_power": round(estimated_total_power, 2),
            "daily_energy": round(total_daily_energy, 1),
            "raw_daily_energy": round(raw_total_daily_energy, 1),
            "monthly_energy": round(total_monthly_energy, 1),
            "electric_energy": round(total_energy, 1),
            "display_electric_energy": round(display_total_energy, 1),
            "effective_electric_energy": round(effective_total_energy, 1),
            "energy_display_mode": energy_display_mode,
        },
    }


def merge_meter_payloads(
    primary_payload,
    secondary_payload,
    overlay_name,
    data_source,
    sort_meter_rows=None,
    build_target_rows=None,
    filter_summary_rows=None,
    serialize_type_counts=None,
):
    if not isinstance(primary_payload, dict):
        return secondary_payload
    if not isinstance(secondary_payload, dict):
        return primary_payload

    primary_rows = list(primary_payload.get("meters", []) or [])
    secondary_rows = list(secondary_payload.get("meters", []) or [])
    secondary_index = index_meter_rows(secondary_rows)
    merged_rows = []
    overlay_count = 0

    for primary_row in primary_rows:
        meter_id = str(primary_row.get("id") or primary_row.get("meter_id") or "").strip()
        source_key = str(primary_row.get("source_key") or "").strip()
        secondary_row = secondary_index.get(source_key) if source_key else None
        if not secondary_row and meter_id:
            secondary_row = secondary_index.get(meter_id)
        if should_overlay_with_candidate(primary_row, secondary_row):
            merged_row = dict(secondary_row)
            merged_row[f"_overlay_from_{overlay_name}"] = True
            merged_row["_overlay_reason"] = "primary_missing_or_offline"
            merged_row["error"] = str(secondary_row.get("error") or primary_row.get("error") or "").strip()
            merged_rows.append(merged_row)
            overlay_count += 1
        else:
            merged_rows.append(primary_row)

    merged_index = index_meter_rows(merged_rows)
    for secondary_row in secondary_rows:
        meter_id = str(secondary_row.get("id") or secondary_row.get("meter_id") or "").strip()
        source_key = str(secondary_row.get("source_key") or "").strip()
        if (source_key and source_key in merged_index) or (meter_id and meter_id in merged_index):
            continue
        if not bool(secondary_row.get("visible_in_meter_center", True)):
            continue
        merged_row = dict(secondary_row)
        merged_row[f"_overlay_from_{overlay_name}"] = True
        merged_row["_overlay_reason"] = "primary_not_returned"
        merged_rows.append(merged_row)
        overlay_count += 1
        if source_key:
            merged_index[source_key] = merged_row
        if meter_id:
            merged_index[meter_id] = merged_row

    if callable(sort_meter_rows):
        merged_rows = sort_meter_rows(merged_rows)
    energy_display_mode = str(
        (primary_payload.get("dashboard_summary", {}) or {}).get("energy_display_mode")
        or (primary_payload.get("summary", {}) or {}).get("energy_display_mode")
        or (secondary_payload.get("dashboard_summary", {}) or {}).get("energy_display_mode")
        or "display"
    )
    rebuilt = rebuild_meter_summary_from_rows(
        merged_rows,
        energy_display_mode=energy_display_mode,
        filter_summary_rows=filter_summary_rows,
        serialize_type_counts=serialize_type_counts,
    )

    merged_payload = dict(primary_payload)
    merged_payload["meters"] = merged_rows
    merged_payload["trend_targets"] = build_target_rows(merged_rows) if callable(build_target_rows) else merged_payload.get("trend_targets", [])
    merged_payload["summary"] = dict(primary_payload.get("summary", {}) or {}, **rebuilt["summary"])
    merged_payload["dashboard_summary"] = dict(primary_payload.get("dashboard_summary", {}) or {}, **rebuilt["dashboard_summary"])
    merged_payload["data_source"] = data_source
    merged_payload["overlay_count"] = overlay_count
    if overlay_name == "local":
        merged_payload["local_overlay_count"] = overlay_count
    if overlay_name == "remote":
        merged_payload["remote_overlay_count"] = overlay_count
    fallback_reference = None
    secondary_reference = (secondary_payload.get("summary", {}) or {}).get("reference_meter")
    primary_reference = (primary_payload.get("summary", {}) or {}).get("reference_meter")
    if isinstance(primary_reference, dict):
        fallback_reference = primary_reference
    elif isinstance(secondary_reference, dict):
        fallback_reference = secondary_reference
    return apply_reference_comparison(merged_payload, fallback_reference)
