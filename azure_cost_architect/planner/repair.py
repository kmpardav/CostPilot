from __future__ import annotations

import json
from copy import deepcopy
from typing import Dict, Iterable, List, Optional

from openai import OpenAI

from ..config import DEFAULT_REQUIRED_CATEGORIES, MODEL_PLANNER
from ..llm.json_repair import extract_json_object
from ..prompts import PROMPT_REPAIR_SYSTEM, PROMPT_REPAIR_USER_TEMPLATE
from ..pricing.catalog_sources import get_catalog_sources
from ..utils.categories import canonical_required_category, normalize_required_categories
from .validation import validate_plan_schema


def build_repair_targets(
    validated_plan: dict,
    *,
    required_categories: Optional[Iterable[str]] = None,
) -> List[Dict]:
    """Collect resources that need pricing-identification repair."""

    metadata = validated_plan.get("metadata") or {}
    required = normalize_required_categories(
        required_categories
        if required_categories is not None
        else metadata.get("required_categories")
        or DEFAULT_REQUIRED_CATEGORIES
    )

    def _all_hints_empty(res: Dict) -> bool:
        return all(not res.get(field) for field in ("product_name_contains", "sku_name_contains", "meter_name_contains", "arm_sku_name_contains"))

    targets: List[Dict] = []
    for scen in validated_plan.get("scenarios", []):
        sid = scen.get("id") or "baseline"
        for res in scen.get("resources", []):
            if not isinstance(res, dict):
                continue
            cat = res.get("category") or "other"
            if res.get("service_name") == "UNKNOWN_SERVICE" or (
                canonical_required_category(cat) in required and _all_hints_empty(res)
            ):
                targets.append(
                    {
                        "scenario_id": sid,
                        "resource_id": res.get("id") or "res",
                        "category": cat,
                        "current": {
                            "service_name": res.get("service_name"),
                            "arm_sku_name": res.get("arm_sku_name"),
                            "product_name_contains": res.get("product_name_contains") or [],
                            "sku_name_contains": res.get("sku_name_contains") or [],
                            "meter_name_contains": res.get("meter_name_contains") or [],
                            "arm_sku_name_contains": res.get("arm_sku_name_contains") or [],
                        },
                    }
                )
    return targets


def build_category_candidates(category: str) -> List[str]:
    """Return canonical service_name candidates for a category (exclude UNKNOWN_SERVICE)."""

    seen: set[str] = set()
    names: List[str] = []
    for src in get_catalog_sources(category):
        if src.service_name == "UNKNOWN_SERVICE" or src.service_name in seen:
            continue
        seen.add(src.service_name)
        names.append(src.service_name)
    return names


def call_repair_llm(
    client: OpenAI,
    validated_plan: dict,
    repair_targets: List[Dict],
    category_candidates: Dict[str, List[str]],
    service_hint_samples: Dict,
    *,
    backend: str = "chat",
) -> Dict:
    """Call the repair LLM and return the parsed JSON response."""

    user_prompt = PROMPT_REPAIR_USER_TEMPLATE.format(
        VALIDATED_PLAN_JSON_HERE=json.dumps(validated_plan, ensure_ascii=False, indent=2),
        REPAIR_TARGETS_JSON_HERE=json.dumps(repair_targets, ensure_ascii=False, indent=2),
        CATEGORY_CANDIDATES_JSON_HERE=json.dumps(category_candidates, ensure_ascii=False, indent=2),
        SERVICE_HINT_SAMPLES_JSON_HERE=json.dumps(service_hint_samples, ensure_ascii=False, indent=2),
    )

    if backend == "responses":
        response = client.responses.create(
            model=MODEL_PLANNER,
            input=[
                {"role": "system", "content": PROMPT_REPAIR_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
            tool_choice="none",
        )
        raw = response.output[0].content[0].text
    else:
        completion = client.chat.completions.create(
            model=MODEL_PLANNER,
            temperature=0.0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": PROMPT_REPAIR_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
        )
        raw = completion.choices[0].message.content or ""

    parsed = json.loads(extract_json_object(raw) or "{}")
    parsed.setdefault("repairs", [])
    return parsed


def apply_repairs(plan: dict, repairs: Iterable[Dict]) -> dict:
    """Apply LLM repairs to the plan, touching only allowed fields."""

    updated = deepcopy(plan)

    def _update_resource(res: Dict, patch: Dict) -> None:
        allowed_fields = {
            "service_name",
            "arm_sku_name",
            "product_name_contains",
            "sku_name_contains",
            "meter_name_contains",
            "arm_sku_name_contains",
            "service_name_suggestions",
        }
        for key, value in patch.items():
            if key in allowed_fields:
                res[key] = value

    for repair in repairs or []:
        sid = repair.get("scenario_id")
        rid = repair.get("resource_id")
        for scen in updated.get("scenarios", []):
            if scen.get("id") != sid:
                continue
            for res in scen.get("resources", []):
                if res.get("id") == rid:
                    _update_resource(res, repair)
                    break

    return validate_plan_schema(updated)


__all__ = [
    "apply_repairs",
    "build_category_candidates",
    "build_repair_targets",
    "call_repair_llm",
]
