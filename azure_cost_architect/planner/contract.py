"""Planner normalization and runtime Pricing Contract enforcement."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Dict, List

from .rules import apply_planner_rules
from .validation import validate_plan_schema
from ..utils.knowledgepack import canonicalize_service_name, get_allowed_service_names


@dataclass
class PlanValidationResult:
    plan: dict
    errors: List[Dict[str, object]]
    rule_changes: List[str]
    canonical_mappings: List[Dict[str, object]]


_HINT_REQUIRED_CATEGORIES = {
    "compute.vm",
    "db.sql",
    "db.sqlmi",
    "cache.redis",
    "storage.blob",
    "network.egress",
    "network.bandwidth",
}


def _missing_hints(res: Dict[str, object]) -> bool:
    category = (res.get("category") or "").lower()
    if category not in _HINT_REQUIRED_CATEGORIES:
        return False
    return not any(
        res.get(field)
        for field in (
            "product_name_contains",
            "sku_name_contains",
            "meter_name_contains",
            "arm_sku_name_contains",
            "arm_sku_name",
        )
    )


def _validate_resource(res: Dict[str, object], allowed: set[str], errors: List[Dict[str, object]], rule_changes: List[str]) -> None:
    canonical = (res.get("service_name") or "").strip()
    suggestions = res.get("service_name_suggestions") or []
    rid = res.get("id") or "resource"

    if res.get("source") == "preset":
        if canonical == "UNKNOWN_SERVICE" and res.get("category"):
            mapped = canonicalize_service_name(res.get("category")).get("canonical")
            if mapped and mapped != "UNKNOWN_SERVICE":
                res["service_name"] = mapped
        return

    if canonical == "UNKNOWN_SERVICE" or canonical not in allowed:
        errors.append(
            {
                "type": "unknown_service",
                "resource_id": rid,
                "service_name_raw": res.get("service_name_raw") or res.get("service_name"),
                "suggestions": suggestions,
            }
        )

    if _missing_hints(res):
        errors.append(
            {
                "type": "missing_hints",
                "resource_id": rid,
                "message": "At least one hint (product_name_contains/sku_name_contains/meter_name_contains/arm_sku_name_contains or arm_sku_name) is required",
            }
        )

    billing_model = (res.get("billing_model") or "payg").strip().lower()
    if billing_model not in {"payg", "reserved", "spot"}:
        res["billing_model"] = "payg"
        rule_changes.append(
            f"resource {rid}: normalized billing_model to payg from '{billing_model}'"
        )

    if billing_model != (res.get("billing_model") or "payg"):
        res["billing_model"] = billing_model or "payg"


def validate_pricing_contract(plan: dict) -> PlanValidationResult:
    """Apply schema normalization + rules + Pricing Contract validation."""

    normalized = apply_planner_rules(validate_plan_schema(deepcopy(plan)))

    rule_changes: List[str] = []
    canonical_mappings: List[Dict[str, object]] = []
    errors: List[Dict[str, object]] = []

    allowed_services = set(get_allowed_service_names())

    for scen in normalized.get("scenarios", []):
        for res in scen.get("resources", []):
            rid = res.get("id") or "resource"
            raw = res.get("service_name_raw") or res.get("service_name") or res.get("category") or ""
            resolved = canonicalize_service_name(raw)
            res["service_name_raw"] = raw
            res["service_name"] = resolved.get("canonical")
            res["service_name_status"] = resolved.get("status")
            res["service_name_suggestions"] = resolved.get("suggestions")

            canonical_mappings.append(
                {
                    "resource_id": rid,
                    "raw": raw,
                    "canonical": res.get("service_name"),
                    "status": res.get("service_name_status"),
                    "suggestions": res.get("service_name_suggestions"),
                }
            )

            if raw != res.get("service_name"):
                rule_changes.append(
                    f"resource {rid}: canonicalized service_name '{raw}' -> '{res.get('service_name')}' ({res.get('service_name_status')})"
                )

            _validate_resource(res, allowed_services, errors, rule_changes)

    return PlanValidationResult(
        plan=normalized,
        errors=errors,
        rule_changes=rule_changes,
        canonical_mappings=canonical_mappings,
    )


__all__ = ["validate_pricing_contract", "PlanValidationResult"]
