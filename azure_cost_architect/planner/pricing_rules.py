"""Deterministic pricing-components rules.

This module is *pure policy* (no I/O).

Why it exists
-------------
We want usage-based and multi-meter services (DNS, Front Door, Monitor ingestion,
Service Bus messaging, Firewall/NAT data processing, etc.) to be modeled as a set
of deterministic pricing line-items, without hardcoding service splits inside the
pricing engine.

How it works
------------
* The planner may emit `resource.pricing_components`.
* If components are missing, the *repair pass* can fill them deterministically
  using `build_pricing_components_for_resource()`.
* The validator can normalize metric aliases via `canonicalize_metrics()`.

Component schema (current)
--------------------------
The project already uses this normalized shape (see planner/validation.py):

    {
      "key": "queries",
      "label": "Queries",
      "units": {"kind": "metric", "metric_key": "queries_per_month", "scale": 1e-6},
      "hours_behavior": "ignore",
      "pricing_hints": {"meter_name_contains": ["Query"]}
    }

The pricing layer expands each component into a child resource `--pc-<key>` and
selects a meter using `pricing_hints`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Canonical metrics schema
# ---------------------------------------------------------------------------

CANONICAL_METRIC_KEYS: set[str] = {
    # Usage counters (counts/month)
    "queries_per_month",
    "transactions_per_month",
    "requests_per_month",
    "operations_per_month",
    "messages_per_month",
    # Data volumes
    "data_processed_gb_per_month",
    "egress_gb_per_month",
    "ingress_gb_per_month",
    "storage_gb",
    # Licensing-style
    "users",
    "devices",
    # Sizing keys used elsewhere in the tool (not all are componentized)
    "vcores",
    "dtus",
    "iops",
    "throughput_ru",
    "throughput_mbps",
    # Helper to allow hourly components to read top-level hours_per_month
    "hours_per_month",
}


# Aliases we are willing to accept (backward compatibility)
METRIC_KEY_ALIASES: Dict[str, str] = {
    # Service-prefixed legacy keys -> canonical
    "dns_queries_per_month": "queries_per_month",
    "dns_query_count_per_month": "queries_per_month",
    "map_transactions_per_month": "transactions_per_month",
    "maps_transactions_per_month": "transactions_per_month",
    "http_requests_per_month": "requests_per_month",
    "api_calls_per_month": "requests_per_month",
    "ops_per_month": "operations_per_month",
    "monthly_operations": "operations_per_month",
    "msg_per_month": "messages_per_month",
    # Data
    "egress_gb": "egress_gb_per_month",
    "ingress_gb": "ingress_gb_per_month",
    "data_processed_gb": "data_processed_gb_per_month",
}


def canonicalize_metrics(metrics: Dict[str, Any]) -> Dict[str, Any]:
    """Return a new metrics dict with alias keys rewritten to canonical.

    Rule: if both alias and canonical exist, canonical wins.
    """

    if not isinstance(metrics, dict):
        return {}

    out: Dict[str, Any] = {}
    # First pass: copy canonical keys as-is
    for k, v in metrics.items():
        if k in CANONICAL_METRIC_KEYS:
            out[k] = v

    # Second pass: map aliases only if canonical missing
    for k, v in metrics.items():
        canon = METRIC_KEY_ALIASES.get(k)
        if canon and canon not in out:
            out[canon] = v

    # Finally: keep any other non-canonical keys (for backward compatibility)
    # but DO NOT let them override canonical values.
    for k, v in metrics.items():
        if k not in out:
            out[k] = v

    return out


# ---------------------------------------------------------------------------
# Pricing components rule table
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ComponentSpec:
    key: str
    label: str
    units: Dict[str, Any]
    hours_behavior: str = "ignore"
    pricing_hints: Optional[Dict[str, Any]] = None


def _pc(
    key: str,
    label: str,
    *,
    units: Dict[str, Any],
    hours_behavior: str = "ignore",
    pricing_hints: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    comp: Dict[str, Any] = {
        "key": key,
        "label": label,
        "units": units,
        "hours_behavior": hours_behavior,
        "pricing_hints": pricing_hints or {},
    }
    return comp


def _metric_units(metric_key: str, *, scale: Optional[float] = None) -> Dict[str, Any]:
    u: Dict[str, Any] = {"kind": "metric", "metric_key": metric_key}
    if scale is not None:
        u["scale"] = scale
    return u


def _fixed_units(value: float) -> Dict[str, Any]:
    return {"kind": "fixed", "value": float(value)}


def _quantity_units() -> Dict[str, Any]:
    return {"kind": "quantity"}


SERVICE_COMPONENT_RULES: Dict[str, List[Dict[str, Any]]] = {
    # Azure DNS: zones + queries
    "azure dns": [
        _pc(
            "zones",
            "Zones",
            units=_quantity_units(),
            hours_behavior="ignore",
            pricing_hints={
                "product_name_contains": ["DNS", "Zone"],
                "meter_name_contains": ["Zone"],
            },
        ),
        _pc(
            "queries",
            "Queries",
            # Many DNS meters are priced per million queries; keep scale optional.
            units=_metric_units("queries_per_month"),
            hours_behavior="ignore",
            pricing_hints={
                "product_name_contains": ["DNS", "Query"],
                "meter_name_contains": ["Query"],
            },
        ),
    ],
    # Azure Maps: transactions
    "azure maps": [
        _pc(
            "transactions",
            "Transactions",
            units=_metric_units("transactions_per_month"),
            hours_behavior="ignore",
            pricing_hints={
                "product_name_contains": ["Maps"],
                "meter_name_contains": ["Transaction", "Transactions"],
            },
        )
    ],
    # Log Analytics / Monitor ingestion (GB)
    "log analytics": [
        _pc(
            "ingestion_gb",
            "Log ingestion (GB)",
            units=_metric_units("data_processed_gb_per_month"),
            hours_behavior="ignore",
            pricing_hints={
                "meter_name_contains": ["Ingestion", "GB"],
                "product_name_contains": ["Log Analytics"],
            },
        )
    ],
    "azure monitor": [
        _pc(
            "ingestion_gb",
            "Data ingestion (GB)",
            units=_metric_units("data_processed_gb_per_month"),
            hours_behavior="ignore",
            pricing_hints={
                "meter_name_contains": ["Ingestion", "GB"],
                "product_name_contains": ["Monitor"],
            },
        )
    ],
    # Service Bus: messaging operations (messages)
    "service bus": [
        _pc(
            "messages",
            "Messages",
            units=_metric_units("messages_per_month"),
            hours_behavior="ignore",
            pricing_hints={
                "meter_name_contains": ["Messaging", "Operation", "Operations"],
                "product_name_contains": ["Service Bus"],
            },
        )
    ],
    # Front Door / CDN: requests + egress
    "front door": [
        _pc(
            "requests",
            "Requests",
            units=_metric_units("requests_per_month"),
            hours_behavior="ignore",
            pricing_hints={"meter_name_contains": ["Request", "Requests"]},
        ),
        _pc(
            "egress",
            "Egress (GB)",
            units=_metric_units("egress_gb_per_month"),
            hours_behavior="ignore",
            pricing_hints={"meter_name_contains": ["Data Transfer", "Egress", "GB"]},
        ),
    ],
    "azure cdn": [
        _pc(
            "requests",
            "Requests",
            units=_metric_units("requests_per_month"),
            hours_behavior="ignore",
            pricing_hints={"meter_name_contains": ["Request", "Requests"]},
        ),
        _pc(
            "egress",
            "Egress (GB)",
            units=_metric_units("egress_gb_per_month"),
            hours_behavior="ignore",
            pricing_hints={"meter_name_contains": ["Data Transfer", "Egress", "GB"]},
        ),
    ],
    # Key Vault: operations (10K / 1M etc)
    "key vault": [
        _pc(
            "operations",
            "Operations",
            units=_metric_units("operations_per_month"),
            hours_behavior="ignore",
            pricing_hints={
                "product_name_contains": ["Key Vault"],
                "meter_name_contains": ["Operation", "Operations"],
            },
        )
    ],
    # Azure Firewall: hourly deployment + data processed
    "azure firewall": [
        _pc(
            "deployment_hours",
            "Deployment (hours)",
            units=_metric_units("hours_per_month"),
            hours_behavior="inherit",
            pricing_hints={"meter_name_contains": ["Deployment"]},
        ),
        _pc(
            "data_processed",
            "Data processed (GB)",
            units=_metric_units("data_processed_gb_per_month"),
            hours_behavior="ignore",
            pricing_hints={"meter_name_contains": ["Data Processed"]},
        ),
    ],
    # NAT Gateway: hourly gateway + data processed
    "nat gateway": [
        _pc(
            "gateway_hours",
            "Gateway (hours)",
            units=_metric_units("hours_per_month"),
            hours_behavior="inherit",
            pricing_hints={
                "product_name_contains": ["NAT Gateway"],
                "meter_name_contains": ["Gateway"],
            },
        ),
        _pc(
            "data_processed",
            "Data processed (GB)",
            units=_metric_units("data_processed_gb_per_month"),
            hours_behavior="ignore",
            pricing_hints={
                "product_name_contains": ["NAT Gateway"],
                "meter_name_contains": ["Data Processed"],
            },
        ),
    ],
    "azure nat gateway": [
        _pc(
            "gateway_hours",
            "Gateway (hours)",
            units=_metric_units("hours_per_month"),
            hours_behavior="inherit",
            pricing_hints={
                "product_name_contains": ["NAT Gateway"],
                "meter_name_contains": ["Gateway"],
            },
        ),
        _pc(
            "data_processed",
            "Data processed (GB)",
            units=_metric_units("data_processed_gb_per_month"),
            hours_behavior="ignore",
            pricing_hints={
                "product_name_contains": ["NAT Gateway"],
                "meter_name_contains": ["Data Processed"],
            },
        ),
    ],
}


def build_pricing_components_for_resource(res: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return a deterministic pricing_components list for *known* services.

    If service not recognized, returns empty list (no fallback guessing here).
    """

    service = str(res.get("service_name") or "").strip().lower()
    if not service:
        return []

    comps = SERVICE_COMPONENT_RULES.get(service)
    if not comps:
        return []

    # Deep-copy-ish (dicts only)
    return [dict(c) for c in comps]


def normalize_pricing_components(res: Dict[str, Any]) -> None:
    """Normalize a resource's pricing_components in-place (shape + aliases).

    * Ensures list[dict]
    * Ensures `units.metric_key` uses canonical key if alias
    """

    comps = res.get("pricing_components")
    if not comps:
        return
    if not isinstance(comps, list):
        res["pricing_components"] = []
        return

    out: List[Dict[str, Any]] = []
    for c in comps:
        if not isinstance(c, dict):
            continue
        key = str(c.get("key") or "").strip()
        units = c.get("units") or {}
        if not key or not isinstance(units, dict):
            continue
        uk = str(units.get("kind") or "").strip().lower()
        if uk == "metric":
            mk = str(units.get("metric_key") or "").strip()
            if mk in METRIC_KEY_ALIASES:
                units["metric_key"] = METRIC_KEY_ALIASES[mk]
        c["units"] = units
        out.append(c)
    res["pricing_components"] = out
