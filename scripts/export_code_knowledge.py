#!/usr/bin/env python3
"""Export Smart Center source knowledge for local-model RAG.

The output is intentionally structured and compact: it teaches the model where
logic lives, what each file owns, which routes exist, and which control paths are
risky without feeding raw source code or secrets into the model.
"""

from __future__ import annotations

import argparse
import ast
import fnmatch
import hashlib
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from paths import DATA_DIR, ensure_directory  # noqa: E402


DEFAULT_EXCLUDES = (
    ".git/**",
    ".venv/**",
    ".worktasks/**",
    "__pycache__/**",
    ".pytest_cache/**",
    ".baseline_reports/**",
    "runtime/**",
    "reports/**",
    "training/**",
    "backups/**",
    "*.db",
    "*.sqlite",
    "*.sqlite3",
    "*.pyc",
    "*.pyo",
    "*.jpg",
    "*.jpeg",
    "*.png",
    "*.gif",
    "*.webp",
    "*.zip",
    "*.tar",
    "*.gz",
)
INCLUDE_SUFFIXES = {
    ".py",
    ".js",
    ".html",
    ".css",
    ".md",
    ".yaml",
    ".yml",
    ".json",
    ".jsonl",
    ".txt",
    ".ps1",
    ".sh",
    ".bat",
    ".cmd",
}
AI_KEYS = (
    "AI_MODULE",
    "AI_PURPOSE",
    "AI_BOUNDARY",
    "AI_DATA_FLOW",
    "AI_RUNTIME",
    "AI_RISK",
    "AI_COMPAT",
    "AI_SEARCH_KEYWORDS",
)
ROUTE_DECORATOR_RE = re.compile(r"@(?:\w+\.)?route\((?P<args>.*)\)")
PERMISSION_RE = re.compile(r"@require_permission\((?P<args>[^)]*)\)")
JS_API_RE = re.compile(r"['\"](?P<path>/api/[A-Za-z0-9_./<>{}:?=&%~+*\\-]+)['\"]")
CONFIG_KEY_RE = re.compile(r"(?:CONFIG|get\()\s*(?:\[|\()\s*['\"](?P<key>[A-Za-z0-9_\\-]+)['\"]")


def _training_dir() -> Path:
    return ensure_directory(DATA_DIR / "training" / "local_model")


def _rel(path: Path) -> str:
    return path.relative_to(PROJECT_ROOT).as_posix()


def _is_excluded(rel_path: str, excludes: tuple[str, ...] = DEFAULT_EXCLUDES) -> bool:
    normalized = rel_path.strip("/")
    for pattern in excludes:
        if fnmatch.fnmatch(normalized, pattern) or fnmatch.fnmatch(f"./{normalized}", pattern):
            return True
        if pattern.endswith("/**") and normalized.startswith(pattern[:-3].rstrip("/") + "/"):
            return True
    return False


def iter_source_files() -> list[Path]:
    files: list[Path] = []
    for path in PROJECT_ROOT.rglob("*"):
        if not path.is_file():
            continue
        rel_path = _rel(path)
        if _is_excluded(rel_path):
            continue
        if path.suffix.lower() not in INCLUDE_SUFFIXES:
            continue
        files.append(path)
    return sorted(files, key=lambda p: _rel(p))


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig", errors="ignore")
    except Exception:
        return ""


def _line_count(text: str) -> int:
    return len(text.splitlines())


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def _shorten(text: Any, limit: int = 420) -> str:
    value = re.sub(r"\s+", " ", str(text or "").strip())
    if len(value) <= limit:
        return value
    return value[: limit - 3].rstrip() + "..."


def _extract_ai_markers(text: str) -> dict[str, str]:
    markers: dict[str, str] = {}
    for line in text.splitlines()[:80]:
        clean = line.strip()
        clean = clean.lstrip("#/<!--* ").rstrip("*/ -->")
        for key in AI_KEYS:
            prefix = f"{key}:"
            if clean.startswith(prefix):
                markers[key] = clean[len(prefix) :].strip()
                break
    return markers


def _extract_python_routes(path: Path, text: str) -> list[dict[str, Any]]:
    routes: list[dict[str, Any]] = []
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return routes
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        route_paths: list[str] = []
        methods: list[str] = []
        permission = ""
        for dec in node.decorator_list:
            call = dec if isinstance(dec, ast.Call) else None
            if not call:
                continue
            func = call.func
            name = ""
            if isinstance(func, ast.Attribute):
                name = func.attr
            elif isinstance(func, ast.Name):
                name = func.id
            if name == "route":
                if call.args and isinstance(call.args[0], ast.Constant):
                    route_paths.append(str(call.args[0].value))
                for keyword in call.keywords:
                    if keyword.arg != "methods":
                        continue
                    value = keyword.value
                    if isinstance(value, (ast.List, ast.Tuple)):
                        for item in value.elts:
                            if isinstance(item, ast.Constant):
                                methods.append(str(item.value).upper())
            elif name == "require_permission":
                if call.args and isinstance(call.args[0], ast.Constant):
                    permission = str(call.args[0].value)
        for route_path in route_paths:
            routes.append(
                {
                    "schema": "smart_center.code_knowledge.v1",
                    "kind": "api_route",
                    "source_file": _rel(path),
                    "line": getattr(node, "lineno", 0),
                    "route": route_path,
                    "methods": methods or ["GET"],
                    "function": node.name,
                    "permission": permission,
                    "risk": _route_risk(route_path, permission),
                    "summary": _route_summary(route_path, methods or ["GET"], permission),
                }
            )
    return routes


def _extract_loose_routes(path: Path, text: str) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".py":
        return []
    routes: list[dict[str, Any]] = []
    for idx, line in enumerate(text.splitlines(), 1):
        for match in JS_API_RE.finditer(line):
            route_path = match.group("path")
            routes.append(
                {
                    "schema": "smart_center.code_knowledge.v1",
                    "kind": "frontend_api_reference",
                    "source_file": _rel(path),
                    "line": idx,
                    "route": route_path,
                    "risk": _route_risk(route_path, ""),
                    "summary": f"{_rel(path)} references {route_path}.",
                }
            )
    return routes


def _route_risk(route_path: str, permission: str = "") -> str:
    haystack = f"{route_path} {permission}".lower()
    if any(token in haystack for token in ("control", "set", "onekey", "wake", "command", "toggle", "test", "update", "save", "config")):
        if any(token in haystack for token in ("power", "sequencer", "ups", "server", "wake", "command", "onekey", "/api/set")):
            return "high"
        return "medium"
    return "low"


def _route_summary(route_path: str, methods: list[str], permission: str) -> str:
    method_text = ",".join(methods or ["GET"])
    permission_text = permission or "no explicit permission"
    risk = _route_risk(route_path, permission)
    return f"{method_text} {route_path} uses {permission_text}; route risk is {risk}."


def _module_from_path(rel_path: str, markers: dict[str, str]) -> str:
    if markers.get("AI_MODULE"):
        return markers["AI_MODULE"]
    parts = rel_path.split("/")
    if parts[0] in {"api", "services", "runtime", "drivers", "static", "templates", "docs", "scripts", "auth"}:
        if len(parts) > 1:
            return f"{parts[0]}/{Path(parts[1]).stem}"
        return parts[0]
    return Path(rel_path).stem


def _tags_for_file(rel_path: str, text: str, markers: dict[str, str]) -> list[str]:
    tags = set()
    lower = f"{rel_path}\n{text[:4000]}".lower()
    for token, tag in (
        ("feishu", "feishu"),
        ("飞书", "feishu"),
        ("local_model", "local_model"),
        ("本地模型", "local_model"),
        ("control", "control"),
        ("控制", "control"),
        ("permission", "permission"),
        ("require_permission", "permission"),
        ("route", "api"),
        ("/api/", "api"),
        ("config", "config"),
        ("training", "training"),
        ("knowledge", "knowledge"),
        ("知识", "knowledge"),
        ("model", "model"),
        ("risk", "risk"),
        ("高", "risk"),
    ):
        if token.lower() in lower:
            tags.add(tag)
    if markers.get("AI_SEARCH_KEYWORDS"):
        for item in re.split(r"[,，\s]+", markers["AI_SEARCH_KEYWORDS"]):
            item = item.strip().lower()
            if item:
                tags.add(item)
    return sorted(tags)


def _control_paths_from_text(text: str) -> list[str]:
    paths = set()
    for match in JS_API_RE.finditer(text):
        route_path = match.group("path")
        if _route_risk(route_path, "") in {"high", "medium"}:
            paths.add(route_path)
    for match in re.finditer(r"['\"](?P<path>/api/[A-Za-z0-9_./<>{}:?=&%~+*\\-]+)['\"]", text):
        route_path = match.group("path")
        if _route_risk(route_path, "") in {"high", "medium"}:
            paths.add(route_path)
    return sorted(paths)


def _config_keys_from_text(text: str) -> list[str]:
    keys = {match.group("key") for match in CONFIG_KEY_RE.finditer(text)}
    return sorted(key for key in keys if len(key) >= 2)[:80]


def build_file_records(files: list[Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in files:
        text = _read_text(path)
        rel_path = _rel(path)
        markers = _extract_ai_markers(text)
        if not markers and path.suffix.lower() in {".json", ".jsonl"} and path.stat().st_size > 512_000:
            continue
        module = _module_from_path(rel_path, markers)
        risk = markers.get("AI_RISK") or ("高" if _control_paths_from_text(text) else "")
        rows.append(
            {
                "schema": "smart_center.code_knowledge.v1",
                "kind": "source_file",
                "source_file": rel_path,
                "module": module,
                "suffix": path.suffix.lower(),
                "line_count": _line_count(text),
                "sha256": _sha256_text(text),
                "ai_markers": markers,
                "purpose": markers.get("AI_PURPOSE") or _infer_file_purpose(rel_path, text),
                "boundary": markers.get("AI_BOUNDARY") or "",
                "risk": risk,
                "compat": markers.get("AI_COMPAT") or "",
                "control_paths": _control_paths_from_text(text),
                "config_keys": _config_keys_from_text(text),
                "tags": _tags_for_file(rel_path, text, markers),
                "summary": _file_summary(rel_path, markers, text),
            }
        )
    return rows


def _infer_file_purpose(rel_path: str, text: str) -> str:
    if rel_path.startswith("api/"):
        return f"Flask API module for {Path(rel_path).stem}."
    if rel_path.startswith("services/"):
        return f"Service helper for {Path(rel_path).stem}."
    if rel_path.startswith("static/js/views/"):
        return f"Frontend view runtime for {Path(rel_path).stem}."
    if rel_path.startswith("docs/"):
        title = next((line.strip("# ").strip() for line in text.splitlines() if line.strip().startswith("#")), "")
        return title or f"Documentation file {rel_path}."
    if rel_path.startswith("scripts/"):
        return f"Operational script {rel_path}."
    return ""


def _file_summary(rel_path: str, markers: dict[str, str], text: str) -> str:
    purpose = markers.get("AI_PURPOSE") or _infer_file_purpose(rel_path, text)
    boundary = markers.get("AI_BOUNDARY") or ""
    risk = markers.get("AI_RISK") or ""
    parts = [f"{rel_path}: {purpose}" if purpose else rel_path]
    if boundary:
        parts.append(f"Boundary: {boundary}")
    if risk:
        parts.append(f"Risk: {risk}")
    return _shorten(" ".join(parts), 700)


def build_route_records(files: list[Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen = set()
    for path in files:
        text = _read_text(path)
        extracted = _extract_python_routes(path, text) + _extract_loose_routes(path, text)
        for row in extracted:
            key = (row.get("kind"), row.get("source_file"), row.get("line"), row.get("route"), tuple(row.get("methods") or []))
            if key in seen:
                continue
            seen.add(key)
            rows.append(row)
    return rows


def build_module_records(file_rows: list[dict[str, Any]], route_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    modules: dict[str, dict[str, Any]] = {}
    for row in file_rows:
        module = str(row.get("module") or "unknown")
        item = modules.setdefault(
            module,
            {
                "schema": "smart_center.code_knowledge.v1",
                "kind": "module_summary",
                "module": module,
                "files": [],
                "routes": [],
                "permissions": set(),
                "risks": set(),
                "tags": set(),
                "control_paths": set(),
                "purposes": [],
            },
        )
        item["files"].append(row["source_file"])
        if row.get("risk"):
            item["risks"].add(str(row.get("risk")))
        for tag in row.get("tags") or []:
            item["tags"].add(str(tag))
        for control_path in row.get("control_paths") or []:
            item["control_paths"].add(str(control_path))
        if row.get("purpose"):
            item["purposes"].append(str(row["purpose"]))
    for row in route_rows:
        source_file = str(row.get("source_file") or "")
        module = next((file_row.get("module") for file_row in file_rows if file_row.get("source_file") == source_file), Path(source_file).stem)
        item = modules.setdefault(
            str(module),
            {
                "schema": "smart_center.code_knowledge.v1",
                "kind": "module_summary",
                "module": str(module),
                "files": [],
                "routes": [],
                "permissions": set(),
                "risks": set(),
                "tags": set(),
                "control_paths": set(),
                "purposes": [],
            },
        )
        if row.get("route"):
            item["routes"].append(row.get("route"))
        if row.get("permission"):
            item["permissions"].add(str(row.get("permission")))
        if row.get("risk"):
            item["risks"].add(str(row.get("risk")))
    results = []
    for module, item in sorted(modules.items()):
        purposes = []
        for purpose in item["purposes"]:
            if purpose and purpose not in purposes:
                purposes.append(purpose)
            if len(purposes) >= 4:
                break
        results.append(
            {
                "schema": item["schema"],
                "kind": item["kind"],
                "module": module,
                "files": sorted(set(item["files"])),
                "routes": sorted(set(item["routes"])),
                "permissions": sorted(item["permissions"]),
                "risks": sorted(item["risks"]),
                "tags": sorted(item["tags"]),
                "control_paths": sorted(item["control_paths"]),
                "summary": _shorten(f"{module} owns: {' '.join(purposes)}", 900),
            }
        )
    return results


def build_design_records(file_rows: list[dict[str, Any]], route_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    control_routes = [row for row in route_rows if row.get("risk") in {"high", "medium"} and row.get("kind") == "api_route"]
    feishu_files = [row for row in file_rows if "feishu" in (row.get("tags") or [])]
    model_files = [row for row in file_rows if "local_model" in (row.get("tags") or []) or "knowledge" in (row.get("tags") or [])]
    return [
        {
            "schema": "smart_center.code_knowledge.v1",
            "kind": "design_note",
            "topic": "feishu_natural_language_control_boundary",
            "title": "飞书自然语言控制边界",
            "summary": (
                "飞书入口应只做消息解析、确认交互和审计上下文；模型只能分类或改写自然语言，"
                "最终执行必须回到 Smart Center API 权限、锁、审计和二次确认链路。"
            ),
            "evidence_files": sorted(row["source_file"] for row in feishu_files[:12]),
            "related_routes": sorted(row["route"] for row in control_routes[:40]),
        },
        {
            "schema": "smart_center.code_knowledge.v1",
            "kind": "design_note",
            "topic": "local_model_knowledge_pipeline",
            "title": "本地模型知识库流水线",
            "summary": (
                "模型学习应分成运行知识和代码知识两类。运行知识来自配置、设备、日志和 insights；"
                "代码知识来自 AI 标记、路由、权限、模块索引和设计文档。高频变化状态用 RAG，不宜固化到微调。"
            ),
            "evidence_files": sorted(row["source_file"] for row in model_files[:16]),
            "related_routes": sorted(row["route"] for row in route_rows if str(row.get("route") or "").startswith("/api/local-model")),
        },
        {
            "schema": "smart_center.code_knowledge.v1",
            "kind": "design_note",
            "topic": "physical_control_safety",
            "title": "真实设备控制安全",
            "summary": (
                "强电、时序电源、UPS、服务器关机/重启、投影/幕布/空调等真实控制必须有清晰目标、权限校验、"
                "operation lock 和确认策略。裸回路编号、模糊场馆名、模型低置信输出不能直接执行。"
            ),
            "evidence_files": sorted({row["source_file"] for row in file_rows if row.get("risk") and ("高" in str(row.get("risk")) or str(row.get("risk")) == "high")})[:30],
            "related_routes": sorted(row["route"] for row in control_routes),
        },
    ]


def _jsonl_write(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def build_code_knowledge_export(out_dir: Path | None = None) -> dict[str, Any]:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = ensure_directory(out_dir or _training_dir())
    files = iter_source_files()
    file_rows = build_file_records(files)
    route_rows = build_route_records(files)
    module_rows = build_module_records(file_rows, route_rows)
    design_rows = build_design_records(file_rows, route_rows)
    all_rows = file_rows + route_rows + module_rows + design_rows
    output_files = {
        "code_files": out_dir / f"code_files_{stamp}.jsonl",
        "code_routes": out_dir / f"code_routes_{stamp}.jsonl",
        "code_modules": out_dir / f"code_modules_{stamp}.jsonl",
        "code_design": out_dir / f"code_design_{stamp}.jsonl",
        "code_knowledge": out_dir / f"code_knowledge_{stamp}.jsonl",
        "code_manifest": out_dir / f"code_manifest_{stamp}.json",
    }
    _jsonl_write(output_files["code_files"], file_rows)
    _jsonl_write(output_files["code_routes"], route_rows)
    _jsonl_write(output_files["code_modules"], module_rows)
    _jsonl_write(output_files["code_design"], design_rows)
    _jsonl_write(output_files["code_knowledge"], all_rows)
    manifest = {
        "schema": "smart_center.code_knowledge_export.v1",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "project_root": str(PROJECT_ROOT),
        "counts": {
            "source_files": len(file_rows),
            "routes": len(route_rows),
            "modules": len(module_rows),
            "design_notes": len(design_rows),
            "all_rows": len(all_rows),
        },
        "files": {name: str(path) for name, path in output_files.items()},
        "recommended_use": [
            "Feed code_knowledge_*.jsonl to the local-model knowledge proxy as source-code navigation context.",
            "Use runtime devices/logs/insights from export_local_model_training.py for changing production facts.",
            "Do not let the model execute route paths directly; route execution must stay inside Smart Center permission and confirmation APIs.",
        ],
    }
    output_files["code_manifest"].write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "generated_at": manifest["generated_at"], "counts": manifest["counts"], "files": manifest["files"]}


def main() -> None:
    parser = argparse.ArgumentParser(description="Export structured Smart Center source-code knowledge for local-model RAG.")
    parser.add_argument("--out-dir", default="", help="output directory; defaults to SMART_CENTER_DATA_DIR/training/local_model")
    args = parser.parse_args()
    out_dir = Path(args.out_dir).expanduser().resolve() if args.out_dir else None
    result = build_code_knowledge_export(out_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
