from typing import Dict

from ..config import HOURS_PROD

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
    "blob.storage": "storage.blob",
    "storage.files": "storage.files",
    "storage.disk": "storage.disk",
    "backup": "backup.vault",
    "backup.vault": "backup.vault",
    "dr": "dr.asr",
    "site.recovery": "dr.asr",
    "bandwidth": "network.egress",
    "network.egress": "network.egress",
    "network.nat": "network.nat",
    "nat": "network.nat",
    "network.gateway": "network.gateway",
    "network.frontdoor": "network.frontdoor",
    "frontdoor": "network.frontdoor",
    "front.door": "network.frontdoor",
    "trafficmanager": "network.traffic_manager",
    "traffic.manager": "network.traffic_manager",
    "appgateway": "network.appgw",
    "app.gw": "network.appgw",
    "lb": "network.lb",
    "loadbalancer": "network.lb",
    "public.ip": "network.public_ip",
    "private.endpoint": "network.private_endpoint",
}


def _canonical_category(raw: str) -> str:
    cat = (raw or "other").lower().strip().replace(" ", ".").replace("-", ".")
    if cat in _CATEGORY_MAP:
        return _CATEGORY_MAP[cat]

    for prefix, canonical in _CATEGORY_MAP.items():
        if cat.startswith(prefix):
            return canonical
    return cat or "other"


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
        if not isinstance(scen["resources"], list):
            scen["resources"] = []

        for res in scen["resources"]:
            if not isinstance(res, dict):
                continue
            res.setdefault("id", "res")
            res["category"] = _canonical_category(res.get("category"))
            res.setdefault("service_name", None)
            res.setdefault("arm_sku_name", None)
            res.setdefault("region", None)
            res.setdefault("quantity", 1)
            res.setdefault("hours_per_month", HOURS_PROD)
            res.setdefault("billing_model", "payg")
            res.setdefault("workload_type", _default_workload_type(res["category"]))
            res.setdefault("criticality", "prod")
            res.setdefault("os_type", "linux" if res["category"].startswith("compute") else "na")
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
