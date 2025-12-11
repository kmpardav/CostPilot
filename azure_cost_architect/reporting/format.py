from typing import Dict, List


def _format_currency(value: float, currency: str) -> str:
    return f"{value:,.2f} {currency}"


def _format_delta(delta: Dict[str, float], currency: str) -> str:
    if not delta:
        return "-"
    absolute = delta.get("absolute")
    percent = delta.get("percent")
    abs_str = f"{absolute:+.2f} {currency}"
    if percent is None:
        return abs_str
    return f"{abs_str} ({percent:+.2f}%)"


def _estimate_ratio(total: float, priced: float) -> str:
    if not total:
        return "0.00%"
    estimated = max(total - priced, 0.0)
    ratio = (estimated / total) * 100.0
    return f"{ratio:.2f}%"


def render_totals_table(plan: Dict) -> str:
    currency = plan.get("metadata", {}).get("currency", "USD")
    rows = [
        "| Scenario | Monthly (priced) | Monthly (est.) | Monthly (total) | Yearly (total) | Est. Ratio |",
        "|---|---|---|---|---|---|",
    ]
    for scenario in plan.get("scenarios", []):
        totals = scenario.get("totals", {})
        priced = totals.get("monthly_priced", 0.0)
        total = totals.get("monthly_with_estimates", 0.0)
        estimated = totals.get("monthly_estimated", total - priced)
        rows.append(
            "| {name} | {mp} | {me} | {mt} | {yt} | {ratio} |".format(
                name=scenario.get("label") or scenario.get("id") or "-",
                mp=_format_currency(priced, currency),
                me=_format_currency(estimated, currency),
                mt=_format_currency(total, currency),
                yt=_format_currency(totals.get("yearly_with_estimates", 0.0), currency),
                ratio=_estimate_ratio(total, priced),
            )
        )
    return "\n".join(rows)


def render_deltas_table(plan: Dict) -> str:
    currency = plan.get("metadata", {}).get("currency", "USD")
    rows = [
        "| Scenario | Δ Monthly (priced) | Δ Monthly (total) | Δ Yearly (total) |",
        "|---|---|---|---|",
    ]
    for scenario in plan.get("scenarios", []):
        totals = scenario.get("totals", {})
        delta = totals.get("delta_vs_baseline", {})
        rows.append(
            "| {name} | {mp} | {mt} | {yt} |".format(
                name=scenario.get("label") or scenario.get("id") or "-",
                mp=_format_delta(delta.get("monthly_priced", {}), currency),
                mt=_format_delta(delta.get("monthly_with_estimates", {}), currency),
                yt=_format_delta(delta.get("yearly_with_estimates", {}), currency),
            )
        )
    return "\n".join(rows)


def render_category_table(scenario: Dict, currency: str) -> str:
    rows: List[str] = [
        "| Category | Monthly (priced) | Monthly (est.) | Monthly (total) |",
        "|---|---|---|---|",
    ]
    for category, totals in sorted((scenario.get("totals", {}).get("by_category") or {}).items()):
        rows.append(
            "| {cat} | {mp} | {me} | {mt} |".format(
                cat=category,
                mp=_format_currency(totals.get("monthly_priced", 0.0), currency),
                me=_format_currency(totals.get("monthly_estimated", 0.0), currency),
                mt=_format_currency(totals.get("monthly_with_estimates", 0.0), currency),
            )
        )
    return "\n".join(rows)


def render_category_deltas(scenario: Dict, baseline: Dict, currency: str) -> str:
    rows: List[str] = [
        "| Category | Δ Monthly (priced) | Δ Monthly (total) |",
        "|---|---|---|",
    ]
    category_deltas = scenario.get("totals", {}).get("delta_vs_baseline", {}).get("by_category", {})
    baseline_categories = baseline.get("totals", {}).get("by_category", {})
    for category in sorted(set(category_deltas.keys()) | set(baseline_categories.keys())):
        delta_entry = category_deltas.get(category, {})
        rows.append(
            "| {cat} | {mp} | {mt} |".format(
                cat=category,
                mp=_format_delta(delta_entry.get("monthly_priced", {}), currency),
                mt=_format_delta(delta_entry.get("monthly_with_estimates", {}), currency),
            )
        )
    return "\n".join(rows)


def render_report(plan: Dict) -> str:
    currency = plan.get("metadata", {}).get("currency", "USD")
    scenarios = plan.get("scenarios", [])
    if not scenarios:
        return ""

    baseline = next(
        (sc for sc in scenarios if (sc.get("id") or "").lower() == "baseline"),
        scenarios[0],
    )

    sections: List[str] = ["## Scenario totals", render_totals_table(plan), "", "## Deltas vs baseline", render_deltas_table(plan)]

    sections.append("")
    sections.append("## Category rollups")
    for scenario in scenarios:
        label = scenario.get("label") or scenario.get("id") or "-"
        sections.append(f"### {label}")
        sections.append(render_category_table(scenario, currency))
        sections.append("")

    sections.append("## Category deltas vs baseline")
    for scenario in scenarios:
        if (scenario.get("id") or "").lower() == "baseline":
            continue
        label = scenario.get("label") or scenario.get("id") or "-"
        sections.append(f"### {label}")
        sections.append(render_category_deltas(scenario, baseline, currency))
        sections.append("")

    return "\n".join(sections).strip()
