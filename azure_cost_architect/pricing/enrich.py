# azure_cost_architect/pricing/enrich.py
from typing import Any, Dict, List, Tuple
import asyncio
import os
import json
import logging

from ..config import DEFAULT_CURRENCY, DEFAULT_REGION, HOURS_PROD, CATALOG_DIR
from .cache import build_cache_key, get_cached_price, set_cached_price
from .normalize import normalize_service_name, sku_keyword_match
from .catalog import load_catalog
from .scoring import score_price_item
from .units import compute_units

_LOGGER = logging.getLogger(__name__)

# ------------------------------------------------------------
# Debug JSONL για scoring επιλογές
# ------------------------------------------------------------
DEBUG_ENV_VAR = "AZCOST_DEBUG_FILE"

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
    - With estimates (priced + estimated).
    """
    by_category: Dict[str, Dict[str, float]] = {}
    monthly_priced = 0.0
    yearly_priced = 0.0
    monthly_with_est = 0.0
    yearly_with_est = 0.0

    for res in scenario.get("resources", []):
        cat = res.get("category") or "other"
        status = (res.get("pricing_status") or "priced").lower()
        monthly = res.get("monthly_cost")
        yearly = res.get("yearly_cost")
        if monthly is None or yearly is None:
            continue

        # Συνολικά totals
        if status == "priced":
            monthly_priced += monthly
            yearly_priced += yearly
            monthly_with_est += monthly
            yearly_with_est += yearly
        elif status == "estimated":
            monthly_with_est += monthly
            yearly_with_est += yearly

        # By-category breakdown
        entry = by_category.setdefault(
            cat,
            {
                "monthly_priced": 0.0,
                "yearly_priced": 0.0,
                "monthly_with_estimates": 0.0,
                "yearly_with_estimates": 0.0,
            },
        )

        if status == "priced":
            entry["monthly_priced"] += monthly
            entry["yearly_priced"] += yearly
            entry["monthly_with_estimates"] += monthly
            entry["yearly_with_estimates"] += yearly
        elif status == "estimated":
            entry["monthly_with_estimates"] += monthly
            entry["yearly_with_estimates"] += yearly

    return {
        "currency": currency,
        # Backwards compatible totals
        "total_monthly": round(monthly_with_est, 2),
        "total_yearly": round(yearly_with_est, 2),
        # Νέα, πιο ρητά totals
        "monthly_priced": round(monthly_priced, 2),
        "yearly_priced": round(yearly_priced, 2),
        "monthly_with_estimates": round(monthly_with_est, 2),
        "yearly_with_estimates": round(yearly_with_est, 2),
        "by_category": {
            k: {
                "monthly": round(v["monthly_with_estimates"], 2),
                "yearly": round(v["yearly_with_estimates"], 2),
                "monthly_priced": round(v["monthly_priced"], 2),
                "yearly_priced": round(v["yearly_priced"], 2),
                "monthly_with_estimates": round(v["monthly_with_estimates"], 2),
                "yearly_with_estimates": round(v["yearly_with_estimates"], 2),
            }
            for k, v in by_category.items()
        },
    }


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

        items = filtered_items or all_items

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

    units = compute_units(resource, unit_of_measure)
    monthly_cost = units * float(unit_price)
    yearly_cost = monthly_cost * 12.0

    reservation_term = (price_info.get("reservationTerm") or "").lower()
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

    def _monthly(s: Dict[str, Any] | None) -> float:
        if not s:
            return 0.0
        t = s.get("totals") or {}
        return float(t.get("monthly_with_estimates") or t.get("total_monthly") or 0.0)

    if baseline and cost_opt:
        mb = _monthly(baseline)
        mc = _monthly(cost_opt)
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
        mh = _monthly(high_perf)
        mc = _monthly(cost_opt)
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
