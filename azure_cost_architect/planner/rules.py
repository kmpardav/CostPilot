"""Planner normalization / warnings before pricing.

This module adds lightweight sanity checks that help the pricing layer by
surfacing missing HA/DR, bandwidth or SKU information early in the flow.
It also applies workload presets (baseline controls, NAT/egress defaults)
to keep scenarios opinionated before pricing.
"""

from typing import Dict, Iterable, List

from .presets import apply_workload_presets


def _is_hp_scenario(scen: Dict) -> bool:
    sid = (scen.get("id") or "").strip().lower()
    label = (scen.get("label") or "").strip().lower()
    return sid in {"high_performance", "high-performance", "hp"} or "high" in label


def _has_redundancy_hint(res: Dict) -> bool:
    text = " ".join(
        [
            str(res.get("arm_sku_name") or res.get("armSkuName") or ""),
            str(res.get("notes") or ""),
            str((res.get("metrics") or {})),
            " ".join(res.get("product_name_contains") or []),
            " ".join(res.get("meter_name_contains") or []),
            " ".join(res.get("sku_name_contains") or []),
            " ".join(res.get("arm_sku_name_contains") or []),
        ]
    ).lower()
    return any(
        tok in text
        for tok in ("zone redundancy", "zone redundant", "zrs", "gzrs", "ra-gzrs", "lrs", "grs")
    )


def _append_unique(lst: List[str], value: str) -> None:
    if value not in lst:
        lst.append(value)


def _has_category(resources: List[Dict], prefix: str) -> bool:
    p = (prefix or "").lower()
    for r in resources:
        if not isinstance(r, dict):
            continue
        c = (r.get("category") or "").lower()
        if c.startswith(p):
            return True
    return False


def _is_internet_facing(plan: Dict, scen: Dict, resources: List[Dict]) -> bool:
    """Deterministic, conservative detector for internet-facing workloads.

    Returns True only when we have strong indicators.
    """
    # Explicit boolean flags if present (highest trust)
    for obj in (plan, scen):
        if isinstance(obj, dict):
            v = obj.get("internet_facing")
            if isinstance(v, bool):
                return v

    # Strong component indicators (short, obvious list)
    edge_prefixes = (
        "network.appgw",      # Application Gateway
        "network.frontdoor",  # Front Door
        "network.public_ip",  # Public IP
        "network.cdn",        # CDN
        "security.waf",       # If modeled separately
    )
    for pfx in edge_prefixes:
        if _has_category(resources, pfx):
            return True

    # Optional fallback: conservative keyword check if input_text is present
    text = " ".join(
        [
            str(plan.get("input_text") or ""),
            str(scen.get("notes") or ""),
        ]
    ).lower()
    if any(k in text for k in ("public", "internet", "extern", "waf", "dmz")):
        return True

    return False


def _ensure_hp_firewall(
    plan: Dict, scen: Dict, resources: List[Dict], scen_warnings: List[str]
) -> None:
    """HP security posture: always add Azure Firewall for internet-facing workloads if absent."""
    if _has_category(resources, "network.firewall"):
        return
    if not _is_internet_facing(plan, scen, resources):
        return

    resources.append(
        {
            "id": "azfw-hp-1",
            "category": "network.firewall",
            "name": "Azure Firewall (HP security posture)",
            "notes": (
                "HP preset: internet-facing workload; add Azure Firewall for centralized policy, "
                "egress control, and threat protection."
            ),
            "metrics": {"hours_per_month": 730},
        }
    )
    scen_warnings.append("hp_security_posture: added network.firewall for internet-facing workload")


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

        # ------------------------------------------------------------
        # Tier-2: Scenario enrichment (HP redundancy variants)
        # ------------------------------------------------------------
        if _is_hp_scenario(scen):
            hp_applied_any = False
            for res in resources:
                cat = (res.get("category") or "").lower()

                # Respect explicit user intent: if any redundancy hint exists, do nothing.
                if _has_redundancy_hint(res):
                    continue

                # SQL: allow Zone Redundancy meters by adding contains-hint.
                if cat.startswith("db.sql"):
                    res.setdefault("product_name_contains", [])
                    _append_unique(res["product_name_contains"], "zone redundancy")
                    hp_applied_any = True

                # Blob: steer to "global ZRS" style by using GZRS hint.
                # (Blob pricing already detects LRS/ZRS/GZRS hints via notes/metrics.)
                if cat.startswith("storage.blob"):
                    notes = (res.get("notes") or "").strip()
                    if "gzrs" not in notes.lower():
                        res["notes"] = (notes + " GZRS").strip()
                    hp_applied_any = True

            if hp_applied_any:
                scen_warnings.append(
                    "hp_variant: added redundancy hints (SQL zone redundancy / Blob GZRS)"
                )

            # ------------------------------------------------------------
            # Tier-2: HP security posture (Firewall) for internet-facing workloads
            # ------------------------------------------------------------
            _ensure_hp_firewall(plan, scen, resources, scen_warnings)

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
