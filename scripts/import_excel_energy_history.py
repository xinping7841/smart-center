import argparse
import json
import os
import shutil
import sqlite3
import sys
import zipfile
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from xml.etree import ElementTree as ET

from paths import CONFIG_FILE as CONFIG_FILE_PATH, ENERGY_LOG_FILE as ENERGY_LOG_FILE_PATH


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOCAL_ENERGY_LOG = Path(ENERGY_LOG_FILE_PATH)
LOCAL_CONFIG = Path(CONFIG_FILE_PATH)
NAS_DB_PATH = PROJECT_ROOT / "meter_service" / "data" / "meter_service.db"

DEFAULT_WORKBOOK = Path(r"C:\Users\gaoxi\Documents\.electricity_counter.xlsx")

# Excel 区域名到当前系统电表/电柜历史 key 的默认映射。
# meter -> energy_log.json 中使用 meter:<meter_id>，NAS SQLite 中也使用同名 cache_key
# cabinet -> energy_log.json 中使用 cabinet:<idx>；若 mirror_local_index 为 true，会额外同步到旧强电历史 key "<idx>"
DEFAULT_SHEET_MAPPINGS = {
    "深澜空间总电表": [{"type": "meter", "id": "legacy_meter_2"}],
    "2号厅": [{"type": "meter", "id": "legacy_meter_3"}],
    "二号厅": [{"type": "meter", "id": "legacy_meter_3"}],
    "1号厅": [{"type": "meter", "id": "meter_1774625129670"}],
    "一号厅": [{"type": "meter", "id": "meter_1774625129670"}],
    "中控室": [{"type": "meter", "id": "legacy_meter_5"}],
    "运营中心": [{"type": "meter", "id": "legacy_meter_6"}],
    "2号厅LED": [{"type": "cabinet", "id": "1", "mirror_local_index": True}],
    "二号厅LED": [{"type": "cabinet", "id": "1", "mirror_local_index": True}],
    "办公室&工作坊": [{"type": "meter", "id": "legacy_meter_9"}],
    "2楼小机房": [{"type": "meter", "id": "legacy_meter_10"}],
    "咖啡厅": [{"type": "meter", "id": "legacy_meter_11"}],
    # 下面这些目前系统里没有明确目标，先保留给后续扩展
    "XR展厅": [{"type": "cabinet", "id": "2", "mirror_local_index": True}],
    "XR展厅LED": [],
    "办公室": [{"type": "meter", "id": "legacy_meter_12"}],
}


def load_json(path: Path, default):
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def backup_file(path: Path):
    if not path.exists():
        return None
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = path.with_name(f"{path.name}.bak_{stamp}")
    shutil.copy2(path, backup)
    return backup


def ns_tag(tag):
    return f"{{http://schemas.openxmlformats.org/spreadsheetml/2006/main}}{tag}"


def rel_tag(tag):
    return f"{{http://schemas.openxmlformats.org/package/2006/relationships}}{tag}"


def office_rel_tag(tag):
    return f"{{http://schemas.openxmlformats.org/officeDocument/2006/relationships}}{tag}"


def excel_date_to_datetime(value):
    base = datetime(1899, 12, 30)
    return base + timedelta(days=float(value))


def parse_xlsx_workbook(path: Path):
    with zipfile.ZipFile(path, "r") as zf:
        shared_strings = []
        if "xl/sharedStrings.xml" in zf.namelist():
            root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            for si in root.findall(ns_tag("si")):
                parts = []
                for text_node in si.iter(ns_tag("t")):
                    parts.append(text_node.text or "")
                shared_strings.append("".join(parts))

        workbook_root = ET.fromstring(zf.read("xl/workbook.xml"))
        rel_root = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
        rel_map = {
            rel.attrib.get("Id"): rel.attrib.get("Target")
            for rel in rel_root.findall(rel_tag("Relationship"))
        }

        sheets = {}
        for sheet in workbook_root.findall(f".//{ns_tag('sheet')}"):
            name = sheet.attrib.get("name", "").strip()
            rel_id = sheet.attrib.get(office_rel_tag("id"))
            target = rel_map.get(rel_id, "")
            if not target:
                continue
            if not target.startswith("xl/"):
                target = f"xl/{target.lstrip('/')}"
            sheets[name] = target

        result = {}
        for name, target in sheets.items():
            sheet_root = ET.fromstring(zf.read(target))
            rows = []
            for row_node in sheet_root.findall(f".//{ns_tag('row')}"):
                row_values = {}
                for cell in row_node.findall(ns_tag("c")):
                    ref = cell.attrib.get("r", "")
                    col_letters = "".join(ch for ch in ref if ch.isalpha())
                    if not col_letters:
                        continue
                    col_index = 0
                    for ch in col_letters:
                        col_index = col_index * 26 + (ord(ch.upper()) - 64)
                    cell_type = cell.attrib.get("t", "")
                    value = None
                    value_node = cell.find(ns_tag("v"))
                    if cell_type == "s" and value_node is not None and value_node.text is not None:
                        try:
                            value = shared_strings[int(value_node.text)]
                        except Exception:
                            value = value_node.text
                    elif cell_type == "inlineStr":
                        value = "".join(node.text or "" for node in cell.iter(ns_tag("t")))
                    elif value_node is not None:
                        value = value_node.text
                    row_values[col_index] = value
                if row_values:
                    rows.append(row_values)
            result[name] = rows
        return result


def to_float(value, default=0.0):
    try:
        if value in (None, ""):
            return default
        return float(str(value).replace(",", ""))
    except Exception:
        return default


def to_datetime(value):
    if value in (None, ""):
        return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(text)
    except Exception:
        pass
    try:
        numeric = float(text)
        if numeric > 1:
            return excel_date_to_datetime(numeric)
    except Exception:
        pass
    return None


def extract_sheet_records(raw_rows):
    entries = []
    for row in raw_rows:
        time_val = row.get(1)
        if str(time_val or "").strip() == "时间":
            continue
        dt = to_datetime(time_val)
        if not dt:
            continue
        cumulative = to_float(row.get(3), None)
        if cumulative is None:
            continue
        consume = to_float(row.get(2), 0.0)
        entries.append({
            "timestamp": dt,
            "consume": round(consume, 4),
            "cumulative": round(cumulative, 4),
        })
    entries.sort(key=lambda item: item["timestamp"])
    return entries


def build_daily_records(entries):
    grouped = defaultdict(list)
    for item in entries:
        grouped[item["timestamp"].strftime("%Y-%m-%d")].append(item)
    daily_records = {}
    for date_text, items in grouped.items():
        items.sort(key=lambda item: item["timestamp"])
        start_energy = round(items[0]["cumulative"], 4)
        end_energy = round(items[-1]["cumulative"], 4)
        if end_energy < start_energy:
            end_energy = start_energy
        daily_records[date_text] = {
            "date": date_text,
            "start_energy": start_energy,
            "end_energy": end_energy,
            "rows": len(items),
        }
    return daily_records


def get_cache_keys(target):
    target_type = str(target.get("type") or "").strip().lower()
    target_id = str(target.get("id") or "").strip()
    if target_type == "meter":
        return [f"meter:{target_id}"]
    if target_type == "cabinet":
        keys = [f"cabinet:{target_id}"]
        if bool(target.get("mirror_local_index", False)):
            keys.append(target_id)
        return keys
    return []


def merge_daily_records(existing_records, imported_by_date):
    existing_map = {}
    for item in existing_records or []:
        date_text = str((item or {}).get("date") or "").strip()
        if not date_text:
            continue
        existing_map[date_text] = {
            "date": date_text,
            "start_energy": round(to_float((item or {}).get("start_energy"), 0.0), 4),
            "end_energy": round(to_float((item or {}).get("end_energy"), 0.0), 4),
        }
    for date_text, payload in imported_by_date.items():
        existing_map[date_text] = {
            "date": date_text,
            "start_energy": round(to_float(payload.get("start_energy"), 0.0), 4),
            "end_energy": round(max(to_float(payload.get("end_energy"), 0.0), to_float(payload.get("start_energy"), 0.0)), 4),
        }
    return sorted(existing_map.values(), key=lambda item: item["date"])


def apply_to_local_energy_log(import_plan, dry_run=False):
    energy_log = load_json(LOCAL_ENERGY_LOG, {})
    updated_keys = {}
    for target_key, daily_map in import_plan.items():
        existing = ((energy_log or {}).get(target_key) or {}).get("daily_records", [])
        merged = merge_daily_records(existing, daily_map)
        updated_keys[target_key] = len(merged)
        if not dry_run:
            energy_log[target_key] = {
                "daily_records": merged,
                "monthly_records": ((energy_log.get(target_key) or {}).get("monthly_records") or {}),
            }
    if not dry_run:
        energy_log["last_sync_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        save_json(LOCAL_ENERGY_LOG, energy_log)
    return updated_keys


def apply_to_nas_db(import_plan, dry_run=False):
    if not NAS_DB_PATH.exists():
        raise FileNotFoundError(f"NAS 历史库不存在: {NAS_DB_PATH}")
    summary = {}
    if dry_run:
        for cache_key, daily_map in import_plan.items():
            summary[cache_key] = len(daily_map)
        return summary
    conn = sqlite3.connect(NAS_DB_PATH)
    cur = conn.cursor()
    try:
        for cache_key, daily_map in import_plan.items():
            count = 0
            for date_text, payload in daily_map.items():
                start_energy = round(to_float(payload.get("start_energy"), 0.0), 4)
                end_energy = round(max(to_float(payload.get("end_energy"), 0.0), start_energy), 4)
                cur.execute(
                    """
                    INSERT INTO meter_daily_records (cache_key, date, start_energy, end_energy)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(cache_key, date) DO UPDATE SET
                        start_energy=excluded.start_energy,
                        end_energy=excluded.end_energy
                    """,
                    (cache_key, date_text, start_energy, end_energy),
                )
                count += 1
            summary[cache_key] = count
        conn.commit()
    finally:
        conn.close()
    return summary


def build_import_plan(sheet_payloads):
    sheet_summaries = []
    import_plan = defaultdict(dict)
    unmapped = []
    for sheet_name, raw_rows in sheet_payloads.items():
        entries = extract_sheet_records(raw_rows)
        if not entries:
            sheet_summaries.append({
                "sheet": sheet_name,
                "rows": 0,
                "days": 0,
                "targets": [],
            })
            continue
        daily_records = build_daily_records(entries)
        targets = DEFAULT_SHEET_MAPPINGS.get(sheet_name, None)
        if targets is None:
            unmapped.append(sheet_name)
            targets = []
        for target in targets:
            for cache_key in get_cache_keys(target):
                import_plan[cache_key].update({k: {"start_energy": v["start_energy"], "end_energy": v["end_energy"]} for k, v in daily_records.items()})
        sheet_summaries.append({
            "sheet": sheet_name,
            "rows": len(entries),
            "days": len(daily_records),
            "targets": targets,
        })
    return import_plan, sheet_summaries, unmapped


def print_sheet_summary(sheet_summaries, unmapped):
    print("Excel 工作表扫描结果:")
    for item in sheet_summaries:
        target_text = ", ".join(
            [f"{target.get('type')}:{target.get('id')}" for target in item["targets"]]
        ) if item["targets"] else "未映射"
        print(f"  - {item['sheet']}: {item['rows']} 条记录, {item['days']} 天, 目标 {target_text}")
    if unmapped:
        print("未映射工作表:")
        for name in unmapped:
            print(f"  - {name}")


def main():
    parser = argparse.ArgumentParser(description="从 Excel 用电汇总表补录本地/NAS 电表历史数据")
    parser.add_argument("--workbook", default=str(DEFAULT_WORKBOOK), help="Excel 文件路径")
    parser.add_argument("--apply", action="store_true", help="正式写入；默认只预演")
    parser.add_argument("--skip-local", action="store_true", help="不写本地主程序 energy_log.json")
    parser.add_argument("--skip-nas", action="store_true", help="不写 NAS 电表服务 SQLite 历史库")
    args = parser.parse_args()

    workbook_path = Path(args.workbook).expanduser()
    if not workbook_path.exists():
        print(f"Excel 文件不存在: {workbook_path}", file=sys.stderr)
        return 1

    if not LOCAL_CONFIG.exists():
        print(f"配置文件不存在: {LOCAL_CONFIG}", file=sys.stderr)
        return 1

    sheet_payloads = parse_xlsx_workbook(workbook_path)
    import_plan, sheet_summaries, unmapped = build_import_plan(sheet_payloads)
    print_sheet_summary(sheet_summaries, unmapped)

    if not import_plan:
        print("没有可导入的历史数据。")
        return 0

    print("")
    print("即将更新的历史 key:")
    for cache_key, daily_map in sorted(import_plan.items()):
        print(f"  - {cache_key}: {len(daily_map)} 天")

    if not args.apply:
        print("")
        print("当前为预演模式，未写入任何文件。")
        print("正式导入请执行: python scripts/import_excel_energy_history.py --apply")
        return 0

    backups = []
    if not args.skip_local and LOCAL_ENERGY_LOG.exists():
        backup = backup_file(LOCAL_ENERGY_LOG)
        if backup:
            backups.append(backup)
    if not args.skip_nas and NAS_DB_PATH.exists():
        backup = backup_file(NAS_DB_PATH)
        if backup:
            backups.append(backup)

    if backups:
        print("")
        print("已创建备份:")
        for item in backups:
            print(f"  - {item}")

    if not args.skip_local:
        local_summary = apply_to_local_energy_log(import_plan, dry_run=False)
        print("")
        print("本地 energy_log.json 已更新:")
        for key, count in sorted(local_summary.items()):
            print(f"  - {key}: {count} 天")

    if not args.skip_nas:
        nas_summary = apply_to_nas_db(import_plan, dry_run=False)
        print("")
        print("NAS meter_service.db 已更新:")
        for key, count in sorted(nas_summary.items()):
            print(f"  - {key}: {count} 天")

    print("")
    print("导入完成。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
