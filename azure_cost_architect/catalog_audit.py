"""Catalog-aware audit tool for existing runs and local catalogs.

Usage:
    python -m azure_cost_architect.catalog_audit --runs-dir runs --catalog-dir catalog --out runs/_catalog_audit.md
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence, Tuple

from .config import CATALOG_DIR, DEFAULT_CURRENCY, DEFAULT_REGION
from .pricing.catalog import _catalog_path
from .pricing.normalize import normalize_service_name


@dataclass
class CatalogEntry:
    path: Path
    category: str | None
    service_name: str | None
    region: str | None
    currency: str | None
    items: list[dict]


def _read_meta(jsonl_path: Path) -> dict:
    meta_path = jsonl_path.with_suffix(jsonl_path.suffix + ".meta")
    if meta_path.exists():
        try:
            return json.loads(meta_path.read_text())
        except Exception:
            return {}
    return {}


def _tokenize(values: Iterable[str]) -> Counter:
    counter: Counter = Counter()
    for value in values:
        for token in str(value).replace("/", " ").replace("-", " ").split():
            token = token.strip().lower()
            if token:
                counter[token] += 1
    return counter


def _load_catalog_entries(catalog_dir: Path) -> list[CatalogEntry]:
    entries: list[CatalogEntry] = []
    for jsonl_file in sorted(catalog_dir.glob("*.jsonl")):
        meta = _read_meta(jsonl_file)
        try:
            with jsonl_file.open("r", encoding="utf-8") as fh:
                items = [json.loads(line) for line in fh if line.strip()]
        except FileNotFoundError:
            items = []

        service_name = meta.get("serviceName")
        region = meta.get("region")
        currency = meta.get("currency")
        category = meta.get("category")

        # Fall back to item fields if meta is missing
        if items:
            first = items[0]
            service_name = service_name or first.get("serviceName")
            region = region or first.get("armRegionName")
            currency = currency or first.get("currencyCode")

        entries.append(
            CatalogEntry(
                path=jsonl_file,
                category=category,
                service_name=service_name,
                region=region,
                currency=currency,
                items=items,
            )
        )
    return entries


def _summarize_category(entries: list[CatalogEntry]) -> list[str]:
    lines: list[str] = []
    for entry in entries:
        service_samples = sorted({item.get("serviceName", "") for item in entry.items})
        product_samples = sorted({item.get("productName", "") for item in entry.items})
        sku_tokens = _tokenize(item.get("skuName", "") for item in entry.items)
        meter_tokens = _tokenize(item.get("meterName", "") for item in entry.items)

        lines.append(f"- Path: `{entry.path}`")
        lines.append(
            f"  - Items: {len(entry.items)} | Region: {entry.region} | Currency: {entry.currency}"
        )
        lines.append(
            f"  - Distinct serviceName: {', '.join(service_samples[:3]) or 'n/a'}"
        )
        lines.append(
            f"  - Sample productName: {', '.join(product_samples[:3]) or 'n/a'}"
        )
        lines.append(
            f"  - Top skuName tokens: {', '.join(token for token, _ in sku_tokens.most_common(10))}"
        )
        lines.append(
            f"  - Top meterName tokens: {', '.join(token for token, _ in meter_tokens.most_common(10))}"
        )
    return lines


def _catalog_for_resource(
    *, category: str, region: str, currency: str, catalog_dir: Path
) -> Tuple[Path, str]:
    service = normalize_service_name(category, None)
    path = Path(
        _catalog_path(str(catalog_dir), service_name=service, region=region, currency=currency)
    )
    reason = (
        f"category='{category}' -> serviceName='{service}' via normalize_service_name; "
        f"region='{region}', currency='{currency}'"
    )
    return path, reason


def _score_candidates(items: list[dict], hints: Sequence[str]) -> list[tuple[int, dict]]:
    hint_tokens = [
        token
        for hint in hints
        for token in str(hint or "").lower().replace("/", " ").replace("-", " ").split()
        if token
    ]
    scored: list[tuple[int, dict]] = []
    for item in items:
        haystack = " ".join(
            str(item.get(key, ""))
            for key in ("productName", "skuName", "meterName", "armSkuName")
        ).lower()
        score = sum(1 for token in hint_tokens if token in haystack)
        scored.append((score, item))
    scored.sort(key=lambda t: t[0], reverse=True)
    return scored


def _render_candidates(scored: list[tuple[int, dict]], limit: int = 10) -> list[str]:
    lines: list[str] = []
    for score, item in scored[:limit]:
        lines.append(
            f"    - score={score} | productName={item.get('productName')} | skuName={item.get('skuName')} | "
            f"meterName={item.get('meterName')} | armSkuName={item.get('armSkuName')} | "
            f"unitOfMeasure={item.get('unitOfMeasure')} | type={item.get('type')} | priceType={item.get('priceType', item.get('type'))} | unitPrice={item.get('unitPrice')}"
        )
    return lines


def _conclusion(match_count: int) -> str:
    if match_count == 0:
        return "Correct meter is not in catalog (catalog incomplete or mapping wrong)."
    if match_count == 1:
        return "Correct meter exists but our selection chose another (single candidate found)."
    return "Ambiguous: multiple meters, need capacity-first / stricter filters."


def build_catalog_audit_report(runs_dir: Path, catalog_dir: Path) -> str:
    entries = _load_catalog_entries(catalog_dir)
    category_index: dict[str, list[CatalogEntry]] = defaultdict(list)
    for entry in entries:
        category_index[entry.category or "unknown"].append(entry)

    lines: list[str] = []
    lines.append("# Catalog Audit Report")
    lines.append("")
    lines.append("## Catalog inventory by category")
    for category in sorted(category_index.keys()):
        lines.append(f"### Category: {category}")
        lines.extend(_summarize_category(category_index[category]))
        lines.append("")

    lines.append("## Run-by-run resource verification")
    for plan_file in sorted(runs_dir.glob("*/plan.json")):
        run_name = plan_file.parent.name
        lines.append(f"### Run: {run_name}")
        try:
            plan = json.loads(plan_file.read_text())
        except Exception as ex:
            lines.append(f"- Failed to read plan: {ex}")
            continue

        for scenario in plan.get("scenarios", []):
            scenario_id = scenario.get("scenario_id", "unknown")
            lines.append(f"- Scenario: {scenario_id}")
            for res in scenario.get("resources", []):
                category = res.get("category", "")
                region = res.get("region") or DEFAULT_REGION
                currency = res.get("currency_code") or DEFAULT_CURRENCY
                arm_sku = res.get("arm_sku_name") or res.get("sku_name") or ""
                reservation_hint = res.get("reservationTerm") or res.get("billing_model", "")
                catalog_path, reason = _catalog_for_resource(
                    category=category, region=region, currency=currency, catalog_dir=catalog_dir
                )
                lines.append(
                    f"  - Resource: id={res.get('id')} | category={category} | region={region} | "
                    f"requested_sku={arm_sku} | billing_model={reservation_hint}"
                )
                lines.append(f"    - Catalog used: `{catalog_path}` (reason: {reason})")

                matched_entry: Optional[CatalogEntry] = next(
                    (e for e in entries if e.path == catalog_path), None
                )
                items = matched_entry.items if matched_entry else []
                scored = _score_candidates(items, hints=[arm_sku, reservation_hint])
                lines.append(f"    - Catalog search results: {len(scored)} candidates")
                lines.extend(_render_candidates(scored))
                lines.append(f"    - Conclusion: {_conclusion(len(scored))}")
            lines.append("")
    return "\n".join(lines).strip() + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit local catalogs against committed runs.")
    parser.add_argument("--runs-dir", default="runs", help="Directory containing run folders with plan.json files.")
    parser.add_argument(
        "--catalog-dir",
        default=CATALOG_DIR,
        help=f"Directory containing local catalog JSONL files (default: {CATALOG_DIR}).",
    )
    parser.add_argument(
        "--out",
        default="runs/_catalog_audit.md",
        help="Output markdown path for the audit report.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    runs_dir = Path(args.runs_dir)
    catalog_dir = Path(args.catalog_dir)
    output_path = Path(args.out)

    report = build_catalog_audit_report(runs_dir, catalog_dir)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")
    print(f"Catalog audit written to {output_path}")


if __name__ == "__main__":
    main()

