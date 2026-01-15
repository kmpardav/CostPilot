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
    PLANNER_PROMPT_POLICY_COMPONENTS,
)
from ..planner.contract import PlanValidationResult, validate_pricing_contract
from ..utils.trace import TraceLogger
from ..utils.knowledgepack import get_taxonomy_option_paths_for_category
from .json_repair import extract_json_object, repair_json_with_llm
from .llm_trace import (
    trace_llm_request,
    trace_llm_response,
    trace_llm_parse,
    trace_llm_validate,
    trace_llm_accepted,
)

_PRICING_COMPONENTS_GUIDANCE = """
PRICING COMPONENTS (IMPORTANT):
Some services are priced via multiple meters (e.g., "zones + queries", "transactions", etc.).
For such resources, emit:

  "pricing_components": [
    {
      "key": "<component-id>",               // e.g. "zones", "queries", "transactions"
      "label": "<human label>",              // optional
      "pricing_hints": {                     // optional meter selection hints
        "product_name_contains": ["..."],
        "meter_name_contains": ["..."]
      },
      "units": {
        "kind": "quantity" | "metric" | "fixed",
        // if kind == "metric":
        "metric_key": "queries_per_month" | "transactions_per_month" | "requests_per_month" | "operations_per_month",
        "scale": 1                           // optional numeric scale
        // if kind == "fixed": "value": 1
      },
      "hours_behavior": "inherit" | "ignore" // ignore for monthly/usage meters
    }
  ]

APPLICATION GATEWAY (Standard_v2 / WAF_v2) PRICING (IMPORTANT):
Azure Application Gateway v2 SKUs (including WAF_v2) are billed as:
  (1) a fixed "gateway-hour" cost, and
  (2) a variable "capacity unit-hour" cost.
They are NOT billed as "WAF requests" counters. Do NOT emit captcha/session meters.

For Application Gateway v2 resources, emit pricing_components like:
  - key: "gateway_hours" with units.kind="fixed" value=730 (prod) or HOURS_PILOT for non-prod
  - key: "capacity_units" with units.kind="metric" metric_key="appgw_capacity_units_per_hour"
    and provide a reasonable default assumption (e.g., 1 for cost_optimized, 1-2 for baseline, 2-5 for high_performance)
    OR provide traffic drivers (throughput_mbps, concurrent_connections) so the pricing layer can estimate.

pricing_hints:
  - gateway_hours: meter_name_contains ["Gateway Hour", "Application Gateway Hour"]
  - capacity_units: meter_name_contains ["Capacity Unit", "Capacity Units"]

EXAMPLES:
1) Azure DNS public zones+queries:
  resource.service_name="Azure DNS"
  pricing_components:
    - key="zones", units.kind="quantity", hints contain ["DNS","Zone"], hours_behavior="ignore"
    - key="queries", units.kind="metric", metric_key="queries_per_month",
      hints contain ["DNS","Query"], hours_behavior="ignore"

2) Azure Maps transactions:
  resource.service_name="Azure Maps"
  pricing_components:
    - key="transactions", units.kind="metric", metric_key="transactions_per_month",
      hints contain ["Maps","Transaction"] or meter_name_contains ["Transaction"], hours_behavior="ignore"

If pricing_components is present, keep the parent resource as a logical container.
Do NOT create separate resources manually; the pricing engine will expand them.
"""

_PLANNER_POLICY_INJECTION = (
    "\n\n"
    + PLANNER_PROMPT_POLICY_COMPONENTS.strip()
    + "\n"
)


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
        repaired = repair_json_with_llm(
            client,
            repair_system_prompt,
            input_text,
            trace=trace,
            stage=f"planner.repair_shape.attempt{attempt or 0}",
        )
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
        repaired_retry = repair_json_with_llm(
            client,
            repair_system_prompt,
            schema_prompt,
            trace=trace,
            stage=f"planner.repair_shape_retry.attempt{attempt or 0}",
        )
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


def _parse_plan_json(
    raw: str, client: OpenAI, *, trace: Optional[TraceLogger], attempt: int
) -> tuple[Optional[Dict[str, Any]], Optional[str]]:
    raw_json = extract_json_object(raw)
    try:
        parsed = json.loads(raw_json)
        trace_llm_parse(trace, stage="planner.parse", ok=True, extracted_json_chars=len(raw_json or ""))
        return parsed, None
    except json.JSONDecodeError as ex:
        repaired = _repair_to_plan_shape(
            client,
            repair_system_prompt=PROMPT_JSON_REPAIR_SYSTEM,
            input_text=raw_json,
            trace=trace,
            attempt=attempt,
        )
        if repaired is None:
            trace_llm_parse(
                trace,
                stage="planner.parse",
                ok=False,
                error=f"repair_failed: {ex}",
                extracted_json_chars=len(raw_json or ""),
            )
            return None, f"repair_failed: {ex}"
        trace_llm_parse(
            trace, stage="planner.parse", ok=False, error=str(ex), extracted_json_chars=len(raw_json or "")
        )
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
    user_prompt = (
        PROMPT_PLANNER_USER_TEMPLATE.format(arch_text=arch_text, mode=mode)
        + "\n\n"
        + _PRICING_COMPONENTS_GUIDANCE
        + _PLANNER_POLICY_INJECTION
    )

    # LLM request trace (structured)
    req_model = MODEL_PLANNER_RESPONSES if backend == "responses" else MODEL_PLANNER
    trace_llm_request(
        trace,
        stage=f"planner.{mode}.attempt{attempt}",
        backend=backend,
        model=req_model,
        temperature=0.0,
        response_format={"type": "json_object"} if backend != "responses" else None,
        messages=[
            {"role": "system", "content": PROMPT_PLANNER_SYSTEM},
            {"role": "user", "content": user_prompt},
        ],
    )
    model_used: str
    raw: str
    if planner_callable:
        model_used, raw = planner_callable(user_prompt)
    elif backend == "responses":
        model_used, raw = _call_planner_responses(client, user_prompt)
    else:
        model_used, raw = _call_planner_chat(client, user_prompt)

    trace_llm_response(
        trace, stage=f"planner.{mode}.attempt{attempt}", backend=backend, model=model_used, raw_text=raw
    )

    parsed, parse_error = _parse_plan_json(raw, client, trace=trace, attempt=attempt)
    validation = validate_pricing_contract(parsed or {}, trace=trace)

    trace_llm_validate(
        trace,
        stage=f"planner.{mode}.attempt{attempt}",
        ok=not bool(validation.errors),
        errors=validation.errors,
        extra={"parse_error": parse_error},
    )

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

    if parsed is not None and not validation.errors:
        trace_llm_accepted(trace, stage=f"planner.{mode}.attempt{attempt}", note="plan accepted")

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

            trace_llm_request(
                trace,
                stage=f"planner.repair_contract.attempt{attempt_no}",
                backend=backend,
                model=MODEL_PLANNER,
                temperature=0.0,
                response_format={"type": "json_object"} if backend != "responses" else None,
                messages=[
                    {"role": "system", "content": PROMPT_PLAN_REPAIR_SYSTEM},
                    {"role": "user", "content": fix_prompt},
                ],
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

        if trace and repaired_raw:
            trace_llm_response(
                trace,
                stage=f"planner.repair_contract.attempt{attempt_no}",
                backend=backend,
                model=MODEL_PLANNER,
                raw_text=repaired_raw,
            )

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
            trace_llm_accepted(
                trace, stage=f"planner.repair_contract.attempt{attempt_no}", note="repaired plan accepted"
            )
            return repaired_validation.plan

    raise ValueError(
        "Planner could not produce a valid plan after max iterations: "
        f"{last_validation.errors if last_validation else 'unknown'}"
    )


def plan_architecture_chat(client: OpenAI, arch_text: str, mode: str = "auto") -> dict:
    return plan_architecture_iterative(client, arch_text, mode=mode, backend="chat")


def plan_architecture_responses(client: OpenAI, arch_text: str, mode: str = "auto") -> dict:
    return plan_architecture_iterative(client, arch_text, mode=mode, backend="responses")
