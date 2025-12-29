import json
import os
import hashlib
from typing import Any, Dict

from rich.console import Console
from ..config import CACHE_FILE

console = Console()
_price_cache_best: Dict[str, Dict[str, Any]] = {}

# Bump when the cache key schema changes (prevents silent collisions with old keys).
CACHE_KEY_VERSION = "v2"

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

def _norm(s: Any) -> str:
    return (s or "").strip().lower()

def _notes_hash(resource: dict) -> str:
    """
    Hash notes so we don't leak/duplicate long user text into cache keys,
    while still making cache reuse safe across different intent.
    """
    notes = _norm(resource.get("notes"))
    if not notes:
        return "no-notes"
    return hashlib.sha1(notes.encode("utf-8")).hexdigest()[:12]

def build_cache_key(resource: dict, region: str, currency: str) -> str:
    """
    Cache key must include any fields that materially affect meter selection.

    IMPORTANT: scoring/select_best_candidate depends on:
      - criticality/environment
      - reservation_term
      - notes (linux/windows/spot/reserved/gp/serverless/etc.)
    so we include a stable intent signature to prevent cross-scenario contamination.
    """
    service_name = (resource.get("service_name") or "").strip()
    arm_sku_name = (resource.get("arm_sku_name") or "").strip()
    category = (resource.get("category") or "").strip()
    billing_model = (resource.get("billing_model") or "payg").strip()
    os_type = (resource.get("os_type") or "na").strip()

    env = _norm(resource.get("criticality") or resource.get("environment") or "prod")
    reservation_term = _norm(resource.get("reservation_term") or resource.get("reservationTerm"))
    notes_sig = _notes_hash(resource)

    # Versioned to avoid collisions with previous cache key schema.
    return "|".join(
        [
            CACHE_KEY_VERSION,
            service_name,
            arm_sku_name,
            region,
            currency,
            category,
            billing_model,
            os_type,
            env,
            reservation_term,
            notes_sig,
        ]
    )

def get_cached_price(key: str) -> dict:
    return _price_cache_best.get(key)

def set_cached_price(key: str, value: dict) -> None:
    _price_cache_best[key] = value
