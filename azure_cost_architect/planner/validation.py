from __future__ import annotations

from typing import Any, Dict, List

from ..config import HOURS_PROD
from ..pricing.catalog_sources import get_catalog_sources
from ..utils.knowledgepack import canonicalize_service_name

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


def _canonical_category(raw: str) -> str:
    if not raw:
        return "other"
    low = raw.strip().lower().replace(" ", "").replace("_", ".")
    return _CATEGORY_MAP.get(low, raw)


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
            res["category"] = _canonical_category(res.get("category"))
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
            res["metrics"] = metrics
            if res["category"].startswith("storage") and "storage_gb" not in metrics:
                metrics["storage_gb"] = 100.0
            if res["category"].startswith("network") and "egress_gb" not in metrics:
                metrics["egress_gb"] = 100.0
            if res["category"].startswith("db.") and "vcores" not in metrics:
                metrics["vcores"] = 2
            if res["category"].startswith("cache.redis") and "throughput_mbps" not in metrics:
                metrics["throughput_mbps"] = 20
            res.setdefault("notes", "")
            res.setdefault("source", "llm-inferred")

    return plan
