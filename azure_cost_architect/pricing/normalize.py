# azure_cost_architect/pricing/normalize.py
import re
from typing import Dict, Optional

from ..utils.knowledgepack import canonicalize_service_name, get_allowed_service_names
from .catalog_sources import _legacy_service_name, get_catalog_sources


def normalize_service_name(category: str, service_name: Optional[str]) -> str:
    """
    Normalize / infer Azure Retail 'serviceName' από λογικό category + υπάρχουσα τιμή.

    Σημαντικό:
    - Για App Service πρέπει να χρησιμοποιούμε **Azure App Service** (όχι "App Service"),
      γιατί έτσι εμφανίζεται στο Azure Retail Prices API.
    """

    cat = (category or "").lower()
    svc = (service_name or "").strip()
    allowed = set(get_allowed_service_names())

    if svc:
        canonical = canonicalize_service_name(svc)
        canonical_value = canonical.get("canonical")
        if canonical_value != "UNKNOWN_SERVICE" and (not allowed or canonical_value in allowed):
            return canonical_value
        for suggestion in canonical.get("suggestions") or []:
            if not allowed or suggestion in allowed:
                return suggestion

    sources = get_catalog_sources(cat)
    allowed_from_sources = {src.service_name for src in sources if src.service_name}

    if allowed_from_sources:
        if svc in allowed_from_sources:
            return svc
        return next(iter(allowed_from_sources))

    return _legacy_service_name(cat, svc)


def sku_keyword_match(requested_sku: str, item: Dict[str, str]) -> bool:
    """
    Lightweight keyword-based matching between a requested SKU hint and a Retail item.

    The goal is not strict equality but to ensure that high-signal hints such as
    reservation term (1y/3y), payg vs reservation, or blob tier (hot/cool/archive)
    are visible in the candidate's metadata (reservationTerm / productName / skuName).
    """

    hint = (requested_sku or "").lower()
    if not hint:
        return True

    # Only keep "safe" tokens we know how to interpret
    tokens = [
        t
        for t in re.split(r"[^a-z0-9]+", hint)
        if t
        in (
            "payg",
            "consumption",
            "reserved",
            "reservation",
            "1y",
            "1yr",
            "1year",
            "3y",
            "3yr",
            "3year",
            "hot",
            "cool",
            "archive",
            "lrs",
            "grs",
            "zrs",
            "gzrs",
            "ragrs",
        )
    ]

    if not tokens:
        return True

    text = " ".join(
        (
            (item.get("reservationTerm") or ""),
            (item.get("productName") or item.get("ProductName") or ""),
            (item.get("skuName") or ""),
            (item.get("armSkuName") or ""),
        )
    ).lower()

    # Normalise reservation tokens
    text = text.replace("one year", "1y").replace("three year", "3y")
    if "1 year" in text:
        text += " 1y"
    if "3 year" in text:
        text += " 3y"

    return all(tok in text for tok in tokens)
