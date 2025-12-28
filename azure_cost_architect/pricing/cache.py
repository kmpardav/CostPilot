import json  # Standard library module: used to read/write JSON files (serialize/deserialize Python objects).
import os    # Standard library module: used for filesystem checks like os.path.exists().

from typing import Any, Dict  # Typing helpers:
                             # - Any: means "any type"
                             # - Dict: typing for dictionaries (hash maps).

from rich.console import Console  # Third-party library (rich): Console is used to print colored/well-formatted messages.
from ..config import CACHE_FILE    # Local import: brings in the path/name of the cache file from config.py.

console = Console()  # Create ONE Console instance (object) that we can reuse for printing warnings.

# Module-level (global) variable:
# This is a dictionary that will hold cached pricing results in memory while the program is running.
# Type meaning: Dict[str, Dict[str, Any]]
# - outer dict key: a cache key string (we build it with build_cache_key)
# - outer dict value: a dict (JSON-like) with cached pricing details
_price_cache_best: Dict[str, Dict[str, Any]] = {}

def load_price_cache() -> None:
    """
    Function: loads the cache JSON file from disk into the in-memory dictionary _price_cache_best.

    Return type: None (meaning: it does not return anything; it only changes global state).
    """
    global _price_cache_best  # "global" keyword: we want to MODIFY the module-level variable, not create a local one.

    # If the cache file does not exist, we simply keep an empty cache and exit.
    if not os.path.exists(CACHE_FILE):
        _price_cache_best = {}  # Ensure the in-memory cache is reset to empty.
        return                 # Exit the function early.

    # Try to read and parse JSON. If anything fails, we show a warning and reset cache.
    try:
        # Open the cache file for reading text ("r") with UTF-8 encoding.
        # Using encoding="utf-8" makes behavior consistent across OSes.
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)  # json.load(file_handle) parses JSON text into Python objects (dict/list/...).

        # We expect the cache to be a dictionary at the top level.
        # If the file contains something else, we discard it to avoid crashes later.
        _price_cache_best = data if isinstance(data, dict) else {}

    except Exception as ex:
        # Catch ANY exception (file permission, invalid JSON, partial write, etc.)
        # Print a yellow warning (Rich markup) and reset cache to empty.
        console.print(f"[yellow]Warning: failed to load {CACHE_FILE}: {ex}[/yellow]")
        _price_cache_best = {}

def save_price_cache() -> None:
    """
    Function: writes the in-memory cache dictionary _price_cache_best back to disk (CACHE_FILE).

    Return type: None (side-effect only).
    """
    try:
        # Open the cache file for writing ("w") in UTF-8.
        # This overwrites the whole file each time.
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            # json.dump(obj, file_handle, ...) writes JSON to the file.
            # indent=2 makes it human-readable.
            # ensure_ascii=False keeps Greek/unicode characters as-is (not escaped).
            json.dump(_price_cache_best, f, indent=2, ensure_ascii=False)

    except Exception as ex:
        # If we fail to write (disk full, no permissions, invalid path), warn but don't crash the whole program.
        console.print(f"[yellow]Warning: failed to save {CACHE_FILE}: {ex}[/yellow]")

def build_cache_key(resource: dict, region: str, currency: str) -> str:
    """
    Function: builds a UNIQUE-ish string key that represents "this resource priced in this region/currency".

    Inputs:
    - resource: dictionary with fields such as service_name, arm_sku_name, category, billing_model, os_type
    - region: armRegionName-like string (e.g., "westeurope")
    - currency: currency code (e.g., "EUR")

    Output:
    - A string key (pipe-separated) used to index _price_cache_best
    """

    # Extract (and normalize) the components used for the cache key.
    # .get(...) reads a key from dict safely, returning None if missing.
    # "or ''" ensures we never call .strip() on None.
    service_name = (resource.get("service_name") or "").strip()

    # arm_sku_name: typically used to better identify the exact SKU/meter you matched.
    arm_sku_name = (resource.get("arm_sku_name") or "").strip()

    # category: your internal canonical category (e.g., compute.vm, databases.sql, cache.redis).
    category = (resource.get("category") or "").strip()

    # billing_model: defaults to "payg" if not present.
    billing_model = (resource.get("billing_model") or "payg").strip()

    # os_type: defaults to "na" if not present (useful for VM pricing differences).
    os_type = (resource.get("os_type") or "na").strip()

    # Build the final cache key:
    # We join all fields with "|" to make it deterministic and easy to parse/debug.
    return "|".join([service_name, arm_sku_name, region, currency, category, billing_model, os_type])

def get_cached_price(key: str) -> dict:
    """
    Function: returns the cached value for a given key (if present).

    Note:
    - This returns whatever dict was stored in _price_cache_best[key]
    - If not found, it returns None (because dict.get(...) returns None by default)
    """
    return _price_cache_best.get(key)  # dict.get(key) -> value if exists else None

def set_cached_price(key: str, value: dict) -> None:
    """
    Function: stores a value in the in-memory cache under the given key.

    Return type: None (side-effect only).
    """
    _price_cache_best[key] = value  # Assignment into dict: overwrites if key already exists.
