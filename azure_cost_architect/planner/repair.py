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
from .contract import validate_pricing_contract
from .pricing_rules import (
    build_pricing_components_for_resource,
    normalize_pricing_components,
)
from .validation import validate_plan_schema


# ---------------------------------------------------------------------------
# Deterministic post-repair enhancements (no LLM dependency)
# - Strengthen pricing_hints using service_name/category when missing
# - Fill missing pricing_components for common usage-based services
# ---------------------------------------------------------------------------

def _append_unique(lst: List[str], value: str) -> None:
    if value and value not in lst:
        lst.append(value)


def _strengthen_hints(res: Dict) -> None:
    """If hints are empty/weak, add safe, generic contains tokens."""
    svc = (res.get("service_name") or "").strip()
    if svc and svc != "UNKNOWN_SERVICE":
        res.setdefault("product_name_contains", [])
        if isinstance(res["product_name_contains"], list):
            _append_unique(res["product_name_contains"], svc)

    cat = (res.get("category") or "").strip()
    if cat:
        res.setdefault("meter_name_contains", [])
        if isinstance(res["meter_name_contains"], list) and not res["meter_name_contains"]:
            c = cat.lower()
            if "dns" in c:
                _append_unique(res["meter_name_contains"], "Zone")
                _append_unique(res["meter_name_contains"], "Query")
            elif "frontdoor" in c or "cdn" in c:
                _append_unique(res["meter_name_contains"], "Request")
                _append_unique(res["meter_name_contains"], "Data Transfer")
            elif "servicebus" in c or "eventhub" in c:
                _append_unique(res["meter_name_contains"], "Message")


def _ensure_pricing_components(res: Dict) -> None:
    """Fill pricing_components when known usage-based services omitted components.

    Conservative: only adds components for services/categories we routinely meter,
    and only when canonical metrics exist (or a safe quantity-only component).
    """
    if res.get("pricing_components"):
        return

    metrics = res.get("metrics") or {}
    if not isinstance(metrics, dict):
        metrics = {}

    svc = (res.get("service_name") or "").strip().lower()
    cat = (res.get("category") or "").strip().lower()

    def _pc(
        key: str,
        label: str,
        *,
        units: Dict,
        hours_behavior: str = "ignore",
        pricing_hints: Optional[Dict] = None,
    ) -> Dict:
        return {
            "key": key,
            "label": label,
            "units": units,
            "hours_behavior": hours_behavior,
            "pricing_hints": pricing_hints or {},
        }

    pcs: List[Dict] = []

    # Azure DNS: zones (quantity) + queries (metric)
    if "azure dns" in svc or "dns" in cat:
        pcs.append(
            _pc(
                "zones",
                "Zones",
                units={"kind": "quantity"},
                pricing_hints={"meter_name_contains": ["Zone"]},
            )
        )
        if "queries_per_month" in metrics:
            pcs.append(
                _pc(
                    "queries",
                    "Queries",
                    units={"kind": "metric", "metric_key": "queries_per_month"},
                    pricing_hints={"meter_name_contains": ["Query", "Queries"]},
                )
            )

    # Azure Maps: transactions
    if "azure maps" in svc or "maps" in cat:
        if "transactions_per_month" in metrics:
            pcs.append(
                _pc(
                    "transactions",
                    "Transactions",
                    units={"kind": "metric", "metric_key": "transactions_per_month"},
                    pricing_hints={"meter_name_contains": ["Transaction", "Transactions"]},
                )
            )

    # Front Door / CDN: requests + egress
    if "front door" in svc or "frontdoor" in cat or "cdn" in cat:
        if "requests_per_month" in metrics:
            pcs.append(
                _pc(
                    "requests",
                    "Requests",
                    units={"kind": "metric", "metric_key": "requests_per_month"},
                    pricing_hints={"meter_name_contains": ["Request", "Requests"]},
                )
            )
        if "egress_gb_per_month" in metrics or "egress_gb" in metrics:
            pcs.append(
                _pc(
                    "egress",
                    "Egress (GB)",
                    units={"kind": "metric", "metric_key": "egress_gb_per_month"},
                    pricing_hints={"meter_name_contains": ["Data Transfer", "Egress", "GB"]},
                )
            )

    # Monitor / Log Analytics: ingestion
    if "log analytics" in svc or "azure monitor" in svc or "monitor" in cat or "loganalytics" in cat:
        if "data_processed_gb_per_month" in metrics:
            pcs.append(
                _pc(
                    "ingestion_gb",
                    "Ingestion (GB)",
                    units={"kind": "metric", "metric_key": "data_processed_gb_per_month"},
                    pricing_hints={"meter_name_contains": ["Ingestion", "Data", "GB"]},
                )
            )

    # Service Bus / Event Hubs: messages
    if "service bus" in svc or "servicebus" in cat or "event hub" in svc or "eventhubs" in cat:
        if "messages_per_month" in metrics:
            pcs.append(
                _pc(
                    "messages",
                    "Messages",
                    units={"kind": "metric", "metric_key": "messages_per_month"},
                    pricing_hints={"meter_name_contains": ["Message", "Messages"]},
                )
            )

    # Key Vault: transactions
    if "key vault" in svc or "keyvault" in cat:
        if "transactions_per_month" in metrics or "operations_per_month" in metrics or "requests_per_month" in metrics:
            pcs.append(
                _pc(
                    "transactions",
                    "Transactions",
                    units={"kind": "metric", "metric_key": "transactions_per_month"},
                    pricing_hints={"meter_name_contains": ["Operation", "Transaction", "Transactions"]},
                )
            )

    # Firewall / NAT: data processed
    if "firewall" in cat or "azure firewall" in svc or "nat" in cat or "nat gateway" in svc:
        if "data_processed_gb_per_month" in metrics:
            pcs.append(
                _pc(
                    "data_processed_gb",
                    "Data processed (GB)",
                    units={"kind": "metric", "metric_key": "data_processed_gb_per_month"},
                    pricing_hints={"meter_name_contains": ["Data", "Processed", "GB"]},
                )
            )

    if pcs:
        res["pricing_components"] = pcs


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
        return all(
            not res.get(field)
            for field in (
                "product_name_contains",
                "sku_name_contains",
                "meter_name_contains",
                "arm_sku_name_contains",
                "arm_sku_name",
            )
        )

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

    def _fill_missing_pricing_components() -> None:
        """Deterministically fill pricing_components for known services.

        This is intentionally conservative:
        - we do NOT guess unknown services
        - we do NOT synthesize components from random metrics
        - we only apply a small, explicit rule table (planner/pricing_rules.py)
        """

        for scen in updated.get("scenarios", []) or []:
            for res in scen.get("resources", []) or []:
                # If planner already emitted components, just normalize shape/aliases.
                if res.get("pricing_components"):
                    normalize_pricing_components(res)
                    continue

                comps = build_pricing_components_for_resource(res)
                if not comps:
                    continue

                # If a component expects hours_per_month, make sure a value exists.
                for comp in comps:
                    units = (comp or {}).get("units") or {}
                    if (
                        isinstance(units, dict)
                        and str(units.get("kind") or "").lower() == "metric"
                        and str(units.get("metric_key") or "") == "hours_per_month"
                    ):
                        # hours_per_month is normally a top-level field; keep it there and
                        # let enrich read it for component units computation.
                        if "hours_per_month" not in res:
                            res["hours_per_month"] = 730

                res["pricing_components"] = comps
                normalize_pricing_components(res)

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
                    _strengthen_hints(res)
                    _ensure_pricing_components(res)
                    break

    _fill_missing_pricing_components()
    for scen in updated.get("scenarios", []) or []:
        for res in scen.get("resources", []) or []:
            if not isinstance(res, dict):
                continue
            _strengthen_hints(res)
            _ensure_pricing_components(res)
    updated = validate_plan_schema(updated)
    contract_result = validate_pricing_contract(updated)
    return contract_result.plan


__all__ = [
    "apply_repairs",
    "build_category_candidates",
    "build_repair_targets",
    "call_repair_llm",
]
