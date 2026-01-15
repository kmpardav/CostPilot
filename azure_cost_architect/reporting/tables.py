from __future__ import annotations

from typing import Any, Dict, List, Tuple


def _md_escape(v: Any) -> str:
    s = "" if v is None else str(v)
    # Escape pipes so Markdown tables don't break
    return s.replace("|", "\\|").replace("\n", " ").strip()


def _money(v: Any) -> str:
    try:
        f = float(v)
    except Exception:
        return ""
    return f"{f:,.2f}"


def _num(v: Any) -> str:
    try:
        f = float(v)
    except Exception:
        return ""
    # Keep compact for huge numbers
    if abs(f) >= 1_000_000:
        return f"{f:,.0f}"
    if abs(f) >= 1_000:
        return f"{f:,.2f}"
    return f"{f:.4g}"


def _category_bucket(category: str) -> str:
    c = (category or "").lower()
    if c.startswith("compute"):
        return "compute"
    if c.startswith("db"):
        return "db"
    if c.startswith("storage"):
        return "storage"
    if c.startswith("network"):
        return "network"
    if c.startswith("analytics") or c.startswith("data"):
        return "analytics"
    if c.startswith("security"):
        return "security"
    if c.startswith("monitor") or c.startswith("ops"):
        return "monitoring"
    if "backup" in c or "dr" in c:
        return "backup/dr"
    return "other"


def _scenario_totals(scenario: Dict[str, Any]) -> Tuple[float, float]:
    m = 0.0
    y = 0.0
    for r in scenario.get("resources", []) or []:
        try:
            m += float(r.get("monthly_cost") or 0.0)
            y += float(r.get("yearly_cost") or 0.0)
        except Exception:
            continue
    return (m, y)


def render_pricing_tables(enriched_plan: Dict[str, Any]) -> str:
    """Render deterministic pricing tables for ALL scenarios.

    This is intentionally code-driven to avoid LLM non-compliance and token limits.
    It appends resource-level and category-level rollups, plus deltas vs baseline.
    """
    scenarios: List[Dict[str, Any]] = list(enriched_plan.get("scenarios", []) or [])
    if not scenarios:
        return ""

    # Pick baseline scenario deterministically
    baseline = None
    for s in scenarios:
        if (s.get("id") or "").lower() in {"baseline", "recommended"}:
            baseline = s
            break
    if baseline is None:
        baseline = scenarios[0]

    base_m, base_y = _scenario_totals(baseline)

    out: List[str] = []
    out.append("\n\n---\n")
    out.append("## Deterministic pricing tables (generated)\n")
    out.append(
        "These tables are generated directly from `debug_enriched.json`/`final_plan.json` to ensure all scenarios are fully covered.\n"
    )

    # Scenario tables
    for s in scenarios:
        sid = s.get("id") or "scenario"
        label = s.get("label") or sid
        out.append(f"\n### Scenario: { _md_escape(label) } (`{_md_escape(sid)}`)\n")

        # Resource-level table
        out.append(
            "| Scenario | Resource ID | Category | Service | SKU (requested / resolved) | Region | Billing | Unit Price | Unit | Units | Monthly Cost | Yearly Cost | Notes |\n"
        )
        out.append(
            "|---|---|---|---|---|---|---|---:|---|---:|---:|---:|---|\n"
        )
        for r in (s.get("resources", []) or []):
            if r.get("_skip_pricing"):
                continue
            scenario_id = sid
            rid = r.get("id")
            cat = r.get("category")
            svc = r.get("service_name") or r.get("serviceName") or ""
            req = r.get("arm_sku_name") or ""
            res = r.get("sku_name") or r.get("skuName") or ""
            region = r.get("region") or r.get("armRegionName") or ""
            billing = r.get("billing_model") or r.get("billingModel") or ""
            unit_price = _money(r.get("unit_price"))
            unit = r.get("unit_of_measure") or ""
            units = _num(r.get("units"))
            mc = _money(r.get("monthly_cost"))
            yc = _money(r.get("yearly_cost"))
            notes = r.get("pricing_status") or r.get("error") or ""
            out.append(
                "| "
                + " | ".join(
                    [
                        _md_escape(scenario_id),
                        _md_escape(rid),
                        _md_escape(cat),
                        _md_escape(svc),
                        _md_escape(f"{req} / {res}"),
                        _md_escape(region),
                        _md_escape(billing),
                        unit_price,
                        _md_escape(unit),
                        units,
                        mc,
                        yc,
                        _md_escape(notes),
                    ]
                )
                + " |\n"
            )

        # Category rollup + estimate ratio
        buckets: Dict[str, Dict[str, float]] = {}
        for r in (s.get("resources", []) or []):
            if r.get("_skip_pricing"):
                continue
            b = _category_bucket(r.get("category") or "")
            buckets.setdefault(b, {"monthly": 0.0, "estimated": 0.0})
            try:
                m = float(r.get("monthly_cost") or 0.0)
            except Exception:
                m = 0.0
            buckets[b]["monthly"] += m
            if (r.get("pricing_status") or "").lower() in {"estimated", "missing"}:
                buckets[b]["estimated"] += m

        out.append("\n**Category rollup**\n\n")
        out.append("| Category | Monthly Total | Est. Monthly | Est. Ratio |\n")
        out.append("|---|---:|---:|---:|\n")
        for b in sorted(buckets.keys()):
            m = buckets[b]["monthly"]
            e = buckets[b]["estimated"]
            ratio = (e / m) if m else 0.0
            out.append(
                f"| { _md_escape(b) } | {m:,.2f} | {e:,.2f} | {ratio:.1%} |\n"
            )

        # Scenario totals & delta vs baseline
        m, y = _scenario_totals(s)
        out.append("\n**Scenario totals & delta vs baseline**\n\n")
        out.append("| Scenario | Monthly | Yearly | Δ Monthly | Δ Monthly % |\n")
        out.append("|---|---:|---:|---:|---:|\n")
        d = m - base_m
        dp = (d / base_m) if base_m else 0.0
        out.append(
            f"| { _md_escape(sid) } | {m:,.2f} | {y:,.2f} | {d:,.2f} | {dp:.1%} |\n"
        )

    return "".join(out)
