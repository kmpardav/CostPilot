#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Build sku_alias_index.json from taxonomy.json (ground truth), once.

Output format MUST match azure_cost_architect/utils/sku_matcher.py expectations:
{ category: { normalized_alias: [aliases...] } }

Important:
- The dict KEY is the *normalized alias* (what match_sku() checks).
- aliases[0] MUST be the canonical ARM SKU to emit.
- We remove ambiguous alias keys (aliases mapping to >1 canonical) per category.
- Categories are auto-discovered from pricing/catalog_sources.py when --categories is omitted.

Default paths (repo root):
  taxonomy.json
  out_kp/sku_alias_index.json
  out_kp/sku_alias_collisions.json  (optional report)

Run:
  python -m azure_cost_architect.build_sku_alias_index
  python -m azure_cost_architect.build_sku_alias_index --categories db.sql,cache.redis
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from .pricing.catalog_sources import CATEGORY_CATALOG_SOURCES, get_catalog_sources
from .utils.knowledgepack import canonicalize_service_name
from .utils.sku_matcher import normalize_sku


# ----------------------------
# Regex parsers for derived aliases
# ----------------------------

# SQL canonical examples:
#   SQLDB_GP_Compute_Gen5_2
#   SQLDB_BC_Compute_Gen4_1
#   SQLDB_GP_Compute_Gen5_ZR
_SQLDB_RE = re.compile(
    r"^SQLDB_(?P<tier>[A-Z]+)_Compute_(?P<gen>Gen\d+)(?:_(?P<size>\d+))?(?P<zr>_ZR)?$"
)

# Redis classic examples:
#   Azure_Redis_Cache_Premium_P1_Cache
#   Azure_Redis_Cache_Standard_C1_Cache
#   Azure_Redis_Cache_Basic_C0_Cache
_REDIS_CLASSIC_RE = re.compile(
    r"^Azure_Redis_Cache_(?P<tier>Basic|Standard|Premium)_(?P<code>[CP])(?P<num>\d+)_Cache$"
)

# Redis managed examples:
#   Azure_Managed_Redis_Balanced_B1
#   Azure_Managed_Redis_Compute_Optimized_X1
_REDIS_MANAGED_RE = re.compile(
    r"^Azure_Managed_Redis_(?P<flavor>Balanced|Compute_Optimized|Memory_Optimized|Flash_Optimized)_(?P<size>[A-Z]\d+)$"
)

# VM examples:
#   Standard_D2s_v3  -> D2s_v3
_VM_STANDARD_RE = re.compile(r"^Standard_(?P<short>.+)$")

# Benign SKU dupes in taxonomy sometimes differ only by Tb vs TB (case of 'b')
_BENIGN_TB_RE = re.compile(r"(?i)(\d+)\s*tb\b")


@dataclass
class CategoryCollisionReport:
    category: str
    canonical_count: int
    alias_key_count: int
    collisions: Dict[str, List[str]]  # normalized_alias -> list of canonicals
    benign_resolved: Dict[str, List[str]]  # normalized_alias -> list of canonicals (auto-resolved)
    removed_alias_keys: int


def repo_root() -> Path:
    # this file lives in <repo>/azure_cost_architect/build_sku_alias_index.py
    return Path(__file__).resolve().parents[1]


def load_taxonomy(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def autodiscover_categories() -> List[str]:
    """
    Auto-discover all category prefixes we support, from the single source of truth:
    CATEGORY_CATALOG_SOURCES.
    """
    return sorted({(k or "").lower().strip() for k in CATEGORY_CATALOG_SOURCES.keys() if (k or "").strip()})


def _tb_equiv_key(s: str) -> str:
    """
    Build a comparison key for "benign collisions" where taxonomy has duplicates like:
      '..._100 TB' vs '..._100 Tb' vs '..._100tb'
    We DON'T mutate the real SKU we emit; we only use this for detecting duplicates.
    """
    raw = (s or "").strip()
    if not raw:
        return ""
    # normalize digit+tb patterns to digit+TB (for comparison only)
    raw = _BENIGN_TB_RE.sub(lambda m: f"{m.group(1)}TB", raw)
    return raw


def _prefer_tb_canonical(canonicals: Iterable[str]) -> str:
    """
    Deterministic winner selection for benign TB/Tb collisions.
    Prefer the variant that already uses 'TB' (uppercase B) in the "digit+TB" pattern.
    """
    cands = [c for c in canonicals if (c or "").strip()]
    if not cands:
        return ""

    def _score(s: str) -> Tuple[int, int, str]:
        # best: explicit uppercase TB after digits, e.g. "100 TB" or "100TB"
        if re.search(r"\d+\s*TB\b|\d+TB\b", s):
            return (0, len(s), s)
        # next: any tb (case-insensitive) after digits
        if re.search(r"(?i)\d+\s*tb\b|\d+tb\b", s):
            return (1, len(s), s)
        return (2, len(s), s)

    return sorted(cands, key=_score)[0]


def _build_taxonomy_service_index(tax: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Build an index:
      canonical_service_name -> [service_node, ...]

    This gives us the "union" behavior:
    - CATEGORY_CATALOG_SOURCES chooses which services we care about per category
    - taxonomy may contain the same service under different names (e.g. "Azure Cache for Redis")
      and we still want to include ALL those nodes when building SKU aliases.
    """
    idx: Dict[str, List[Dict[str, Any]]] = {}
    for _, family_node in (tax or {}).items():
        if not isinstance(family_node, dict):
            continue
        children = family_node.get("children")
        if not isinstance(children, dict):
            continue
        for svc_name, svc_node in children.items():
            if not isinstance(svc_node, dict):
                continue
            raw = (svc_name or "").strip()
            if not raw:
                continue
            canonical = (canonicalize_service_name(raw) or {}).get("canonical") or raw
            idx.setdefault(canonical, []).append(svc_node)
    return idx


def find_service_node(tax: Dict[str, Any], service_name: str) -> Optional[Dict[str, Any]]:
    """
    taxonomy.json structure:
      root[Family]['children'][ServiceName] -> node
    """
    if not service_name:
        return None

    for _, family_node in tax.items():
        if not isinstance(family_node, dict):
            continue
        children = family_node.get("children")
        if isinstance(children, dict) and service_name in children:
            node = children.get(service_name)
            if isinstance(node, dict):
                return node
    return None


def iter_arm_sku_names(service_node: Dict[str, Any]) -> Iterable[str]:
    """
    Traverse service subtree and yield armSkuNames found at leaf meter nodes.
    Leaf meter nodes contain key: "armSkuNames": [ ... ].
    """
    stack = [service_node]
    while stack:
        node = stack.pop()
        if not isinstance(node, dict):
            continue

        arm_list = node.get("armSkuNames")
        if isinstance(arm_list, list):
            for arm in arm_list:
                if isinstance(arm, str) and arm.strip():
                    yield arm.strip()

        children = node.get("children")
        if isinstance(children, dict):
            for child in children.values():
                if isinstance(child, dict):
                    stack.append(child)


def derive_aliases(category: str, canonical_arm: str) -> Set[str]:
    """
    Given a canonical armSkuName from taxonomy, derive LLM-friendly aliases.
    These aliases become *keys* in the alias index (after normalization).
    """
    aliases: Set[str] = set()
    cat = (category or "").lower()
    arm = (canonical_arm or "").strip()

    if not arm:
        return aliases

    # Always include canonical itself (so exact/canonical strings can match)
    aliases.add(arm)

    if cat == "db.sql":
        m = _SQLDB_RE.match(arm)
        if m:
            tier = m.group("tier") or ""
            gen = m.group("gen") or ""
            size = m.group("size") or ""
            zr = m.group("zr") or ""

            # GP_Gen5_2, BC_Gen4_1, GP_Gen5_ZR
            if tier and gen and size:
                aliases.add(f"{tier}_{gen}_{size}{zr}")
                aliases.add(f"{tier}{gen}{size}{zr}")          # GPGen52
                aliases.add(f"{tier}-{gen}-{size}{zr}")        # GP-Gen5-2
            elif tier and gen:
                aliases.add(f"{tier}_{gen}{zr}")
                aliases.add(f"{tier}{gen}{zr}")

    elif cat == "cache.redis":
        m = _REDIS_CLASSIC_RE.match(arm)
        if m:
            tier = m.group("tier")
            code = m.group("code")
            num = m.group("num")
            short = f"{code}{num}"  # P1 / C1
            aliases.add(short)
            aliases.add(f"{tier}_{short}")          # Premium_P1
            aliases.add(f"{tier}{short}")           # PremiumP1
            aliases.add(f"{tier} {short}")          # Premium P1

        m2 = _REDIS_MANAGED_RE.match(arm)
        if m2:
            flavor = m2.group("flavor") or ""
            size = m2.group("size") or ""
            aliases.add(size)                        # B1 / X1
            aliases.add(f"{flavor}_{size}")          # Balanced_B1
            aliases.add(f"{flavor}{size}")           # BalancedB1
            aliases.add(f"{flavor} {size}")          # Balanced B1

    elif cat.startswith("compute.vm"):
        m = _VM_STANDARD_RE.match(arm)
        if m:
            aliases.add(m.group("short"))

    return aliases


def build_alias_index(
    taxonomy: Dict[str, Any],
    categories: List[str],
) -> Tuple[Dict[str, Dict[str, List[str]]], Dict[str, CategoryCollisionReport]]:
    """
    Build alias index in the shape expected by sku_matcher:

      index[category][normalized_alias_key] = [canonical_arm, <extra aliases...>]

    Collision handling:
    - If a normalized alias maps to >1 canonical within the SAME category, we remove that alias key.
    - We emit a collision report per category.
    """
    index: Dict[str, Dict[str, List[str]]] = {}
    reports: Dict[str, CategoryCollisionReport] = {}
    tax_service_index = _build_taxonomy_service_index(taxonomy)

    for category in categories:
        cat = (category or "").lower().strip()
        if not cat:
            continue

        sources = get_catalog_sources(cat)
        if not sources:
            continue

        # Build a UNION of service nodes in taxonomy that belong to the same canonical serviceName(s)
        # that the category maps to (CATEGORY_CATALOG_SOURCES + knowledgepack canonicalization).
        service_nodes: List[Dict[str, Any]] = []
        seen_node_ids: Set[int] = set()
        for s in sources:
            raw = (s.service_name or "").strip()
            if not raw:
                continue
            # 1) exact lookup (if taxonomy has the exact key)
            exact = find_service_node(taxonomy, raw)
            if isinstance(exact, dict) and id(exact) not in seen_node_ids:
                seen_node_ids.add(id(exact))
                service_nodes.append(exact)
            # 2) canonical union lookup (captures synonyms / naming variants in taxonomy)
            canonical = (canonicalize_service_name(raw) or {}).get("canonical") or raw
            for node in tax_service_index.get(canonical, []):
                if id(node) not in seen_node_ids:
                    seen_node_ids.add(id(node))
                    service_nodes.append(node)

        # aggregate canonicals from all service names for that category
        canonicals: Set[str] = set()
        for node in service_nodes:
            canonicals.update(iter_arm_sku_names(node))

        canonicals = {c for c in canonicals if c}
        if not canonicals:
            continue

        # alias_norm -> {canonical1, canonical2, ...}
        alias_norm_to_canonicals: Dict[str, Set[str]] = {}
        # canonical -> alias strings (for building alias lists)
        canonical_to_aliases: Dict[str, Set[str]] = {}

        for canonical in sorted(canonicals):
            aliases = derive_aliases(cat, canonical)
            if not aliases:
                continue
            canonical_to_aliases[canonical] = set(aliases)

            for a in aliases:
                an = normalize_sku(a)
                if not an:
                    continue
                alias_norm_to_canonicals.setdefault(an, set()).add(canonical)

        # Step 1: detect collisions (alias_norm with >1 canonical)
        raw_collisions: Dict[str, Set[str]] = {
            an: set(owners)
            for an, owners in alias_norm_to_canonicals.items()
            if len(owners) > 1
        }

        # Step 2: resolve "benign" collisions (TB vs Tb) by choosing a preferred canonical
        # and keeping the other canonical(s) as extra aliases (so user inputs still match).
        benign_resolved: Dict[str, List[str]] = {}
        for an, owners in list(raw_collisions.items()):
            owners_list = sorted([o for o in owners if o])
            if not owners_list:
                continue
            equiv = {_tb_equiv_key(o) for o in owners_list}
            if len(equiv) != 1:
                continue  # hard collision, keep as-is

            chosen = _prefer_tb_canonical(owners_list)
            if not chosen:
                continue

            # collapse this alias_norm to a single canonical
            alias_norm_to_canonicals[an] = {chosen}

            # merge the "losing" canonicals into chosen's alias set (so they still match)
            merged: Set[str] = set()
            for o in owners_list:
                merged.update(canonical_to_aliases.get(o, set()) or {o})
                merged.add(o)
            canonical_to_aliases.setdefault(chosen, set()).update(merged)

            benign_resolved[an] = owners_list

        # Step 3: recompute HARD collisions after benign resolution
        collisions: Dict[str, List[str]] = {
            an: sorted(list(owners))
            for an, owners in alias_norm_to_canonicals.items()
            if len(owners) > 1
        }

        # build category map: normalized_alias_key -> alias_list
        # (only for aliases that map to exactly 1 canonical)
        cat_map: Dict[str, List[str]] = {}
        removed_alias_keys = 0

        for an, owners in alias_norm_to_canonicals.items():
            if len(owners) != 1:
                removed_alias_keys += 1
                continue

            canonical = next(iter(owners))

            # alias list: [canonical, ...other aliases for that canonical]
            alias_list = [canonical]
            extra = sorted(canonical_to_aliases.get(canonical, set()) - {canonical})
            alias_list.extend(extra)

            # deterministic dedup
            seen = set()
            final_list: List[str] = []
            for x in alias_list:
                if x not in seen:
                    seen.add(x)
                    final_list.append(x)

            cat_map[an] = final_list

        index[cat] = cat_map
        reports[cat] = CategoryCollisionReport(
            category=cat,
            canonical_count=len(canonicals),
            alias_key_count=len(cat_map),
            collisions=collisions,
            benign_resolved=benign_resolved,
            removed_alias_keys=removed_alias_keys,
        )

    return index, reports


def parse_categories_arg(arg: str) -> List[str]:
    if arg.strip():
        return [c.strip().lower() for c in arg.split(",") if c.strip()]
    # auto-discover all known category prefixes from catalog_sources
    return autodiscover_categories()


def _top_collisions(report: CategoryCollisionReport, limit: int = 15) -> List[Tuple[str, int, List[str]]]:
    items = [(an, len(owners), owners) for an, owners in (report.collisions or {}).items()]
    items.sort(key=lambda x: (-x[1], x[0]))
    return items[:limit]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--taxonomy", default="", help="Path to taxonomy.json (default: <repo_root>/taxonomy.json)")
    ap.add_argument("--out", default="", help="Output path (default: <repo_root>/out_kp/sku_alias_index.json)")
    ap.add_argument(
        "--collision-out",
        default="",
        help="Optional collision report JSON path (default: <repo_root>/out_kp/sku_alias_collisions.json)",
    )
    ap.add_argument("--categories", default="", help="Comma-separated categories to include (optional)")
    ap.add_argument("--print-collisions", action="store_true", help="Print top collisions per category to stdout")
    args = ap.parse_args()

    root = repo_root()
    tax_path = Path(args.taxonomy) if args.taxonomy else (root / "taxonomy.json")
    out_path = Path(args.out) if args.out else (root / "out_kp" / "sku_alias_index.json")
    collision_out = (
        Path(args.collision_out)
        if args.collision_out
        else (root / "out_kp" / "sku_alias_collisions.json")
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    collision_out.parent.mkdir(parents=True, exist_ok=True)

    taxonomy = load_taxonomy(tax_path)
    categories = parse_categories_arg(args.categories)

    index, reports = build_alias_index(taxonomy, categories)

    out_path.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")

    # Build collision report payload (always write; it's small and useful)
    report_payload = {}
    for cat, rep in reports.items():
        report_payload[cat] = {
            "canonical_count": rep.canonical_count,
            "alias_key_count": rep.alias_key_count,
            "collision_key_count": len(rep.collisions),
            "benign_resolved_key_count": len(rep.benign_resolved or {}),
            "removed_alias_keys": rep.removed_alias_keys,
            "benign_resolved_samples": [
                {"normalized_alias": an, "canonicals": owners}
                for an, owners in sorted((rep.benign_resolved or {}).items())[:15]
            ],
            "top_collisions": [
                {"normalized_alias": an, "canonical_count": cnt, "canonicals": owners}
                for an, cnt, owners in _top_collisions(rep, limit=15)
            ],
        }
    collision_out.write_text(json.dumps(report_payload, indent=2, ensure_ascii=False), encoding="utf-8")

    # stdout summary
    cat_summ = {c: len(index.get(c, {})) for c in categories}
    total_keys = sum(cat_summ.values())
    total_collision_keys = sum(len(r.collisions) for r in reports.values())
    total_benign = sum(len(r.benign_resolved or {}) for r in reports.values())
    print(f"OK: wrote {out_path}")
    print(f"Categories: {cat_summ} | total_alias_keys={total_keys}")
    print(f"Collision keys removed (hard): {total_collision_keys} (details in {collision_out})")
    print(f"Benign collisions auto-resolved (TB/Tb): {total_benign} (details in {collision_out})")

    if args.print_collisions:
        for cat in sorted(reports.keys()):
            rep = reports[cat]
            top = _top_collisions(rep, limit=10)
            if not top:
                continue
            print(f"\n[{cat}] top collisions:")
            for an, cnt, owners in top:
                print(f"  - {an}: {cnt} canonicals (e.g. {owners[:3]})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
