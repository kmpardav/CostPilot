"""Catalog sanity helpers used by audits and tests.

These helpers are intentionally side-effect free: they only inspect the local
catalog files to confirm that expected meters/tiers are present. Pricing logic
must not depend on them at runtime.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Sequence

from .catalog import _catalog_filename
from .normalize import normalize_service_name
from ..config import CATALOG_DIR, DEFAULT_CURRENCY, DEFAULT_REGION


def _iter_catalog_items(
    category: str, *, catalog_dir: str, region: str, currency: str
) -> list[dict]:
    service_name = normalize_service_name(category, None)
    path = Path(catalog_dir) / _catalog_filename(service_name, region, currency)
    if not path.exists():
        return []

    items: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except Exception:
                continue
    return items


def assert_catalog_has_capacity_meters(
    *,
    category: str,
    patterns: Sequence[str],
    exclude: Iterable[str] | None = None,
    catalog_dir: str = CATALOG_DIR,
    region: str = DEFAULT_REGION,
    currency: str = DEFAULT_CURRENCY,
) -> None:
    """Assert that a storage catalog contains capacity-focused meters.

    The function scans the given catalog and ensures that at least one item
    contains all ``patterns`` (case-insensitive) while excluding any text that
    contains one of the ``exclude`` terms. It raises ``AssertionError`` with a
    short diagnostic summary when no match is found.
    """

    exclude = [e.lower() for e in exclude or []]
    required = [p.lower() for p in patterns]
    items = _iter_catalog_items(
        category, catalog_dir=catalog_dir, region=region, currency=currency
    )

    for item in items:
        text = " ".join(
            (
                str(item.get("productName", "")),
                str(item.get("skuName", "")),
                str(item.get("meterName", "")),
                str(item.get("armSkuName", "")),
                str(item.get("unitOfMeasure", "")),
            )
        ).lower()

        if any(term and term in text for term in exclude):
            continue

        if all(part in text for part in required):
            return

    sample = [(item.get("skuName"), item.get("meterName")) for item in items[:5]]
    raise AssertionError(
        "No capacity meter matched patterns={} (exclude={}) in category='{}' "
        "for region='{}', currency='{}'. Sample meters: {}".format(
            required, exclude, category, region, currency, sample
        )
    )


def assert_catalog_has_expected_tier(
    *,
    category: str,
    patterns: Sequence[str],
    fields: Sequence[str],
    catalog_dir: str = CATALOG_DIR,
    region: str = DEFAULT_REGION,
    currency: str = DEFAULT_CURRENCY,
) -> None:
    """Assert that a catalog exposes an expected tier/token across selected fields."""

    required = [p.lower() for p in patterns]
    field_set = set(fields)
    items = _iter_catalog_items(
        category, catalog_dir=catalog_dir, region=region, currency=currency
    )

    for item in items:
        haystack_parts = [str(item.get(f, "")) for f in field_set]
        haystack = " ".join(haystack_parts).lower()
        if all(part in haystack for part in required):
            return

    raise AssertionError(
        "Patterns={} were not found in fields={} for category='{}' (region='{}', "
        "currency='{}').".format(required, fields, category, region, currency)
    )

