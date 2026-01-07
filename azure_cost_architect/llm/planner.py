import json
from dataclasses import dataclass
from typing import Any, Dict, Optional

from openai import OpenAI

from ..config import MODEL_PLANNER, MODEL_PLANNER_RESPONSES
from ..prompts import (
    PROMPT_PLANNER_SYSTEM,
    PROMPT_PLANNER_USER_TEMPLATE,
    PROMPT_JSON_REPAIR_SYSTEM,
    PROMPT_PLAN_REPAIR_SYSTEM,
)
from ..planner.contract import PlanValidationResult, validate_pricing_contract
from ..utils.trace import TraceLogger
from ..utils.knowledgepack import get_taxonomy_option_paths_for_category
from .json_repair import extract_json_object, repair_json_with_llm


@dataclass
class PlannerAttempt:
    attempt: int
    raw_response: str
    parsed: Optional[Dict[str, Any]]
    parse_error: Optional[str]
    validation: PlanValidationResult


def _is_plan_shaped(obj: Any) -> bool:
    """Minimal shape check: enough to prevent useless repair outputs."""
    if not isinstance(obj, dict):
        return False
    metadata = obj.get("metadata")
    scenarios = obj.get("scenarios")
    if not isinstance(metadata, dict):
        return False
    if not isinstance(scenarios, list) or not scenarios:
        return False
    return True


def _repair_to_plan_shape(
    client: OpenAI,
    *,
    repair_system_prompt: str,
    input_text: str,
    trace: Optional[TraceLogger] = None,
    attempt: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """
    Repair input_text into a plan-shaped JSON dict.
    Returns dict on success, None on failure (caller can continue loop).
    """
    try:
        repaired = repair_json_with_llm(client, repair_system_prompt, input_text)
    except Exception as ex:
        if trace:
            trace.log("planner_repair_exception", {"attempt": attempt, "error": str(ex)})
        return None

    if _is_plan_shaped(repaired):
        return repaired

    schema_prompt = (
        "You returned valid JSON, but it is not a valid plan object.\n"
        "Return a SINGLE JSON OBJECT with this minimal schema:\n"
        "{\n"
        '  "metadata": { ... },\n'
        '  "scenarios": [ { "id": "...", "label": "...", "resources": [ ... ] } ]\n'
        "}\n"
        "Do not wrap it in an array. Do not return partial fragments.\n\n"
        "Here is the previous output to transform into the required schema:\n"
        f"{json.dumps(repaired)}"
    )
    if trace:
        trace.log(
            "planner_repair_bad_shape",
            {
                "attempt": attempt,
                "got_keys": list(repaired.keys()) if isinstance(repaired, dict) else str(type(repaired)),
            },
        )
    try:
        repaired_retry = repair_json_with_llm(client, repair_system_prompt, schema_prompt)
    except Exception as ex:
        if trace:
            trace.log("planner_repair_exception_retry", {"attempt": attempt, "error": str(ex)})
        return None
    if _is_plan_shaped(repaired_retry):
        return repaired_retry
    if trace:
        trace.log("planner_repair_bad_shape_retry", {"attempt": attempt})
    return None


def _snippet(text: str, *, max_chars: int = 2000) -> str:
    """Return a bounded snippet for prompts/traces to avoid runaway token growth."""
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"\n...[truncated {len(text) - max_chars} chars]"


def _log_planner_trace(
    trace: Optional[TraceLogger],
    *,
    attempt: int,
    backend: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    raw: str,
    parsed: Optional[Dict[str, Any]],
    parse_error: Optional[str],
    validation: PlanValidationResult,
) -> None:
    if not trace:
        return
    trace.log(
        "phase1_planner",
        {
            "attempt": attempt,
            "backend": backend,
            "model": model,
            "temperature": 0.0,
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "raw_response": raw,
            "parsed": parsed,
            "parse_error": parse_error,
            "validation_errors": validation.errors,
        },
    )
    trace.log(
        "phase2_validation",
        {
            "attempt": attempt,
            "rule_changes": validation.rule_changes,
            "canonical_mappings": validation.canonical_mappings,
            "errors": validation.errors,
        },
    )


def _call_planner_chat(client: OpenAI, user_prompt: str) -> tuple[str, str]:
    completion = client.chat.completions.create(
        model=MODEL_PLANNER,
        response_format={"type": "json_object"},
        temperature=0.0,
        messages=[
            {"role": "system", "content": PROMPT_PLANNER_SYSTEM},
            {"role": "user", "content": user_prompt},
        ],
    )
    raw = completion.choices[0].message.content or ""
    return MODEL_PLANNER, raw


def _call_planner_responses(client: OpenAI, user_prompt: str) -> tuple[str, str]:
    response = client.responses.create(
        model=MODEL_PLANNER_RESPONSES,
        input=[
            {"role": "system", "content": PROMPT_PLANNER_SYSTEM},
            {"role": "user", "content": user_prompt},
        ],
        # Planner should be deterministic and reproducible; avoid web_search here.
        temperature=0.0,
    )
    # Be defensive: Responses output can contain multiple segments/items.
    parts: list[str] = []
    for out in getattr(response, "output", []) or []:
        for c in getattr(out, "content", []) or []:
            txt = getattr(c, "text", None)
            if txt:
                parts.append(txt)
    raw = "\n".join(parts).strip()
    return MODEL_PLANNER_RESPONSES, raw


def _parse_plan_json(raw: str, client: OpenAI) -> tuple[Optional[Dict[str, Any]], Optional[str]]:
    raw_json = extract_json_object(raw)
    try:
        parsed = json.loads(raw_json)
        return parsed, None
    except json.JSONDecodeError as ex:
        repaired = _repair_to_plan_shape(
            client,
            repair_system_prompt=PROMPT_JSON_REPAIR_SYSTEM,
            input_text=raw_json,
            trace=None,
            attempt=None,
        )
        if repaired is None:
            return None, f"repair_failed: {ex}"
        return repaired, str(ex)


def _planner_attempt(
    *,
    client: OpenAI,
    arch_text: str,
    mode: str,
    backend: str,
    trace: Optional[TraceLogger],
    attempt: int,
    planner_callable=None,
) -> PlannerAttempt:
    user_prompt = PROMPT_PLANNER_USER_TEMPLATE.format(arch_text=arch_text, mode=mode)
    model_used: str
    raw: str
    if planner_callable:
        model_used, raw = planner_callable(user_prompt)
    elif backend == "responses":
        model_used, raw = _call_planner_responses(client, user_prompt)
    else:
        model_used, raw = _call_planner_chat(client, user_prompt)

    parsed, parse_error = _parse_plan_json(raw, client)
    validation = validate_pricing_contract(parsed or {}, trace=trace)

    _log_planner_trace(
        trace,
        attempt=attempt,
        backend=backend,
        model=model_used,
        system_prompt=PROMPT_PLANNER_SYSTEM,
        user_prompt=user_prompt,
        raw=raw,
        parsed=parsed,
        parse_error=parse_error,
        validation=validation,
    )

    return PlannerAttempt(
        attempt=attempt,
        raw_response=raw,
        parsed=parsed,
        parse_error=parse_error,
        validation=validation,
    )


def _build_taxonomy_option_injection(
    errors: list[dict],
    *,
    trace: Optional[TraceLogger],
    attempt_no: int,
    max_paths_per_resource: int = 15,
) -> str:
    """Build deterministic, ground-truth options for repair prompts.

    When the planner emits unknown/non-ARM SKUs, we inject a compact list of
    valid taxonomy paths (family/service/product/sku/meter/armSkuNames, etc.)
    so the model can pick from *known-good* options.
    """

    if not errors:
        return ""

    unknown = [e for e in errors if (e.get("type") == "unknown_sku")]
    if not unknown:
        return ""

    payload: list[dict] = []
    total_paths = 0
    for e in unknown:
        category = e.get("category") or ""
        paths = get_taxonomy_option_paths_for_category(
            str(category), limit=max_paths_per_resource
        )
        total_paths += len(paths)
        payload.append(
            {
                "resource_id": e.get("resource_id"),
                "category": category,
                "requested_sku": e.get("requested_sku"),
                "taxonomy_option_paths": paths,
            }
        )

    if trace is not None:
        trace.anomaly(
            "taxonomy_option_injection",
            message=(
                "Injected ground-truth taxonomy option paths into planner repair prompt "
                "for unknown_sku resources."
            ),
            data={
                "attempt": attempt_no,
                "unknown_sku_count": len(unknown),
                "option_path_count": total_paths,
                "resource_ids": [p.get("resource_id") for p in payload],
            },
        )

    return (
        "\n\n---\n"
        "GROUND-TRUTH TAXONOMY OPTIONS (MUST USE)\n"
        "The prior plan contained unknown/non-ARM SKU tokens. For each resource below, "
        "choose a valid arm_sku_name OR adjust hints to match one of the taxonomy_option_paths. "
        "Do not invent SKUs.\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
        + "\n---\n"
    )


def plan_architecture_iterative(
    client: OpenAI,
    arch_text: str,
    *,
    mode: str = "auto",
    backend: str = "chat",
    max_iters: int = 3,
    trace: Optional[TraceLogger] = None,
    planner_callable=None,
    repair_callable=None,
) -> dict:
    """Multi-pass planner + repair loop enforcing the Pricing Contract."""

    last_validation: Optional[PlanValidationResult] = None
    attempts: list[PlannerAttempt] = []

    for idx in range(max_iters):
        attempt_no = idx + 1
        attempt = _planner_attempt(
            client=client,
            arch_text=arch_text,
            mode=mode,
            backend=backend,
            trace=trace,
            attempt=attempt_no,
            planner_callable=planner_callable,
        )
        attempts.append(attempt)
        last_validation = attempt.validation

        if not attempt.validation.errors:
            return attempt.validation.plan

        # Ask LLM to repair using the validation errors
        errors_json = json.dumps(attempt.validation.errors)
        taxonomy_injection = _build_taxonomy_option_injection(
            attempt.validation.errors,
            trace=trace,
            attempt_no=attempt_no,
        )
        if attempt.parsed is None:
            # Parsing failed; give the repair model enough context to reconstruct intent.
            fix_prompt = (
                "The previous model output could not be parsed as valid JSON or did not contain a valid JSON object. "
                "Reconstruct a complete plan JSON that satisfies the Pricing Contract.\n"
                "Return ONLY valid JSON (no markdown, no commentary).\n\n"
                f"Parse error: {attempt.parse_error}\n"
                "Raw model output snippet:\n"
                f"{_snippet(attempt.raw_response)}\n\n"
                f"Contract validation errors: {errors_json}\n"
                f"{taxonomy_injection}"
            )
        else:
            fix_prompt = (
                "The previous plan violated the Pricing Contract. "
                "Review the following errors and return ONLY valid JSON with corrections.\n"
                f"Errors: {errors_json}\n"
                f"{taxonomy_injection}\n"
                f"Prior plan: {json.dumps(attempt.parsed)}"
            )
        if trace:
            trace.log(
                "phase1_planner_repair",
                {
                    "attempt": attempt_no,
                    "errors": attempt.validation.errors,
                    "prompt": fix_prompt,
                    "had_parsed_plan": attempt.parsed is not None,
                    "parse_error": attempt.parse_error,
                },
            )

        repaired_raw: Optional[str] = None
        try:
            if repair_callable:
                repaired_raw = repair_callable(fix_prompt)
                parsed = json.loads(extract_json_object(repaired_raw))
                if not _is_plan_shaped(parsed):
                    if trace:
                        trace.log(
                            "planner_repair_bad_shape_external",
                            {
                                "attempt": attempt_no,
                                "got_keys": list(parsed.keys())
                                if isinstance(parsed, dict)
                                else str(type(parsed)),
                            },
                        )
                    continue
            else:
                parsed = _repair_to_plan_shape(
                    client,
                    repair_system_prompt=PROMPT_PLAN_REPAIR_SYSTEM,
                    input_text=fix_prompt,
                    trace=trace,
                    attempt=attempt_no,
                )
                if parsed is None:
                    continue
        except Exception as ex:
            # Do not crash the whole run; record failure and continue loop.
            if trace:
                trace.log(
                    "phase1_planner_repair_failed",
                    {"attempt": attempt_no, "error": str(ex), "repair_raw": repaired_raw},
                )
            continue

        repaired_validation = validate_pricing_contract(parsed or {}, trace=trace)
        _log_planner_trace(
            trace,
            attempt=attempt_no,
            backend=backend,
            model=MODEL_PLANNER,
            system_prompt=PROMPT_PLANNER_SYSTEM,
            user_prompt=fix_prompt,
            raw=repaired_raw or json.dumps(parsed),
            parsed=parsed,
            parse_error=None,
            validation=repaired_validation,
        )

        if not repaired_validation.errors:
            return repaired_validation.plan

    raise ValueError(
        "Planner could not produce a valid plan after max iterations: "
        f"{last_validation.errors if last_validation else 'unknown'}"
    )


def plan_architecture_chat(client: OpenAI, arch_text: str, mode: str = "auto") -> dict:
    return plan_architecture_iterative(client, arch_text, mode=mode, backend="chat")


def plan_architecture_responses(client: OpenAI, arch_text: str, mode: str = "auto") -> dict:
    return plan_architecture_iterative(client, arch_text, mode=mode, backend="responses")
