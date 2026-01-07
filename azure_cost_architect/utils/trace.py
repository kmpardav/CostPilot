"""Lightweight JSONL tracing helper for deterministic runs.

Why this exists
--------------
CostPilot debugging needs more than normal INFO logs.

We want:
1) A structured, append-only JSONL trace for machines (tools/grep).
2) A human-readable narrative that explains what happened step-by-step.

Compatibility
-------------
Older code writes events with fields {timestamp, phase, payload}.
This module keeps that working, while adding a richer event model.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, Optional, Union


TraceLevel = Union[str]


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _coerce_level(level: Optional[str]) -> str:
    lvl = (level or "pipeline").strip().lower()
    if lvl not in {"pipeline", "verbose", "debug"}:
        return "pipeline"
    return lvl


@dataclass
class TraceLogger:
    """
    Append-only JSONL trace writer.

    Levels:
      - pipeline: major steps only (safe default)
      - verbose: include important decisions (cache hit/miss, filters, counts)
      - debug: include deep spans + optional payload snapshots
    """

    path: Path
    enabled: bool = True
    level: str = "pipeline"
    story_enabled: bool = False
    _initialized: bool = field(default=False, init=False, repr=False)
    _span_stack: list = field(default_factory=list, init=False, repr=False)

    @property
    def is_verbose(self) -> bool:
        return self.level in {"verbose", "debug"}

    @property
    def is_debug(self) -> bool:
        return self.level == "debug"

    def _ensure_parent(self) -> None:
        if self._initialized:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialized = True

    def _write(self, obj: Dict[str, Any]) -> None:
        if not self.enabled:
            return
        self._ensure_parent()
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")

    # --- Back-compat API (phase + payload) ---
    def log(
        self,
        phase: str,
        payload: Dict[str, Any],
        *,
        scenario_id: Optional[str] = None,
        resource_id: Optional[str] = None,
    ) -> None:
        obj: Dict[str, Any] = {
            "timestamp": _utc_iso(),
            "phase": phase,
            "payload": payload,
        }
        if scenario_id:
            obj["scenario_id"] = scenario_id
        if resource_id:
            obj["resource_id"] = resource_id
        self._write(obj)

    # --- Rich event API ---
    def event(
        self,
        name: str,
        *,
        message: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
        scenario_id: Optional[str] = None,
        resource_id: Optional[str] = None,
    ) -> None:
        obj: Dict[str, Any] = {
            "timestamp": _utc_iso(),
            "kind": "event",
            "name": name,
            "message": message,
            "data": data or {},
            "span": list(self._span_stack),
        }
        if scenario_id:
            obj["scenario_id"] = scenario_id
        if resource_id:
            obj["resource_id"] = resource_id
        self._write(obj)

    def note(self, message: str, *, data: Optional[Dict[str, Any]] = None) -> None:
        self.event("note", message=message, data=data)

    def anomaly(
        self,
        name: str,
        *,
        message: str,
        data: Optional[Dict[str, Any]] = None,
        scenario_id: Optional[str] = None,
        resource_id: Optional[str] = None,
    ) -> None:
        # Always write anomalies regardless of level; they're the whole point.
        self.event(
            f"anomaly.{name}",
            message=message,
            data=data or {},
            scenario_id=scenario_id,
            resource_id=resource_id,
        )

    class _Span:
        def __init__(self, trace: "TraceLogger", name: str, message: Optional[str], data: Dict[str, Any]):
            self.trace = trace
            self.name = name
            self.message = message
            self.data = data
            self.t0 = 0.0

        def __enter__(self) -> "TraceLogger._Span":
            self.t0 = time.time()
            self.trace._span_stack.append(self.name)
            self.trace._write(
                {
                    "timestamp": _utc_iso(),
                    "kind": "span_start",
                    "name": self.name,
                    "message": self.message,
                    "data": self.data,
                    "span": list(self.trace._span_stack),
                }
            )
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            dur_ms = (time.time() - self.t0) * 1000.0
            self.trace._write(
                {
                    "timestamp": _utc_iso(),
                    "kind": "span_end",
                    "name": self.name,
                    "ok": exc is None,
                    "error": None if exc is None else repr(exc),
                    "duration_ms": round(dur_ms, 3),
                    "span": list(self.trace._span_stack),
                }
            )
            self.trace._span_stack.pop()

    def span(
        self,
        name: str,
        *,
        message: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
    ) -> "TraceLogger._Span":
        # Even at pipeline level spans are useful for the main stages.
        return TraceLogger._Span(self, name=name, message=message, data=data or {})

    # --- Story rendering ---
    def render_story_markdown(self, out_path: Path) -> Path:
        if not self.enabled:
            return out_path
        out_path.parent.mkdir(parents=True, exist_ok=True)

        lines: list[str] = []
        lines.append("# CostPilot run story")
        lines.append("")
        lines.append(f"- Trace file: `{self.path}`")
        lines.append("")

        def _indent(n: int) -> str:
            return "  " * n

        for ev in self._iter_events():
            kind = ev.get("kind")
            if kind == "span_start":
                depth = max(0, len(ev.get("span", [])) - 1)
                lines.append(f"{_indent(depth)}- **START** `{ev.get('name')}` — {ev.get('message') or ''}".rstrip())
                data = ev.get("data") or {}
                if data:
                    lines.append(f"{_indent(depth+1)}- data: `{json.dumps(data, ensure_ascii=False)}`")
            elif kind == "span_end":
                depth = max(0, len(ev.get("span", [])) - 1)
                ok = ev.get("ok")
                dur = ev.get("duration_ms")
                lines.append(
                    f"{_indent(depth)}- **END** `{ev.get('name')}` — ok={ok} ({dur} ms)"
                )
                err = ev.get("error")
                if err:
                    lines.append(f"{_indent(depth+1)}- error: `{err}`")
            elif kind == "event":
                name = ev.get("name")
                msg = ev.get("message") or ""
                depth = len(ev.get("span", []))
                if (name or "").startswith("anomaly."):
                    lines.append(f"{_indent(depth)}- ⚠️ **{name}** — {msg}".rstrip())
                elif name == "note":
                    lines.append(f"{_indent(depth)}- {msg}".rstrip())
                else:
                    lines.append(f"{_indent(depth)}- `{name}` — {msg}".rstrip())

        out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return out_path

    def _iter_events(self) -> Iterator[Dict[str, Any]]:
        if not self.path.exists():
            return iter(())
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except Exception:
                    # ignore bad lines
                    continue


def build_trace_logger(
    path: Path,
    *,
    enabled: bool = True,
    level: str = "pipeline",
    story_enabled: bool = False,
) -> TraceLogger:
    return TraceLogger(path=path, enabled=enabled, level=_coerce_level(level), story_enabled=story_enabled)


def traced(name: str, *, level: str = "debug"):
    """Decorator that records a span when trace level is high enough.

    - level='debug' means it only spans when TraceLogger.is_debug is True
    - level='verbose' means spans at verbose or debug
    - level='pipeline' means always spans when trace enabled
    """

    want = _coerce_level(level)

    def _should(trace: Any) -> bool:
        if not trace:
            return False
        if want == "pipeline":
            return True
        if want == "verbose":
            return getattr(trace, "is_verbose", False)
        return getattr(trace, "is_debug", False)

    def _wrap(fn):
        import inspect

        if inspect.iscoroutinefunction(fn):
            async def _inner(*args, **kwargs):
                trace = kwargs.get("trace")
                if _should(trace):
                    with trace.span(name, message=f"call {fn.__name__}"):
                        return await fn(*args, **kwargs)
                return await fn(*args, **kwargs)
            return _inner

        def _inner(*args, **kwargs):
            trace = kwargs.get("trace")
            if _should(trace):
                with trace.span(name, message=f"call {fn.__name__}"):
                    return fn(*args, **kwargs)
            return fn(*args, **kwargs)

        return _inner

    return _wrap
