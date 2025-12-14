#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
discover_services.py — Enumerate Azure Retail Prices API serviceName/serviceFamily/productName "universe"

Goal
- Build a local index of *all* distinct `serviceName` values (and their `serviceFamily`) seen in the Azure Retail Prices API.
- Optionally emit productName samples per service so you can understand what each catalog contains.

Why this exists
- The Retail Prices API has no dedicated "list services" endpoint; the practical approach is to page through
  /api/retail/prices and collect distinct fields.

Docs reference:
- Azure Retail Prices API: https://learn.microsoft.com/en-us/rest/api/cost-management/retail-prices/azure-retail-prices

Usage examples
1) Discover serviceNames for one region (fast-ish):
   python discover_services.py --currency EUR --region westeurope --outdir out

2) Discover serviceNames across ALL regions (large):
   python discover_services.py --currency EUR --region all --max-pages 200 --outdir out

3) Primary meter region only (often cleaner):
   python discover_services.py --currency EUR --region westeurope --primary-only --outdir out

Outputs (in --outdir)
- services_index.json : mapping serviceName -> stats (serviceFamily, count, sample product/sku/meter names)
- services_list.txt   : one serviceName per line (stable sorted)
- summary.md          : human-readable summary (top services by item count)

Notes
- `$top` must be 1..1000. This script clamps it and also sanitizes any weird nextLink that returns invalid `$top`.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import time
from collections import defaultdict
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import requests

RETAIL_API_URL = "https://prices.azure.com/api/retail/prices"
DEFAULT_API_VERSION = "2023-01-01-preview"

# -----------------------------
# Helpers
# -----------------------------

def clamp_top(n: int) -> int:
    """Retail Prices API supports $top 1..1000."""
    try:
        n = int(n)
    except Exception:
        return 1000
    if n < 1:
        return 1000
    if n > 1000:
        return 1000
    return n


def sanitize_next_link(next_link: str, page_size: int) -> str:
    """
    Defensive: if the API returns a nextLink with an invalid $top (e.g., negative),
    replace it with a valid value.
    """
    if not next_link:
        return ""
    # Replace $top=-1000 (or any non-positive) with $top=<page_size>
    def _fix(m):
        raw = m.group(2)
        try:
            val = int(raw)
        except Exception:
            val = page_size
        if val <= 0:
            val = page_size
        return f"{m.group(1)}{val}"

    next_link = re.sub(r"([?&]\$top=)(-?\d+)", _fix, next_link)
    # If there is no $top at all, do nothing (API default is already 1000)
    return next_link


def http_get_json(session: requests.Session, url: str, retries: int = 4, backoff: float = 1.2) -> Dict[str, Any]:
    last_ex: Optional[Exception] = None
    for attempt in range(retries):
        try:
            r = session.get(url, timeout=(10, 60))
            r.raise_for_status()
            return r.json()
        except Exception as ex:
            last_ex = ex
            sleep_s = (backoff ** attempt) + random.random() * 0.25
            time.sleep(sleep_s)
    raise RuntimeError(f"GET failed after retries: {last_ex}") from last_ex


def build_first_url(
    *,
    api_version: str,
    currency: str,
    region: str,
    page_size: int,
    primary_only: bool,
    odata_filter: Optional[str],
) -> str:
    # Build as a string (requests params encoding + $filter quoting tends to be annoying to keep readable)
    url = f"{RETAIL_API_URL}?api-version={api_version}&currencyCode={currency}"

    # Region filtering: only if region != "all"
    # API uses armRegionName for filtering (OData)
    if region and region.lower() != "all":
        region = region.strip().lower()
        region_filter = f"armRegionName eq '{region}'"
        odata_filter = f"({odata_filter}) and {region_filter}" if odata_filter else region_filter

    if primary_only:
        # As per MS docs, pass meterRegion='primary' (with quotes)
        url += "&meterRegion='primary'"

    # Clamp page size
    page_size = clamp_top(page_size)
    url += f"&$top={page_size}"

    if odata_filter:
        # Keep it URL-safe with minimal changes (spaces -> %20 etc.)
        from urllib.parse import quote
        url += "&$filter=" + quote(odata_filter, safe="()'=,:$")

    return url


@dataclass
class ServiceStats:
    serviceFamily: Optional[str] = None
    item_count: int = 0
    sample_productNames: list[str] = None
    sample_skuNames: list[str] = None
    sample_meterNames: list[str] = None

    def __post_init__(self):
        self.sample_productNames = self.sample_productNames or []
        self.sample_skuNames = self.sample_skuNames or []
        self.sample_meterNames = self.sample_meterNames or []


def add_sample(lst: list[str], value: str, limit: int) -> None:
    value = (value or "").strip()
    if not value:
        return
    if value in lst:
        return
    if len(lst) < limit:
        lst.append(value)
    else:
        # reservoir-ish replace
        if random.random() < 0.10:
            lst[random.randrange(0, len(lst))] = value


# -----------------------------
# Main
# -----------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="Discover Azure Retail Prices API serviceName/serviceFamily universe.")
    ap.add_argument("--currency", default=os.getenv("AZURECOST_DEFAULT_CURRENCY", "EUR"))
    ap.add_argument("--region", default=os.getenv("AZURECOST_DEFAULT_REGION", "westeurope"),
                    help="armRegionName to filter (e.g., westeurope). Use 'all' for no region filter.")
    ap.add_argument("--api-version", default=DEFAULT_API_VERSION)
    ap.add_argument("--top", type=int, default=1000, help="Page size ($top). Clamped to 1..1000.")
    ap.add_argument("--max-pages", type=int, default=50, help="Safety limit for pages (set higher for full crawl).")
    ap.add_argument("--max-items", type=int, default=0, help="Stop after N items (0 = no limit).")
    ap.add_argument("--primary-only", action="store_true", help="Use meterRegion='primary'.")
    ap.add_argument("--filter", default="", help="Optional OData $filter string (WITHOUT the $filter= prefix).")
    ap.add_argument("--sample-limit", type=int, default=8, help="How many samples to keep per service.")
    ap.add_argument("--outdir", default="out_services", help="Output directory.")
    args = ap.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    page_size = clamp_top(args.top)

    url = build_first_url(
        api_version=args.api_version,
        currency=args.currency,
        region=args.region,
        page_size=page_size,
        primary_only=bool(args.primary_only),
        odata_filter=(args.filter or "").strip() or None,
    )

    session = requests.Session()
    services: Dict[str, ServiceStats] = {}
    total_items = 0
    page = 0

    while url:
        page += 1
        if args.max_pages and page > args.max_pages:
            break

        data = http_get_json(session, url)
        items = data.get("Items") or data.get("items") or []
        next_link = data.get("NextPageLink") or data.get("nextPageLink") or ""

        for it in items:
            total_items += 1
            svc = (it.get("serviceName") or "").strip()
            fam = (it.get("serviceFamily") or "").strip() or None
            if not svc:
                continue
            st = services.get(svc)
            if not st:
                st = ServiceStats(serviceFamily=fam, item_count=0)
                services[svc] = st

            st.item_count += 1
            if st.serviceFamily is None and fam:
                st.serviceFamily = fam

            add_sample(st.sample_productNames, it.get("productName", ""), args.sample_limit)
            add_sample(st.sample_skuNames, it.get("skuName", ""), args.sample_limit)
            add_sample(st.sample_meterNames, it.get("meterName", ""), args.sample_limit)

            if args.max_items and total_items >= args.max_items:
                url = ""
                break

        if not url:
            break

        url = sanitize_next_link(next_link, page_size)

    # Write outputs
    index_payload = {k: asdict(v) for k, v in services.items()}
    (outdir / "services_index.json").write_text(json.dumps(index_payload, indent=2, ensure_ascii=False), encoding="utf-8")

    services_sorted = sorted(services.keys(), key=lambda s: s.lower())
    (outdir / "services_list.txt").write_text("\n".join(services_sorted) + "\n", encoding="utf-8")

    # A tiny markdown summary
    top_by_count = sorted(services.items(), key=lambda kv: kv[1].item_count, reverse=True)[:50]
    md_lines = []
    md_lines.append("# Azure Retail Prices — Discovered services summary")
    md_lines.append("")
    md_lines.append(f"- Region filter: `{args.region}`")
    md_lines.append(f"- Currency: `{args.currency}`")
    md_lines.append(f"- Pages crawled: `{page}`")
    md_lines.append(f"- Total items scanned: `{total_items}`")
    md_lines.append(f"- Distinct serviceName: `{len(services)}`")
    md_lines.append("")
    md_lines.append("## Top services by item count (first 50)")
    md_lines.append("")
    md_lines.append("| serviceName | serviceFamily | items | sample productName |")
    md_lines.append("|---|---:|---:|---|")
    for svc, st in top_by_count:
        sample = (st.sample_productNames[0] if st.sample_productNames else "")
        md_lines.append(f"| {svc} | {st.serviceFamily or ''} | {st.item_count} | {sample} |")
    (outdir / "summary.md").write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    print(f"[ok] wrote {outdir/'services_index.json'}")
    print(f"[ok] wrote {outdir/'services_list.txt'}")
    print(f"[ok] wrote {outdir/'summary.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
