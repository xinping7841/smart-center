import math
import os
import re
import socket
import threading
import time
from typing import Dict, List, Optional, Tuple


Q1_COMMAND = "Q1\r"
Q6_COMMAND = "Q6\r"
WA_COMMAND = "WA\r"

_SHUTDOWN_DELAY_RE = re.compile(r"^(?:\.[2-9]|10|0[1-9])$")

_HEX_TOKEN_RE = re.compile(r"^[0-9A-Fa-f]+$")
_Q6_PACKED_CODE_RE = re.compile(r"^[0-9]{2,}$")
_LAST_GOOD_CACHE: Dict[str, Dict[str, object]] = {}
_LAST_GOOD_LOCK = threading.Lock()


SYSTEM_MODE_MAP = {
    "0": "上电初始化",
    "1": "待机",
    "2": "旁路",
    "3": "在线",
    "4": "电池",
    "5": "电池测试",
    "6": "故障",
    "7": "变频",
    "8": "高效",
    "9": "关机",
}

BATTERY_TEST_MAP = {
    "0": "空闲",
    "1": "测试中",
    "2": "测试正常",
    "3": "测试异常",
    "4": "不可测试",
    "5": "测试取消",
}

Q1_STATUS_BITS = [
    ("mains_abnormal", "市电异常"),
    ("battery_low", "电池低压"),
    ("bypass_active", "旁路输出"),
    ("ups_fault", "UPS故障"),
    ("offline_type", "后备机"),
    ("testing", "测试进行中"),
    ("shutdown_active", "关机激活"),
    ("buzzer_active", "蜂鸣器激活"),
]

WA_STATUS_BITS = [
    ("mains_abnormal", "市电异常"),
    ("battery_low", "电池低压"),
    ("bypass_active", "旁路模式"),
    ("ups_fault", "UPS故障"),
    ("offline_type", "后备机"),
    ("testing", "测试进行中"),
    ("reserved_1", "保留1"),
    ("reserved_0", "保留0"),
]

FAULT_TABLE = {
    0: "系统无故障",
    1: "BUS 软启动超时",
    2: "BUS 高压故障",
    3: "BUS 低压故障",
    4: "BUS 不平衡故障",
    5: "BUS 短路故障",
    6: "逆变软启动超时",
    7: "逆变电压高压故障",
    8: "逆变电压低压故障",
    9: "输出电压短路",
    10: "R 相逆变电压短路",
    11: "S 相逆变电压短路",
    12: "T 相逆变电压短路",
    13: "RS 相线电压短路",
    14: "ST 相线电压短路",
    15: "TR 相线电压短路",
    16: "负功故障",
    17: "R 相负功故障",
    18: "S 相负功故障",
    19: "T 相负功故障",
    20: "三相总负功故障",
    21: "不均流故障",
    22: "过载故障",
    23: "过温故障",
    24: "INV 继电器无法闭合",
    25: "INV 继电器粘连",
    26: "市电输入 SCR 故障",
    27: "电池输入 SCR 故障",
    28: "旁路输入 SCR 故障",
    29: "整流器故障",
    30: "输入过流故障",
    31: "输入输出接线错误",
    32: "通讯线未接",
    33: "主机线故障",
    34: "CAN 通讯线故障",
    35: "同步信号线故障",
    36: "工作电源故障",
    37: "所有风扇故障",
    38: "DSP 异常",
    39: "充电器输出软启动超时",
    40: "UPS 模块全故障",
    41: "市电输入 NTC 开路故障",
    42: "市电输入 Fuse 开路故障",
    43: "输出负载不平衡故障",
    44: "输入不一致故障",
    45: "EEPROM 数据丢失",
    46: "市电支援失效",
    47: "电源失效",
    48: "系统过容",
    49: "ADS7869 异常",
    50: "静态开关硬件故障",
    51: "并机模式输出断路器断开",
    52: "R 相 BUS Fuse 故障",
    53: "S 相 BUS Fuse 故障",
    54: "T 相 BUS Fuse 故障",
    55: "NTC 故障",
    56: "并机线故障",
    57: "电池故障",
    58: "频繁过流故障",
    59: "电池过充故障",
    60: "EPO 故障",
}

WARNING_TABLE = {
    0: "内部告警",
    1: "EPO 开关未接",
    2: "模块未锁",
    3: "市电异常",
    4: "输入中线丢失",
    5: "市电相序错误",
    6: "L/N 反接",
    7: "旁路异常",
    8: "旁路相序错误",
    9: "电池未接",
    10: "电池电压低告警",
    11: "电池过充",
    12: "电池反接",
    13: "过载预警",
    14: "过载告警",
    15: "风扇故障",
    16: "维修旁路盖板打开",
    17: "充电器故障",
    18: "物理位置错误",
    19: "不满足开机条件",
    20: "冗余丢失",
    21: "模块未插稳",
    22: "电池维护时间到",
    23: "巡检维护时间到",
    24: "过保维护时间到",
    25: "温度过低",
    26: "温度过高",
    27: "电池过温",
    28: "风扇维护时间到",
    29: "BUS 电容维护时间到",
    30: "系统过容",
    31: "高优先级外部告警",
}


def _safe_float(value: object, default: Optional[float] = None) -> Optional[float]:
    try:
        if value in (None, "", "---", "---.-"):
            return default
        return float(value)
    except Exception:
        return default


def _safe_int(value: object, default: int = 0) -> int:
    number = _safe_float(value, None)
    if number is None:
        return default
    try:
        return int(number)
    except Exception:
        return default


def _raw_preview(raw: Optional[str], limit: int = 120) -> str:
    text = str(raw or "").replace("\r", "").replace("\n", " ").strip()
    if not text:
        return "--"
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _split_response(raw: str) -> List[str]:
    text = str(raw or "").strip()
    text = text.replace("\r", " ").replace("(", " ").replace(")", " ")
    return [part.strip() for part in text.split() if part.strip()]


def _split_frames(raw: str) -> List[str]:
    text = str(raw or "").replace("\n", "\r")
    return [chunk.strip() for chunk in text.split("\r") if chunk and chunk.strip()]


def _candidate_token_lists(raw: str) -> List[List[str]]:
    candidates: List[List[str]] = []
    seen = set()
    for frame in _split_frames(raw):
        tokens = _split_response(frame)
        if not tokens:
            continue
        key = tuple(tokens)
        if key in seen:
            continue
        seen.add(key)
        candidates.append(tokens)
    merged = _split_response(raw)
    if merged:
        key = tuple(merged)
        if key not in seen:
            candidates.append(merged)
    return candidates


def _is_bit_field_text(value: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    return all(ch in "01" for ch in text)


def _is_hex_text(value: object) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    return bool(_HEX_TOKEN_RE.fullmatch(text))


def _extract_known_reply(raw: str) -> str:
    chunks = _split_frames(raw)
    if not chunks:
        return ""
    for idx in range(len(chunks) - 1, -1, -1):
        chunk = chunks[idx]
        if not chunk.startswith("("):
            continue
        parts = _split_response(chunk)
        if len(parts) >= 8:
            return chunk
    return chunks[-1]


def _score_q1_window(tokens: List[str]) -> int:
    if len(tokens) < 8:
        return -999
    if not _is_bit_field_text(tokens[7]):
        return -999
    score = 0
    ranges = [
        (0.0, 650.0),   # input_voltage
        (0.0, 650.0),   # transfer_voltage
        (0.0, 650.0),   # output_voltage
        (0.0, 150.0),   # load_percent
        (30.0, 80.0),   # input_frequency
        (0.0, 120.0),   # battery_voltage_like
        (-40.0, 120.0), # temperature
    ]
    for idx, (minimum, maximum) in enumerate(ranges):
        val = _safe_float(tokens[idx], None)
        if val is None:
            score -= 8
            continue
        score += 4
        if minimum <= val <= maximum:
            score += 4
        elif idx == 4 and 0 <= val <= 120:
            score += 1
        else:
            score -= 4
    score += 20
    return score


def _score_q6_window(tokens: List[str]) -> int:
    normalized = _normalize_q6_fields(tokens)
    if not normalized:
        return -999
    tokens = normalized
    score = 0
    ranges = {
        0: (0.0, 650.0),
        1: (0.0, 650.0),
        2: (0.0, 650.0),
        3: (30.0, 80.0),
        4: (0.0, 650.0),
        5: (0.0, 650.0),
        6: (0.0, 650.0),
        7: (30.0, 80.0),
        8: (0.0, 500.0),
        9: (0.0, 500.0),
        10: (0.0, 500.0),
        11: (-800.0, 800.0),
        12: (-800.0, 800.0),
        13: (-40.0, 120.0),
        14: (0.0, 200000.0),
        15: (0.0, 100.0),
    }
    for idx, (minimum, maximum) in ranges.items():
        val = _safe_float(tokens[idx], None)
        if val is None:
            score -= 6
            continue
        score += 3
        if minimum <= val <= maximum:
            score += 3
        else:
            score -= 3

    kb = str(tokens[16])
    mode_key = kb[:1]
    battery_test_key = kb[1:2]
    score += 10 if mode_key in SYSTEM_MODE_MAP else -6
    score += 8 if battery_test_key in BATTERY_TEST_MAP else -4
    score += 4 if _is_hex_text(tokens[17]) else -2
    score += 4 if _is_hex_text(tokens[18]) else -2
    yo = str(tokens[19] or "")
    if yo:
        score += 4 if len(yo) >= 2 and yo[0] in {"0", "1"} and yo[1] in {"0", "1"} else -2
    return score


def _score_wa_window(tokens: List[str]) -> int:
    if len(tokens) < 13:
        return -999
    if not _is_bit_field_text(tokens[12]):
        return -999
    score = 0
    for idx in range(0, 11):
        val = _safe_float(tokens[idx], None)
        if val is None:
            score -= 4
            continue
        score += 2
        if idx <= 7 and abs(val) <= 1000:
            score += 1
        if idx >= 8 and 0 <= val <= 500:
            score += 2
    total_power_val = _safe_float(tokens[6], None)
    if total_power_val is None:
        score -= 6
    elif abs(total_power_val) <= 200:
        score += 6
    elif abs(total_power_val) <= 1000:
        score += 2
    else:
        score -= 8

    load_val = _safe_float(tokens[11], None)
    if load_val is None:
        score -= 8
    elif 0 <= load_val <= 130:
        score += 8
    elif 0 <= load_val <= 200:
        score += 3
    else:
        score -= 8

    score += 18
    return score


def _select_best_window(raw: str, size: int, score_fn, *, min_score: int, cmd_name: str) -> List[str]:
    best_tokens: Optional[List[str]] = None
    best_score = -10_000
    for tokens in _candidate_token_lists(raw):
        if len(tokens) < size:
            continue
        for start in range(0, len(tokens) - size + 1):
            window = tokens[start : start + size]
            score = int(score_fn(window))
            if score > best_score:
                best_score = score
                best_tokens = window
    if best_tokens is None:
        raise ValueError(f"{cmd_name} 响应字段不足")
    if best_score < min_score:
        raise ValueError(f"{cmd_name} 响应格式异常(score={best_score})")
    return best_tokens


def _select_best_q6_fields(raw: str, *, min_score: int = 30) -> List[str]:
    best_tokens: Optional[List[str]] = None
    best_score = -10_000
    for tokens in _candidate_token_lists(raw):
        if len(tokens) < 20:
            continue
        for start in range(0, len(tokens) - 20 + 1):
            window = tokens[start : start + 22]
            score = int(_score_q6_window(window))
            if score > best_score:
                best_score = score
                best_tokens = _normalize_q6_fields(window)
    if best_tokens is None:
        raise ValueError("Q6 响应字段不足")
    if best_score < min_score:
        raise ValueError(f"Q6 响应格式异常(score={best_score})")
    return best_tokens


def _resolve_supply_state(system_mode_code, mains_abnormal=False, is_bypass=False):
    mode = str(system_mode_code or "").strip()
    if is_bypass or mode == "2":
        return "旁路供电"
    if mode == "4":
        return "电池供电"
    if mode == "8":
        return "高效供电"
    if mains_abnormal:
        return "逆变供电"
    if mode == "3":
        return "市电供电"
    if mode == "1":
        return "待机"
    if mode == "6":
        return "故障"
    return SYSTEM_MODE_MAP.get(mode, f"模式 {mode}") if mode else "未知"


def _decode_status_bits(bit_text: str, labels: List[Tuple[str, str]]) -> Dict[str, object]:
    text = str(bit_text or "").strip()
    # 某些设备会在状态位字段出现异常字符，兜底为全 0，避免误判。
    if not _is_bit_field_text(text):
        text = "0" * len(labels)
    padded = text[: len(labels)].ljust(len(labels), "0")
    flags: Dict[str, object] = {}
    active: List[str] = []
    for idx, (key, label) in enumerate(labels):
        is_active = padded[idx] == "1"
        flags[key] = is_active
        if is_active and not key.startswith("reserved"):
            active.append(label)
    flags["raw"] = padded
    flags["active_labels"] = active
    return flags


def _hex_ascii_bits_to_indices(hex_text: str) -> List[int]:
    text = str(hex_text or "").strip()
    if not text:
        return []
    try:
        value = int(text, 16)
    except Exception:
        return []
    active = []
    for bit in range(32):
        if value & (1 << bit):
            active.append(bit)
    return active


def _hex_ascii_fault_container_indices(hex_text: str) -> List[int]:
    """Q6 fault field is four fault containers, each encoded as one hex byte."""
    text = str(hex_text or "").strip()
    if not _is_hex_text(text):
        return []
    if len(text) % 2:
        text = text.zfill(len(text) + 1)
    if len(text) > 8:
        text = text[-8:]
    if len(text) < 8:
        text = text.zfill(8)
    indexes: List[int] = []
    for idx in range(0, 8, 2):
        try:
            value = int(text[idx : idx + 2], 16)
        except Exception:
            continue
        if value == 0:
            continue
        if value not in indexes:
            indexes.append(value)
    return indexes


def _decode_faults(hex_text: str) -> List[str]:
    indexes = _hex_ascii_fault_container_indices(hex_text)
    if not indexes:
        return []
    return [FAULT_TABLE.get(idx, f"故障码 {idx}") for idx in indexes]


def _decode_warnings(hex_text: str) -> List[str]:
    indexes = _hex_ascii_bits_to_indices(hex_text)
    if not indexes:
        return []
    return [WARNING_TABLE.get(idx, f"告警位 {idx}") for idx in indexes]


def _normalize_q6_fields(tokens: List[str]) -> Optional[List[str]]:
    """Normalize Q6 replies to the document layout.

    The vendor protocol defines the tail fields as packed ASCII tokens:
    ``KB`` for system mode and battery-test state, and ``YO`` for transformer
    type and LCD output-voltage mode. Some serial gateways can split those
    packed fields, so this function accepts both packed and split forms and
    returns the canonical 20-field layout.
    """
    if len(tokens) < 20:
        return None
    head = list(tokens[:16])
    tail = list(tokens[16:])
    if not tail:
        return None

    kb = str(tail[0] or "").strip()
    offset = 1
    if len(kb) >= 2 and _Q6_PACKED_CODE_RE.fullmatch(kb):
        kb = kb[:2]
    elif len(kb) == 1 and len(tail) >= 2:
        b_code = str(tail[1] or "").strip()
        if len(b_code) >= 1 and b_code[:1].isdigit():
            kb = f"{kb[:1]}{b_code[:1]}"
            offset = 2
        else:
            return None
    else:
        return None

    if len(tail) <= offset + 1:
        return None
    fault_raw = str(tail[offset] or "").strip()
    warning_raw = str(tail[offset + 1] or "").strip()
    if not (_is_hex_text(fault_raw) and _is_hex_text(warning_raw)):
        return None
    offset += 2

    yo = ""
    if len(tail) > offset:
        yo_token = str(tail[offset] or "").strip()
        if len(yo_token) >= 2 and all(ch in "01" for ch in yo_token[:2]):
            yo = yo_token[:2]
        elif len(yo_token) >= 1 and yo_token[:1] in {"0", "1"}:
            next_token = str(tail[offset + 1] or "").strip() if len(tail) > offset + 1 else ""
            if next_token[:1] in {"0", "1"}:
                yo = f"{yo_token[:1]}{next_token[:1]}"
            else:
                yo = yo_token[:1]

    return head + [kb, fault_raw, warning_raw, yo]


def _display_voltage_kind(output_mode_code: str) -> str:
    if output_mode_code == "1":
        return "相电压"
    if output_mode_code == "0":
        return "线电压"
    return "--"


def _transformer_type_text(transformer_code: str) -> str:
    if transformer_code == "1":
        return "Y型"
    if transformer_code == "0":
        return "Δ型"
    return "--"


def _derive_output_voltage_sets(fields: List[str], output_mode_code: str) -> Dict[str, object]:
    reported = [_safe_float(fields[idx]) for idx in (4, 5, 6)]
    if output_mode_code == "1":
        phase = reported
        line = [round(value * math.sqrt(3), 3) if value is not None else None for value in reported]
    elif output_mode_code == "0":
        line = reported
        phase = [round(value / math.sqrt(3), 3) if value is not None else None for value in reported]
    else:
        phase = [None, None, None]
        line = [None, None, None]
    return {
        "output_reported_voltage_kind": _display_voltage_kind(output_mode_code),
        "output_phase_voltage_r": phase[0],
        "output_phase_voltage_s": phase[1],
        "output_phase_voltage_t": phase[2],
        "output_line_voltage_r": line[0],
        "output_line_voltage_s": line[1],
        "output_line_voltage_t": line[2],
    }


def _normalize_shutdown_delay(delay_text: object) -> str:
    text = str(delay_text or "").strip()
    if not text:
        return ".3"
    if not _SHUTDOWN_DELAY_RE.fullmatch(text):
        raise ValueError("UPS 关机延时仅支持 .2-.9、01-10（单位：分钟）")
    return text


def _estimate_payload_quality(*, q1_ok: bool, q6_ok: bool, wa_ok: bool, fallback_used: Dict[str, bool], query_warnings: List[str]) -> Dict[str, object]:
    score = 100
    details: List[str] = []
    if not q1_ok:
        score -= 55
        details.append("Q1 不可用")
    if not q6_ok:
        score -= 22
        details.append("Q6 不可用")
    if not wa_ok:
        score -= 18
        details.append("WA 不可用")
    if fallback_used.get("q1"):
        score -= 30
        details.append("Q1 使用回退缓存")
    if fallback_used.get("q6"):
        score -= 12
        details.append("Q6 使用回退缓存")
    if fallback_used.get("wa"):
        score -= 10
        details.append("WA 使用回退缓存")
    warn_penalty = min(len(query_warnings or []), 6) * 4
    score -= warn_penalty
    score = max(0, min(100, score))
    if score >= 85:
        level = "high"
        text = "高"
    elif score >= 60:
        level = "medium"
        text = "中"
    else:
        level = "low"
        text = "低"
    return {
        "score": score,
        "level": level,
        "text": text,
        "details": details,
    }


def parse_q1_response(raw: str) -> Dict[str, object]:
    parts = _select_best_window(raw, 8, _score_q1_window, min_score=18, cmd_name="Q1")
    battery_cell_voltage = _safe_float(parts[5])
    battery_12v_block_voltage = battery_cell_voltage * 6 if battery_cell_voltage is not None else None
    status_flags = _decode_status_bits(parts[7], Q1_STATUS_BITS)
    return {
        "input_voltage": _safe_float(parts[0]),
        "last_transfer_voltage": _safe_float(parts[1]),
        "output_voltage": _safe_float(parts[2]),
        "load_percent": _safe_float(parts[3]),
        "input_frequency": _safe_float(parts[4]),
        "battery_cell_voltage": battery_cell_voltage,
        "battery_12v_block_voltage": battery_12v_block_voltage,
        "battery_pack_voltage": battery_12v_block_voltage,
        "temperature": _safe_float(parts[6]),
        "status_bits": status_flags,
    }


def parse_q6_response(raw: str) -> Dict[str, object]:
    parts = _select_best_q6_fields(raw, min_score=30)
    fields = _normalize_q6_fields(parts)
    if not fields:
        raise ValueError("Q6 响应字段异常，无法规范化")
    kb = str(fields[16] or "").strip()
    mode_key = kb[:1]
    battery_test_key = kb[1:2]
    fault_raw = str(fields[17] or "").strip()
    warning_raw = str(fields[18] or "").strip()
    yo = str(fields[19] or "").strip()
    transformer_code = yo[:1] if len(yo) >= 1 else ""
    output_mode_code = yo[1:2] if len(yo) >= 2 else ""
    payload = {
        "input_voltage_r": _safe_float(fields[0]),
        "input_voltage_s": _safe_float(fields[1]),
        "input_voltage_t": _safe_float(fields[2]),
        "input_frequency": _safe_float(fields[3]),
        "output_voltage_r": _safe_float(fields[4]),
        "output_voltage_s": _safe_float(fields[5]),
        "output_voltage_t": _safe_float(fields[6]),
        "output_frequency": _safe_float(fields[7]),
        "output_current_r": _safe_float(fields[8]),
        "output_current_s": _safe_float(fields[9]),
        "output_current_t": _safe_float(fields[10]),
        "battery_positive_voltage": _safe_float(fields[11]),
        "battery_negative_voltage": _safe_float(fields[12]),
        "temperature": _safe_float(fields[13]),
        "backup_time_seconds": _safe_int(fields[14], 0),
        "battery_capacity_percent": _safe_float(fields[15]),
        "kb_code_raw": kb,
        "system_mode_code": mode_key,
        "system_mode_text": SYSTEM_MODE_MAP.get(mode_key, f"模式 {mode_key}"),
        "battery_test_code": battery_test_key,
        "battery_test_text": BATTERY_TEST_MAP.get(battery_test_key, f"状态 {battery_test_key}"),
        "fault_code_raw": fault_raw,
        "fault_labels": _decode_faults(fault_raw),
        "warning_code_raw": warning_raw,
        "warning_labels": _decode_warnings(warning_raw),
        "yo_code_raw": yo,
        "transformer_type_code": transformer_code,
        "transformer_type": _transformer_type_text(transformer_code),
        "output_voltage_display_mode_code": output_mode_code,
        "output_voltage_display_mode": _display_voltage_kind(output_mode_code),
    }
    payload.update(_derive_output_voltage_sets(fields, output_mode_code))
    return payload


def parse_wa_response(raw: str) -> Dict[str, object]:
    candidate = _select_best_window(raw, 13, _score_wa_window, min_score=18, cmd_name="WA")

    status_flags = _decode_status_bits(candidate[12], WA_STATUS_BITS)
    return {
        "real_power_r_kw": _safe_float(candidate[0]),
        "real_power_s_kw": _safe_float(candidate[1]),
        "real_power_t_kw": _safe_float(candidate[2]),
        "apparent_power_r_kva": _safe_float(candidate[3]),
        "apparent_power_s_kva": _safe_float(candidate[4]),
        "apparent_power_t_kva": _safe_float(candidate[5]),
        "total_real_power_kw": _safe_float(candidate[6]),
        "total_apparent_power_kva": _safe_float(candidate[7]),
        "output_current_r": _safe_float(candidate[8]),
        "output_current_s": _safe_float(candidate[9]),
        "output_current_t": _safe_float(candidate[10]),
        "load_percent": _safe_float(candidate[11]),
        "status_bits": status_flags,
    }


class UpsDriver:
    def __init__(self, cfg: Dict[str, object]):
        self.cfg = cfg or {}
        self.timeout = max(float(self.cfg.get("timeout_sec", 2.0) or 2.0), 0.5)
        self.query_retries = max(int(self.cfg.get("query_retries", 4) or 4), 0)
        self.retry_backoff_ms = max(int(self.cfg.get("retry_backoff_ms", 200) or 200), 0)
        self.frame_settle_ms = max(int(self.cfg.get("frame_settle_ms", 120) or 120), 20)
        self.response_window_ms = max(int(self.cfg.get("response_window_ms", 1300) or 1300), 200)
        self.require_parenthesized_frame = bool(self.cfg.get("require_parenthesized_frame", True))
        self.command_gap_ms = max(int(self.cfg.get("command_gap_ms", 80) or 80), 0)
        self.fallback_cache_ttl_sec = max(float(self.cfg.get("fallback_cache_ttl_sec", 600.0) or 600.0), 5.0)

    def _cache_key(self) -> str:
        ups_id = str(self.cfg.get("id") or self.cfg.get("name") or "").strip()
        comm_mode = str(self.cfg.get("comm_mode", "TCP")).upper()
        if comm_mode == "COM":
            endpoint = str(self.cfg.get("com_port", "COM1")).strip()
        else:
            endpoint = f"{str(self.cfg.get('ip', '')).strip()}:{int(self.cfg.get('port', 23) or 23)}"
        return f"{ups_id}|{comm_mode}|{endpoint}"

    def _load_last_good(self) -> Dict[str, object]:
        key = self._cache_key()
        with _LAST_GOOD_LOCK:
            return dict(_LAST_GOOD_CACHE.get(key, {}) or {})

    def _save_last_good(self, payload: Dict[str, object]) -> None:
        key = self._cache_key()
        with _LAST_GOOD_LOCK:
            _LAST_GOOD_CACHE[key] = dict(payload or {})

    def _query_window_sec(self) -> float:
        return max(self.timeout + (self.response_window_ms / 1000.0), self.timeout + 0.25)

    def _tail_settle_sec(self) -> float:
        return max(self.frame_settle_ms / 1000.0, 0.02)

    @staticmethod
    def _pick_frame_text(text: str, *, require_parenthesized: bool) -> str:
        frames = _split_frames(text)
        if not frames:
            return ""
        if require_parenthesized:
            for frame in reversed(frames):
                if str(frame).lstrip().startswith("("):
                    return frame
        return frames[-1]

    def _communicate_tcp(self, payload: str) -> str:
        ip = str(self.cfg.get("ip", "")).strip()
        port = int(self.cfg.get("port", 23) or 23)
        if not ip:
            raise ValueError("UPS 未配置 IP 地址")
        with socket.create_connection((ip, port), timeout=self.timeout) as sock:
            sock.settimeout(self.timeout)
            sock.sendall(payload.encode("ascii"))
            data = b""
            start = time.monotonic()
            got_delimiter = False
            while time.monotonic() - start < self._query_window_sec():
                try:
                    chunk = sock.recv(4096)
                except socket.timeout:
                    break
                if not chunk:
                    break
                data += chunk
                if b"\r" in chunk:
                    got_delimiter = True
                    # 把 socket timeout 降到短等待，尽量吸收同一批次的后续帧，减少截断/串包影响。
                    sock.settimeout(self._tail_settle_sec())
            text = data.decode("ascii", errors="ignore")
            frame = self._pick_frame_text(text, require_parenthesized=self.require_parenthesized_frame)
            if got_delimiter and frame:
                return frame
        if not str(text or "").strip():
            raise TimeoutError("UPS 无响应")
        frame = self._pick_frame_text(text, require_parenthesized=self.require_parenthesized_frame)
        return frame or text

    def _communicate_com(self, payload: str) -> str:
        try:
            import serial
        except Exception as exc:
            raise RuntimeError(f"缺少 pyserial: {exc}") from exc
        com_port = str(self.cfg.get("com_port", "COM1")).strip()
        baudrate = int(self.cfg.get("baudrate", 2400) or 2400)
        data_bits = int(self.cfg.get("data_bits", 8) or 8)
        stop_bits = int(self.cfg.get("stop_bits", 1) or 1)
        parity_name = str(self.cfg.get("parity", "NONE")).upper()
        parity_map = {
            "NONE": serial.PARITY_NONE,
            "ODD": serial.PARITY_ODD,
            "EVEN": serial.PARITY_EVEN,
        }
        parity = parity_map.get(parity_name, serial.PARITY_NONE)
        with serial.Serial(
            port=com_port,
            baudrate=baudrate,
            bytesize=data_bits,
            parity=parity,
            stopbits=stop_bits,
            timeout=self.timeout,
        ) as ser:
            ser.reset_input_buffer()
            ser.write(payload.encode("ascii"))
            ser.flush()
            data = b""
            start = time.monotonic()
            while time.monotonic() - start < self._query_window_sec():
                chunk = ser.read(512)
                if not chunk:
                    break
                data += chunk
                if b"\r" in chunk:
                    tail_start = time.monotonic()
                    while time.monotonic() - tail_start < self._tail_settle_sec():
                        extra = ser.read(512)
                        if not extra:
                            break
                        data += extra
                        tail_start = time.monotonic()
                    break
        text = data.decode("ascii", errors="ignore")
        if not str(text or "").strip():
            raise TimeoutError("UPS 无响应")
        frame = self._pick_frame_text(text, require_parenthesized=self.require_parenthesized_frame)
        return frame or text

    def query_raw(self, payload: str) -> str:
        comm_mode = str(self.cfg.get("comm_mode", "TCP")).upper()
        if comm_mode == "COM":
            return self._communicate_com(payload)
        return self._communicate_tcp(payload)

    def _safe_query(self, payload: str, *, validator=None) -> Tuple[Optional[str], Optional[Exception]]:
        attempts = self.query_retries + 1
        last_exc: Optional[Exception] = None
        last_raw: Optional[str] = None
        for idx in range(attempts):
            try:
                raw = self.query_raw(payload)
                if raw and str(raw).strip():
                    last_raw = raw
                    if validator is not None:
                        try:
                            validator(raw)
                        except Exception as validate_exc:
                            last_exc = validate_exc
                            if idx < attempts - 1:
                                gap = (self.command_gap_ms + (idx * self.retry_backoff_ms)) / 1000.0
                                if gap > 0:
                                    time.sleep(gap)
                                continue
                            return last_raw, last_exc
                    return raw, None
                last_exc = TimeoutError("UPS 返回空帧")
            except Exception as exc:
                last_exc = exc
            if idx < attempts - 1:
                gap = (self.command_gap_ms + (idx * self.retry_backoff_ms)) / 1000.0
                if gap > 0:
                    time.sleep(gap)
        return last_raw, (last_exc or TimeoutError("UPS 查询失败"))

    def get_status(self) -> Dict[str, object]:
        request_started_at = time.time()
        q1_raw, q1_error = self._safe_query(Q1_COMMAND, validator=parse_q1_response)
        if self.command_gap_ms > 0:
            time.sleep(self.command_gap_ms / 1000.0)
        q6_raw, q6_error = self._safe_query(Q6_COMMAND, validator=parse_q6_response)
        if self.command_gap_ms > 0:
            time.sleep(self.command_gap_ms / 1000.0)
        wa_raw, wa_error = self._safe_query(WA_COMMAND, validator=parse_wa_response)

        q1: Dict[str, object] = {}
        q6: Dict[str, object] = {}
        wa: Dict[str, object] = {}
        query_warnings: List[str] = []
        protocol_support = {"q1": False, "q6": False, "wa": False}
        fallback_used = {"q1": False, "q6": False, "wa": False}

        if q1_raw:
            try:
                q1 = parse_q1_response(q1_raw)
                protocol_support["q1"] = True
            except Exception as exc:
                q1_error = exc

        if q6_raw:
            try:
                q6 = parse_q6_response(q6_raw)
                protocol_support["q6"] = True
            except Exception as exc:
                q6_error = exc
        if wa_raw:
            try:
                wa = parse_wa_response(wa_raw)
                protocol_support["wa"] = True
            except Exception as exc:
                wa_error = exc

        cache = self._load_last_good()
        cached_at = _safe_float(cache.get("saved_at"), None)
        cache_age_sec = max(0.0, time.time() - cached_at) if cached_at is not None else None
        can_fallback = cache_age_sec is not None and cache_age_sec <= self.fallback_cache_ttl_sec

        if not q1 and can_fallback and isinstance(cache.get("q1"), dict) and cache.get("q1"):
            q1 = dict(cache.get("q1") or {})
            fallback_used["q1"] = True
            query_warnings.append(f"Q1 已回退到最近有效值（约 {int(cache_age_sec)}s 前）")
        if not q6 and can_fallback and isinstance(cache.get("q6"), dict) and cache.get("q6"):
            q6 = dict(cache.get("q6") or {})
            fallback_used["q6"] = True
            query_warnings.append(f"Q6 已回退到最近有效值（约 {int(cache_age_sec)}s 前）")
        if not wa and can_fallback and isinstance(cache.get("wa"), dict) and cache.get("wa"):
            wa = dict(cache.get("wa") or {})
            fallback_used["wa"] = True
            query_warnings.append(f"WA 已回退到最近有效值（约 {int(cache_age_sec)}s 前）")

        if not q1:
            root_error = q1_error or ValueError("Q1 无可用回包")
            raise RuntimeError(f"Q1 不可用: {root_error}")

        if q1_error and not protocol_support["q1"]:
            query_warnings.append(f"Q1 不可用: {q1_error}；回包: {_raw_preview(q1_raw)}")
        if q6_error and not protocol_support["q6"]:
            query_warnings.append(f"Q6 不可用: {q6_error}；回包: {_raw_preview(q6_raw)}")
        if wa_error and not protocol_support["wa"]:
            query_warnings.append(f"WA 不可用: {wa_error}；回包: {_raw_preview(wa_raw)}")

        if protocol_support["q1"] or protocol_support["q6"] or protocol_support["wa"]:
            merged_cache = dict(cache)
            if protocol_support["q1"]:
                merged_cache["q1"] = dict(q1)
            if protocol_support["q6"]:
                merged_cache["q6"] = dict(q6)
            if protocol_support["wa"]:
                merged_cache["wa"] = dict(wa)
            merged_cache["saved_at"] = time.time()
            self._save_last_good(merged_cache)

        alerts = list(
            dict.fromkeys(
                (q6.get("fault_labels") or [])
                + (q6.get("warning_labels") or [])
                + (q1.get("status_bits", {}).get("active_labels") or [])
            )
        )
        query_warnings = list(dict.fromkeys([item for item in query_warnings if item]))

        fallback_mode = "旁路" if q1.get("status_bits", {}).get("bypass_active") else "在线"
        mains_abnormal = bool(q1.get("status_bits", {}).get("mains_abnormal"))
        is_bypass = bool(q1.get("status_bits", {}).get("bypass_active"))
        system_mode_code = q6.get("system_mode_code")
        quality = _estimate_payload_quality(
            q1_ok=bool(protocol_support["q1"]),
            q6_ok=bool(protocol_support["q6"]),
            wa_ok=bool(protocol_support["wa"]),
            fallback_used=fallback_used,
            query_warnings=query_warnings,
        )
        current_ts = time.time()
        last_success_at_ts: Optional[float] = None
        if protocol_support["q1"] or protocol_support["q6"] or protocol_support["wa"]:
            last_success_at_ts = current_ts
        else:
            last_success_at_ts = _safe_float(cache.get("saved_at"), None)
        last_success_age_sec = max(0.0, current_ts - last_success_at_ts) if last_success_at_ts is not None else None
        fallback_active = any(bool(v) for v in fallback_used.values())
        link_hint = "串口服务器透传" if str(self.cfg.get("comm_mode", "TCP")).upper() != "COM" else "本机串口"
        return {
            "online": True,
            "raw": {"q1": q1_raw or "", "q6": q6_raw or "", "wa": wa_raw or ""},
            "raw_preview": {
                "q1": _raw_preview(q1_raw),
                "q6": _raw_preview(q6_raw),
                "wa": _raw_preview(wa_raw),
            },
            "protocol_support": {
                "q1": bool(protocol_support["q1"]),
                "q6": bool(protocol_support["q6"]),
                "wa": bool(protocol_support["wa"]),
                "q1_fallback": bool(fallback_used["q1"]),
                "q6_fallback": bool(fallback_used["q6"]),
                "wa_fallback": bool(fallback_used["wa"]),
            },
            "poll_diagnostics": {
                "transport": str(self.cfg.get("comm_mode", "TCP")).upper(),
                "transport_hint": link_hint,
                "query_retries": int(self.query_retries),
                "retry_backoff_ms": int(self.retry_backoff_ms),
                "command_gap_ms": int(self.command_gap_ms),
                "timeout_sec": float(self.timeout),
                "response_window_ms": int(self.response_window_ms),
                "frame_settle_ms": int(self.frame_settle_ms),
                "require_parenthesized_frame": bool(self.require_parenthesized_frame),
                "fallback_cache_ttl_sec": float(self.fallback_cache_ttl_sec),
                "fallback_active": fallback_active,
                "quality": quality,
                "last_success_age_sec": last_success_age_sec,
                "collected_cost_ms": max(0, int((time.time() - request_started_at) * 1000)),
            },
            "field_counts": {
                "q1": len(_split_response(q1_raw or "")),
                "q6": len(_split_response(q6_raw or "")),
                "wa": len(_split_response(wa_raw or "")),
            },
            "q1": q1,
            "q6": q6,
            "wa": wa,
            "input_voltage": q1.get("input_voltage"),
            "output_voltage": q1.get("output_voltage"),
            "load_percent": wa.get("load_percent") if wa.get("load_percent") is not None else q1.get("load_percent"),
            "input_frequency": q1.get("input_frequency"),
            "output_frequency": q6.get("output_frequency"),
            "temperature": q6.get("temperature") if q6.get("temperature") is not None else q1.get("temperature"),
            "battery_voltage": q6.get("battery_positive_voltage") if q6.get("battery_positive_voltage") is not None else q1.get("battery_12v_block_voltage"),
            "battery_capacity_percent": q6.get("battery_capacity_percent"),
            "backup_time_seconds": q6.get("backup_time_seconds"),
            "system_mode": q6.get("system_mode_text") or fallback_mode,
            "system_mode_code": system_mode_code,
            "supply_state": _resolve_supply_state(system_mode_code, mains_abnormal=mains_abnormal, is_bypass=is_bypass),
            "battery_test_text": q6.get("battery_test_text"),
            "battery_test_code": q6.get("battery_test_code"),
            "total_real_power_kw": wa.get("total_real_power_kw"),
            "total_apparent_power_kva": wa.get("total_apparent_power_kva"),
            "input_voltage_r": q6.get("input_voltage_r"),
            "input_voltage_s": q6.get("input_voltage_s"),
            "input_voltage_t": q6.get("input_voltage_t"),
            "output_voltage_r": q6.get("output_voltage_r"),
            "output_voltage_s": q6.get("output_voltage_s"),
            "output_voltage_t": q6.get("output_voltage_t"),
            "output_reported_voltage_kind": q6.get("output_reported_voltage_kind"),
            "output_phase_voltage_r": q6.get("output_phase_voltage_r"),
            "output_phase_voltage_s": q6.get("output_phase_voltage_s"),
            "output_phase_voltage_t": q6.get("output_phase_voltage_t"),
            "output_line_voltage_r": q6.get("output_line_voltage_r"),
            "output_line_voltage_s": q6.get("output_line_voltage_s"),
            "output_line_voltage_t": q6.get("output_line_voltage_t"),
            "output_current_r": q6.get("output_current_r"),
            "output_current_s": q6.get("output_current_s"),
            "output_current_t": q6.get("output_current_t"),
            "transformer_type": q6.get("transformer_type"),
            "transformer_type_code": q6.get("transformer_type_code"),
            "output_voltage_display_mode": q6.get("output_voltage_display_mode"),
            "output_voltage_display_mode_code": q6.get("output_voltage_display_mode_code"),
            "fault_code_raw": q6.get("fault_code_raw"),
            "warning_code_raw": q6.get("warning_code_raw"),
            "fault_labels": q6.get("fault_labels", []),
            "warning_labels": q6.get("warning_labels", []),
            "alerts": alerts,
            "query_warnings": query_warnings,
            "data_quality_score": quality.get("score"),
            "data_quality_level": quality.get("level"),
            "data_quality_text": quality.get("text"),
            "data_quality_details": quality.get("details", []),
            "is_bypass": is_bypass,
            "is_fault": bool(q1.get("status_bits", {}).get("ups_fault")),
            "is_battery_low": bool(q1.get("status_bits", {}).get("battery_low")),
            "mains_abnormal": mains_abnormal,
        }

    def shutdown(self, delay_text: str = ".3") -> Tuple[bool, str]:
        delay_text = _normalize_shutdown_delay(delay_text)
        payload = f"S{delay_text}\r"
        response, err = self._safe_query(payload, validator=None)
        if err or not response:
            raise RuntimeError(f"UPS 关机命令发送失败: {err or '未知错误'}")
        clean = _extract_known_reply(response) or _raw_preview(response, limit=240)
        return True, clean
