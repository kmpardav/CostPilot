import json
from dataclasses import dataclass
from typing import Any, Dict, Optional

from openai import OpenAI

from ..config import MODEL_PLANNER, MODEL_PLANNER_RESPONSES
from ..prompts import PROMPT_PLANNER_SYSTEM, PROMPT_PLANNER_USER_TEMPLATE
from ..planner.contract import PlanValidationResult, validate_pricing_contract
from ..utils.trace import TraceLogger
from .json_repair import extract_json_object, repair_json_with_llm


@dataclass
class PlannerAttempt:
    attempt: int
    raw_response: str
    parsed: Optional[Dict[str, Any]]
    parse_error: Optional[str]
    validation: PlanValidationResult


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
        tools=[{"type": "web_search"}],
        tool_choice="auto",
    )
    raw = response.output[0].content[0].text
    return MODEL_PLANNER_RESPONSES, raw


def _parse_plan_json(raw: str, client: OpenAI) -> tuple[Optional[Dict[str, Any]], Optional[str]]:
    raw_json = extract_json_object(raw)
    try:
        parsed = json.loads(raw_json)
        return parsed, None
    except json.JSONDecodeError as ex:
        try:
            repaired = repair_json_with_llm(client, PROMPT_PLANNER_SYSTEM, raw_json)
            return repaired, str(ex)
        except Exception as repair_ex:  # pragma: no cover - defensive
            return None, f"repair_failed: {repair_ex}"


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
    validation = validate_pricing_contract(parsed or {})

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
        fix_prompt = (
            "The previous plan violated the Pricing Contract. "
            "Review the following errors and return ONLY valid JSON with corrections.\n"
            f"Errors: {errors_json}\n"
            f"Prior plan: {json.dumps(attempt.parsed or {})}"
        )
        if trace:
            trace.log(
                "phase1_planner_repair",
                {
                    "attempt": attempt_no,
                    "errors": attempt.validation.errors,
                    "prompt": fix_prompt,
                },
            )

        if repair_callable:
            repaired_raw = repair_callable(fix_prompt)
            parsed = json.loads(extract_json_object(repaired_raw))
        else:
            repaired = repair_json_with_llm(client, PROMPT_PLANNER_SYSTEM, fix_prompt)
            parsed = repaired

        repaired_validation = validate_pricing_contract(parsed or {})
        _log_planner_trace(
            trace,
            attempt=attempt_no,
            backend=backend,
            model=MODEL_PLANNER,
            system_prompt=PROMPT_PLANNER_SYSTEM,
            user_prompt=fix_prompt,
            raw=json.dumps(parsed),
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
