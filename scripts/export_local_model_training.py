#!/usr/bin/env python3
# AI_MODULE: local_model_training_export_cli
# AI_PURPOSE: Export runtime device knowledge and source-code knowledge packages for Smart Center local-model learning.
# AI_BOUNDARY: Calls export builders and copies artifacts only; it must not poll devices directly or execute control routes.
# AI_DATA_FLOW: CONFIG/runtime logs/codebase -> training/local_model JSON/JSONL -> optional NAS backup mirror.
# AI_RUNTIME: Manual or timer-driven maintenance command on node-120, often before refreshing node-123 summaries.
# AI_RISK: Medium. Exports must keep secrets redacted and avoid treating runtime dumps or backups as source of truth.
# AI_COMPAT: Output filenames and manifest counts are used by /api/local-model/knowledge-status and refresh scripts.
# AI_SEARCH_KEYWORDS: local model training, export, runtime knowledge, code knowledge, NAS sync.
import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from api.local_model import build_training_export, normalize_local_model_config  # noqa: E402
from config import CONFIG  # noqa: E402
from paths import CONFIG_FILE, DATA_DIR, ensure_directory  # noqa: E402
from scripts.export_code_knowledge import build_code_knowledge_export_with_options  # noqa: E402


DEFAULT_NAS_DIR = "/mnt/ubuntu01/smart-center-backups/local-model-training"
DEFAULT_KEEP_DAYS = 180


def _safe_stamp(value=None):
    raw = str(value or datetime.now().isoformat(timespec="seconds")).strip()
    return (
        raw.replace("T", "_")
        .replace(":", "")
        .replace("-", "")
        .replace(" ", "_")
        .replace(".", "")
    )


def _copy_file_atomic(source, target):
    source_path = Path(source)
    target_path = Path(target)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = target_path.with_name(f".{target_path.name}.tmp")
    shutil.copy2(source_path, tmp_path)
    tmp_path.replace(target_path)


def _clear_dir(path):
    target = Path(path)
    if not target.exists():
        target.mkdir(parents=True, exist_ok=True)
        return
    if not target.is_dir():
        raise RuntimeError(f"not a directory: {target}")
    for child in target.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def _prune_old_runs(base_dir, keep_days):
    keep_days = int(keep_days or 0)
    if keep_days <= 0:
        return []
    cutoff = datetime.now() - timedelta(days=keep_days)
    removed = []
    by_day = Path(base_dir) / "by-day"
    if not by_day.is_dir():
        return removed
    for day_dir in sorted(by_day.iterdir()):
        if not day_dir.is_dir():
            continue
        try:
            day_value = datetime.strptime(day_dir.name, "%Y-%m-%d")
        except ValueError:
            continue
        if day_value < cutoff:
            shutil.rmtree(day_dir)
            removed.append(str(day_dir))
    return removed


def sync_export_to_nas(export_payload, nas_dir, keep_days=DEFAULT_KEEP_DAYS):
    base_dir = ensure_directory(Path(nas_dir))
    if not str(base_dir).startswith("/mnt/"):
        raise RuntimeError(f"refuse to sync outside /mnt: {base_dir}")
    generated_at = export_payload.get("generated_at") or datetime.now().isoformat(timespec="seconds")
    try:
        generated_dt = datetime.fromisoformat(str(generated_at))
    except ValueError:
        generated_dt = datetime.now()
    day_text = generated_dt.strftime("%Y-%m-%d")
    run_id = _safe_stamp(generated_at)
    run_dir = ensure_directory(base_dir / "by-day" / day_text / run_id)
    latest_dir = base_dir / "latest"
    _clear_dir(latest_dir)

    copied = {}
    for name, source in sorted((export_payload.get("files") or {}).items()):
        source_path = Path(source)
        if not source_path.is_file():
            continue
        run_target = run_dir / source_path.name
        latest_target = latest_dir / source_path.name
        _copy_file_atomic(source_path, run_target)
        _copy_file_atomic(source_path, latest_target)
        copied[name] = {
            "source": str(source_path),
            "run_path": str(run_target),
            "latest_path": str(latest_target),
            "size": run_target.stat().st_size,
        }

    manifest = {
        "schema": "smart_center.local_model_training_sync.v1",
        "generated_at": generated_at,
        "synced_at": datetime.now().isoformat(timespec="seconds"),
        "nas_dir": str(base_dir),
        "run_dir": str(run_dir),
        "latest_dir": str(latest_dir),
        "counts": export_payload.get("counts") or {},
        "files": copied,
        "keep_days": int(keep_days or 0),
    }
    for target in (run_dir / "manifest.json", latest_dir / "manifest.json"):
        target.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (base_dir / "latest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    removed = _prune_old_runs(base_dir, keep_days)
    manifest["removed"] = removed
    return manifest


def main():
    parser = argparse.ArgumentParser(description="Export Smart Center local-model training data and optionally sync to NAS.")
    parser.add_argument("--skip-code-knowledge", action="store_true", help="do not export source-code/module knowledge")
    parser.add_argument("--skip-full-code-context", action="store_true", help="do not export redacted source chunks for high-context model refresh")
    parser.add_argument("--sync-nas", action="store_true", help="copy generated files to NAS training directory")
    parser.add_argument("--nas-dir", default=os.environ.get("SMART_CENTER_LOCAL_MODEL_TRAINING_NAS_DIR", DEFAULT_NAS_DIR))
    parser.add_argument("--keep-days", type=int, default=int(os.environ.get("SMART_CENTER_LOCAL_MODEL_TRAINING_KEEP_DAYS", DEFAULT_KEEP_DAYS)))
    args = parser.parse_args()

    ensure_directory(DATA_DIR / "training" / "local_model")
    model_cfg = normalize_local_model_config(CONFIG.get("local_model"))
    export_cfg = model_cfg.get("training_export") if isinstance(model_cfg.get("training_export"), dict) else {}
    export_payload = build_training_export()
    include_code_knowledge = bool(export_cfg.get("include_code_knowledge", True)) and not args.skip_code_knowledge
    include_full_context = bool(export_cfg.get("include_full_code_context", True)) and not args.skip_full_code_context
    code_knowledge_payload = None if not include_code_knowledge else build_code_knowledge_export_with_options(include_full_context=include_full_context)
    alias_count = int((export_payload.get("counts") or {}).get("device_aliases") or 0)
    if alias_count < 20:
        print(
            (
                f"WARNING: device_aliases only {alias_count}; config source may be an empty/default file: "
                f"{CONFIG_FILE}. Set SMART_CENTER_DATA_DIR or SMART_CENTER_CONFIG_FILE to the production data path."
            ),
            file=sys.stderr,
        )
    result = {"ok": True, "export": export_payload}
    if code_knowledge_payload:
        result["code_knowledge"] = code_knowledge_payload
    if args.sync_nas:
        result["nas"] = sync_export_to_nas(export_payload, args.nas_dir, args.keep_days)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
