"""Helpers for loading the Retail Pricing knowledge pack and canonical names."""

from __future__ import annotations

import json
import os
from difflib import get_close_matches
from functools import lru_cache
from pathlib import Path
from typing import Dict, List

_DEFAULT_CONTEXT_PATH = Path(__file__).resolve().parents[2] / "out_kp" / "llm_context.json"


@lru_cache(maxsize=1)
def load_llm_context() -> Dict:
    """Load the pre-generated llm_context.json payload (cached)."""

    path = os.getenv("AZURECOST_LLM_CONTEXT", str(_DEFAULT_CONTEXT_PATH))
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return {}


def get_allowed_service_names() -> List[str]:
    ctx = load_llm_context()
    allowed = ctx.get("allowed_service_names") or []
    return list(allowed)


def get_compact_service_metadata(*, common_limit: int = 30, sample_limit: int = 3, token_limit: int = 5) -> Dict[str, Dict]:
    """Return a compact subset of service metadata for prompt injection."""

    ctx = load_llm_context()
    meta = ctx.get("service_metadata") or {}
    if not meta:
        return {}

    ranked = sorted(
        meta.items(),
        key=lambda kv: (kv[1].get("count", 0) or 0),
        reverse=True,
    )

    compact: Dict[str, Dict] = {}
    for name, info in ranked[:common_limit]:
        compact[name] = {
            "family": info.get("serviceFamily"),
            "top_tokens": [t[0] for t in (info.get("top_tokens") or [])[:token_limit]],
            "sample_products": (info.get("sample_productNames") or [])[:sample_limit],
            "sample_skus": (info.get("sample_skuNames") or [])[:sample_limit],
            "sample_meters": (info.get("sample_meterNames") or [])[:sample_limit],
        }
    return compact


def canonicalize_service_name(name: str) -> Dict[str, object]:
    """Normalize user-supplied serviceName to the canonical Retail value."""

    raw = (name or "").strip()
    allowed = get_allowed_service_names()
    allowed_lower = {svc.lower(): svc for svc in allowed}
    synonyms = {
        "azure cache for redis": ("Redis Cache", []),
        "redis": ("Redis Cache", []),
        "azure openai": ("Foundry Models", ["Foundry Tools"]),
        "openai": ("Foundry Models", ["Foundry Tools"]),
        "ip addresses": ("Virtual Network", []),
        "public ip": ("Virtual Network", []),
        "public ip addresses": ("Virtual Network", []),
    }

    if raw in allowed_lower.values():
        return {"canonical": raw, "status": "exact", "suggestions": []}

    lowered = raw.lower()
    if lowered in allowed_lower:
        canonical = allowed_lower[lowered]
        return {"canonical": canonical, "status": "case_fixed", "suggestions": []}

    if lowered in synonyms:
        canonical, extra = synonyms[lowered]
        return {"canonical": canonical, "status": "synonym", "suggestions": extra}

    fuzzy = get_close_matches(raw, allowed, n=3, cutoff=0.65)
    if fuzzy:
        return {"canonical": fuzzy[0], "status": "fuzzy", "suggestions": fuzzy}

    return {"canonical": "UNKNOWN_SERVICE", "status": "unknown", "suggestions": get_close_matches(raw, allowed, n=3, cutoff=0.45)}


__all__ = [
    "load_llm_context",
    "get_allowed_service_names",
    "get_compact_service_metadata",
    "canonicalize_service_name",
]
