# azure_cost_architect/pricing/enrich.py
from typing import Any, Dict, List, Tuple, Optional
import asyncio
import os
import json
import logging
import re

from ..config import DEFAULT_CURRENCY, DEFAULT_REGION, HOURS_PROD, CATALOG_DIR
from .cache import build_cache_key, get_cached_price, set_cached_price
from .normalize import normalize_service_name, sku_keyword_match
from .catalog import load_catalog
from .scoring import score_price_item
from .units import compute_units

_LOGGER = logging.getLogger(__name__)

# Conservative placeholder to prevent undercounting when pricing is missing/ambiguous.
DEFAULT_MISSING_MONTHLY_PENALTY = 100.0

# ------------------------------------------------------------
# Debug JSONL για scoring επιλογές
# ------------------------------------------------------------
DEBUG_ENV_VAR = "AZCOST_DEBUG_FILE"


def _compute_delta_entry(current: float, baseline: float) -> Dict[str, Any]:
    absolute = round(current - baseline, 2)
    percent = None
    if baseline:
        percent = round((absolute / baseline) * 100.0, 2)
    return {"absolute": absolute, "percent": percent}


def compute_delta_vs_baseline(
    baseline_totals: Dict[str, Any], scenario_totals: Dict[str, Any]
) -> Dict[str, Any]:
    """Compute deltas for totals and per-category rollups versus a baseline."""

    if not baseline_totals:
        return {}

    base_categories = baseline_totals.get("by_category", {})
    scenario_categories = scenario_totals.get("by_category", {})

    delta_by_category: Dict[str, Dict[str, Any]] = {}
    for category, values in scenario_categories.items():
        base_vals = base_categories.get(category, {})
        modeled_current = values.get("monthly_priced", 0.0) + values.get(
            "monthly_estimated", 0.0
        )
        modeled_base = base_vals.get("monthly_priced", 0.0) + base_vals.get(
            "monthly_estimated", 0.0
        )
        delta_by_category[category] = {
            "monthly_priced": _compute_delta_entry(
                values.get("monthly_priced", 0.0), base_vals.get("monthly_priced", 0.0)
            ),
            "monthly_modeled": _compute_delta_entry(modeled_current, modeled_base),
            "yearly_priced": _compute_delta_entry(
                values.get("yearly_priced", 0.0), base_vals.get("yearly_priced", 0.0)
            ),
            "yearly_modeled": _compute_delta_entry(
                values.get("yearly_priced", 0.0) + values.get("yearly_estimated", 0.0),
                base_vals.get("yearly_priced", 0.0)
                + base_vals.get("yearly_estimated", 0.0),
            ),
        }

    return {
        "monthly_priced": _compute_delta_entry(
            scenario_totals.get("monthly_priced", 0.0),
            baseline_totals.get("monthly_priced", 0.0),
        ),
        "monthly_modeled": _compute_delta_entry(
            scenario_totals.get("modeled_total", 0.0),
            baseline_totals.get("modeled_total", 0.0),
        ),
        "yearly_priced": _compute_delta_entry(
            scenario_totals.get("yearly_priced", 0.0),
            baseline_totals.get("yearly_priced", 0.0),
        ),
        "yearly_modeled": _compute_delta_entry(
            scenario_totals.get("yearly_priced", 0.0) + scenario_totals.get("yearly_estimated", 0.0),
            baseline_totals.get("yearly_priced", 0.0) + baseline_totals.get("yearly_estimated", 0.0),
        ),
        "by_category": delta_by_category,
    }

def _get_debug_file() -> str:
    """
    Διαβάζει πάντα τη μεταβλητή περιβάλλοντος AZCOST_DEBUG_FILE τη στιγμή
    που γίνεται το append, ώστε να πιάνει τις ρυθμίσεις του CLI.
    """
    return os.getenv(DEBUG_ENV_VAR, "")



def _append_scoring_debug(
    scenario: Dict[str, Any],
    resource: Dict[str, Any],
    scored_items: List[Tuple[int, Dict[str, Any]]],
    selected_item: Dict[str, Any],
    *,
    currency: str,
    region: str,
) -> None:
    """Γράφει μία γραμμή JSON με τους top candidates & τον επιλεγμένο meter."""
    debug_file = _get_debug_file()
    if not debug_file:
        return

    try:
        top = []
        for score, it in scored_items[:10]:
            top.append(
                {
                    "score": score,
                    "skuName": it.get("skuName"),
                    "meterName": it.get("meterName"),
                    "productName": it.get("ProductName") or it.get("productName"),
                    "armSkuName": it.get("armSkuName"),
                    "unitPrice": it.get("unitPrice"),
                    "unitOfMeasure": it.get("unitOfMeasure"),
                    "type": it.get("type"),
                    "reservationTerm": it.get("reservationTerm"),
                }
            )
        rec = {
            "scenario_id": scenario.get("id") or scenario.get("name"),
            "resource_id": resource.get("id"),
            "category": resource.get("category"),
            "requested": {
                "serviceName": resource.get("service_name") or resource.get("serviceName"),
                "armSkuName": (resource.get("sku") or {}).get("armSkuName")
                or resource.get("arm_sku_name")
                or resource.get("armSkuName"),
            },
            "region": region,
            "currency": currency,
            "selected": {
                "skuName": selected_item.get("skuName"),
                "meterName": selected_item.get("meterName"),
                "productName": selected_item.get("ProductName")
                or selected_item.get("productName"),
                "armSkuName": selected_item.get("armSkuName"),
                "unitPrice": selected_item.get("unitPrice"),
                "unitOfMeasure": selected_item.get("unitOfMeasure"),
                "type": selected_item.get("type"),
                "reservationTerm": selected_item.get("reservationTerm"),
            },
            "candidates": top,
        }
        with open(debug_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        # Δεν θέλουμε να επηρεάζει την εκτέλεση σε περίπτωση σφάλματος I/O
        pass


# ------------------------------------------------------------
# Aggregation των κόστους ανά σενάριο
# ------------------------------------------------------------


def aggregate_scenario_costs(scenario: Dict[str, Any], currency: str) -> Dict[str, Any]:
    """
    Υπολογίζει συνολικά κόστη ανά scenario, ξεχωρίζοντας:
    - Priced only (μόνο resources με πλήρη τιμή)
    - With estimates (priced + estimated)
    - Missing (explicitly counted so incompleteness is visible).
    """
    by_category: Dict[str, Dict[str, float]] = {}
    monthly_priced = 0.0
    yearly_priced = 0.0
    monthly_estimated = 0.0
    yearly_estimated = 0.0
    monthly_with_est = 0.0
    yearly_with_est = 0.0
    monthly_missing = 0.0
    yearly_missing = 0.0
    missing_count = 0
    mismatch_count = 0
    reservation_ambiguous_count = 0
    priced_count = 0
    estimated_count = 0
    total_resources = len(scenario.get("resources", []))
    compare_skip_reason: Optional[str] = None

    for res in scenario.get("resources", []):
        cat = res.get("category") or "other"
        status = (res.get("pricing_status") or "priced").lower()
        monthly = res.get("monthly_cost")
        yearly = res.get("yearly_cost")

        if res.get("sku_mismatch") or status == "sku_mismatch":
            mismatch_count += 1
        if status == "reservation_uom_ambiguous":
            reservation_ambiguous_count += 1

        entry = by_category.setdefault(
            cat,
            {
                "monthly_priced": 0.0,
                "yearly_priced": 0.0,
                "monthly_estimated": 0.0,
                "yearly_estimated": 0.0,
                "monthly_missing": 0.0,
                "yearly_missing": 0.0,
                "monthly_with_estimates": 0.0,
                "yearly_with_estimates": 0.0,
            },
        )

        missing_like_status = status in {
            "missing",
            "sku_mismatch",
            "reservation_uom_ambiguous",
        }
        missing_reason = missing_like_status or monthly is None or yearly is None

        if missing_reason:
            missing_count += 1
            compare_skip_reason = compare_skip_reason or (
                "reservation_ambiguous" if status == "reservation_uom_ambiguous" else None
            )
            compare_skip_reason = compare_skip_reason or (
                "sku_mismatch" if status == "sku_mismatch" else None
            )
            compare_skip_reason = compare_skip_reason or (
                "missing_pricing" if status == "missing" or monthly is None else None
            )
            monthly_missing_contrib = max(
                float(monthly) if monthly is not None else 0.0,
                DEFAULT_MISSING_MONTHLY_PENALTY,
            )
            yearly_missing_contrib = max(
                float(yearly) if yearly is not None else 0.0,
                DEFAULT_MISSING_MONTHLY_PENALTY * 12,
            )
            monthly_missing += monthly_missing_contrib
            yearly_missing += yearly_missing_contrib
            monthly_with_est += monthly_missing_contrib
            yearly_with_est += yearly_missing_contrib
            entry["monthly_missing"] += monthly_missing_contrib
            entry["yearly_missing"] += yearly_missing_contrib
            entry["monthly_with_estimates"] += monthly_missing_contrib
            entry["yearly_with_estimates"] += yearly_missing_contrib
            continue

        # Συνολικά totals
        if status == "priced":
            monthly_priced += monthly
            yearly_priced += yearly
            monthly_with_est += monthly
            yearly_with_est += yearly
            priced_count += 1
            entry["monthly_priced"] += monthly
            entry["yearly_priced"] += yearly
            entry["monthly_with_estimates"] += monthly
            entry["yearly_with_estimates"] += yearly
        elif status == "estimated":
            monthly_estimated += monthly
            yearly_estimated += yearly
            monthly_with_est += monthly
            yearly_with_est += yearly
            estimated_count += 1
            entry["monthly_estimated"] += monthly
            entry["yearly_estimated"] += yearly
            entry["monthly_with_estimates"] += monthly
            entry["yearly_with_estimates"] += yearly
        else:
            # Unknown status is treated as missing to avoid undercounting.
            missing_count += 1
            compare_skip_reason = compare_skip_reason or "missing_pricing"
            monthly_missing_contrib = max(
                float(monthly) if monthly is not None else 0.0,
                DEFAULT_MISSING_MONTHLY_PENALTY,
            )
            yearly_missing_contrib = max(
                float(yearly) if yearly is not None else 0.0,
                DEFAULT_MISSING_MONTHLY_PENALTY * 12,
            )
            monthly_missing += monthly_missing_contrib
            yearly_missing += yearly_missing_contrib
            monthly_with_est += monthly_missing_contrib
            yearly_with_est += yearly_missing_contrib
            entry["monthly_missing"] += monthly_missing_contrib
            entry["yearly_missing"] += yearly_missing_contrib
            entry["monthly_with_estimates"] += monthly_missing_contrib
            entry["yearly_with_estimates"] += yearly_missing_contrib

        # By-category breakdown
    modeled_total = monthly_priced + monthly_estimated
    is_complete = (
        missing_count == 0
        and mismatch_count == 0
        and reservation_ambiguous_count == 0
    )
    comparable = is_complete and not compare_skip_reason

    completeness_ratio = 0.0
    if total_resources:
        completeness_ratio = (priced_count + estimated_count) / float(total_resources)
        if completeness_ratio > 1:
            completeness_ratio = 1.0
    if is_complete:
        completeness_ratio = 1.0

    if not comparable and compare_skip_reason is None:
        if mismatch_count:
            compare_skip_reason = "sku_mismatch"
        elif reservation_ambiguous_count:
            compare_skip_reason = "reservation_ambiguous"
        elif missing_count:
            compare_skip_reason = "missing_pricing"
        else:
            compare_skip_reason = "incomplete"

    return {
        "currency": currency,
        "is_complete": is_complete,
        "completeness": completeness_ratio,
        "comparable": comparable,
        "compare_skip_reason": compare_skip_reason,
        "missing_count": missing_count,
        "mismatch_count": mismatch_count,
        "reservation_ambiguous_count": reservation_ambiguous_count,
        # Backwards compatible totals
        "total_monthly": round(monthly_with_est, 2),
        "total_yearly": round(yearly_with_est, 2),
        # Νέα, πιο ρητά totals
        "monthly_priced": round(monthly_priced, 2),
        "yearly_priced": round(yearly_priced, 2),
        "monthly_estimated": round(monthly_estimated, 2),
        "yearly_estimated": round(yearly_estimated, 2),
        "monthly_missing": round(monthly_missing, 2),
        "yearly_missing": round(yearly_missing, 2),
        "priced_total": round(monthly_priced, 2),
        "estimated_total": round(monthly_estimated, 2),
        "missing_total": round(monthly_missing, 2),
        "modeled_total": round(modeled_total, 2),
        "monthly_with_estimates": round(monthly_with_est, 2),
        "yearly_with_estimates": round(yearly_with_est, 2),
        "by_category": {
            k: {
                "monthly": round(v["monthly_with_estimates"], 2),
                "yearly": round(v["yearly_with_estimates"], 2),
                "monthly_priced": round(v["monthly_priced"], 2),
                "yearly_priced": round(v["yearly_priced"], 2),
                "monthly_estimated": round(v["monthly_estimated"], 2),
                "yearly_estimated": round(v["yearly_estimated"], 2),
                "monthly_missing": round(v["monthly_missing"], 2),
                "yearly_missing": round(v["yearly_missing"], 2),
                "monthly_with_estimates": round(v["monthly_with_estimates"], 2),
                "yearly_with_estimates": round(v["yearly_with_estimates"], 2),
            }
            for k, v in by_category.items()
        },
    }


def attach_baseline_deltas(enriched_scenarios: List[Dict[str, Any]]) -> None:
    """Attach delta_vs_baseline field to every scenario totals."""

    if not enriched_scenarios:
        return

    baseline = next(
        (
            sc
            for sc in enriched_scenarios
            if (sc.get("id") or "").lower() == "baseline"
        ),
        enriched_scenarios[0],
    )
    baseline_totals = baseline.get("totals") or {}

    def _comparison_blocker(totals: Dict[str, Any]) -> Optional[str]:
        if totals.get("mismatch_count"):
            return "sku_mismatch"
        if totals.get("reservation_ambiguous_count"):
            return "reservation_ambiguous"
        if totals.get("missing_count"):
            return "missing_pricing"
        if totals.get("is_complete") is False:
            return totals.get("compare_skip_reason") or "incomplete"
        return None

    baseline_blocker = _comparison_blocker(baseline_totals)

    for sc in enriched_scenarios:
        sc.setdefault("totals", {})
        scenario_blocker = _comparison_blocker(sc["totals"])
        blocker = baseline_blocker or scenario_blocker
        sc["totals"]["comparable"] = blocker is None
        sc["totals"]["compare_skip_reason"] = blocker or sc["totals"].get(
            "compare_skip_reason"
        )
        if blocker:
            sc["totals"]["delta_vs_baseline"] = {
                "status": "not_comparable",
                "reason": blocker,
                "source": "baseline" if baseline_blocker else "scenario",
            }
        else:
            sc["totals"]["delta_vs_baseline"] = compute_delta_vs_baseline(
                baseline_totals, sc["totals"]
            )


# ------------------------------------------------------------
# Filtering των candidate items βάσει intent / SKU
# ------------------------------------------------------------


def filter_items_by_sku_intent(
    category: str, requested_sku: str, items: List[Dict[str, Any]]
) -> Tuple[List[Dict[str, Any]], bool]:
    """
    Εφαρμόζει "σκληρό" φιλτράρισμα στα Retail items με βάση το ζητούμενο SKU/tier.

    Επιστρέφει (filtered_items, had_mismatch).
    - Αν had_mismatch == True και filtered_items είναι άδειο, σημαίνει ότι δεν βρέθηκε
      κανένα meter συμβατό με το ζητούμενο SKU/tier.
    """
    cat = (category or "").lower()
    rs = (requested_sku or "").lower()

    if not rs:
        return items, False

    filtered = items

    # High-signal keyword matching (reservation term, blob tiers, payg/reservation)
    keyword_filtered = [it for it in filtered if sku_keyword_match(rs, it)]
    if keyword_filtered:
        filtered = keyword_filtered

    # App Service Plans – δεν επιτρέπουμε downgrade P → B ή S → B
    if cat.startswith("appservice"):
        if rs.startswith("p"):  # Premium
            filtered = [
                it
                for it in filtered
                if ("premium" in (it.get("productName") or "").lower())
                or (it.get("skuName") or "").lower().startswith("p")
            ]
        elif rs.startswith("s"):  # Standard
            filtered = [
                it
                for it in filtered
                if ("standard" in (it.get("productName") or "").lower())
                or (it.get("skuName") or "").lower().startswith("s")
            ]
        elif rs.startswith("b"):  # Basic
            filtered = [
                it
                for it in filtered
                if ("basic" in (it.get("productName") or "").lower())
                or (it.get("skuName") or "").lower().startswith("b")
            ]

    # Application Gateway v2 – κόβουμε Basic meters όταν ζητείται v2/WAF_v2
    if cat.startswith("network.appgw") and "v2" in rs:
        filtered = [
            it
            for it in filtered
            if ("v2" in (it.get("productName") or "").lower())
            and (
                "basic application gateway"
                not in (it.get("productName") or "").lower()
            )
        ]

    # Blob redundancy (LRS/GRS/ZRS) hints
    if cat.startswith("storage.blob"):
        requested_redundancy = _detect_redundancy_hint(rs)
        if requested_redundancy:
            filtered_with_redundancy = [
                it
                for it in filtered
                if _detect_redundancy_hint(
                    " ".join(
                        [
                            it.get("productName") or "",
                            it.get("meterName") or "",
                            it.get("skuName") or "",
                        ]
                    )
                )
                == requested_redundancy
            ]
            filtered = filtered_with_redundancy or filtered

    # SQL Single DB GP_Gen5_n – προτιμάμε Compute Gen5, όχι management/backup
    if cat.startswith("db.sql") and "gp_gen5" in rs:
        filtered = [
            it
            for it in filtered
            if ("compute gen5" in (it.get("productName") or "").lower())
            and (
                "shared resource management"
                not in (it.get("productName") or "").lower()
            )
            and ("backup" not in (it.get("productName") or "").lower())
        ]

    # Αν μετά το filtering δεν έμεινε τίποτα, σημαίνει ότι δεν βρήκαμε
    # συμβατά meters – θα χρειαστεί manual check.
    if filtered:
        return filtered, False
    else:
        return items, True


def _filter_by_billing_model(
    resource: Dict[str, Any], items: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    billing = (resource.get("billing_model") or "payg").lower()
    reservation_term = (resource.get("reservation_term") or resource.get("reservationTerm") or "").lower()

    def _matches_reservation(it: Dict[str, Any]) -> bool:
        term = (it.get("reservationTerm") or "").lower()
        if not reservation_term:
            return True
        if "3" in reservation_term:
            return "3" in term
        if "1" in reservation_term:
            return "1" in term
        return True

    if billing == "reserved":
        candidates = [
            it
            for it in items
            if (it.get("type") or "").lower() == "reservation" and _matches_reservation(it)
        ]
        if candidates:
            return candidates

    if billing == "spot":
        spot = [
            it
            for it in items
            if "spot" in (it.get("productName") or "").lower()
            or "spot" in (it.get("meterName") or "").lower()
        ]
        if spot:
            return spot

    # Default PAYG
    payg = [
        it
        for it in items
        if (it.get("type") or "").lower() != "reservation"
        and not (it.get("reservationTerm") or "")
    ]
    return payg


def _select_cheapest_item(
    resource: Dict[str, Any], items: List[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    arm_sku = resource.get("arm_sku_name") or resource.get("armSkuName") or ""
    candidates = [it for it in items if sku_keyword_match(arm_sku, it)]
    if not candidates:
        candidates = items
    if not candidates:
        return None
    return sorted(candidates, key=lambda it: float(it.get("unitPrice") or 0.0))[0]


def _detect_redundancy_hint(text: str) -> str:
    low = (text or "").lower()
    if "ragrs" in low or "ra-grs" in low:
        return "ragrs"
    if "gzrs" in low:
        return "gzrs"
    if "grs" in low:
        return "grs"
    if "zrs" in low:
        return "zrs"
    if "lrs" in low:
        return "lrs"
    return ""


def _price_blob_storage(
    resource: Dict[str, Any], category: str, region: str, currency: str
) -> bool:
    def _requested_redundancy(res: Dict[str, Any]) -> str:
        return _detect_redundancy_hint(
            " ".join(
                [
                    res.get("arm_sku_name") or "",
                    res.get("notes") or "",
                    res.get("sku_name") or "",
                    json.dumps(res.get("metrics") or {}),
                ]
            )
        )

    def _matches_redundancy(candidate: Dict[str, Any], requested: str) -> bool:
        if not requested:
            return True
        text = " ".join(
            [
                candidate.get("productName") or "",
                candidate.get("meterName") or "",
                candidate.get("skuName") or "",
            ]
        )
        cand = _detect_redundancy_hint(text)
        return not cand or cand == requested

    items = load_catalog(base_dir=CATALOG_DIR, category=category, region=region, currency=currency)
    if not items:
        resource.update(
            {
                "unit_price": None,
                "unit_of_measure": None,
                "currency_code": None,
                "sku_name": None,
                "meter_name": None,
                "product_name": None,
                "units": None,
                "monthly_cost": None,
                "yearly_cost": None,
                "error": "Blob storage pricing missing from catalog",
                "pricing_status": "missing",
            }
        )
        return True

    metrics = resource.get("metrics") or {}
    tiers = [
        ("hot", float(metrics.get("hot_gb") or metrics.get("storage_hot_gb") or 0.0)),
        ("cool", float(metrics.get("cool_gb") or metrics.get("storage_cool_gb") or 0.0)),
        ("archive", float(metrics.get("archive_gb") or metrics.get("storage_archive_gb") or 0.0)),
    ]

    requested_redundancy = _requested_redundancy(resource)

    if all(val <= 0 for _, val in tiers):
        fallback = float(metrics.get("storage_gb") or 0.0)
        if fallback <= 0:
            fallback = 100.0
        tiers[0] = ("hot", fallback)

    total_monthly = 0.0
    chosen: List[Dict[str, Any]] = []

    for tier, qty in tiers:
        if qty <= 0:
            continue

        def _tier_match(it: Dict[str, Any]) -> bool:
            text = " ".join(
                [
                    (it.get("productName") or ""),
                    (it.get("meterName") or ""),
                    (it.get("skuName") or ""),
                ]
            ).lower()
            return tier in text

        tier_items = [it for it in items if _tier_match(it)] or items
        tier_items = [it for it in tier_items if _matches_redundancy(it, requested_redundancy)] or tier_items
        capacity_first = [
            it
            for it in tier_items
            if "gb" in (it.get("unitOfMeasure") or "").lower()
            and "operation" not in (it.get("meterName") or "").lower()
        ]
        tier_items = capacity_first or tier_items
        selected = _select_cheapest_item(resource, tier_items)
        if not selected:
            continue

        uom = selected.get("unitOfMeasure") or ""
        pack = 1.0
        if "gb" in uom.lower():
            m = re.search(r"([\d,.]+)\s*gb", uom.lower())
            if m:
                try:
                    pack = float(m.group(1).replace(",", "")) or 1.0
                except ValueError:
                    pack = 1.0
        units = qty / pack
        cost = units * float(selected.get("unitPrice") or 0.0)
        total_monthly += cost
        chosen.append(
            {
                "tier": tier,
                "meter_name": selected.get("meterName"),
                "product_name": selected.get("productName") or selected.get("ProductName"),
                "unit_price": selected.get("unitPrice"),
                "unit_of_measure": selected.get("unitOfMeasure"),
                "currency_code": selected.get("currencyCode"),
                "units": units,
                "monthly_cost": cost,
            }
        )

    resource.update(
        {
            "unit_price": None,
            "unit_of_measure": None,
            "currency_code": currency,
            "sku_name": resource.get("arm_sku_name"),
            "meter_name": ", ".join(c.get("meter_name") or "" for c in chosen if c.get("meter_name")),
            "product_name": ", ".join(c.get("product_name") or "" for c in chosen if c.get("product_name")),
            "units": None,
            "monthly_cost": round(total_monthly, 2),
            "yearly_cost": round(total_monthly * 12, 2),
            "pricing_status": "estimated" if chosen else "missing",
            "error": "" if chosen else "Blob tier meters not found",
            "sku_candidates": chosen,
        }
    )
    return True


# ------------------------------------------------------------
# Pricing ενός resource από local catalog + cache
# ------------------------------------------------------------


async def fetch_price_for_resource(
    scenario: Dict[str, Any],
    resource: Dict[str, Any],
    default_region: str,
    currency: str,
    debug: bool = False,
) -> None:
    category = resource.get("category") or "other"
    service_name = normalize_service_name(category, resource.get("service_name"))
    arm_sku_name = resource.get("arm_sku_name") or resource.get("armSkuName") or None
    region = (resource.get("region") or default_region or DEFAULT_REGION).strip() or DEFAULT_REGION

    resource["service_name"] = service_name
    resource["region"] = region

    res_id = (resource.get("id") or "").lower()

    if debug and _LOGGER.isEnabledFor(logging.DEBUG):
        _LOGGER.debug(
            "Pricing resource id=%s category=%s service_name=%s arm_sku_name=%s region=%s",
            resource.get("id"),
            category,
            service_name,
            arm_sku_name,
            region,
        )

    # 0) Special cases που είναι λογικά resources χωρίς άμεσο κόστος
    # Virtual Network – δεν χρεώνεται απευθείας
    if category.startswith("network.vnet"):
        resource.update(
            {
                "unit_price": 0.0,
                "unit_of_measure": "VNet (no direct charge)",
                "currency_code": currency,
                "sku_name": "Virtual Network",
                "meter_name": "",
                "product_name": "Virtual Network (logical)",
                "sku_candidates": [],
                "pricing_status": "priced",
                "units": float(resource.get("quantity", 1.0)),
                "monthly_cost": 0.0,
                "yearly_cost": 0.0,
                "error": "",
            }
        )
        if debug:
            _LOGGER.debug("Resource %s is network.vnet – assigning 0 cost.", resource.get("id"))
        return

    # App Service Web App – το κόστος είναι στο Plan, όχι στο Web App
    if category.startswith("appservice") and (
        "webapp" in res_id
        or resource.get("kind") == "webapp"
        or resource.get("role") == "webapp"
    ):
        resource.update(
            {
                "unit_price": 0.0,
                "unit_of_measure": "Included in App Service plan",
                "currency_code": currency,
                "sku_name": resource.get("arm_sku_name") or "",
                "meter_name": "",
                "product_name": "Web App (logical, billed via App Service Plan)",
                "sku_candidates": [],
                "pricing_status": "priced",
                "units": float(resource.get("quantity", 1.0)),
                "monthly_cost": 0.0,
                "yearly_cost": 0.0,
                "error": "",
            }
        )
        if debug:
            _LOGGER.debug("Resource %s is WebApp logical – cost is in App Service plan.", resource.get("id"))
        return

    # Ειδικές διαδρομές pricing
    if category.startswith("storage.blob"):
        if _price_blob_storage(resource, category, region, currency):
            return

    # Cache key για price cache (json)
    cache_key = build_cache_key(resource, region, currency)
    price_info = get_cached_price(cache_key)

    if price_info and debug:
        _LOGGER.debug(
            "Cache hit for resource %s (category=%s, arm_sku_name=%s).",
            resource.get("id"),
            category,
            arm_sku_name,
        )

    if not price_info:
        # ------------------------------------------------------------
        # 1) Φόρτωση όλων των items από τον τοπικό catalog
        #    (αν δεν υπάρχει file, load_catalog θα προσπαθήσει να τον φτιάξει).
        # ------------------------------------------------------------
        all_items: List[Dict[str, Any]] = load_catalog(
            base_dir=CATALOG_DIR,
            category=category,
            region=region,
            currency=currency,
        )

        if not all_items:
            msg = (
                f"No pricing items found in local catalog for category='{category}', "
                f"region='{region}', currency='{currency}'."
            )
            resource.update(
                {
                    "unit_price": None,
                    "unit_of_measure": None,
                    "currency_code": None,
                    "sku_name": None,
                    "meter_name": None,
                    "product_name": None,
                    "units": None,
                    "monthly_cost": None,
                    "yearly_cost": None,
                    "error": "Price not found (empty local catalog)",
                    "sku_candidates": [],
                    "pricing_status": "missing",
                }
            )
            _LOGGER.warning("Pricing missing for resource %s: %s", resource.get("id"), msg)
            return

        # ------------------------------------------------------------
        # 2) Σκληρό filtering βάσει ζητούμενου SKU/tier (χωρίς API calls)
        # ------------------------------------------------------------
        filtered_items, had_mismatch = filter_items_by_sku_intent(
            category, arm_sku_name or "", all_items
        )
        resource["sku_mismatch"] = had_mismatch
        if had_mismatch and not filtered_items:
            resource.update(
                {
                    "unit_price": None,
                    "unit_of_measure": None,
                    "currency_code": None,
                    "sku_name": None,
                    "meter_name": None,
                    "product_name": None,
                    "units": None,
                    "monthly_cost": None,
                    "yearly_cost": None,
                    "error": "No allowed Retail meters match requested SKU/tier – manual check required",
                    "sku_candidates": [],
                    "pricing_status": "missing",
                }
            )
            _LOGGER.warning(
                "Resource %s has requested SKU='%s' but no compatible meters were found in catalog (category=%s).",
                resource.get("id"),
                arm_sku_name,
                category,
            )
            return

        # 2b) Billing model (payg/reserved/spot) filtering
        billing_filtered = _filter_by_billing_model(resource, filtered_items or all_items)
        items = (
            billing_filtered
            if billing_filtered is not None
            else (filtered_items or all_items)
        )

        if not items:
            resource.update(
                {
                    "unit_price": None,
                    "unit_of_measure": None,
                    "currency_code": None,
                    "sku_name": None,
                    "meter_name": None,
                    "product_name": None,
                    "units": None,
                    "monthly_cost": None,
                    "yearly_cost": None,
                    "error": "No pricing items match billing model",
                    "sku_candidates": [],
                    "pricing_status": "missing",
                }
            )
            return

        # ------------------------------------------------------------
        # 3) Scoring όλων των candidate items από τον κατάλογο
        # ------------------------------------------------------------
        scored_items: List[Tuple[int, Dict[str, Any]]] = [
            (score_price_item(resource, it, HOURS_PROD), it) for it in items
        ]

        # Θέλουμε: μεγαλύτερο score, αλλά σε ισοπαλία το ΦΘΗΝΟΤΕΡΟ unitPrice.
        scored_items.sort(
            key=lambda pair: (-pair[0], float(pair[1].get("unitPrice") or 0.0))
        )
        best_item_score, best_item = scored_items[0]

        if debug and _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug(
                "Selected meter for resource %s (category=%s): product='%s', meter='%s', sku='%s', unit_price=%s, score=%s",
                resource.get("id"),
                category,
                (best_item.get("ProductName") or best_item.get("productName")),
                best_item.get("meterName"),
                best_item.get("skuName"),
                best_item.get("unitPrice"),
                best_item_score,
            )

        # JSONL debug του scoring
        _append_scoring_debug(
            scenario,
            resource,
            scored_items,
            best_item,
            currency=currency,
            region=region,
        )

        candidates = [
            {
                "score": score,
                "arm_sku_name": it.get("armSkuName"),
                "sku_name": it.get("skuName"),
                "meter_name": it.get("meterName"),
                "product_name": it.get("productName") or it.get("ProductName"),
                "unit_price": it.get("unitPrice"),
                "unit_of_measure": it.get("unitOfMeasure"),
                "currency_code": it.get("currencyCode"),
                "type": it.get("type"),
                "reservationTerm": it.get("reservationTerm"),
            }
            for (score, it) in scored_items[:5]
        ]

        price_info = {
            "unit_price": best_item.get("unitPrice"),
            "unit_of_measure": best_item.get("unitOfMeasure"),
            "currency_code": best_item.get("currencyCode"),
            "sku_name": best_item.get("skuName"),
            "meter_name": best_item.get("meterName"),
            "product_name": best_item.get("ProductName") or best_item.get("productName"),
            "sku_candidates": candidates,
        }
        if best_item.get("reservationTerm"):
            price_info["reservationTerm"] = best_item.get("reservationTerm")
        if best_item.get("type"):
            price_info["type"] = best_item.get("type")

        set_cached_price(cache_key, price_info)

    # end if not price_info

    unit_price = price_info.get("unit_price")
    unit_of_measure = price_info.get("unit_of_measure") or ""
    currency_code = price_info.get("currency_code")
    price_type = (price_info.get("type") or "").lower()
    reservation_term_raw = price_info.get("reservationTerm") or ""
    reservation_term = reservation_term_raw.lower()

    # pricing_status: priced / estimated / missing
    pricing_status = "priced" if unit_price is not None else "missing"
    if pricing_status == "priced":
        # Σημείωσε explicit 'estimated' για κατηγορίες που ξέρουμε ότι το μοντέλο είναι απλουστευμένο
        if category.startswith("storage.blob") or category.startswith("network.appgw"):
            pricing_status = "estimated"

        resource.update(
            {
                "unit_price": unit_price,
                "unit_of_measure": unit_of_measure,
                "currency_code": currency_code,
                "sku_name": price_info.get("sku_name"),
                "meter_name": price_info.get("meter_name"),
                "product_name": price_info.get("product_name"),
                "type": price_info.get("type"),
                "reservationTerm": price_info.get("reservationTerm"),
                "sku_candidates": price_info.get("sku_candidates", []),
                "pricing_status": pricing_status,
                "error": "",
            }
        )

    if unit_price is None:
        resource.update(
            {
                "units": None,
                "monthly_cost": None,
                "yearly_cost": None,
                "pricing_status": "missing",
                "error": "Price item selected but unit_price is null",
            }
        )
        _LOGGER.warning(
            "Resource %s selected a price item but unit_price is null (category=%s).",
            resource.get("id"),
            category,
        )
        return

    ambiguous_reservation = False
    if price_type == "reservation" and reservation_term:
        uom_low = unit_of_measure.lower()
        if "hour" in uom_low or "month" in uom_low:
            ambiguous_reservation = True

    if ambiguous_reservation:
        resource.update(
            {
                "units": 1.0,
                "monthly_cost": DEFAULT_MISSING_MONTHLY_PENALTY,
                "yearly_cost": DEFAULT_MISSING_MONTHLY_PENALTY * 12,
                "pricing_status": "reservation_uom_ambiguous",
                "error": "Reservation unit of measure looks hourly/monthly; treated as ambiguous",
            }
        )
        return

    units = compute_units(resource, unit_of_measure)
    monthly_cost = units * float(unit_price)
    yearly_cost = monthly_cost * 12.0

    if price_type == "reservation" and reservation_term:
        # Εδώ θεωρούμε ότι unit_price είναι συνολικό κόστος για όλο το term
        if "3 year" in reservation_term:
            monthly_cost = float(unit_price) / 36.0
            yearly_cost = float(unit_price) / 3.0
        elif "1 year" in reservation_term:
            monthly_cost = float(unit_price) / 12.0
            yearly_cost = float(unit_price)

        # Σε reservation σενάρια συνήθως units=1 (αγοράζεις 1 reservation)
        units = 1.0

    requested_sku = (resource.get("arm_sku_name") or resource.get("armSkuName") or "").lower()
    resolved_text = " ".join(
        [
            str(resource.get("sku_name") or ""),
            str(resource.get("meter_name") or ""),
            str(resource.get("product_name") or ""),
        ]
    ).lower()
    if requested_sku and requested_sku not in resolved_text:
        resource["pricing_status"] = "sku_mismatch"
        resource["sku_mismatch"] = True

    resource["units"] = round(units, 4)
    resource["monthly_cost"] = round(monthly_cost, 2)
    resource["yearly_cost"] = round(yearly_cost, 2)


# ------------------------------------------------------------
# Sanity checks στα scenarios (π.χ. cost_optimized vs baseline)
# ------------------------------------------------------------


def _log_scenario_consistency(enriched_scenarios: List[Dict[str, Any]]) -> None:
    """
    Δεν αλλάζει τιμές, απλώς γράφει WARNING αν:
    - cost_optimized βγει ακριβότερο από baseline,
    - cost_optimized βγει ακριβότερο από high_performance.
    """
    if not enriched_scenarios:
        return

    def _name(s: Dict[str, Any]) -> str:
        return (s.get("label") or s.get("id") or "").lower()

    by_name = { _name(s): s for s in enriched_scenarios if _name(s) }

    def _find(keys: List[str]) -> Dict[str, Any] | None:
        for s in enriched_scenarios:
            name = _name(s)
            if any(k in name for k in keys):
                return s
        return None

    baseline = _find(["baseline"])
    cost_opt = _find(["cost_optimized", "cost-optimized", "cost optimised", "cost optimized"])
    high_perf = _find(["high_performance", "high-performance", "high performance"])

    def _monthly_modeled(s: Dict[str, Any] | None) -> float:
        if not s:
            return 0.0
        t = s.get("totals") or {}
        return float(t.get("modeled_total") or t.get("monthly_priced") or 0.0)

    def _is_comparable(s: Dict[str, Any] | None) -> bool:
        if not s:
            return False
        t = s.get("totals") or {}
        return bool(t.get("comparable") or t.get("is_complete"))

    if baseline and cost_opt:
        if not (_is_comparable(baseline) and _is_comparable(cost_opt)):
            _LOGGER.info(
                "Skipping cost ordering check for baseline vs cost_optimized because one is incomplete.",
            )
        else:
            mb = _monthly_modeled(baseline)
            mc = _monthly_modeled(cost_opt)
            if mc > mb:
                _LOGGER.warning(
                    "Cost-optimized scenario '%s' (%.2f) is more expensive than baseline '%s' (%.2f). "
                    "This may be acceptable, but please review large-cost resources (e.g. storage, SQL, Redis).",
                    baseline.get("label") or baseline.get("id"),
                    mc,
                    cost_opt.get("label") or cost_opt.get("id"),
                    mb,
                )

    if high_perf and cost_opt:
        if not (_is_comparable(high_perf) and _is_comparable(cost_opt)):
            _LOGGER.info(
                "Skipping cost ordering check for high_performance vs cost_optimized because one is incomplete.",
            )
        else:
            mh = _monthly_modeled(high_perf)
            mc = _monthly_modeled(cost_opt)
            if mc > mh:
                _LOGGER.warning(
                    "Cost-optimized scenario '%s' (%.2f) is more expensive than high-performance '%s' (%.2f). "
                    "Check scoring heuristics and SKUs for heavy resources.",
                    cost_opt.get("label") or cost_opt.get("id"),
                    mc,
                    high_perf.get("label") or high_perf.get("id"),
                    mh,
                )


# ------------------------------------------------------------
# Enrich ολόκληρου plan με τιμές από local catalogs + cache
# ------------------------------------------------------------


async def enrich_plan_with_prices(plan: Dict[str, Any], debug: bool = False) -> Dict[str, Any]:
    metadata = plan.get("metadata") or {}
    default_region = metadata.get("default_region") or DEFAULT_REGION
    currency = metadata.get("currency") or DEFAULT_CURRENCY

    scenarios = plan.get("scenarios") or []
    enriched_scenarios: List[Dict[str, Any]] = []

    _LOGGER.info(
        "Enriching plan with prices using local catalogs (default_region=%s, currency=%s, scenarios=%d).",
        default_region,
        currency,
        len(scenarios),
    )

    for scenario in scenarios:
        resources = scenario.get("resources") or []
        _LOGGER.info(
            "Enriching scenario '%s' (id=%s) with %d resources.",
            scenario.get("label") or scenario.get("id"),
            scenario.get("id"),
            len(resources),
        )

        for res in resources:
            res.setdefault("quantity", 1)
            res.setdefault("hours_per_month", HOURS_PROD)
            res.setdefault("billing_model", "payg")
            res.setdefault("criticality", "prod")
            res.setdefault("os_type", "na")
            res.setdefault("metrics", {})
            # Για debugging convenience
            res["_scenario_id"] = scenario.get("id")

        sem = asyncio.Semaphore(6)

        async def fetch_with_sem(res: Dict[str, Any]):
            async with sem:
                try:
                    await fetch_price_for_resource(
                        scenario,
                        res,
                        default_region,
                        currency,
                        debug=debug,
                    )
                except Exception as ex:
                    res.update(
                        {
                            "unit_price": None,
                            "unit_of_measure": None,
                            "currency_code": None,
                            "sku_name": None,
                            "meter_name": None,
                            "product_name": None,
                            "units": None,
                            "monthly_cost": None,
                            "yearly_cost": None,
                            "pricing_status": "missing",
                            "error": f"Exception during pricing: {ex}",
                            "sku_candidates": res.get("sku_candidates", []),
                        }
                    )
                    _LOGGER.exception(
                        "Exception while pricing resource %s (category=%s).",
                        res.get("id"),
                        res.get("category"),
                    )

        await asyncio.gather(*[fetch_with_sem(r) for r in resources], return_exceptions=True)

        enriched_scenario = {
            "id": scenario.get("id"),
            "label": scenario.get("label"),
            "description": scenario.get("description"),
            "resources": resources,
        }
        enriched_scenario["totals"] = aggregate_scenario_costs(enriched_scenario, currency=currency)
        _LOGGER.info(
            "Scenario '%s' totals: monthly_priced=%.2f, monthly_with_estimates=%.2f %s.",
            enriched_scenario.get("label") or enriched_scenario.get("id"),
            enriched_scenario["totals"]["monthly_priced"],
            enriched_scenario["totals"]["monthly_with_estimates"],
            currency,
        )
        enriched_scenarios.append(enriched_scenario)

    # Sanity checks στα scenarios (baseline vs cost_optimized vs high_performance)
    _log_scenario_consistency(enriched_scenarios)
    attach_baseline_deltas(enriched_scenarios)

    enriched_plan = {
        "metadata": {
            "version": metadata.get("version", "1.0"),
            "currency": currency,
            "default_region": default_region,
        },
        "scenarios": enriched_scenarios,
    }
    with open("debug_enriched.json", "w", encoding="utf-8") as f:
        json.dump(enriched_plan, f, indent=2, ensure_ascii=False)

    _LOGGER.info("Enrichment finished. Saved debug_enriched.json.")
    return enriched_plan
