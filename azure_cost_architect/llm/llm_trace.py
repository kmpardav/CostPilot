from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..utils.trace import TraceLogger


# -----------------------------------------------------------------------------
# LLM Trace policy
#
# - By default (pipeline/verbose), we log hashes + metadata (safe, light).
# - At debug level OR when COSTPILOT_TRACE_LLM_FULL=1, we persist full payloads:
#     runs/<run_id>/llm_payloads/prompt_<sha>.txt
#     runs/<run_id>/llm_payloads/response_<sha>.txt
#
# Redaction is applied before writing payload files.
# -----------------------------------------------------------------------------

ENV_TRACE_LLM_FULL = "COSTPILOT_TRACE_LLM_FULL"

_REDACT_PATTERNS: list[tuple[re.Pattern, str]] = [
    # OpenAI keys / bearer tokens
    (re.compile(r"\bsk-[A-Za-z0-9]{10,}\b"), "<REDACTED:OPENAI_KEY>"),
    (re.compile(r"(?i)\bBearer\s+[A-Za-z0-9\-\._~\+\/]+=*\b"), "Bearer <REDACTED:TOKEN>"),
    # Azure-ish secrets (best-effort)
    (re.compile(r"(?i)AccountKey=[^;\"'\s]+"), "AccountKey=<REDACTED:ACCOUNT_KEY>"),
    (re.compile(r"(?i)SharedAccessSignature=[^;\"'\s]+"), "SharedAccessSignature=<REDACTED:SAS>"),
    (re.compile(r"(?i)\bsig=[^&\"'\s]+"), "sig=<REDACTED:SAS_SIG>"),
]


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _redact(text: str) -> str:
    if not text:
        return text
    out = text
    for pat, repl in _REDACT_PATTERNS:
        out = pat.sub(repl, out)
    return out


def _payload_dir(trace: TraceLogger) -> Path:
    # trace.path == runs/<run_id>/trace.jsonl
    return trace.path.parent / "llm_payloads"


def _write_payload(trace: TraceLogger, kind: str, text: str) -> Dict[str, Any]:
    redacted = _redact(text or "")
    h = _sha256(redacted)
    d = _payload_dir(trace)
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{kind}_{h}.txt"
    if not p.exists():
        p.write_text(redacted, encoding="utf-8")
    return {"sha256": h, "path": str(p), "chars": len(redacted)}


def _want_full_payloads(trace: Optional[TraceLogger]) -> bool:
    if not trace or not trace.enabled:
        return False
    v = (os.getenv(ENV_TRACE_LLM_FULL, "") or "").strip().lower()
    if v in {"1", "true", "yes", "y"}:
        return True
    return bool(getattr(trace, "is_debug", False))


def _messages_transcript(messages: List[Dict[str, Any]]) -> str:
    lines: list[str] = []
    for m in messages:
        role = m.get("role", "unknown")
        content = m.get("content", "")
        lines.append(f"[{role}]\n{content}\n")
    return ("\n".join(lines)).strip() + "\n"


def trace_llm_request(
    trace: Optional[TraceLogger],
    *,
    stage: str,
    backend: str,
    model: str,
    messages: List[Dict[str, Any]],
    temperature: float,
    response_format: Optional[Dict[str, Any]] = None,
    max_tokens: Optional[int] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    if not trace or not trace.enabled:
        return

    data: Dict[str, Any] = {
        "stage": stage,
        "backend": backend,
        "model": model,
        "temperature": temperature,
        "response_format": response_format,
        "max_tokens": max_tokens,
        "messages_count": len(messages),
    }
    if extra:
        data.update(extra)

    if _want_full_payloads(trace):
        transcript = _messages_transcript(messages)
        data["prompt_payload"] = _write_payload(trace, "prompt", transcript)
    else:
        joined = "\n".join((m.get("role", "") + ":" + str(m.get("content", ""))) for m in messages)
        data["prompt_sha256"] = _sha256(_redact(joined))

    trace.event("llm.request", message=f"{stage} request", data=data)


def trace_llm_response(
    trace: Optional[TraceLogger],
    *,
    stage: str,
    backend: str,
    model: str,
    raw_text: str,
    finish_reason: Optional[str] = None,
    usage: Optional[Dict[str, Any]] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    if not trace or not trace.enabled:
        return

    data: Dict[str, Any] = {
        "stage": stage,
        "backend": backend,
        "model": model,
        "finish_reason": finish_reason,
        "usage": usage,
        "response_chars": len(raw_text or ""),
    }
    if extra:
        data.update(extra)

    if _want_full_payloads(trace):
        data["response_payload"] = _write_payload(trace, "response", raw_text or "")
    else:
        data["response_sha256"] = _sha256(_redact(raw_text or ""))

    trace.event("llm.response", message=f"{stage} response", data=data)


def trace_llm_parse(
    trace: Optional[TraceLogger],
    *,
    stage: str,
    ok: bool,
    error: Optional[str] = None,
    extracted_json_chars: Optional[int] = None,
) -> None:
    if not trace or not trace.enabled:
        return
    trace.event(
        "llm.parse",
        message=f"{stage} parse ok={ok}",
        data={"stage": stage, "ok": ok, "error": error, "extracted_json_chars": extracted_json_chars},
    )


def trace_llm_validate(
    trace: Optional[TraceLogger],
    *,
    stage: str,
    ok: bool,
    errors: Optional[list[dict]] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    if not trace or not trace.enabled:
        return
    data: Dict[str, Any] = {"stage": stage, "ok": ok, "errors": errors or []}
    if extra:
        data.update(extra)
    trace.event("llm.validate", message=f"{stage} validate ok={ok}", data=data)


def trace_llm_accepted(
    trace: Optional[TraceLogger],
    *,
    stage: str,
    note: str,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    if not trace or not trace.enabled:
        return
    data: Dict[str, Any] = {"stage": stage}
    if extra:
        data.update(extra)
    trace.event("llm.accepted", message=f"{stage}: {note}", data=data)
