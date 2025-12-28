import json
import os
from typing import Any, Dict

from rich.console import Console
from ..config import CACHE_FILE

console = Console()
_price_cache_best: Dict[str, Dict[str, Any]] = {}

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

def build_cache_key(resource: dict, region: str, currency: str) -> str:
    service_name = (resource.get("service_name") or "").strip()
    arm_sku_name = (resource.get("arm_sku_name") or "").strip()
    category = (resource.get("category") or "").strip()
    billing_model = (resource.get("billing_model") or "payg").strip()
    os_type = (resource.get("os_type") or "na").strip()
    return "|".join([service_name, arm_sku_name, region, currency, category, billing_model, os_type])

def get_cached_price(key: str) -> dict:
    return _price_cache_best.get(key)

def set_cached_price(key: str, value: dict) -> None:
    _price_cache_best[key] = value
