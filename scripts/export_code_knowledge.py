#!/usr/bin/env python3
# AI_MODULE: code_knowledge_exporter
# AI_PURPOSE: Export Smart Center source-code structure, AI markers, routes, module cards, and redacted code chunks for local-model RAG.
# AI_BOUNDARY: Produces knowledge files only; it must not import runtime device drivers in ways that poll or control real hardware.
# AI_DATA_FLOW: Git/worktree source files -> AI marker extraction, route scan, redacted chunks -> training/local_model code_*.json/jsonl.
# AI_RUNTIME: Run manually or through scripts/export_local_model_training.py on node-120 before refreshing the local-model knowledge context.
# AI_RISK: Medium. Bad exclusions or redaction can leak secrets or teach stale/generated code as source of truth.
# AI_COMPAT: code_manifest/code_system_map/code_knowledge/full_code_context schemas are consumed by local-model pages and refresh scripts.
# AI_SEARCH_KEYWORDS: code knowledge, AI markers, RAG, full_code_context, module_cards, route scan.
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
    "config.json",
    "*.env",
    "*.pem",
    "*.key",
    "auth_users.json",
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
FULL_CONTEXT_SUFFIXES = {
    ".py",
    ".js",
    ".html",
    ".css",
    ".md",
    ".yaml",
    ".yml",
    ".txt",
    ".ps1",
    ".sh",
}
FULL_CONTEXT_JSON_ALLOWLIST = (
    "docs/LOCAL_MODEL_CONTROL_INTENTS.jsonl",
    "docs/LOCAL_MODEL_QUERY_INTENTS.jsonl",
)
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
REQUIRED_AI_KEYS = (
    "AI_MODULE",
    "AI_PURPOSE",
    "AI_BOUNDARY",
    "AI_RISK",
)
ROUTE_DECORATOR_RE = re.compile(r"@(?:\w+\.)?route\((?P<args>.*)\)")
PERMISSION_RE = re.compile(r"@require_permission\((?P<args>[^)]*)\)")
JS_API_RE = re.compile(r"['\"](?P<path>/api/[A-Za-z0-9_./<>{}:?=&%~+*\\-]+)['\"]")
CONFIG_KEY_RE = re.compile(r"(?:CONFIG|get\()\s*(?:\[|\()\s*['\"](?P<key>[A-Za-z0-9_\\-]+)['\"]")
SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)(?P<prefix>['\"]?(?:password|passwd|token|secret|api_key|apikey|authorization|access_key|private_key|community)['\"]?\s*[:=]\s*)"
    r"(?P<quote>['\"]?)(?P<value>[^'\"\\s,}\\]]+)(?P=quote)"
)
RTSP_AUTH_RE = re.compile(r"(?i)(rtsp://)([^:@/\\s]+):([^@/\\s]+)@")
BEARER_RE = re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+")


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


def _redact_source_text(text: str) -> str:
    redacted = RTSP_AUTH_RE.sub(r"\1***:***@", text)
    redacted = BEARER_RE.sub(r"\1***REDACTED***", redacted)
    return SECRET_ASSIGNMENT_RE.sub(r"\g<prefix>\g<quote>***REDACTED***\g<quote>", redacted)


def _full_context_allowed(path: Path) -> bool:
    rel_path = _rel(path)
    lower = rel_path.lower()
    if rel_path in FULL_CONTEXT_JSON_ALLOWLIST:
        return True
    if path.suffix.lower() not in FULL_CONTEXT_SUFFIXES:
        return False
    if any(token in lower for token in ("/.env", "secret", "private", "credential", "auth_users", "config.json")):
        return False
    if any(token in lower for token in ("/static/vendor/", ".min.js", ".min.css", "/node_modules/", "/dist/")):
        return False
    if path.stat().st_size > 1_200_000:
        return False
    return True


def _chunk_source_text(text: str, *, max_chars: int = 12000, max_lines: int = 260) -> list[tuple[int, int, str]]:
    chunks: list[tuple[int, int, str]] = []
    lines = text.splitlines()
    current: list[str] = []
    current_chars = 0
    start_line = 1
    for index, line in enumerate(lines, 1):
        line_size = len(line) + 1
        if current and (current_chars + line_size > max_chars or len(current) >= max_lines):
            chunks.append((start_line, index - 1, "\n".join(current)))
            current = []
            current_chars = 0
            start_line = index
        current.append(line)
        current_chars += line_size
    if current:
        chunks.append((start_line, start_line + len(current) - 1, "\n".join(current)))
    return chunks


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


def _marker_required_for_file(row: dict[str, Any]) -> bool:
    rel_path = str(row.get("source_file") or "")
    suffix = str(row.get("suffix") or "")
    if rel_path.startswith(("tests/", ".baseline_reports/", "deploy/meter_service_bundle/")):
        return False
    if suffix in {".bat", ".cmd", ".txt"}:
        return False
    if rel_path.startswith("docs/"):
        return rel_path in {
            "docs/AI_NAVIGATION.md",
            "docs/AI_CODE_MARKERS.md",
            "docs/LOCAL_MODEL_LEARNING.md",
            "docs/QUERY_KNOWLEDGE_BASE.md",
            "docs/MODULE_INDEX.yaml",
        }
    if rel_path.startswith(("api/", "services/", "runtime/", "drivers/", "templates/", "static/js/", "scripts/")):
        return True
    if rel_path.endswith("_core.py") or rel_path in {
        "app.py",
        "background.py",
        "config.py",
        "data_logger.py",
        "event_logger.py",
        "modbus_core.py",
        "paths.py",
        "power.py",
        "screen_core.py",
        "snmp_core.py",
        "universal_core.py",
    }:
        return True
    return False


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


def build_marker_coverage(file_rows: list[dict[str, Any]]) -> dict[str, Any]:
    missing_required: list[dict[str, Any]] = []
    missing_any: list[dict[str, Any]] = []
    complete_count = 0
    required_target_count = 0
    required_target_complete_count = 0
    for row in file_rows:
        markers = row.get("ai_markers") if isinstance(row.get("ai_markers"), dict) else {}
        present = sorted(key for key in AI_KEYS if markers.get(key))
        required_missing = [key for key in REQUIRED_AI_KEYS if not markers.get(key)]
        any_missing = [key for key in AI_KEYS if not markers.get(key)]
        marker_required = _marker_required_for_file(row)
        if not any_missing:
            complete_count += 1
        if marker_required:
            required_target_count += 1
            if not required_missing:
                required_target_complete_count += 1
        if marker_required and required_missing:
            missing_required.append(
                {
                    "source_file": row.get("source_file"),
                    "module": row.get("module"),
                    "line_count": row.get("line_count"),
                    "present": present,
                    "missing": required_missing,
                    "risk": row.get("risk") or "",
                }
            )
        if any_missing:
            missing_any.append(
                {
                    "source_file": row.get("source_file"),
                    "module": row.get("module"),
                    "present_count": len(present),
                    "missing": any_missing,
                    "risk": row.get("risk") or "",
                }
            )
    total = len(file_rows)
    return {
        "schema": "smart_center.ai_marker_coverage.v1",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "required_keys": list(REQUIRED_AI_KEYS),
        "all_keys": list(AI_KEYS),
        "counts": {
            "source_files": total,
            "marker_required_files": required_target_count,
            "complete_all_markers": complete_count,
            "required_target_complete": required_target_complete_count,
            "required_target_missing_required": len(missing_required),
            "missing_any_marker": len(missing_any),
            "coverage_percent_all_markers": round((complete_count / total * 100) if total else 100, 2),
            "coverage_percent_required_targets": round(
                (required_target_complete_count / required_target_count * 100) if required_target_count else 100,
                2,
            ),
        },
        "missing_required_top": sorted(
            missing_required,
            key=lambda item: (str(item.get("risk") or ""), -(int(item.get("line_count") or 0)), str(item.get("source_file") or "")),
            reverse=True,
        )[:120],
        "missing_any_top": missing_any[:240],
        "long_term_rule": "Every Smart Center code change should keep AI_* markers current so node-123 can learn module purpose, boundaries, data flow, runtime, risk, compatibility, and search keywords.",
    }


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


def build_module_cards(module_rows: list[dict[str, Any]], file_rows: list[dict[str, Any]], route_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    file_by_module: dict[str, list[dict[str, Any]]] = {}
    route_by_module: dict[str, list[dict[str, Any]]] = {}
    for row in file_rows:
        file_by_module.setdefault(str(row.get("module") or "unknown"), []).append(row)
    for route in route_rows:
        source_file = str(route.get("source_file") or "")
        module = next((str(row.get("module") or "unknown") for row in file_rows if row.get("source_file") == source_file), Path(source_file).stem)
        route_by_module.setdefault(module, []).append(route)
    cards: list[dict[str, Any]] = []
    for module in sorted({str(row.get("module") or "unknown") for row in module_rows}):
        module_file_rows = file_by_module.get(module, [])
        module_route_rows = route_by_module.get(module, [])
        purposes = []
        boundaries = []
        for row in module_file_rows:
            purpose = str(row.get("purpose") or "").strip()
            boundary = str(row.get("boundary") or "").strip()
            if purpose and purpose not in purposes:
                purposes.append(purpose)
            if boundary and boundary not in boundaries:
                boundaries.append(boundary)
        risks = sorted({str(row.get("risk") or "") for row in module_file_rows + module_route_rows if row.get("risk")})
        control_paths = sorted({path for row in module_file_rows for path in (row.get("control_paths") or [])})
        cards.append(
            {
                "schema": "smart_center.module_card.v1",
                "kind": "module_card",
                "module": module,
                "purpose": _shorten(" ".join(purposes[:3]), 900),
                "boundary": _shorten(" ".join(boundaries[:3]), 700),
                "files": sorted(str(row.get("source_file") or "") for row in module_file_rows),
                "routes": sorted(str(row.get("route") or "") for row in module_route_rows if row.get("route")),
                "permissions": sorted({str(row.get("permission") or "") for row in module_route_rows if row.get("permission")}),
                "risk": risks[-1] if risks else "",
                "risk_notes": risks,
                "control_paths": control_paths,
                "search_keywords": sorted({tag for row in module_file_rows for tag in (row.get("tags") or [])})[:40],
                "model_use": "用于让本地模型快速定位模块边界、关键文件、API 路由和真实控制风险；不能作为直接执行依据。",
            }
        )
    return cards


def build_code_system_map(
    file_rows: list[dict[str, Any]],
    route_rows: list[dict[str, Any]],
    module_rows: list[dict[str, Any]],
    design_rows: list[dict[str, Any]],
    module_cards: list[dict[str, Any]],
) -> dict[str, Any]:
    api_routes = [row for row in route_rows if row.get("kind") == "api_route"]
    frontend_refs = [row for row in route_rows if row.get("kind") == "frontend_api_reference"]
    high_risk_routes = [row for row in api_routes if row.get("risk") == "high"]
    medium_risk_routes = [row for row in api_routes if row.get("risk") == "medium"]
    control_modules = sorted(
        {
            str(row.get("module") or "")
            for row in module_cards
            if row.get("control_paths") or row.get("risk") in {"high", "medium", "高", "中"}
        }
    )
    marker_coverage = build_marker_coverage(file_rows)
    return {
        "schema": "smart_center.code_system_map.v1",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "project_root": str(PROJECT_ROOT),
        "counts": {
            "source_files": len(file_rows),
            "api_routes": len(api_routes),
            "frontend_api_references": len(frontend_refs),
            "modules": len(module_rows),
            "module_cards": len(module_cards),
            "design_notes": len(design_rows),
            "high_risk_routes": len(high_risk_routes),
            "medium_risk_routes": len(medium_risk_routes),
            "ai_marker_complete_all": marker_coverage["counts"]["complete_all_markers"],
            "ai_marker_missing_required": marker_coverage["counts"]["required_target_missing_required"],
        },
        "ai_marker_coverage": marker_coverage["counts"],
        "ai_marker_rule": marker_coverage["long_term_rule"],
        "entrypoints": {
            "flask_app": "app.py",
            "main_template": "templates/index.html",
            "local_model_api": "api/local_model.py",
            "feishu_adapter": "services/feishu_bot.py",
            "control_router": "services/control_intent_router.py",
            "training_export": "scripts/export_local_model_training.py",
        },
        "module_index": [
            {
                "module": row.get("module"),
                "file_count": len(row.get("files") or []),
                "route_count": len(row.get("routes") or []),
                "risk": row.get("risk") or "",
                "purpose": row.get("purpose") or "",
                "top_files": (row.get("files") or [])[:8],
            }
            for row in module_cards
        ],
        "control_boundary": {
            "model_role": "本地模型只能做意图理解、代码/运行知识检索、模糊文本改写和摘要。",
            "execution_role": "真实控制必须回到 Smart Center API、权限、操作锁、审计和确认策略。",
            "high_risk_route_samples": [
                {"route": row.get("route"), "source_file": row.get("source_file"), "permission": row.get("permission")}
                for row in high_risk_routes[:80]
            ],
            "medium_risk_route_samples": [
                {"route": row.get("route"), "source_file": row.get("source_file"), "permission": row.get("permission")}
                for row in medium_risk_routes[:80]
            ],
            "control_modules": control_modules,
        },
        "knowledge_strategy": {
            "primary": "结构化 RAG 知识包，适合快速变化的设备、状态、日志和代码边界。",
            "high_context_refresh": "定期生成 full_code_context_*.jsonl，让 128K/256K 上下文本地模型周期性阅读脱敏源码上下文并生成更完整的系统理解。",
            "fine_tuning": "只用于人工审核后的 query/control 示例，不用于原始源码、密钥、配置快照或未审核日志。",
        },
    }


def build_full_code_context(files: list[Path], file_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    meta_by_file = {str(row.get("source_file") or ""): row for row in file_rows}
    rows: list[dict[str, Any]] = []
    for path in files:
        if not _full_context_allowed(path):
            continue
        rel_path = _rel(path)
        text = _redact_source_text(_read_text(path))
        if not text.strip():
            continue
        file_meta = meta_by_file.get(rel_path, {})
        for chunk_index, (start_line, end_line, chunk_text) in enumerate(_chunk_source_text(text), 1):
            rows.append(
                {
                    "schema": "smart_center.full_code_context.v1",
                    "kind": "source_chunk",
                    "source_file": rel_path,
                    "module": file_meta.get("module") or _module_from_path(rel_path, file_meta.get("ai_markers") or {}),
                    "suffix": path.suffix.lower(),
                    "chunk_index": chunk_index,
                    "line_start": start_line,
                    "line_end": end_line,
                    "sha256": _sha256_text(chunk_text),
                    "purpose": file_meta.get("purpose") or "",
                    "risk": file_meta.get("risk") or "",
                    "tags": file_meta.get("tags") or [],
                    "content": chunk_text,
                    "safety_note": "已排除运行配置和常见密钥文件，并对源码中的 token/password/RTSP 凭据做基础脱敏；该内容只用于高上下文理解和 RAG，不可直接执行控制。",
                }
            )
    return rows


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
                "代码知识来自 AI 标记、路由、权限、模块索引和设计文档。高频变化状态用 RAG；"
                "3090 高显存机器可周期性读取脱敏 full_code_context，但不宜把原始全量源码固化到微调。"
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
    return build_code_knowledge_export_with_options(out_dir=out_dir, include_full_context=True)


def build_code_knowledge_export_with_options(out_dir: Path | None = None, *, include_full_context: bool = True) -> dict[str, Any]:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = ensure_directory(out_dir or _training_dir())
    files = iter_source_files()
    file_rows = build_file_records(files)
    route_rows = build_route_records(files)
    module_rows = build_module_records(file_rows, route_rows)
    design_rows = build_design_records(file_rows, route_rows)
    module_card_rows = build_module_cards(module_rows, file_rows, route_rows)
    marker_coverage = build_marker_coverage(file_rows)
    system_map = build_code_system_map(file_rows, route_rows, module_rows, design_rows, module_card_rows)
    full_context_rows = build_full_code_context(files, file_rows) if include_full_context else []
    all_rows = file_rows + route_rows + module_rows + design_rows + module_card_rows
    output_files = {
        "code_files": out_dir / f"code_files_{stamp}.jsonl",
        "code_routes": out_dir / f"code_routes_{stamp}.jsonl",
        "code_modules": out_dir / f"code_modules_{stamp}.jsonl",
        "module_cards": out_dir / f"module_cards_{stamp}.jsonl",
        "code_design": out_dir / f"code_design_{stamp}.jsonl",
        "ai_marker_coverage": out_dir / f"ai_marker_coverage_{stamp}.json",
        "code_knowledge": out_dir / f"code_knowledge_{stamp}.jsonl",
        "code_system_map": out_dir / f"code_system_map_{stamp}.json",
        "code_manifest": out_dir / f"code_manifest_{stamp}.json",
    }
    if include_full_context:
        output_files["full_code_context"] = out_dir / f"full_code_context_{stamp}.jsonl"
    _jsonl_write(output_files["code_files"], file_rows)
    _jsonl_write(output_files["code_routes"], route_rows)
    _jsonl_write(output_files["code_modules"], module_rows)
    _jsonl_write(output_files["module_cards"], module_card_rows)
    _jsonl_write(output_files["code_design"], design_rows)
    _jsonl_write(output_files["code_knowledge"], all_rows)
    output_files["ai_marker_coverage"].write_text(json.dumps(marker_coverage, ensure_ascii=False, indent=2), encoding="utf-8")
    output_files["code_system_map"].write_text(json.dumps(system_map, ensure_ascii=False, indent=2), encoding="utf-8")
    if include_full_context:
        _jsonl_write(output_files["full_code_context"], full_context_rows)
    manifest = {
        "schema": "smart_center.code_knowledge_export.v1",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "project_root": str(PROJECT_ROOT),
        "counts": {
            "source_files": len(file_rows),
            "routes": len(route_rows),
            "modules": len(module_rows),
            "module_cards": len(module_card_rows),
            "design_notes": len(design_rows),
            "full_code_context_chunks": len(full_context_rows),
            "all_rows": len(all_rows),
            "ai_marker_complete_all": marker_coverage["counts"]["complete_all_markers"],
            "ai_marker_missing_required": marker_coverage["counts"]["required_target_missing_required"],
        },
        "files": {name: str(path) for name, path in output_files.items()},
        "recommended_use": [
            "Feed code_knowledge_*.jsonl to the local-model knowledge proxy as source-code navigation context.",
            "Feed module_cards_*.jsonl and code_system_map_*.json before full_code_context_*.jsonl so the model sees module boundaries first.",
            "Use full_code_context_*.jsonl only for high-context periodic refresh or RAG indexing; it is redacted source context, not a control executor.",
            "Use runtime devices/logs/insights from export_local_model_training.py for changing production facts.",
            "Do not let the model execute route paths directly; route execution must stay inside Smart Center permission and confirmation APIs.",
            "For future code changes, update AI_* markers in touched files and review ai_marker_coverage_*.json before refreshing node-123 knowledge.",
        ],
    }
    output_files["code_manifest"].write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "generated_at": manifest["generated_at"], "counts": manifest["counts"], "files": manifest["files"]}


def main() -> None:
    parser = argparse.ArgumentParser(description="Export structured Smart Center source-code knowledge for local-model RAG.")
    parser.add_argument("--out-dir", default="", help="output directory; defaults to SMART_CENTER_DATA_DIR/training/local_model")
    parser.add_argument("--skip-full-code-context", action="store_true", help="skip redacted source chunks for high-context model refresh")
    args = parser.parse_args()
    out_dir = Path(args.out_dir).expanduser().resolve() if args.out_dir else None
    result = build_code_knowledge_export_with_options(out_dir, include_full_context=not args.skip_full_code_context)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
