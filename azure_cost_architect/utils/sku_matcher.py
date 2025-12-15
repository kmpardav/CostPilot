"""Utility helpers for validating and normalizing ARM SKU names.

This module is designed to keep planner output aligned with real Azure SKUs by
using an alias index derived from the local pricing catalogs.  The index is
loaded once (using :func:`load_sku_alias_index`) and then passed to
``match_sku`` whenever we need to validate or normalize a SKU suggestion.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, List, Optional

_ENV_ALIAS_INDEX = "AZCOST_SKU_ALIAS_INDEX"
_DEFAULT_ALIAS_FILE = Path(__file__).resolve().parents[2] / "out_kp" / "sku_alias_index.json"


def normalize_sku(name: str) -> str:
    """Normalize SKU strings by trimming, lowercasing, and removing separators."""

    return (name or "").strip().lower().replace(" ", "").replace("_", "")


def load_sku_alias_index(file_path: Optional[str] = None) -> Dict[str, Dict[str, List[str]]]:
    """Load the SKU alias index from JSON.

    The structure expected is ``{category: {normalized_sku: [aliases...]}}`` where
    the first entry in each alias list should be the canonical SKU to emit.  If
    the file is missing or unreadable, an empty mapping is returned so callers
    can no-op gracefully.
    """

    path = file_path or os.getenv(_ENV_ALIAS_INDEX) or str(_DEFAULT_ALIAS_FILE)

    try:
        with open(path, "r", encoding="utf-8") as handle:
            raw_index: Dict[str, Dict[str, List[str]]] = json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError, TypeError):
        return {}

    normalized_index: Dict[str, Dict[str, List[str]]] = {}
    for category, entries in (raw_index or {}).items():
        cat_key = (category or "").lower()
        normalized_index.setdefault(cat_key, {})
        for norm_key, aliases in (entries or {}).items():
            alias_list = aliases or []
            normalized_index[cat_key][normalize_sku(norm_key)] = alias_list
            for alias in alias_list:
                normalized_index[cat_key].setdefault(normalize_sku(alias), alias_list)

    return normalized_index


def match_sku(
    input_sku: str,
    category: str,
    alias_index: Dict[str, Dict[str, List[str]]],
) -> Dict[str, Optional[str]]:
    """Attempt to match an input SKU to the alias index for a given category.

    Returns a dictionary with the resolved SKU, how it was matched, and any
    suggestions if we could not find a direct match.
    """

    norm = normalize_sku(input_sku)
    cat_key = (category or "").lower()

    if cat_key not in alias_index:
        return {
            "matched_sku": None,
            "matched_by": None,
            "reason": f"Category '{cat_key}' not found in alias index.",
            "suggestions": [],
        }

    category_index = alias_index[cat_key]

    if norm in category_index:
        canonical = (category_index[norm] or [None])[0]
        return {
            "matched_sku": canonical,
            "matched_by": "normalized_alias",
            "reason": f"Normalized match for '{input_sku}' → '{canonical}'",
            "suggestions": [],
        }

    suggestions: List[str] = []
    for cand_norm, aliases in category_index.items():
        if norm in cand_norm or cand_norm in norm:
            suggestions.extend(aliases or [])

    return {
        "matched_sku": None,
        "matched_by": None,
        "reason": f"No direct match found for '{input_sku}'",
        "suggestions": sorted(set(suggestions))[:5],
    }


__all__ = ["normalize_sku", "load_sku_alias_index", "match_sku"]
