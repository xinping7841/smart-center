import math
import threading
import time
from collections import deque
from datetime import datetime


_HISTORY_LOCK = threading.Lock()
_HISTORY_MAX_POINTS = 240
_HISTORY_MAX_AGE_SEC = 2 * 60 * 60
_MIN_SAMPLE_INTERVAL_SEC = 30.0
_MIN_TREND_WINDOW_SEC = 3 * 60
_RECENT_TREND_WINDOW_SEC = 45 * 60
_MIN_MEANINGFUL_SLOPE_PER_MIN = 1.5
_ENV_LUX_HISTORY = {}


def _to_float(value):
    try:
        num = float(value)
    except Exception:
        return None
    if math.isnan(num) or math.isinf(num):
        return None
    return num


def _to_timestamp(value):
    if isinstance(value, datetime):
        return value.timestamp()
    text = str(value or "").strip()
    if not text:
        return time.time()
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except Exception:
        return time.time()


def record_env_lux_sample(device_id, lux, sampled_at=None, online=True):
    key = str(device_id or "").strip()
    lux_value = _to_float(lux)
    if not key or lux_value is None or online is False:
        return False

    sample_ts = _to_timestamp(sampled_at)
    sample = {"ts": sample_ts, "lux": round(lux_value, 2)}

    with _HISTORY_LOCK:
        history = _ENV_LUX_HISTORY.setdefault(key, deque(maxlen=_HISTORY_MAX_POINTS))
        cutoff_ts = sample_ts - _HISTORY_MAX_AGE_SEC
        while history and float(history[0].get("ts", 0) or 0) < cutoff_ts:
            history.popleft()

        if history:
            last_ts = float(history[-1].get("ts", 0) or 0)
            if sample_ts <= last_ts:
                sample["ts"] = last_ts + 0.001
                sample_ts = sample["ts"]
            if (sample_ts - last_ts) < _MIN_SAMPLE_INTERVAL_SEC:
                history[-1] = sample
                return True

        history.append(sample)
        return True


def get_env_lux_history(device_id, limit=None):
    key = str(device_id or "").strip()
    with _HISTORY_LOCK:
        items = list(_ENV_LUX_HISTORY.get(key, ()))
    if limit is not None:
        try:
            limit_num = max(int(limit), 0)
        except Exception:
            limit_num = 0
        if limit_num:
            items = items[-limit_num:]
    return [
        {
            "ts": datetime.fromtimestamp(float(item.get("ts", 0) or 0)).isoformat(),
            "lux": round(float(item.get("lux", 0) or 0), 2),
        }
        for item in items
    ]


def _select_trend_points(history, now_ts):
    recent_points = [item for item in history if now_ts - float(item.get("ts", 0) or 0) <= _RECENT_TREND_WINDOW_SEC]
    if len(recent_points) >= 4:
        return recent_points
    return history


def _calculate_linear_slope(points):
    if len(points) < 2:
        return None

    base_ts = float(points[0].get("ts", 0) or 0)
    xs = [float(item.get("ts", 0) or 0) - base_ts for item in points]
    ys = [float(item.get("lux", 0) or 0) for item in points]
    count = len(xs)
    mean_x = sum(xs) / count
    mean_y = sum(ys) / count
    denominator = sum((x - mean_x) ** 2 for x in xs)
    if denominator <= 1e-9:
        return None
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    return numerator / denominator


def build_env_lux_trend(device_id, current_lux=None, threshold=None, op="<"):
    key = str(device_id or "").strip()
    with _HISTORY_LOCK:
        history = list(_ENV_LUX_HISTORY.get(key, ()))

    now_ts = time.time()
    if history:
        cutoff_ts = now_ts - _HISTORY_MAX_AGE_SEC
        history = [item for item in history if float(item.get("ts", 0) or 0) >= cutoff_ts]

    current_value = _to_float(current_lux)
    if current_value is None and history:
        current_value = _to_float(history[-1].get("lux"))

    threshold_value = _to_float(threshold)
    if len(history) < 2:
        return {
            "available": False,
            "direction": "unknown",
            "sample_count": len(history),
            "span_sec": 0.0,
            "delta_lux": None,
            "slope_lux_per_min": None,
            "estimate_to_threshold_sec": 0.0 if threshold_value is not None and current_value is not None and (
                (op in {"<", "<="} and current_value <= threshold_value)
                or (op in {">", ">="} and current_value >= threshold_value)
            ) else None,
            "predicted_cross_at": datetime.fromtimestamp(now_ts).isoformat()
            if threshold_value is not None and current_value is not None and (
                (op in {"<", "<="} and current_value <= threshold_value)
                or (op in {">", ">="} and current_value >= threshold_value)
            )
            else None,
            "confidence": 0.0,
        }

    points = _select_trend_points(history, now_ts)
    span_sec = max(float(points[-1].get("ts", 0) or 0) - float(points[0].get("ts", 0) or 0), 0.0)
    slope_per_sec = _calculate_linear_slope(points)
    slope_per_min = slope_per_sec * 60.0 if slope_per_sec is not None else None
    delta_lux = float(points[-1].get("lux", 0) or 0) - float(points[0].get("lux", 0) or 0)
    abs_slope = abs(slope_per_min or 0.0)

    if slope_per_min is None or span_sec < _MIN_TREND_WINDOW_SEC:
        direction = "unknown"
    elif abs_slope < _MIN_MEANINGFUL_SLOPE_PER_MIN:
        direction = "stable"
    elif slope_per_min < 0:
        direction = "falling"
    else:
        direction = "rising"

    eta_sec = None
    if threshold_value is not None and current_value is not None and slope_per_sec is not None:
        if op in {"<", "<="}:
            if current_value <= threshold_value:
                eta_sec = 0.0
            elif direction == "falling":
                eta_sec = max((current_value - threshold_value) / abs(slope_per_sec), 0.0)
        elif op in {">", ">="}:
            if current_value >= threshold_value:
                eta_sec = 0.0
            elif direction == "rising":
                eta_sec = max((threshold_value - current_value) / max(slope_per_sec, 1e-9), 0.0)

    predicted_cross_at = None
    if eta_sec is not None:
        predicted_cross_at = datetime.fromtimestamp(now_ts + eta_sec).isoformat()

    confidence = min(
        1.0,
        (
            min(len(points) / 12.0, 1.0) * 0.45
            + min(span_sec / (20 * 60.0), 1.0) * 0.45
            + (0.10 if direction != "unknown" else 0.0)
        ),
    )

    return {
        "available": True,
        "direction": direction,
        "sample_count": len(points),
        "span_sec": round(span_sec, 1),
        "delta_lux": round(delta_lux, 2),
        "slope_lux_per_min": round(slope_per_min, 2) if slope_per_min is not None else None,
        "estimate_to_threshold_sec": round(eta_sec, 1) if eta_sec is not None else None,
        "predicted_cross_at": predicted_cross_at,
        "confidence": round(confidence, 3),
    }
