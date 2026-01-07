"""Planner normalization and runtime Pricing Contract enforcement."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Dict, List, Optional

from .rules import apply_planner_rules
from .validation import validate_plan_schema
from ..pricing.catalog_sources import get_catalog_sources
from ..utils.knowledgepack import (
    build_taxonomy_registry,
    canonicalize_service_name,
    get_allowed_service_names,
    load_taxonomy,
    suggest_arm_sku_names,
)
from ..utils.sku_matcher import load_sku_alias_index, match_sku, normalize_sku
from ..utils.trace import TraceLogger

FALLBACK_CATEGORY = "__unclassified__"


@dataclass
class PlanValidationResult:
    plan: dict
    errors: List[Dict[str, object]]
    rule_changes: List[str]
    canonical_mappings: List[Dict[str, object]]


_SKU_ALIAS_INDEX = load_sku_alias_index()
_taxonomy_registry = None


def _get_registry():
    global _taxonomy_registry
    if _taxonomy_registry is None:
        taxonomy = load_taxonomy()
        _taxonomy_registry = build_taxonomy_registry(taxonomy)
    return _taxonomy_registry


_HINT_REQUIRED_CATEGORIES = {
    "compute.vm",
    "db.sql",
    "db.sqlmi",
    "cache.redis",
    "storage.blob",
    "network.egress",
    "network.bandwidth",
}


# For some services, the planner will often emit "portal slang" SKUs (e.g. GP_Gen5, S2).
# These are not ARM SKU names and should not hard-fail the entire planning loop.
# Instead, we downgrade unknown_sku to a non-fatal warning and let pricing resolve via hints.
_NON_FATAL_SKU_CATEGORIES = {
    "db.sqlmi",
    "appservice",
}


def _prefer_arm_style(raw: str, options: List[str]) -> str:
    if not options:
        return raw
    return options[0] or raw


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


def _validate_resource(
    res: Dict[str, object],
    allowed: set[str],
    *,
    enforce_allowed: bool,
    errors: List[Dict[str, object]],
    rule_changes: List[str],
) -> None:
    canonical = (res.get("service_name") or "").strip()
    suggestions = res.get("service_name_suggestions") or []
    rid = res.get("id") or "resource"

    if res.get("source") == "preset":
        if canonical == "UNKNOWN_SERVICE" and res.get("category"):
            mapped = canonicalize_service_name(res.get("category")).get("canonical")
            if mapped and mapped != "UNKNOWN_SERVICE":
                res["service_name"] = mapped
        return

    # IMPORTANT:
    # If allowed-services knowledgepack is missing/empty, OR this resource is unclassified,
    # do NOT block the planner with unknown_service errors; keep the resource and let pricing estimate.
    if enforce_allowed and allowed:
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


def _apply_sku_matching(
    res: Dict[str, object],
    *,
    resource_id: str,
    errors: List[Dict[str, object]],
    rule_changes: List[str],
    trace: Optional[TraceLogger] = None,
) -> None:
    if not _SKU_ALIAS_INDEX:
        return

    requested = (
        res.get("arm_sku_name")
        or (res.get("sku") or {}).get("armSkuName")
        or res.get("armSkuName")
        or ""
    ).strip()

    if not requested:
        return

    match = match_sku(requested, res.get("category") or "", _SKU_ALIAS_INDEX)
    diagnostics = {
        "input": requested,
        "matched": match.get("matched_sku"),
        "method": match.get("matched_by"),
        "reason": match.get("reason"),
    }
    if match.get("suggestions"):
        diagnostics["suggestions"] = match.get("suggestions")
    res["sku_match_diagnostics"] = diagnostics

    resolved = match.get("matched_sku")
    cat_key = (res.get("category") or "").lower()
    options: List[str] = []
    if cat_key in _SKU_ALIAS_INDEX:
        options = _SKU_ALIAS_INDEX[cat_key].get(normalize_sku(requested), [])
        if not options and resolved:
            options = _SKU_ALIAS_INDEX[cat_key].get(normalize_sku(resolved), [])

    if options:
        resolved = _prefer_arm_style(requested, options)
        diagnostics["matched"] = resolved
    if resolved:
        if resolved != requested:
            res["arm_sku_name"] = resolved
            rule_changes.append(
                "resource {rid}: normalized arm_sku_name '{requested}' -> "
                "'{resolved}' ({method})".format(
                    rid=resource_id, requested=requested, resolved=resolved, method=match.get("matched_by") or "sku_matcher"
                )
            )
        return

    if (res.get("category") or "").lower() not in _SKU_ALIAS_INDEX:
        return

    suggestions = match.get("suggestions") or []
    if not suggestions:
        # Deterministic fallback: search taxonomy armSkuNames universe.
        suggestions = suggest_arm_sku_names(requested, limit=8)

    cat_lower = (res.get("category") or "").lower()
    if cat_lower in _NON_FATAL_SKU_CATEGORIES:
        # Downgrade to warning: clear the invalid arm_sku_name and let pricing resolve via hints.
        if trace is not None:
            trace.anomaly(
                "unknown_sku_nonfatal",
                message=(
                    f"Non-fatal unknown_sku for resource '{resource_id}' (category='{cat_lower}'): "
                    f"arm_sku_name='{requested}'. Downgrading and clearing arm_sku_name so pricing can resolve via hints."
                ),
                data={
                    "resource_id": resource_id,
                    "category": cat_lower,
                    "requested_sku": requested,
                    "suggestions": suggestions,
                },
            )
        res["arm_sku_name"] = None
        res.setdefault("pricing_notes", [])
        res["pricing_notes"].append(
            "Planner emitted a non-ARM SKU token; cleared arm_sku_name so pricing can resolve via hints."
        )
        if suggestions:
            res["arm_sku_name_suggestions"] = suggestions
        rule_changes.append(
            f"resource {resource_id}: downgraded unknown_sku '{requested}' for category '{cat_lower}' (non-fatal); cleared arm_sku_name"
        )
        return

    if trace is not None:
        trace.anomaly(
            "unknown_sku",
            message=(
                f"Fatal unknown_sku for resource '{resource_id}' (category='{cat_lower}'): "
                f"arm_sku_name='{requested}'. No deterministic match/suggestions found."
            ),
            data={
                "resource_id": resource_id,
                "category": cat_lower,
                "requested_sku": requested,
                "suggestions": suggestions,
            },
        )
    errors.append(
        {
            "type": "unknown_sku",
            "resource_id": resource_id,
            "category": res.get("category"),
            "requested_sku": requested,
            "suggestions": suggestions,
        }
    )


def validate_pricing_contract(
    plan: dict,
    *,
    trace: Optional[TraceLogger] = None,
) -> PlanValidationResult:
    """Apply schema normalization + rules + Pricing Contract validation."""

    normalized = apply_planner_rules(validate_plan_schema(deepcopy(plan)))

    rule_changes: List[str] = []
    canonical_mappings: List[Dict[str, object]] = []
    errors: List[Dict[str, object]] = []
    has_unclassified = False

    allowed_services_list = get_allowed_service_names() or []
    allowed_services = set(allowed_services_list)
    # If allowed_services is empty, enforcement must be disabled; otherwise every service becomes "unknown".
    enforce_allowed_globally = bool(allowed_services)

    registry = _get_registry()

    for scen in normalized.get("scenarios", []):
        for res in scen.get("resources", []):
            rid = res.get("id") or "resource"
            raw_category = res.get("category")
            is_category_registered = bool(raw_category) and bool(registry.get(raw_category))

            # If category is unknown to taxonomy, we MUST NOT drop/skip the resource.
            # Mark it as estimated and keep it in the plan so downstream reporting/pricing stays complete.
            if not is_category_registered:
                res["original_category"] = raw_category
                res["category"] = FALLBACK_CATEGORY
                res["pricing_status"] = "estimated"
                res.setdefault("pricing_notes", [])
                res["pricing_notes"].append(
                    f"Category '{raw_category}' not found in taxonomy registry; keeping resource as estimated under '{FALLBACK_CATEGORY}'."
                )
                has_unclassified = True
            else:
                registry.require(raw_category)

            raw = res.get("service_name_raw") or res.get("service_name") or raw_category or ""

            # Candidate serviceName hints only make sense when category is known and mapped to catalog sources.
            candidates: List[str] = []
            if is_category_registered:
                try:
                    candidates = [
                        src.service_name
                        for src in get_catalog_sources(raw_category or "")
                        if src.service_name != "UNKNOWN_SERVICE"
                    ]
                except Exception:
                    candidates = []

            resolved = canonicalize_service_name(raw, category_candidates=candidates)
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

            # Enforce allowed-services only if:
            #  - knowledgepack provided a non-empty allowed list, AND
            #  - the resource category is known (otherwise treat as estimated).
            enforce_allowed = enforce_allowed_globally and is_category_registered

            _validate_resource(
                res,
                allowed_services,
                enforce_allowed=enforce_allowed,
                errors=errors,
                rule_changes=rule_changes,
            )
            _apply_sku_matching(
                res,
                resource_id=rid,
                errors=errors,
                rule_changes=rule_changes,
                trace=trace,
            )

    if has_unclassified:
        normalized.setdefault("meta", {})
        normalized["meta"]["has_unclassified_resources"] = True

    return PlanValidationResult(
        plan=normalized,
        errors=errors,
        rule_changes=rule_changes,
        canonical_mappings=canonical_mappings,
    )


__all__ = ["validate_pricing_contract", "PlanValidationResult"]
