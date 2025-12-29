"""Planner normalization / warnings before pricing.

This module adds lightweight sanity checks that help the pricing layer by
surfacing missing HA/DR, bandwidth or SKU information early in the flow.
It also applies workload presets (baseline controls, NAT/egress defaults)
to keep scenarios opinionated before pricing.
"""

from typing import Dict, Iterable

from .presets import apply_workload_presets


def _category_needs_sku(category: str) -> bool:
    cat = (category or "").lower()
    return cat.startswith(
        (
            "compute",
            "db.",
            "cache.redis",
            "analytics.",
            "appservice",
            "function",
            "containerapps",
        )
    )


def _collect_categories(resources: Iterable[Dict]) -> set[str]:
    categories: set[str] = set()
    for res in resources:
        cat = (res.get("category") or "").lower()
        categories.add(cat)
    return categories


def apply_planner_rules(plan: dict) -> dict:
    if not isinstance(plan, dict):
        return {"metadata": {}, "scenarios": []}

    plan.setdefault("warnings", [])
    plan_warnings = plan.get("warnings") or []

    for scen in plan.get("scenarios", []):
        if not isinstance(scen, dict):
            continue
        scen_warnings = scen.setdefault("warnings", [])
        resources = [res for res in scen.get("resources", []) if isinstance(res, dict)]
        scen["resources"] = resources

        preset_warnings = apply_workload_presets(resources)
        scen_warnings.extend(preset_warnings)
        cats = _collect_categories(resources)

        if not any(c.startswith("backup.vault") or c.startswith("dr.asr") for c in cats):
            scen_warnings.append(
                "ha_dr_missing: add backup.vault and/or dr.asr for resilience"
            )

        if not any(
            c.startswith("network.egress")
            or c.startswith("network.nat")
            or c.startswith("network.gateway")
            for c in cats
        ):
            scen_warnings.append(
                "bandwidth_missing: estimate outbound via network.nat or network.egress"
            )

        missing_skus = sorted(
            res.get("id", "res")
            for res in resources
        if _category_needs_sku(res.get("category"))
        and not (
            res.get("arm_sku_name")
            or (res.get("sku") or {}).get("armSkuName")
            or (res.get("arm_sku_name_contains") or [])
            or (res.get("sku_name_contains") or [])
            or (res.get("meter_name_contains") or [])
            or (res.get("product_name_contains") or [])
        )
        )
        if missing_skus:
            scen_warnings.append(
                "sku_missing: " + ", ".join(missing_skus)
            )

        missing_db_sizing = sorted(
            res.get("id", "res")
            for res in resources
            if (res.get("category") or "").startswith("db.")
            and not (res.get("metrics") or {}).get("vcores")
        )
        if missing_db_sizing:
            scen_warnings.append("db_sizing_missing: " + ", ".join(missing_db_sizing))

        plan_warnings.extend(w for w in scen_warnings if w)

    plan["warnings"] = sorted(set(plan_warnings))
    return plan


__all__ = ["apply_planner_rules"]
