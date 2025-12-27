#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
categories.py

This module defines:
1) The canonical INTERNAL guardrail families used by your tool.
2) A normalization layer that maps many possible user/LLM "category-like tokens"
   into those canonical families.

KEY IDEA (do not confuse with Excel taxonomy)
---------------------------------------------
Azure Retail taxonomy Excel shows:
- serviceFamily (e.g., "Compute", "Databases", "Networking", "Storage", ...)
- serviceName  (e.g., "Azure Kubernetes Service", "Azure Container Apps", ...)

Your tool uses a DIFFERENT concept:
- canonical guardrail families for completeness checks:
  compute, db, cache, network, storage

Therefore:
- It is OK that Excel says "Databases" while you use canonical key "db".
- It is OK that Excel says "Azure Kubernetes Service" while you accept "aks" as a shorthand
  that normalizes into the canonical family (compute).

What matters is:
- Consistency of canonical keys across config.py / cli.py / repair logic
- A robust alias table so that common synonyms don't cause false negatives.
"""

from __future__ import annotations

from typing import Optional


# ---------------------------------------------------------------------
# Canonical guardrail families (internal)
# ---------------------------------------------------------------------
# These are the only values that should be returned by canonical_required_category()
# for guardrail checks.
#
# IMPORTANT:
# Keep these aligned with config.DEFAULT_REQUIRED_CATEGORIES.
_CANONICAL_FAMILIES = {
    "compute",
    "db",
    "cache",
    "network",
    "storage",
}


# ---------------------------------------------------------------------
# Alias map: "prefix/synonym" -> canonical family
# ---------------------------------------------------------------------
# This dict is intentionally permissive:
# - It accepts multiple naming styles (Excel-like, slang, abbreviations).
# - It accepts both singular/plural ("database", "databases").
# - It accepts common Azure terms ("vnet", "vpn", "expressroute") that should count as "network".
#
# How matching works:
# - We normalize the input category string to lowercase.
# - We take the first segment before '.' as the "head" (e.g., "db.sql" -> "db").
# - We first try exact canonical match.
# - If not, we try alias match on:
#   a) full string prefix matches (most specific first)
#   b) head token match
#
# NOTE:
# Adding aliases is a SAFE change: it only improves normalization.
_CATEGORY_ALIASES = {
    # ---- Compute-like shorthands ----
    "appservice": "compute",
    "appservice.plan": "compute",
    "azureappservice": "compute",
    "function": "compute",
    "functions": "compute",
    "azurefunctions": "compute",
    "aks": "compute",
    "kubernetes": "compute",
    "k8s": "compute",
    "container": "compute",
    "containers": "compute",
    "containerapps": "compute",
    "azurecontainerapps": "compute",
    "vm": "compute",
    "vms": "compute",
    "virtualmachine": "compute",
    "virtualmachines": "compute",
    "compute": "compute",  # allow Excel family wording "Compute" -> compute

    # ---- Database-like shorthands (Excel family "Databases") ----
    "db": "db",
    "database": "db",
    "databases": "db",      # IMPORTANT: covers Excel family label
    "sql": "db",            # common shorthand; still okay because it's a guardrail family
    "sqldb": "db",
    "postgres": "db",
    "postgresql": "db",
    "mysql": "db",
    "mariadb": "db",
    "cosmos": "db",
    "cosmosdb": "db",
    "redis": "cache",       # redis is typically cache, even though Excel may list it under Databases

    # ---- Cache-like shorthands ----
    "cache": "cache",
    "caching": "cache",
    "redis.cache": "cache",
    "rediscache": "cache",

    # ---- Network-like shorthands (Excel family "Networking") ----
    "network": "network",
    "networking": "network",   # IMPORTANT: covers Excel family label
    "net": "network",
    "vnet": "network",
    "virtualnetwork": "network",
    "vpn": "network",
    "vpngateway": "network",
    "expressroute": "network",
    "lb": "network",
    "loadbalancer": "network",
    "frontdoor": "network",
    "applicationgateway": "network",
    "ddos": "network",
    "dns": "network",
    "cdn": "network",

    # ---- Storage-like shorthands (Excel family "Storage") ----
    "storage": "storage",       # IMPORTANT: covers Excel family label
    "blob": "storage",
    "blobs": "storage",
    "files": "storage",
    "file": "storage",
    "disk": "storage",
    "disks": "storage",
    "manageddisk": "storage",
    "manageddisks": "storage",
    "netapp": "storage",
}


def _norm(s: Optional[str]) -> str:
    """
    Normalize a category string:
    - None -> ""
    - strip whitespace
    - lowercase
    """
    return (s or "").strip().lower()


def canonical_required_category(category: str) -> Optional[str]:
    """
    Convert a user/LLM/internal category string into one canonical guardrail family.

    Returns:
        One of: {"compute", "db", "cache", "network", "storage"}
        or None if the category cannot be mapped.

    Why this exists:
        The tool's guardrails should not depend on the exact words the planner uses.
        Example: "databases.sql" and "db.sql" should both count as "db".
        Example: "networking.vnet" and "network.vnet" should both count as "network".

    Matching logic:
    1) Normalize input (lowercase, strip).
    2) If the full token is already canonical -> return it.
    3) Try the most specific alias keys first (prefix match).
       This allows mappings like "appservice.plan" before "appservice".
    4) Fall back to the head token (before '.') and match again.
    """
    c = _norm(category)
    if not c:
        return None

    # Already canonical?
    if c in _CANONICAL_FAMILIES:
        return c

    # Try prefix matches (most specific first: longer keys first).
    # Example: "appservice.plan.p1v3" should match "appservice.plan" before "appservice".
    for key in sorted(_CATEGORY_ALIASES.keys(), key=len, reverse=True):
        if c == key or c.startswith(key + "."):
            mapped = _CATEGORY_ALIASES[key]
            return mapped if mapped in _CANONICAL_FAMILIES else None

    # Head-token fallback: "databases.sql" -> head "databases"
    head = c.split(".", 1)[0]
    if head in _CANONICAL_FAMILIES:
        return head
    if head in _CATEGORY_ALIASES:
        mapped = _CATEGORY_ALIASES[head]
        return mapped if mapped in _CANONICAL_FAMILIES else None

    return None


def normalize_required_categories(required: list[str]) -> list[str]:
    """
    Normalize a list of "required categories" into canonical guardrail families.

    Input may contain:
    - canonical keys already (compute/db/cache/network/storage)
    - synonyms (databases/networking/vnet/sql/etc.)

    Output is:
    - unique canonical keys
    - stable order (first occurrence wins)

    This function is typically used by cli.py after reading:
    - config.DEFAULT_REQUIRED_CATEGORIES
    - or user-provided --required-categories
    """
    seen = set()
    out: list[str] = []

    for r in required or []:
        canon = canonical_required_category(r)
        if not canon:
            continue
        if canon not in seen:
            seen.add(canon)
            out.append(canon)

    return out
