"""Opinionated workload presets for planner output.

This module injects baseline controls (Key Vault, Log Analytics, Backup)
and connectivity assumptions (NAT/egress) when scenarios omit them. It is
intentionally lightweight so it can run before pricing without extra API
lookups.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Tuple

from ..config import HOURS_PROD


def _resource_ids(resources: Iterable[Dict]) -> set[str]:
    return {res.get("id", "") for res in resources if isinstance(res, dict)}


def _make_unique_id(base: str, existing: set[str]) -> str:
    if base not in existing:
        return base
    idx = 2
    while f"{base}-{idx}" in existing:
        idx += 1
    return f"{base}-{idx}"


def _ensure_resource(resources: List[Dict], template: Dict) -> Dict | None:
    existing_ids = _resource_ids(resources)
    if any(
        res.get("category") == template.get("category") and res.get("source") != "preset"
        for res in resources
        if isinstance(res, dict)
    ):
        return None

    resource = template.copy()
    resource["id"] = _make_unique_id(template.get("id", "res"), existing_ids)
    resources.append(resource)
    return resource


def _preset_resource(
    *,
    id: str,
    category: str,
    workload_type: str,
    metrics: Dict | None = None,
    notes: str = "",
) -> Dict:
    return {
        "id": id,
        "category": category,
        "service_name": None,
        "service_name_raw": None,
        "service_name_status": "unknown",
        "service_name_suggestions": [],
        "arm_sku_name": None,
        "region": None,
        "quantity": 1,
        "hours_per_month": HOURS_PROD,
        "billing_model": "payg",
        "workload_type": workload_type,
        "criticality": "prod",
        "os_type": "na",
        "product_name_contains": [],
        "sku_name_contains": [],
        "meter_name_contains": [],
        "arm_sku_name_contains": [],
        "metrics": metrics or {},
        "notes": notes,
        "source": "preset",
    }


def _has_category(resources: Iterable[Dict], prefixes: Tuple[str, ...]) -> bool:
    for res in resources:
        cat = (res.get("category") or "").lower()
        if cat.startswith(prefixes):
            return True
    return False


def infer_archetype_flags(resources: Iterable[Dict]) -> Dict[str, bool]:
    has_web = _has_category(resources, ("compute", "appservice", "function", "containerapps"))
    has_db = _has_category(resources, ("db.",))
    has_cache = _has_category(resources, ("cache.redis",))
    has_analytics = _has_category(resources, ("analytics.",))
    has_gateway = _has_category(resources, ("network.appgw", "network.frontdoor", "network.gateway"))

    return {
        "web_db_stack": has_web and has_db,
        "cache_present": has_cache,
        "analytics_stack": has_analytics,
        "fronting_gateway": has_gateway,
        "internet_facing": has_web or has_gateway,
    }


def apply_workload_presets(resources: List[Dict]) -> List[str]:
    """Add baseline resources / warnings for common archetypes.

    Returns warnings so the caller can surface recommendations while keeping
    the plan deterministic and testable.
    """

    warnings: List[str] = []
    archetype = infer_archetype_flags(resources)

    # Baseline controls for prod-like stacks
    has_prod_workload = _has_category(resources, ("compute", "db.", "cache.redis"))
    if has_prod_workload:
        _ensure_resource(
            resources,
            _preset_resource(
                id="kv-secure",
                category="security.keyvault",
                workload_type="other",
                notes="Added by preset: secrets/keys for services",
            ),
        )
        _ensure_resource(
            resources,
            _preset_resource(
                id="log-analytics",
                category="monitoring.loganalytics",
                workload_type="other",
                metrics={"storage_gb": 200.0},
                notes="Added by preset: centralized logs",
            ),
        )
        _ensure_resource(
            resources,
            _preset_resource(
                id="backup-vault",
                category="backup.vault",
                workload_type="dr",
                metrics={"storage_gb": 200.0},
                notes="Added by preset: baseline backup vault",
            ),
        )

    # Connectivity defaults
    has_egress = _has_category(
        resources,
        (
            "network.egress",
            "network.nat",
            "network.vpngw",
            "network.er",
            "network.gateway",
            "network.frontdoor",
        ),
    )
    if archetype["internet_facing"] and not has_egress:
        added = _ensure_resource(
            resources,
            _preset_resource(
                id="nat-egress",
                category="network.nat",
                workload_type="network_egress",
                metrics={"egress_gb": 500.0},
                notes="Added by preset: baseline outbound bandwidth",
            ),
        )
        if added:
            warnings.append("bandwidth_inferred: added network.nat with default egress_gb")

    # Web + DB archetype: encourage cache or gateway
    if archetype["web_db_stack"] and not archetype["cache_present"]:
        warnings.append("cache_recommended: add cache.redis for session/offloading")

    if archetype["internet_facing"] and not archetype["fronting_gateway"]:
        warnings.append("waf_recommended: consider network.appgw or network.frontdoor")

    if archetype["analytics_stack"] and not _has_category(resources, ("messaging.eventhubs", "messaging.servicebus")):
        warnings.append("ingestion_missing: add messaging layer for analytics feeds")

    return warnings


__all__ = ["apply_workload_presets", "infer_archetype_flags"]
