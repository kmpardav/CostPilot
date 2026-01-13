import hashlib
import json
import json as _json
import os
from hashlib import sha1
from typing import Any, Dict

from rich.console import Console
from ..config import get_cache_file

console = Console()
_price_cache_best: Dict[str, Dict[str, Any]] = {}

# Bump when the cache key schema changes (prevents silent collisions with old keys).
# Cache schema bump: signature now considers category_priced_as
CACHE_KEY_VERSION = "v5"

def load_price_cache() -> None:
    global _price_cache_best
    cache_file = get_cache_file()
    if not os.path.exists(cache_file):
        _price_cache_best = {}
        return
    try:
        with open(cache_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        _price_cache_best = data if isinstance(data, dict) else {}
    except Exception as ex:
        console.print(f"[yellow]Warning: failed to load {cache_file}: {ex}[/yellow]")
        _price_cache_best = {}

def save_price_cache() -> None:
    cache_file = get_cache_file()
    try:
        os.makedirs(os.path.dirname(cache_file) or ".", exist_ok=True)
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(_price_cache_best, f, indent=2, ensure_ascii=False)
    except Exception as ex:
        console.print(f"[yellow]Warning: failed to save {cache_file}: {ex}[/yellow]")

def _norm(value: Any) -> str:
    return (str(value).strip() if value is not None else "").strip()

def _intent_signature(resource: dict) -> str:
    """
    Stable signature of the pricing intent when arm_sku_name is missing.
    Prevents cache collisions between resources that share service/category
    but differ in SKU/meter/product intent hints.
    """
    sku_contains = resource.get("sku_name_contains") or resource.get("skuNameContains") or []
    meter_contains = resource.get("meter_name_contains") or resource.get("meterNameContains") or []
    product_contains = resource.get("product_name_contains") or resource.get("productNameContains") or []

    if isinstance(sku_contains, str):
        sku_contains = [sku_contains]
    if isinstance(meter_contains, str):
        meter_contains = [meter_contains]
    if isinstance(product_contains, str):
        product_contains = [product_contains]

    raw = "|".join(
        [
            "sku=" + ",".join(sorted(_norm(x).lower() for x in sku_contains if _norm(x))),
            "meter=" + ",".join(sorted(_norm(x).lower() for x in meter_contains if _norm(x))),
            "prod=" + ",".join(sorted(_norm(x).lower() for x in product_contains if _norm(x))),
        ]
    )
    return sha1(raw.encode("utf-8")).hexdigest()[:12]

def _pricing_signature(resource: dict) -> str:
    """
    Build a stable, pricing-relevant signature for cache keys.
    We intentionally ignore non-pricing fields (names, descriptions, etc.).
    """
    arm_sku_name = _norm(resource.get("arm_sku_name") or resource.get("armSkuName"))
    intent_signature = _intent_signature(resource) if not arm_sku_name else ""
    sig = {
        # primary routing
        "category": _norm(resource.get("category_priced_as") or resource.get("category")).lower(),
        "service_name": _norm(resource.get("service_name") or resource.get("serviceName")).lower(),
        "arm_sku_name": arm_sku_name.lower(),
        "intent_signature": intent_signature,
        "billing_model": _norm(resource.get("billing_model") or resource.get("billingModel") or "payg").lower(),
        "os_type": _norm(resource.get("os_type") or resource.get("osType") or "na").lower(),
        # sizing / quantity (these frequently change pricing selection)
        "quantity": resource.get("quantity", 1.0),
        "hours": resource.get("hours_per_month", resource.get("hours", 730)),
        # optional hints that materially affect meter match
        "sku_name_hint": _norm(resource.get("sku_name") or resource.get("skuName")).lower(),
        "meter_name_hint": _norm(resource.get("meter_name") or resource.get("meterName")).lower(),
        "product_name_hint": _norm(resource.get("product_name") or resource.get("productName")).lower(),
        "price_type": _norm(resource.get("price_type") or resource.get("priceType")).lower(),
        "reservation_term": _norm(
            resource.get("reservation_term") or resource.get("reservationTerm")
        ).lower(),
        "tier": _norm(resource.get("tier")).lower(),
        # generic sizing knobs (safe to include if present)
        "vcores": resource.get("vcores"),
        "capacity_gb": resource.get("capacity_gb"),
        "storage_gb": resource.get("storage_gb"),
        "throughput": resource.get("throughput"),
    }
    payload = _json.dumps(sig, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def build_cache_key(resource: dict, region: str, currency: str, *, scenario_id: str | None = None) -> str:
    """
    Scenario-isolated cache key to prevent cross-scenario contamination.
    """
    sid = _norm(scenario_id or resource.get("scenario_id") or "na")
    sig_hash = _pricing_signature(resource)
    return "|".join(
        [
            CACHE_KEY_VERSION,
            _norm(region).lower(),
            _norm(currency).upper(),
            sid.lower(),
            sig_hash,
        ]
    )

def get_cached_price(key: str) -> dict:
    return _price_cache_best.get(key)

def set_cached_price(key: str, value: dict) -> None:
    _price_cache_best[key] = value

def cached_entry_is_usable(entry: dict, *, currency: str) -> bool:
    """
    Tiny schema guard: cache must contain the minimal fields we rely on downstream.
    If not, ignore cache and re-score from catalog.
    """
    if not isinstance(entry, dict):
        return False
    unit_price = entry.get("unit_price", entry.get("unitPrice"))
    sku_name = entry.get("sku_name", entry.get("skuName"))
    meter_name = entry.get("meter_name", entry.get("meterName"))
    cur = entry.get("currency_code", entry.get("currencyCode"))
    if unit_price is None or sku_name is None or meter_name is None:
        return False
    if cur and str(cur).upper() != str(currency).upper():
        return False
    return True
