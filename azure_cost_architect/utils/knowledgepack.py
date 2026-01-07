"""Helpers for loading the Retail Pricing knowledge pack and canonical names."""

from __future__ import annotations

import json
import logging
import os
import re
from difflib import get_close_matches
from functools import lru_cache
from pathlib import Path
from typing import Dict, List

from azure_cost_architect.taxonomy.registry import CanonicalService, TaxonomyRegistry

LOG = logging.getLogger(__name__)
_DEFAULT_CONTEXT_PATH = Path(__file__).resolve().parents[2] / "out_kp" / "llm_context.json"
_DEFAULT_TAXONOMY_PATH = Path(__file__).resolve().parents[2] / "taxonomy.json"
_FALLBACK_TAXONOMY_PATH = Path(__file__).resolve().parents[2] / "out_kp" / "taxonomy.json"

# Common alias -> Azure Retail Prices API serviceName canonical values
SERVICE_NAME_ALIASES: Dict[str, str] = {
    # Marketing / renamed services
    "microsoft purview": "Azure Purview",
    "azure purview": "Azure Purview",
    "microsoft sentinel": "Sentinel",
    "microsoft defender for cloud": "Microsoft Defender for Cloud",
    "entra id": "Azure Active Directory",
    "microsoft entra id": "Azure Active Directory",
    "azure ad": "Azure Active Directory",
    "azure ai services": "Cognitive Services",
    "azure cognitive services": "Cognitive Services",
    "api management": "API Management",
    "azure api management": "API Management",
}


@lru_cache(maxsize=1)
def load_llm_context() -> Dict:
    """Load the pre-generated llm_context.json payload (cached)."""

    path = os.getenv("AZURECOST_LLM_CONTEXT", str(_DEFAULT_CONTEXT_PATH))
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception as exc:
        LOG.warning("Failed to load llm_context.json from %s: %s", path, exc)
        return {"allowed_service_names": [], "service_metadata": {}}


@lru_cache(maxsize=1)
def load_taxonomy() -> Dict:
    """Load taxonomy.json (cached)."""
    env_path = os.getenv("AZURECOST_TAXONOMY")
    if env_path:
        path = Path(env_path)
    else:
        path = _DEFAULT_TAXONOMY_PATH if _DEFAULT_TAXONOMY_PATH.exists() else _FALLBACK_TAXONOMY_PATH

    if not path.exists():
        raise FileNotFoundError(f"taxonomy.json not found at {path}")

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        LOG.warning("Failed to load taxonomy.json from %s: %s", path, exc)
        return {}


def get_allowed_service_names() -> List[str]:
    ctx = load_llm_context()
    allowed = ctx.get("allowed_service_names") or []
    return list(allowed)


def get_compact_service_metadata(*, common_limit: int = 25, sample_limit: int = 3, token_limit: int = 5) -> Dict[str, Dict]:
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


def canonicalize_service_name(
    name: str,
    *,
    category_candidates: list[str] | None = None,
) -> Dict[str, object]:
    """Normalize user-supplied serviceName to a canonical Retail value.

    Key design points:
    - If llm_context.json is missing (allowed list empty), we *do not* force UNKNOWN_SERVICE.
      Instead, we treat the input as already-canonical and rely on category_candidates / catalog mapping.
    - If we do have an allowed list, we only emit values inside it.
    """

    raw = (name or "").strip()
    alias = SERVICE_NAME_ALIASES.get(raw.lower())
    if alias:
        raw = alias
    if not raw:
        return {"canonical": "UNKNOWN_SERVICE", "status": "missing", "suggestions": []}

    allowed = get_allowed_service_names()
    allowed_set = set(allowed)
    has_allowed = bool(allowed_set)
    allowed_lower = {svc.lower(): svc for svc in allowed}

    candidates = [c for c in (category_candidates or []) if c]
    if has_allowed:
        allowed_candidates = [c for c in candidates if c in allowed_set]
        if allowed_candidates:
            candidates = allowed_candidates

    def _in_allowed(candidate: str) -> bool:
        return bool(candidate) and (not has_allowed or candidate in allowed_set)

    def _suggestions(limit: int = 3, cutoff: float = 0.6) -> List[str]:
        scope = candidates or allowed
        if not scope:
            return []
        fuzzy = get_close_matches(raw, scope, n=limit, cutoff=cutoff)
        if len(fuzzy) < limit:
            for svc in scope:
                if svc not in fuzzy:
                    fuzzy.append(svc)
                if len(fuzzy) >= limit:
                    break
        return fuzzy[:limit]

    synonyms = {
        "azure cache for redis": ("Redis Cache", []),
        "redis": ("Redis Cache", []),
        "redis cache": ("Redis Cache", []),
        "azure sql": ("SQL Database", ["SQL Managed Instance"]),
        "sql": ("SQL Database", ["SQL Managed Instance"]),
        "vm": ("Virtual Machines", []),
        "virtual machine": ("Virtual Machines", []),
        "virtual machines": ("Virtual Machines", []),
        "ip addresses": ("Virtual Network", []),
        "public ip": ("Virtual Network", []),
        "public ip addresses": ("Virtual Network", []),
    }

    if not has_allowed:
        if raw.lower() in synonyms:
            canonical, extra = synonyms[raw.lower()]
            return {"canonical": canonical, "status": "synonym", "suggestions": extra}
        if candidates:
            return {
                "canonical": candidates[0],
                "status": "category_default",
                "suggestions": candidates[:3],
            }
        return {"canonical": raw, "status": "no_context", "suggestions": []}

    if _in_allowed(raw):
        return {"canonical": raw, "status": "exact", "suggestions": []}

    lowered = raw.lower()
    if lowered in allowed_lower and _in_allowed(allowed_lower[lowered]):
        canonical = allowed_lower[lowered]
        return {"canonical": canonical, "status": "case_fixed", "suggestions": []}

    if lowered in synonyms:
        canonical, extra = synonyms[lowered]
        if _in_allowed(canonical):
            return {"canonical": canonical, "status": "synonym", "suggestions": extra}

    fuzzy = get_close_matches(raw, allowed, n=3, cutoff=0.65)
    if fuzzy:
        return {"canonical": fuzzy[0], "status": "fuzzy", "suggestions": fuzzy[:3]}

    if candidates:
        return {
            "canonical": candidates[0],
            "status": "category_default",
            "suggestions": candidates[:3],
        }

    return {
        "canonical": "UNKNOWN_SERVICE",
        "status": "unknown",
        "suggestions": _suggestions(limit=3, cutoff=0.45),
    }


def build_taxonomy_registry(taxonomy: dict) -> TaxonomyRegistry:
    registry = TaxonomyRegistry()

    families = None
    if isinstance(taxonomy, dict):
        families = taxonomy.get("families")
    elif isinstance(taxonomy, list):
        families = taxonomy

    if families:
        for family in families:
            for service in family.get("services", []):
                category = service.get("category")
                if not category:
                    continue

                registry.register(
                    CanonicalService(
                        canonical_key=service["key"],
                        taxonomy_path=[
                            family["name"],
                            service["name"],
                        ],
                        category=category,
                        retail_service_name=service.get("retail_service_name", service["name"]),
                        region_mode=service.get("region_mode", "regional"),
                        pricing_strategy=service.get("pricing_strategy", "estimate_only"),
                        preferred_meter_keywords=service.get("preferred_meter_keywords", []),
                        disallowed_meter_keywords=service.get("disallowed_meter_keywords", []),
                        fallback_strategy=service.get("fallback_strategy", "estimate"),
                    )
                )

        return registry

    try:
        from ..pricing.catalog_sources import CATEGORY_CATALOG_SOURCES
    except Exception:
        return registry

    for category, sources in (CATEGORY_CATALOG_SOURCES or {}).items():
        service_name = None
        region_mode = "regional"
        if sources:
            source = sources[0]
            service_name = getattr(source, "service_name", None)
            region_mode = getattr(source, "arm_region_mode", "regional") or "regional"

        registry.register(
            CanonicalService(
                canonical_key=category,
                taxonomy_path=[category],
                category=category,
                retail_service_name=service_name or category,
                region_mode=region_mode,
                pricing_strategy="estimate_only",
                preferred_meter_keywords=[],
                disallowed_meter_keywords=[],
                fallback_strategy="estimate",
            )
        )

    return registry


# ---------------------------------------------------------------------------
# SKU suggestion helpers (taxonomy-driven, deterministic)
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _collect_all_arm_sku_names() -> List[str]:
    """Collect all distinct armSkuNames found in taxonomy.json.

    This is used as a deterministic fallback to suggest valid ARM SKU strings
    when the planner emits "portal slang".
    """

    taxonomy = load_taxonomy() or {}
    found: set[str] = set()

    def _walk(node: object) -> None:
        if not isinstance(node, dict):
            return

        # Meter nodes in our taxonomy store armSkuNames directly.
        arm_list = node.get("armSkuNames")
        if isinstance(arm_list, list):
            for v in arm_list:
                if isinstance(v, str) and v.strip():
                    found.add(v.strip())

        children = node.get("children")
        if isinstance(children, dict):
            for child in children.values():
                _walk(child)

    # Support both schema styles:
    # 1) dict of families: { "Databases": {children...}, ... }
    # 2) {"families": [ ... ]}
    if isinstance(taxonomy, dict) and "families" in taxonomy:
        families = taxonomy.get("families") or []
        if isinstance(families, list):
            for fam in families:
                _walk(fam)
    elif isinstance(taxonomy, dict):
        for fam in taxonomy.values():
            _walk(fam)
    elif isinstance(taxonomy, list):
        for fam in taxonomy:
            _walk(fam)

    return sorted(found)


def suggest_arm_sku_names(raw_sku: str, *, limit: int = 8) -> List[str]:
    """Suggest likely ARM SKU names from taxonomy based on a raw token.

    Heuristic: tokenized substring match on the armSkuNames universe.
    This is only a *suggestion* mechanism; it does not claim perfect mapping.
    """

    raw = (raw_sku or "").strip()
    if not raw:
        return []

    # Normalize common planner tokens like "GP_Gen5" -> ["gp", "gen5"]
    tokens = [t for t in re.split(r"[^a-zA-Z0-9]+", raw.lower()) if t]
    if not tokens:
        return []

    universe = _collect_all_arm_sku_names()
    scored: list[tuple[int, str]] = []
    for sku in universe:
        s = sku.lower()
        score = sum(1 for t in tokens if t in s)
        if score:
            scored.append((score, sku))

    scored.sort(key=lambda x: (x[0], len(x[1])), reverse=True)
    return [sku for _, sku in scored[:limit]]


__all__ = [
    "load_llm_context",
    "load_taxonomy",
    "get_allowed_service_names",
    "get_compact_service_metadata",
    "canonicalize_service_name",
    "build_taxonomy_registry",
    "suggest_arm_sku_names",
]
