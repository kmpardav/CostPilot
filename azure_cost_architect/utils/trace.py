"""Lightweight JSONL tracing helper for deterministic runs."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


@dataclass
class TraceLogger:
    """Append-only JSONL trace writer with structured phases."""

    path: Path
    enabled: bool = True
    _initialized: bool = field(default=False, init=False, repr=False)

    def _ensure_parent(self) -> None:
        if self._initialized:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialized = True

    def log(
        self,
        phase: str,
        payload: Dict[str, Any],
        *,
        scenario_id: Optional[str] = None,
        resource_id: Optional[str] = None,
    ) -> None:
        if not self.enabled:
            return

        self._ensure_parent()
        event: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "phase": phase,
            "payload": payload,
        }
        if scenario_id:
            event["scenario_id"] = scenario_id
        if resource_id:
            event["resource_id"] = resource_id

        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")


def build_trace_logger(path: Path | str, enabled: bool = True) -> TraceLogger:
    return TraceLogger(Path(path), enabled=enabled)


__all__ = ["TraceLogger", "build_trace_logger"]
