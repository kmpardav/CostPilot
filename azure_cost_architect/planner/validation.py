from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional

from ..config import HOURS_PROD
from ..pricing.catalog_sources import get_catalog_sources, CATEGORY_CATALOG_SOURCES
from ..utils.knowledgepack import canonicalize_service_name

from .pricing_rules import (
    CANONICAL_METRIC_KEYS,
    METRIC_KEY_ALIASES,
    canonicalize_metrics,
    normalize_pricing_components,
)

FALLBACK_CATEGORY = "__unclassified__"

_CATEGORY_MAP: Dict[str, str] = {
    "aks": "compute.aks",
    "vm": "compute.vm",
    "vmss": "compute.vmss",
    "appservice": "appservice",
    "app.service": "appservice",
    "function": "function",
    "containerapps": "containerapps",
    "container.apps": "containerapps",
    "sqlmi": "db.sqlmi",
    "sql.mi": "db.sqlmi",
    "sql.db": "db.sql",
    "sql.database": "db.sql",
    "postgres": "db.postgres",
    "mysql": "db.mysql",
    "cosmos": "db.cosmos",
    "redis": "cache.redis",
    "cache": "cache.redis",
    "storage.blob": "storage.blob",
    "storage.files": "storage.files",
    "storage.disk": "storage.disk",
    "storage": "storage.blob",
    "fabric": "analytics.fabric",
    "microsoftfabric": "analytics.fabric",
    "azuremachinelearning": "ai.azureml",
    "machinelearning": "ai.azureml",
    "azureml": "ai.azureml",
    "synapse": "analytics.synapse",
    "datafactory": "analytics.datafactory",
    "databricks": "analytics.databricks",
    "adf": "analytics.datafactory",
    "eventhub": "messaging.eventhubs",
    "servicebus": "messaging.servicebus",
    "eventgrid": "messaging.eventgrid",
    "loganalytics": "monitoring.loganalytics",
    "keyvault": "security.keyvault",
    "backup": "backup.vault",
    "site_recovery": "dr.asr",
    "asr": "dr.asr",
    "vnet": "network.vnet",
    "appgw": "network.appgw",
    "application_gateway": "network.appgw",
    "frontdoor": "network.frontdoor",
    "firewall": "network.firewall",
    "nat": "network.nat",
    "lb": "network.lb",
    "bastion": "network.bastion",
    "vpn": "network.vpngw",
    "er": "network.er",
    "public_ip": "network.public_ip",
    "apim": "integration.apim",
    "api_management": "integration.apim",
    "sentinel": "security.sentinel",
    "defender": "security.defender",
    "defender_for_cloud": "security.defender",
    "purview": "governance.purview",
}


def _safe_category(category: Optional[str]) -> str:
    """
    Returns a category that is guaranteed to be accepted by the taxonomy registry.
    Any unknown/empty category becomes FALLBACK_CATEGORY.
    """
    c = (category or "").strip()
    if not c:
        return FALLBACK_CATEGORY
    if c.lower() in {"other", "misc", "unknown"}:
        return FALLBACK_CATEGORY
    return c


def _build_service_to_category_index() -> Dict[str, str]:
    """
    Build a best-effort reverse index:
      Retail serviceName -> canonical CostPilot category
    using the CATEGORY_CATALOG_SOURCES mapping (single source of truth).
    """
    out: Dict[str, str] = {}
    for cat, sources in CATEGORY_CATALOG_SOURCES.items():
        for src in sources:
            svc = (getattr(src, "service_name", None) or "").strip()
            if not svc:
                continue
            # Prefer the first (most-specific) mapping encountered.
            out.setdefault(svc, cat)
    return out


_SERVICE_TO_CATEGORY = _build_service_to_category_index()


def _infer_category_from_service_name(service_name_raw: str) -> str | None:
    """
    If the planner gives category=other/unknown, try to infer category from service_name.
    This avoids taxonomy-registry failures and prevents pricing from skipping everything.
    """
    raw = (service_name_raw or "").strip()
    if not raw:
        return None
    canon = canonicalize_service_name(raw).get("canonical") or raw
    # Try canonical first, then raw.
    return _SERVICE_TO_CATEGORY.get(canon) or _SERVICE_TO_CATEGORY.get(raw)


def _canonical_category(raw: str) -> str:
    if not raw:
        return FALLBACK_CATEGORY
    low = raw.strip().lower().replace(" ", "").replace("_", ".")
    mapped = _CATEGORY_MAP.get(low, raw)
    return _safe_category(mapped)


def _list_field(value: Any) -> List[str]:
    """Normalize hint-like fields to a list[str] (never None)."""
    if value is None:
        return []
    if isinstance(value, list):
        out: List[str] = []
        for v in value:
            if v is None:
                continue
            s = str(v).strip()
            if s:
                out.append(s)
        return out
    if isinstance(value, str):
        s = value.strip()
        return [s] if s else []
    s = str(value).strip()
    return [s] if s else []


def _category_candidates(category: str) -> list[str]:
    cat = (category or "other").lower()

    candidates = [cat]
    if "." in cat:
        candidates.append(cat.split(".", 1)[0])

    # Add “known sources” from config for that broad category
    try:
        sources = get_catalog_sources(category=cat)
        for s in sources:
            if isinstance(s, dict) and s.get("category"):
                candidates.append(str(s["category"]).lower())
    except Exception:
        pass

    # Dedup
    seen = set()
    out = []
    for c in candidates:
        if c not in seen:
            out.append(c)
            seen.add(c)
    return out


def _default_workload_type(category: str) -> str:
    cat = category.lower()
    if cat.startswith("compute.aks") or cat.startswith("compute.vmss"):
        return "kubernetes_node"
    if cat.startswith("compute.vm"):
        return "web_app"
    if cat.startswith("appservice") or cat.startswith("function") or cat.startswith("containerapps"):
        return "web_app"
    if cat.startswith("db."):
        return "db"
    if cat.startswith("cache.redis"):
        return "cache"
    if cat.startswith("network.appgw") or cat.startswith("network.frontdoor"):
        return "gateway"
    if cat.startswith("backup") or cat.startswith("dr"):
        return "dr"
    if cat.startswith("network"):
        return "network_egress"
    return "other"


def validate_plan_schema(plan: dict) -> dict:
    """Normalize planner JSON into a shape that downstream pricing can rely on.

    This is intentionally conservative: it never invents SKUs/meters.
    It only normalizes types, canonicalizes category/service_name, and applies safe defaults.
    """

    if not isinstance(plan, dict):
        return {"metadata": {}, "scenarios": []}

    plan.setdefault("metadata", {})
    plan.setdefault("scenarios", [])
    if not isinstance(plan["scenarios"], list):
        plan["scenarios"] = []

    for scen in plan["scenarios"]:
        if not isinstance(scen, dict):
            continue
        scen.setdefault("id", "baseline")
        scen.setdefault("label", scen["id"])
        scen.setdefault("description", "")
        scen.setdefault("resources", [])
        if isinstance(scen.get("resources"), dict):
            scen["resources"] = [scen["resources"]]
        elif not isinstance(scen.get("resources"), list):
            scen["resources"] = []

        for res in scen["resources"]:
            if not isinstance(res, dict):
                continue
            res.setdefault("id", "res")
            # --- Category / ServiceName canonicalization ---
            category_raw = str(res.get("category") or "")
            category = _canonical_category(category_raw)

            if category != (category_raw or ""):
                res["category_raw"] = category_raw or res.get("category_raw")

            # Fallback: if planner gives other/unknown category, infer from service name
            # so the resource remains priceable and taxonomy-compliant.
            if category.lower() in {"other", "unknown", "misc", FALLBACK_CATEGORY}:
                inferred = _infer_category_from_service_name(
                    str(res.get("service_name") or res.get("service_name_raw") or "")
                )
                if inferred:
                    category = inferred

            res["category"] = category

            # -----------------------------------------------------------------
            # Generic service-scoped category fallback:
            # If category still looks "fallback-ish" but we have a valid canonical
            # service_name, bind category to: service::<ServiceName>
            # This unlocks Retail API catalog routing without maintaining per-service
            # category maps.
            # -----------------------------------------------------------------
            cat_l = (res.get("category") or "").strip().lower()
            svc = (res.get("service_name") or "").strip()
            if svc and svc != "UNKNOWN_SERVICE" and cat_l in ("other", "unknown", "misc", FALLBACK_CATEGORY):
                res["category"] = f"service::{svc}"
            candidates = _category_candidates(res["category"])
            service_info = canonicalize_service_name(
                res.get("service_name"), category_candidates=candidates
            )
            res["service_name_raw"] = res.get("service_name_raw") or res.get("service_name")
            res["service_name_status"] = service_info.get("status")
            res["service_name_suggestions"] = _list_field(service_info.get("suggestions"))
            if service_info.get("canonical") == "UNKNOWN_SERVICE":
                res["service_name"] = "UNKNOWN_SERVICE"
            else:
                res["service_name"] = service_info["canonical"]

            # --- armSkuName normalization (never gates other defaults) ---
            res.setdefault("arm_sku_name", None)
            if not res.get("arm_sku_name"):
                sku = res.get("sku") or {}
                if isinstance(sku, dict) and sku.get("armSkuName"):
                    res["arm_sku_name"] = sku.get("armSkuName")

            # --- Safe defaults / normalization (MUST run for every resource) ---
            res.setdefault("region", None)
            res.setdefault("quantity", 1)
            res.setdefault("hours_per_month", HOURS_PROD)
            res.setdefault("billing_model", "payg")
            res.setdefault("workload_type", _default_workload_type(res["category"]))
            res.setdefault("criticality", "prod")
            res.setdefault("os_type", "linux" if res["category"].startswith("compute.") else "na")

            # Hint arrays must always be lists.
            res["product_name_contains"] = _list_field(res.get("product_name_contains"))
            res["sku_name_contains"] = _list_field(res.get("sku_name_contains"))
            res["meter_name_contains"] = _list_field(res.get("meter_name_contains"))
            res["arm_sku_name_contains"] = _list_field(res.get("arm_sku_name_contains"))

            metrics = res.get("metrics") if isinstance(res.get("metrics"), dict) else {}
            metrics = canonicalize_metrics(metrics)
            res["metrics"] = metrics
            if res["category"].startswith("storage") and "storage_gb" not in metrics:
                metrics["storage_gb"] = 100.0
            if res["category"].startswith("network") and "egress_gb_per_month" not in metrics:
                metrics["egress_gb_per_month"] = 100.0
            if res["category"].startswith("db.") and "vcores" not in metrics:
                metrics["vcores"] = 2
            if res["category"].startswith("cache.redis") and "throughput_mbps" not in metrics:
                metrics["throughput_mbps"] = 20
            res.setdefault("notes", "")
            res.setdefault("source", "llm-inferred")

            # -------------------------------------------------------------
            # Normalize pricing_components (optional)
            # -------------------------------------------------------------
            pcs = res.get("pricing_components")
            normalize_pricing_components(res)
            pcs = res.get("pricing_components")
            if pcs is None:
                continue
            if not isinstance(pcs, list):
                # If LLM emitted a single object, wrap it; else drop invalid
                pcs = [pcs] if isinstance(pcs, dict) else []

            normalized: List[Dict[str, Any]] = []
            seen_keys = set()
            for comp in pcs:
                if not isinstance(comp, dict):
                    continue
                key = str(comp.get("key") or "").strip()
                if not key or key in seen_keys:
                    continue
                seen_keys.add(key)

                comp_norm = copy.deepcopy(comp)

                # Defaults
                comp_norm.setdefault("label", "")
                comp_norm.setdefault("pricing_hints", {})
                if not isinstance(comp_norm["pricing_hints"], dict):
                    comp_norm["pricing_hints"] = {}

                comp_norm.setdefault("hours_behavior", "inherit")
                if comp_norm["hours_behavior"] not in ("inherit", "ignore"):
                    comp_norm["hours_behavior"] = "inherit"

                comp_norm.setdefault("units", {})
                if not isinstance(comp_norm["units"], dict):
                    comp_norm["units"] = {}

                unit_kind = str(comp_norm["units"].get("kind") or "").strip().lower()
                if unit_kind not in ("quantity", "metric", "fixed"):
                    unit_kind = "quantity"
                comp_norm["units"]["kind"] = unit_kind

                if unit_kind == "metric":
                    metric_key = str(comp_norm["units"].get("metric_key") or "").strip()
                    comp_norm["units"]["metric_key"] = metric_key
                    # Optional scale
                    if "scale" in comp_norm["units"]:
                        try:
                            comp_norm["units"]["scale"] = float(comp_norm["units"]["scale"])
                        except Exception:
                            comp_norm["units"].pop("scale", None)
                elif unit_kind == "fixed":
                    try:
                        comp_norm["units"]["value"] = float(comp_norm["units"].get("value", 1.0))
                    except Exception:
                        comp_norm["units"]["value"] = 1.0

                normalized.append(comp_norm)

            res["pricing_components"] = normalized

            # Enforce canonical metric keys for component metric_key (no silent fallbacks).
            comps = res.get("pricing_components") or []
            if isinstance(comps, list) and comps:
                for comp in comps:
                    units = (comp or {}).get("units") or {}
                    if not isinstance(units, dict):
                        continue
                    if str(units.get("kind") or "").strip().lower() != "metric":
                        continue
                    metric_key = str(units.get("metric_key") or "").strip()
                    if metric_key and metric_key not in CANONICAL_METRIC_KEYS and metric_key not in METRIC_KEY_ALIASES:
                        errors.append(
                            f"pricing_components[{res.get('id')}] metric_key '{metric_key}' is not canonical; "
                            f"use one of: {sorted(CANONICAL_METRIC_KEYS)}"
                        )
                    canon = METRIC_KEY_ALIASES.get(metric_key)
                    if canon and canon in metrics and metric_key not in metrics:
                        metrics[metric_key] = metrics[canon]

    return plan
