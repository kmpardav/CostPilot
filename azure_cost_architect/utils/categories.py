"""Helpers for normalizing resource categories to canonical prefixes."""

from __future__ import annotations

from typing import Iterable, List

FAMILY_NOTE = "NOTE: This module collapses taxonomy categories into coarse families (compute/db/network/storage)."


# Map common category families to the canonical prefixes used by guardrails.
_CATEGORY_ALIASES = {
    "appservice": "compute",
    "appservice.plan": "compute",
    "function": "compute",
    "functions": "compute",
    "aks": "compute",
    "kubernetes": "compute",
    "container": "compute",
}


def canonical_required_category(category: str) -> str:
    """Return a normalized prefix for required-category filtering.

    The guardrails may work on coarse families (compute, db, cache, network, storage).
    Some services sit under other namespaces (e.g., appservice), so we collapse
    them to the compute family to avoid missing blockers.

    DO NOT use this for taxonomy validation or pricing catalogs.
    """

    low = (category or "other").strip().lower()
    for prefix, target in _CATEGORY_ALIASES.items():
        if low.startswith(prefix):
            return target

    # Default to the primary segment before any dot separator (compute.vm -> compute).
    base = low.split(".", 1)[0]
    return base or "other"


def normalize_required_categories(categories: Iterable[str]) -> List[str]:
    seen: set[str] = set()
    normalized: List[str] = []
    for cat in categories:
        norm = canonical_required_category(cat)
        if norm not in seen:
            seen.add(norm)
            normalized.append(norm)
    return normalized
