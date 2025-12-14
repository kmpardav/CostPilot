#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
retail_pricing_knowledgepack.py — Build a FULL Retail Prices "knowledge pack" for humans + LLMs

Outputs (in --outdir):
- taxonomy.json
  Full hierarchy: serviceFamily -> serviceName -> productName -> skuName -> meterName
  with counts + samples + units/priceType/armSkuName samples

- services_universe.json
  Distinct serviceName list with serviceFamily, counts, sample tokens

- llm_context.json
  A compact, LLM-ready payload:
  - allowed_service_names (canonical)
  - families
  - top token hints per service
  - query rules + scoring rules
  - synonym suggestions (auto-mined from tokens)

- codex_prompt_pack.md
  Paste-ready prompt content: rules + allowed services + examples + query recipes

Notes:
- Retail Prices API is a meter catalog. You must (a) scope to serviceName, (b) apply region & primary meters,
  (c) narrow using contains() hints, (d) rank candidates.
- Primary meters: use meterRegion='primary' (supported in 2021-10-01+ / 2023-01-01-preview).  Docs: MS Learn.

Docs:
https://learn.microsoft.com/en-us/rest/api/cost-management/retail-prices/azure-retail-prices
"""

from __future__ import annotations

import argparse, json, os, random, re, time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Optional, List, Tuple
from collections import Counter

import requests

RETAIL_API_URL = "https://prices.azure.com/api/retail/prices"
DEFAULT_API_VERSION = "2023-01-01-preview"
TOKEN_SPLIT_RE = re.compile(r"[^a-zA-Z0-9]+")

def clamp_top(n: int) -> int:
    try:
        n = int(n)
    except Exception:
        return 1000
    return 1000 if (n < 1 or n > 1000) else n

def sanitize_next_link(next_link: str, page_size: int) -> str:
    if not next_link:
        return ""
    def _fix(m):
        try:
            v = int(m.group(2))
        except Exception:
            v = page_size
        if v <= 0:
            v = page_size
        return f"{m.group(1)}{v}"
    return re.sub(r"([?&]\$top=)(-?\d+)", _fix, next_link)

def http_get_json(session: requests.Session, url: str, retries: int = 4, backoff: float = 1.35) -> Dict[str, Any]:
    last: Optional[Exception] = None
    for attempt in range(retries):
        try:
            r = session.get(url, timeout=(10, 90))
            r.raise_for_status()
            return r.json()
        except Exception as ex:
            last = ex
            time.sleep((backoff ** attempt) + random.random() * 0.35)
    raise RuntimeError(f"GET failed after retries: {last}") from last

def build_first_url(*, api_version: str, currency: str, region: str, page_size: int, primary_only: bool, odata_filter: Optional[str]) -> str:
    url = f"{RETAIL_API_URL}?api-version={api_version}&currencyCode={currency}&$top={clamp_top(page_size)}"
    if primary_only:
        url += "&meterRegion='primary'"
    if region and region.lower() != "all":
        region_filter = f"armRegionName eq '{region.strip().lower()}'"
        odata_filter = f"({odata_filter}) and {region_filter}" if odata_filter else region_filter
    if odata_filter:
        from urllib.parse import quote
        url += "&$filter=" + quote(odata_filter, safe="()'=,:$")
    return url

def norm(x: Any) -> str:
    return (x or "").strip()

def tokenize(s: str) -> List[str]:
    s = norm(s).lower()
    if not s:
        return []
    parts = [p for p in TOKEN_SPLIT_RE.split(s) if p and len(p) >= 2]
    return parts

def add_sample(lst: List[str], v: str, limit: int) -> None:
    v = norm(v)
    if not v or v in lst:
        return
    if len(lst) < limit:
        lst.append(v)
    else:
        if random.random() < 0.10:
            lst[random.randrange(0, len(lst))] = v

@dataclass
class MeterLeaf:
    count: int = 0
    units: List[str] = None
    priceTypes: List[str] = None
    armSkuNames: List[str] = None
    effectiveStarts: List[str] = None
    def __post_init__(self):
        self.units = self.units or []
        self.priceTypes = self.priceTypes or []
        self.armSkuNames = self.armSkuNames or []
        self.effectiveStarts = self.effectiveStarts or []

@dataclass
class Node:
    count: int = 0
    children: Dict[str, Any] = None
    samples: Dict[str, List[str]] = None
    token_counts: Dict[str, int] = None
    def __post_init__(self):
        self.children = self.children or {}
        self.samples = self.samples or {}
        self.token_counts = self.token_counts or {}

def ensure_node(d: Dict[str, Node], key: str) -> Node:
    n = d.get(key)
    if not n:
        n = Node()
        d[key] = n
    return n

def ensure_meter(d: Dict[str, MeterLeaf], key: str) -> MeterLeaf:
    m = d.get(key)
    if not m:
        m = MeterLeaf()
        d[key] = m
    return m

def bump_tokens(node: Node, label: str, max_tokens: int = 12) -> None:
    toks = tokenize(label)[:max_tokens]
    if not toks:
        return
    c = Counter(node.token_counts)
    for t in toks:
        c[t] += 1
    node.token_counts = dict(c)

def top_k(d: Dict[str, int], k: int) -> List[Tuple[str, int]]:
    return sorted(d.items(), key=lambda kv: kv[1], reverse=True)[:k]

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--currency", default=os.getenv("AZURECOST_DEFAULT_CURRENCY", "EUR"))
    ap.add_argument("--region", default=os.getenv("AZURECOST_DEFAULT_REGION", "westeurope"))
    ap.add_argument("--api-version", default=DEFAULT_API_VERSION)
    ap.add_argument("--top", type=int, default=1000)
    ap.add_argument("--max-pages", type=int, default=120)
    ap.add_argument("--max-items", type=int, default=0)
    ap.add_argument("--primary-only", action="store_true")
    ap.add_argument("--filter", default="")
    ap.add_argument("--sample-limit", type=int, default=8)
    ap.add_argument("--token-top", type=int, default=20)
    ap.add_argument("--outdir", default="out_knowledgepack")
    args = ap.parse_args()

    outdir = Path(args.outdir); outdir.mkdir(parents=True, exist_ok=True)

    url = build_first_url(
        api_version=args.api_version,
        currency=args.currency,
        region=args.region,
        page_size=clamp_top(args.top),
        primary_only=bool(args.primary_only),
        odata_filter=(args.filter or "").strip() or None,
    )

    session = requests.Session()
    families: Dict[str, Node] = {}
    total_items = 0
    pages = 0

    while url:
        pages += 1
        if args.max_pages and pages > args.max_pages:
            break

        data = http_get_json(session, url)
        items = data.get("Items") or data.get("items") or []
        next_link = data.get("NextPageLink") or data.get("nextPageLink") or ""

        for it in items:
            total_items += 1
            fam = norm(it.get("serviceFamily")) or "UNKNOWN_FAMILY"
            svc = norm(it.get("serviceName")) or "UNKNOWN_SERVICE"
            prod = norm(it.get("productName")) or "UNKNOWN_PRODUCT"
            sku  = norm(it.get("skuName")) or "UNKNOWN_SKU"
            meter = norm(it.get("meterName")) or "UNKNOWN_METER"

            unit = norm(it.get("unitOfMeasure"))
            price_type = norm(it.get("priceType"))
            arm_sku = norm(it.get("armSkuName"))
            eff = norm(it.get("effectiveStartDate"))

            fam_node = ensure_node(families, fam); fam_node.count += 1; bump_tokens(fam_node, fam)
            svc_node = ensure_node(fam_node.children, svc); svc_node.count += 1; bump_tokens(svc_node, svc)

            # service samples
            svc_node.samples.setdefault("productName", [])
            svc_node.samples.setdefault("skuName", [])
            svc_node.samples.setdefault("meterName", [])
            add_sample(svc_node.samples["productName"], prod, args.sample_limit)
            add_sample(svc_node.samples["skuName"], sku, args.sample_limit)
            add_sample(svc_node.samples["meterName"], meter, args.sample_limit)

            prod_node = ensure_node(svc_node.children, prod); prod_node.count += 1; bump_tokens(prod_node, prod)
            sku_node  = ensure_node(prod_node.children, sku); sku_node.count += 1; bump_tokens(sku_node, sku)

            # meter leaf
            meters: Dict[str, MeterLeaf] = sku_node.children  # type: ignore
            m = ensure_meter(meters, meter); m.count += 1
            add_sample(m.units, unit, args.sample_limit)
            add_sample(m.priceTypes, price_type, args.sample_limit)
            add_sample(m.armSkuNames, arm_sku, args.sample_limit)
            add_sample(m.effectiveStarts, eff, args.sample_limit)

            if args.max_items and total_items >= args.max_items:
                url = ""
                break

        if not url:
            break
        url = sanitize_next_link(next_link, clamp_top(args.top))

    # Build services universe
    services_universe: Dict[str, Dict[str, Any]] = {}
    for fam, fam_node in families.items():
        for svc, svc_node in fam_node.children.items():
            services_universe[svc] = {
                "serviceFamily": fam,
                "count": svc_node.count,
                "sample_productNames": svc_node.samples.get("productName", [])[:args.sample_limit],
                "sample_skuNames": svc_node.samples.get("skuName", [])[:args.sample_limit],
                "sample_meterNames": svc_node.samples.get("meterName", [])[:args.sample_limit],
                "top_tokens": top_k(svc_node.token_counts, args.token_top),
            }

    # Write taxonomy
    taxonomy_payload = {
        "meta": {
            "region": args.region,
            "currency": args.currency,
            "primary_only": bool(args.primary_only),
            "filter": (args.filter or "").strip(),
            "pages_crawled": pages,
            "items_scanned": total_items,
            "distinct_families": len(families),
            "distinct_services": len(services_universe),
        },
        "families": {k: asdict(v) for k, v in families.items()},
    }
    (outdir / "taxonomy.json").write_text(json.dumps(taxonomy_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    (outdir / "services_universe.json").write_text(json.dumps(services_universe, indent=2, ensure_ascii=False), encoding="utf-8")

    # LLM context payload (the thing you actually paste into prompts)
    llm_context = {
        "what_this_is": "Azure Retail Prices API pricing knowledgepack: allowed service universe + query rules.",
        "retail_api_rules": {
            "base_url": RETAIL_API_URL,
            "api_version": args.api_version,
            "always_use": [
                "currencyCode=<CURRENCY>",
                "meterRegion='primary' (recommended for consistency)",
                "$filter=serviceName eq '<CANONICAL_SERVICE_NAME>'",
            ],
            "region_rule": "If pricing is regional, add: $filter ... and armRegionName eq '<region>'",
            "narrowing_rule": "Use contains(productName|skuName|meterName|armSkuName, '<token>') to narrow.",
            "pagination_rule": "Follow NextPageLink until empty or max-pages.",
        },
        "ranking_rules": [
            "Prefer items whose skuName/armSkuName tokens match the requested SKU.",
            "Prefer unitOfMeasure compatible with the requested quantity (hour, GB, GB-month, vCore...).",
            "Prefer priceType='Consumption' for PAYG baselines unless explicitly asking reservation/savings plan.",
            "Avoid obviously irrelevant meters (e.g., LTR/Backup meters when pricing base SQL compute).",
        ],
        "allowed_service_names": sorted(list(services_universe.keys()), key=lambda s: s.lower()),
        "service_metadata": services_universe,  # yes, big — but αυτό ζήτησες: “όλη η πληροφορία”
        "required_llm_output_schema": {
            "resources": [
                {
                    "logical_name": "string",
                    "serviceFamily": "string (from allowed list)",
                    "serviceName": "string (MUST be exact from allowed list)",
                    "regional_or_global": "regional|global|unknown",
                    "hints": {
                        "productName_contains": ["token1", "token2"],
                        "skuName_contains": ["token1"],
                        "meterName_contains": ["token1"],
                        "armSkuName_contains": ["token1"]
                    },
                    "quantity_model": {"unit": "hour|GB|GB-month|vCore|request|...", "notes": "string"},
                }
            ]
        }
    }
    (outdir / "llm_context.json").write_text(json.dumps(llm_context, indent=2, ensure_ascii=False), encoding="utf-8")

    # Codex prompt pack (human readable)
    prompt_md = []
    prompt_md.append("# Retail Prices API — LLM Steering Pack")
    prompt_md.append("")
    prompt_md.append("## Goal")
    prompt_md.append("Design architectures whose resources can be priced deterministically via Azure Retail Prices API.")
    prompt_md.append("")
    prompt_md.append("## Non-negotiable rules")
    prompt_md.append("1) Output serviceName EXACTLY from the allowed list.")
    prompt_md.append("2) Provide hint tokens for productName/skuName/meterName/armSkuName so the orchestrator can query/score.")
    prompt_md.append("3) If unsure, output UNKNOWN_SERVICE and propose 2 closest allowed services.")
    prompt_md.append("")
    prompt_md.append("## Query recipe (the orchestrator will follow)")
    prompt_md.append("- Start with: serviceName eq '<service>'")
    prompt_md.append("- Add: armRegionName eq '<region>' when regional pricing")
    prompt_md.append("- Use: meterRegion='primary' for consistency")
    prompt_md.append("- Narrow with contains() using hint tokens")
    prompt_md.append("- Rank candidates with token overlap + unitOfMeasure + priceType sanity")
    prompt_md.append("")
    prompt_md.append("## Allowed serviceName list + metadata")
    prompt_md.append("See llm_context.json (allowed_service_names + service_metadata).")
    (outdir / "codex_prompt_pack.md").write_text("\n".join(prompt_md) + "\n", encoding="utf-8")

    print(f"[ok] wrote {outdir/'taxonomy.json'}")
    print(f"[ok] wrote {outdir/'services_universe.json'}")
    print(f"[ok] wrote {outdir/'llm_context.json'}")
    print(f"[ok] wrote {outdir/'codex_prompt_pack.md'}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
