import hashlib
import json
import json as _json
import os
from typing import Any, Dict

from rich.console import Console
from ..config import CACHE_FILE

console = Console()
_price_cache_best: Dict[str, Dict[str, Any]] = {}

# Bump when the cache key schema changes (prevents silent collisions with old keys).
CACHE_KEY_VERSION = "v3"

def load_price_cache() -> None:
    global _price_cache_best
    if not os.path.exists(CACHE_FILE):
        _price_cache_best = {}
        return
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        _price_cache_best = data if isinstance(data, dict) else {}
    except Exception as ex:
        console.print(f"[yellow]Warning: failed to load {CACHE_FILE}: {ex}[/yellow]")
        _price_cache_best = {}

def save_price_cache() -> None:
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(_price_cache_best, f, indent=2, ensure_ascii=False)
    except Exception as ex:
        console.print(f"[yellow]Warning: failed to save {CACHE_FILE}: {ex}[/yellow]")

def _pricing_signature(resource: dict) -> str:
    """
    Build a stable, pricing-relevant signature for cache keys.
    We intentionally ignore non-pricing fields (names, descriptions, etc.).
    """
    sig = {
        # primary routing
        "category": (resource.get("category") or "").strip(),
        "service_name": (resource.get("service_name") or "").strip(),
        "arm_sku_name": (resource.get("arm_sku_name") or "").strip(),
        "billing_model": (resource.get("billing_model") or "payg").strip(),
        "os_type": (resource.get("os_type") or "na").strip(),
        # sizing / quantity (these frequently change pricing selection)
        "quantity": resource.get("quantity", 1.0),
        "hours": resource.get("hours", 730),
        # optional hints that materially affect meter match
        "sku_name_hint": (resource.get("sku_name") or "").strip(),
        "meter_name_hint": (resource.get("meter_name") or "").strip(),
        "product_name_hint": (resource.get("product_name") or "").strip(),
        "price_type": (resource.get("price_type") or "").strip(),
        "reservation_term": (resource.get("reservation_term") or "").strip(),
        "tier": (resource.get("tier") or "").strip(),
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
    sid = (scenario_id or resource.get("scenario_id") or "na").strip()
    sig_hash = _pricing_signature(resource)
    return "|".join([CACHE_KEY_VERSION, region, currency, sid, sig_hash])

def get_cached_price(key: str) -> dict:
    return _price_cache_best.get(key)

def set_cached_price(key: str, value: dict) -> None:
    _price_cache_best[key] = value
