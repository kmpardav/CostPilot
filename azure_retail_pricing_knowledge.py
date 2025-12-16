#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
azure_retail_pricing_knowledge.py (v3) — Knowledge Pack builder with CHECKPOINT + RESUME

What it does
- Crawls Azure Retail Prices API and produces:
  - taxonomy.json           (full hierarchy: family -> service -> product -> sku -> meter)
  - services_universe.json  (per serviceName: top products/SKUs/meters + regions)
  - llm_context.json        (prompt steering pack + query/ranking rules)
  - state.json              (resume checkpoint state)

Why v3
- Adds robust checkpointing + resume:
  - Writes state.json every N pages (default 25)
  - Can resume from state.json (default) or a user-provided --resume-url
  - Handles transient DNS/network hiccups more gracefully with longer retries/backoff
- Keeps output Windows-safe (UTF-8) and allows --errors replace

Usage
1) Regional pack (recommended for actual pricing):
   python azure_retail_pricing_knowledge.py --region westeurope --currency EUR --primary-only --max-pages 2000 --outdir out_kp_we

2) Global pack (steering / taxonomy):
   python azure_retail_pricing_knowledge.py --region all --currency EUR --primary-only --max-pages 5000 --outdir out_kp_global

3) Resume from checkpoint automatically:
   python azure_retail_pricing_knowledge.py --region all --currency EUR --primary-only --outdir out_kp_global --resume

4) Force resume from a specific nextLink:
   python azure_retail_pricing_knowledge.py --outdir out_kp_global --resume-url "<NextPageLink>"
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Optional, List, Tuple
from collections import Counter, defaultdict

import requests

BASE_URL = "https://prices.azure.com/api/retail/prices"
DEFAULT_API_VERSION = "2023-01-01-preview"
TOKEN_SPLIT = re.compile(r"[^a-zA-Z0-9]+")


# -----------------------------
# Helpers
# -----------------------------

def clamp_top(n: int) -> int:
    try:
        n = int(n)
    except Exception:
        return 1000
    return 1000 if n < 1 or n > 1000 else n


def norm(v: Any) -> str:
    return (v or "").strip()


def tokenize(s: str) -> List[str]:
    s = norm(s).lower()
    return [p for p in TOKEN_SPLIT.split(s) if len(p) >= 2]


def sanitize_next_link(url: str, page_size: int) -> str:
    """Fix any weird NextPageLink containing invalid $top like -1000."""
    if not url:
        return ""
    return re.sub(r"([?&]\$top=)(-?\d+)", lambda m: f"{m.group(1)}{page_size}", url)


def safe_write_json(path: Path, obj: Any, *, encoding: str, errors: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding=encoding, errors=errors) as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def safe_read_json(path: Path, *, encoding: str, errors: str) -> Optional[dict]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding=encoding, errors=errors))
    except Exception:
        return None


def top_k(counter: Counter, k: int) -> List[Tuple[str, int]]:
    return counter.most_common(k)


def build_first_url(*, api_version: str, currency: str, region: str, top: int, primary_only: bool) -> str:
    top = clamp_top(top)
    url = f"{BASE_URL}?api-version={api_version}&currencyCode={currency}&$top={top}"
    if primary_only:
        # NOTE: Azure Retail API supports meterRegion='primary' (with single quotes)
        url += "&meterRegion='primary'"
    if region and region.lower() != "all":
        url += f"&$filter=armRegionName eq '{region.strip().lower()}'"
    return url


def http_get_json(
    session: requests.Session,
    url: str,
    *,
    retries: int = 10,
    backoff: float = 1.6,
    timeout: Tuple[int, int] = (10, 90),
) -> Dict[str, Any]:
    """
    More resilient GET:
    - more retries
    - longer exponential backoff
    - catches Requests exceptions (DNS, connect reset, timeouts, etc.)
    """
    last: Optional[Exception] = None
    for attempt in range(retries):
        try:
            r = session.get(url, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except requests.exceptions.RequestException as ex:
            last = ex
            sleep_s = (backoff ** attempt) + random.random()
            time.sleep(sleep_s)
    raise RuntimeError(f"GET failed after retries: {last}") from last


# -----------------------------
# Data structures
# -----------------------------

@dataclass
class Meter:
    count: int = 0
    units: List[str] = None
    priceTypes: List[str] = None
    armSkuNames: List[str] = None

    def __post_init__(self):
        self.units = self.units or []
        self.priceTypes = self.priceTypes or []
        self.armSkuNames = self.armSkuNames or []


@dataclass
class Node:
    count: int = 0
    children: Dict[str, Any] = None
    token_counts: Dict[str, int] = None
    samples: Dict[str, List[str]] = None

    def __post_init__(self):
        self.children = self.children or {}
        self.token_counts = self.token_counts or {}
        self.samples = self.samples or {}


def add_sample(lst: List[str], v: str, limit: int) -> None:
    v = norm(v)
    if not v or v in lst:
        return
    if len(lst) < limit:
        lst.append(v)
    else:
        if random.random() < 0.10:
            lst[random.randrange(0, len(lst))] = v


# -----------------------------
# Checkpoint state
# -----------------------------

def default_state_path(outdir: Path) -> Path:
    return outdir / "state.json"


def write_checkpoint(
    state_path: Path,
    *,
    next_url: str,
    pages: int,
    total: int,
    region: str,
    currency: str,
    primary_only: bool,
    api_version: str,
    top: int,
    encoding: str,
    errors: str,
) -> None:
    payload = {
        "next_url": next_url,
        "pages": pages,
        "total": total,
        "region": region,
        "currency": currency,
        "primary_only": primary_only,
        "api_version": api_version,
        "top": top,
        "written_at_epoch": int(time.time()),
    }
    safe_write_json(state_path, payload, encoding=encoding, errors=errors)


# -----------------------------
# Main
# -----------------------------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--region",
        default=os.getenv("AZURECOST_DEFAULT_REGION", "westeurope"),
        help="armRegionName to filter, e.g. westeurope. Use 'all' for global crawl (no region filter).",
    )
    ap.add_argument("--currency", default=os.getenv("AZURECOST_DEFAULT_CURRENCY", "EUR"))
    ap.add_argument("--api-version", default=DEFAULT_API_VERSION)
    ap.add_argument("--primary-only", action="store_true")
    ap.add_argument("--top", type=int, default=1000)
    ap.add_argument("--max-pages", type=int, default=120)
    ap.add_argument("--max-items", type=int, default=0)

    ap.add_argument("--sample-limit", type=int, default=6)
    ap.add_argument("--token-top", type=int, default=20)
    ap.add_argument("--keep-top-k", type=int, default=60, help="Top product/SKU/meter hints per service for LLM.")

    ap.add_argument("--outdir", default="out_pricing_knowledge")
    ap.add_argument("--encoding", default="utf-8", choices=["utf-8", "utf-8-sig"])
    ap.add_argument("--errors", default="replace", choices=["strict", "replace"])

    ap.add_argument("--raw-sample", action="store_true")
    ap.add_argument("--raw-sample-rate", type=float, default=0.001)

    # CHECKPOINT / RESUME
    ap.add_argument("--checkpoint-every", type=int, default=25, help="Write state.json every N pages (0 disables).")
    ap.add_argument("--resume", action="store_true", help="Resume from outdir/state.json if present.")
    ap.add_argument("--resume-state", default="", help="Path to a state.json to resume from (optional).")
    ap.add_argument("--resume-url", default="", help="Override resume URL (a NextPageLink) and continue from there.")

    # HTTP tuning
    ap.add_argument("--http-retries", type=int, default=10)
    ap.add_argument("--http-backoff", type=float, default=1.6)

    args = ap.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    page_size = clamp_top(args.top)

    # Decide state file
    state_path = Path(args.resume_state) if args.resume_state else default_state_path(outdir)

    # Starting URL
    url = build_first_url(
        api_version=args.api_version,
        currency=args.currency,
        region=args.region,
        top=page_size,
        primary_only=bool(args.primary_only),
    )

    pages = 0
    total = 0

    # Resume logic
    if args.resume or args.resume_state:
        st = safe_read_json(state_path, encoding=args.encoding, errors=args.errors) or {}
        if st.get("next_url"):
            url = st["next_url"]
            pages = int(st.get("pages", 0))
            total = int(st.get("total", 0))
            print(f"[resume] from {state_path} pages={pages} total={total}")
        else:
            print(f"[resume] no next_url in {state_path}; starting fresh")

    if args.resume_url:
        url = args.resume_url.strip()
        print(f"[resume] overriding URL from --resume-url (pages={pages}, total={total})")

    session = requests.Session()
    session.headers.update({"Accept": "application/json"})

    # Full taxonomy (heavy but accurate)
    families: Dict[str, Node] = {}

    # Service-level aggregations (LLM steering)
    svc_family: Dict[str, str] = {}
    svc_count: Counter = Counter()
    svc_tokens: Dict[str, Counter] = defaultdict(Counter)
    svc_products: Dict[str, Counter] = defaultdict(Counter)
    svc_skus: Dict[str, Counter] = defaultdict(Counter)
    svc_meters: Dict[str, Counter] = defaultdict(Counter)
    svc_regions: Dict[str, Counter] = defaultdict(Counter)

    # Optional raw sampling
    raw_fh = None
    if args.raw_sample:
        raw_fh = (outdir / "raw_items_sample.jsonl").open("w", encoding=args.encoding, errors=args.errors)

    try:
        # Crawl loop
        while url and (not args.max_pages or pages < args.max_pages):
            pages += 1

            payload = http_get_json(
                session,
                url,
                retries=int(args.http_retries),
                backoff=float(args.http_backoff),
            )

            items = payload.get("Items") or payload.get("items") or []
            next_link = payload.get("NextPageLink") or payload.get("nextPageLink") or ""

            for it in items:
                total += 1

                fam = norm(it.get("serviceFamily")) or "UNKNOWN_FAMILY"
                svc = norm(it.get("serviceName")) or "UNKNOWN_SERVICE"
                prod = norm(it.get("productName")) or "UNKNOWN_PRODUCT"
                sku = norm(it.get("skuName")) or "UNKNOWN_SKU"
                meter = norm(it.get("meterName")) or "UNKNOWN_METER"

                arm_region = norm(it.get("armRegionName")) or ""

                unit = norm(it.get("unitOfMeasure"))
                price_type = norm(it.get("priceType") or it.get("type"))
                arm_sku = norm(it.get("armSkuName"))

                # --- taxonomy ---
                fam_node = families.setdefault(fam, Node())
                fam_node.count += 1

                svc_node = fam_node.children.setdefault(svc, Node())
                svc_node.count += 1
                for t in tokenize(svc):
                    svc_node.token_counts[t] = svc_node.token_counts.get(t, 0) + 1

                svc_node.samples.setdefault("productName", [])
                svc_node.samples.setdefault("skuName", [])
                svc_node.samples.setdefault("meterName", [])
                add_sample(svc_node.samples["productName"], prod, args.sample_limit)
                add_sample(svc_node.samples["skuName"], sku, args.sample_limit)
                add_sample(svc_node.samples["meterName"], meter, args.sample_limit)

                prod_node = svc_node.children.setdefault(prod, Node())
                prod_node.count += 1

                sku_node = prod_node.children.setdefault(sku, Node())
                sku_node.count += 1

                meters: Dict[str, Meter] = sku_node.children  # type: ignore
                m = meters.setdefault(meter, Meter())
                m.count += 1
                if unit and unit not in m.units:
                    m.units.append(unit)
                if price_type and price_type not in m.priceTypes:
                    m.priceTypes.append(price_type)
                if arm_sku and arm_sku not in m.armSkuNames:
                    m.armSkuNames.append(arm_sku)

                # --- service-level ---
                svc_count[svc] += 1
                svc_family.setdefault(svc, fam)
                svc_products[svc][prod] += 1
                svc_skus[svc][sku] += 1
                svc_meters[svc][meter] += 1
                if arm_region:
                    svc_regions[svc][arm_region] += 1
                for t in tokenize(svc):
                    svc_tokens[svc][t] += 1

                if raw_fh and random.random() < float(args.raw_sample_rate):
                    raw_fh.write(json.dumps(it, ensure_ascii=False) + "\n")

                if args.max_items and total >= args.max_items:
                    next_link = ""
                    break

            # Compute next URL
            url = sanitize_next_link(next_link, page_size)

            # Checkpoint
            if args.checkpoint_every and args.checkpoint_every > 0 and (pages % int(args.checkpoint_every) == 0):
                write_checkpoint(
                    state_path,
                    next_url=url,
                    pages=pages,
                    total=total,
                    region=args.region,
                    currency=args.currency,
                    primary_only=bool(args.primary_only),
                    api_version=args.api_version,
                    top=page_size,
                    encoding=args.encoding,
                    errors=args.errors,
                )
                print(f"[checkpoint] wrote {state_path} (pages={pages}, total={total}, has_next={bool(url)})")

            if not url:
                break

    finally:
        if raw_fh:
            raw_fh.close()

    # Build outputs
    services_universe: Dict[str, Dict[str, Any]] = {}
    for svc in sorted(svc_count.keys(), key=lambda s: s.lower()):
        services_universe[svc] = {
            "serviceFamily": svc_family.get(svc, "UNKNOWN_FAMILY"),
            "items": int(svc_count[svc]),
            "top_tokens": top_k(svc_tokens[svc], int(args.token_top)),
            "top_productNames": top_k(svc_products[svc], int(args.keep_top_k)),
            "top_skuNames": top_k(svc_skus[svc], int(args.keep_top_k)),
            "top_meterNames": top_k(svc_meters[svc], int(args.keep_top_k)),
            "top_armRegions": top_k(svc_regions[svc], 25),
        }

    taxonomy_obj = {k: asdict(v) for k, v in families.items()}

    safe_write_json(outdir / "taxonomy.json", taxonomy_obj, encoding=args.encoding, errors=args.errors)
    safe_write_json(outdir / "services_universe.json", services_universe, encoding=args.encoding, errors=args.errors)

    llm_context = {
        "what_this_is": "Retail Prices API knowledgepack: canonical service universe + SKU/product/meter hints + query rules.",
        "scope": {
            "region_filter": args.region,
            "currency": args.currency,
            "primary_only": bool(args.primary_only),
            "pages_crawled": pages,
            "items_scanned": total,
        },
        "retail_api_rules": {
            "base_url": BASE_URL,
            "api_version": args.api_version,
            "recommended_defaults": {
                "currencyCode": args.currency,
                "meterRegion": "primary" if args.primary_only else "any",
                "armRegionName": None if args.region.lower() == "all" else args.region.lower(),
                "$top": page_size,
            },
            "two_phase_query": {
                "phase_A_anchor": "serviceName eq '<CANONICAL_SERVICE_NAME>'",
                "phase_B_narrow": "contains(productName|skuName|meterName|armSkuName,'<token>')",
            },
            "regional_rule": "If pricing is regional, add armRegionName eq '<region>'. For global scope, omit region filter.",
            "pagination_rule": "Follow NextPageLink; sanitize invalid $top if present.",
        },
        "ranking_rules": [
            "Prefer highest overlap between requested hints and (skuName/armSkuName/productName/meterName).",
            "Prefer unitOfMeasure compatible with quantity model (hour, GB, GB-month, vCore, request...).",
            "Prefer priceType='Consumption' for PAYG baseline unless explicitly asking Reservation/SavingsPlan.",
            "Reject irrelevant meters (backup/LTR/geo/etc.) unless explicitly requested.",
        ],
        "allowed_service_names": sorted(list(services_universe.keys()), key=lambda s: s.lower()),
        "service_metadata": services_universe,
        "required_llm_output_schema": {
            "resources": [
                {
                    "logical_name": "string",
                    "serviceName": "string (MUST be exact from allowed_service_names)",
                    "serviceFamily": "string (optional but recommended)",
                    "regional_or_global": "regional|global|unknown",
                    "hints": {
                        "productName_contains": ["token1"],
                        "skuName_contains": ["token1"],  # e.g. 'P1 v3'
                        "meterName_contains": ["token1"],
                        "armSkuName_contains": ["token1"],
                    },
                    "quantity_model": {"unit": "hour|GB|GB-month|vCore|request|...", "notes": "string"},
                }
            ]
        },
        "prompt_guidance": [
            "Do NOT invent serviceName. Pick from allowed_service_names.",
            "When you pick a serviceName, also pick 1-3 skuName hints from service_metadata[service].top_skuNames.",
            "Use canonical SKU formatting as seen in top_skuNames (e.g. 'P1 v3').",
        ],
    }

    safe_write_json(outdir / "llm_context.json", llm_context, encoding=args.encoding, errors=args.errors)

    # Final checkpoint: mark completion (next_url empty)
    write_checkpoint(
        state_path,
        next_url="",
        pages=pages,
        total=total,
        region=args.region,
        currency=args.currency,
        primary_only=bool(args.primary_only),
        api_version=args.api_version,
        top=page_size,
        encoding=args.encoding,
        errors=args.errors,
    )

    print(f"[OK] Crawled {total} items in {pages} pages")
    print(f"[OK] Wrote: {outdir/'taxonomy.json'}")
    print(f"[OK] Wrote: {outdir/'services_universe.json'}")
    print(f"[OK] Wrote: {outdir/'llm_context.json'}")
    print(f"[OK] Wrote: {state_path} (resume state)")
    if args.raw_sample:
        print(f"[OK] Wrote: {outdir/'raw_items_sample.jsonl'} (sampled)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
