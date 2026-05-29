"""Persistent feedback memory for natural-language controls.

AI_MODULE: control_learning
AI_PURPOSE: Let Feishu/local-model control routing improve from confirmed and
cancelled user actions without bypassing Smart Center safety checks.
AI_BOUNDARY: Stores examples and suggests previously confirmed command payloads;
execution, permissions, and confirmation remain outside this module.
AI_DATA_FLOW: source_text + command + outcome -> jsonl memory -> exact/near text
suggestions for later routing.
AI_RISK: Medium. Only confirmed examples are reusable; cancelled/rejected text is
remembered to avoid repeating bad guesses.
"""

from __future__ import annotations

import json
import time
from copy import deepcopy
from pathlib import Path
from typing import Any

from services.device_aliases import normalize_alias_text


class ControlLearningStore:
    def __init__(self, path: str | Path, *, max_rows: int = 2000) -> None:
        self.path = Path(path)
        self.max_rows = max(100, int(max_rows or 2000))

    def append(self, source_text: str, command: dict[str, Any] | None, outcome: str, *, reason: str = "") -> None:
        text = str(source_text or "").strip()
        if not text:
            return
        row = {
            "schema": "smart_center.control_feedback.v1",
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "source_text": text,
            "normalized_text": normalize_alias_text(text),
            "outcome": str(outcome or "").strip() or "unknown",
            "reason": str(reason or "").strip(),
            "command": self._safe_command(command),
        }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
            self._trim_if_needed()
        except Exception:
            return

    def suggest(self, source_text: str) -> dict[str, Any] | None:
        normalized = normalize_alias_text(source_text)
        if not normalized:
            return None
        best: tuple[int, int, dict[str, Any]] | None = None
        for index, row in enumerate(self._read_rows()):
            if row.get("outcome") not in {"confirmed", "executed", "direct_executed"}:
                continue
            row_norm = str(row.get("normalized_text") or "")
            command = row.get("command")
            if not row_norm or not isinstance(command, dict):
                continue
            score = 0
            if row_norm == normalized:
                score = 120
            elif len(row_norm) >= 4 and (row_norm in normalized or normalized in row_norm):
                score = 80 + min(len(row_norm), len(normalized), 30)
            if score and (best is None or (score, index) > (best[0], best[1])):
                best = (score, index, command)
        if not best or best[0] < 80:
            return None
        command = deepcopy(best[2])
        command["confidence"] = "medium"
        command["inference_reason"] = "来自之前已确认的自然语言控制记忆，仍按安全策略确认或执行。"
        return command

    def rejected_recently(self, source_text: str) -> bool:
        normalized = normalize_alias_text(source_text)
        if not normalized:
            return False
        for row in reversed(self._read_rows()[-100:]):
            if row.get("normalized_text") == normalized and row.get("outcome") in {"cancelled", "rejected"}:
                return True
        return False

    def _read_rows(self) -> list[dict[str, Any]]:
        if not self.path.is_file():
            return []
        rows: list[dict[str, Any]] = []
        try:
            for line in self.path.read_text(encoding="utf-8-sig", errors="ignore").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                if isinstance(row, dict):
                    rows.append(row)
        except Exception:
            return []
        return rows

    def _trim_if_needed(self) -> None:
        rows = self._read_rows()
        if len(rows) <= self.max_rows:
            return
        keep = rows[-self.max_rows :]
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as handle:
            for row in keep:
                handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
        tmp.replace(self.path)

    @staticmethod
    def _safe_command(command: dict[str, Any] | None) -> dict[str, Any]:
        if not isinstance(command, dict):
            return {}
        safe_keys = {
            "type",
            "risk",
            "label",
            "path",
            "payload",
            "action",
            "method",
            "timeout_sec",
            "confidence",
            "inference_reason",
        }
        return deepcopy({key: command.get(key) for key in safe_keys if key in command})
