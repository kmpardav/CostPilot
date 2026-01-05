from textwrap import dedent

from azure_cost_architect.pricing.enrich import (
    DEFAULT_MISSING_MONTHLY_PENALTY,
    aggregate_scenario_costs,
    attach_baseline_deltas,
)
from azure_cost_architect.reporting.format import render_report


def test_aggregate_scenario_costs_tracks_estimates_and_categories():
    scenario = {
        "id": "baseline",
        "resources": [
            {
                "id": "vm1",
                "category": "compute",
                "monthly_cost": 100.0,
                "yearly_cost": 1200.0,
                "pricing_status": "priced",
            },
            {
                "id": "storage1",
                "category": "storage",
                "monthly_cost": 25.0,
                "yearly_cost": 300.0,
                "pricing_status": "estimated",
            },
            {
                "id": "redis-missing",
                "category": "cache",
                "monthly_cost": None,
                "yearly_cost": None,
                "pricing_status": "missing",
            },
        ],
    }

    totals = aggregate_scenario_costs(scenario, currency="USD")

    assert totals["monthly_priced"] == 100.0
    assert totals["monthly_estimated"] == 25.0
    assert totals["monthly_with_estimates"] == 125.0
    assert totals["yearly_estimated"] == 300.0
    assert totals["missing_total"] == 0.0
    assert totals["missing_count"] == 1
    assert totals["monthly_missing"] == 0.0
    assert totals["is_complete"] is False
    assert totals["by_category"]["compute"]["monthly_priced"] == 100.0
    assert totals["by_category"]["storage"]["monthly_estimated"] == 25.0


def test_render_report_with_deltas_snapshot():
    plan = {
        "metadata": {"currency": "USD"},
        "scenarios": [
            {
                "id": "baseline",
                "resources": [
                    {
                        "category": "compute",
                        "monthly_cost": 100.0,
                        "yearly_cost": 1200.0,
                        "pricing_status": "priced",
                    },
                    {
                        "category": "storage",
                        "monthly_cost": 25.0,
                        "yearly_cost": 300.0,
                        "pricing_status": "estimated",
                    },
                    {
                        "category": "network",
                        "monthly_cost": 10.0,
                        "yearly_cost": 120.0,
                        "pricing_status": "priced",
                    },
                ],
            },
            {
                "id": "cost_optimized",
                "resources": [
                    {
                        "category": "compute",
                        "monthly_cost": 70.0,
                        "yearly_cost": 840.0,
                        "pricing_status": "priced",
                    },
                    {
                        "category": "storage",
                        "monthly_cost": 15.0,
                        "yearly_cost": 180.0,
                        "pricing_status": "estimated",
                    },
                    {
                        "category": "network",
                        "monthly_cost": 8.0,
                        "yearly_cost": 96.0,
                        "pricing_status": "priced",
                    },
                ],
            },
        ],
    }

    for scenario in plan["scenarios"]:
        scenario["totals"] = aggregate_scenario_costs(scenario, currency="USD")
    attach_baseline_deltas(plan["scenarios"])

    report = render_report(plan)

    assert report == dedent(
        """
        ## Completeness & comparison guardrails
        - baseline: ✅ complete
        - cost_optimized: ✅ complete

        ## Scenario totals
        | Scenario | Complete? | Missing/Mismatch/Res | Monthly (priced) | Monthly (est.) | Monthly (missing) | Monthly (modeled) | Monthly (display)* | Yearly (display)* | Est. Ratio |
        |---|---|---|---|---|---|---|---|---|---|
        | baseline | ✅ | 0 missing / 0 mismatch / 0 res? | 110.00 USD | 25.00 USD | 0.00 USD | 135.00 USD | 135.00 USD | 1,620.00 USD | 18.52% |
        | cost_optimized | ✅ | 0 missing / 0 mismatch / 0 res? | 78.00 USD | 15.00 USD | 0.00 USD | 93.00 USD | 93.00 USD | 1,116.00 USD | 16.13% |

        *Display totals include missing placeholders; comparisons use modeled (priced+estimated) only.

        ## Deltas vs baseline
        | Scenario | Δ Monthly (priced) | Δ Monthly (modeled) | Δ Yearly (modeled) |
        |---|---|---|---|
        | baseline | +0.00 USD (+0.00%) | +0.00 USD (+0.00%) | +0.00 USD (+0.00%) |
        | cost_optimized | -32.00 USD (-29.09%) | -42.00 USD (-31.11%) | -504.00 USD (-31.11%) |

        ## Category rollups
        ### baseline
        | Category | Monthly (priced) | Monthly (est.) | Monthly (modeled) |
        |---|---|---|---|
        | compute | 100.00 USD | 0.00 USD | 100.00 USD |
        | network | 10.00 USD | 0.00 USD | 10.00 USD |
        | storage | 0.00 USD | 25.00 USD | 25.00 USD |

        ### cost_optimized
        | Category | Monthly (priced) | Monthly (est.) | Monthly (modeled) |
        |---|---|---|---|
        | compute | 70.00 USD | 0.00 USD | 70.00 USD |
        | network | 8.00 USD | 0.00 USD | 8.00 USD |
        | storage | 0.00 USD | 15.00 USD | 15.00 USD |

        ## Category deltas vs baseline
        ### cost_optimized
        | Category | Δ Monthly (priced) | Δ Monthly (modeled) |
        |---|---|---|
        | compute | - | - |
        | network | - | - |
        | storage | - | - |
        """
    ).strip()


def test_render_report_marks_incomplete_deltas():
    plan = {
        "metadata": {"currency": "USD"},
        "scenarios": [
            {
                "id": "baseline",
                "resources": [
                    {
                        "category": "compute",
                        "monthly_cost": 100.0,
                        "yearly_cost": 1200.0,
                        "pricing_status": "priced",
                    },
                ],
            },
            {
                "id": "high_performance",
                "resources": [
                    {
                        "category": "compute",
                        "monthly_cost": None,
                        "yearly_cost": None,
                        "pricing_status": "missing",
                    }
                ],
            },
        ],
    }

    for scenario in plan["scenarios"]:
        scenario["totals"] = aggregate_scenario_costs(scenario, currency="USD")
    attach_baseline_deltas(plan["scenarios"])

    report = render_report(plan)

    assert "n/a (not comparable: missing_pricing)" in report
    assert "⚠️" in report
    assert "100.00 USD" in report
    assert "Comparisons/deltas are suppressed" in report
    assert plan["scenarios"][1]["totals"].get("comparable") is False
    assert plan["scenarios"][1]["totals"].get("compare_skip_reason") == "missing_pricing"


def test_render_report_suppresses_mismatch_comparisons():
    plan = {
        "metadata": {"currency": "USD"},
        "scenarios": [
            {
                "id": "baseline",
                "resources": [
                    {
                        "category": "compute",
                        "monthly_cost": 100.0,
                        "yearly_cost": 1200.0,
                        "pricing_status": "priced",
                    },
                ],
            },
            {
                "id": "alt",
                "resources": [
                    {
                        "category": "compute",
                        "monthly_cost": 90.0,
                        "yearly_cost": 1080.0,
                        "pricing_status": "sku_mismatch",
                        "sku_mismatch": True,
                    }
                ],
            },
        ],
    }

    for scenario in plan["scenarios"]:
        scenario["totals"] = aggregate_scenario_costs(scenario, currency="USD")
    attach_baseline_deltas(plan["scenarios"])

    report = render_report(plan)

    assert "n/a (not comparable: sku_mismatch)" in report
    assert "1 missing / 1 mismatch / 0 res?" in report
    assert plan["scenarios"][1]["totals"].get("comparable") is False


def test_missing_penalty_prevents_inversion_and_marks_incomparable():
    plan = {
        "metadata": {"currency": "USD"},
        "scenarios": [
            {
                "id": "baseline",
                "resources": [
                    {
                        "category": "compute",
                        "monthly_cost": 80.0,
                        "yearly_cost": 960.0,
                        "pricing_status": "priced",
                    },
                ],
            },
            {
                "id": "high_performance",
                "resources": [
                    {
                        "category": "compute",
                        "monthly_cost": 10.0,
                        "yearly_cost": 120.0,
                        "pricing_status": "priced",
                    },
                    {
                        "category": "cache",
                        "monthly_cost": None,
                        "yearly_cost": None,
                        "pricing_status": "missing",
                    },
                ],
            },
        ],
    }

    for scenario in plan["scenarios"]:
        scenario["totals"] = aggregate_scenario_costs(scenario, currency="USD")
    attach_baseline_deltas(plan["scenarios"])

    baseline_totals = plan["scenarios"][0]["totals"]
    high_perf_totals = plan["scenarios"][1]["totals"]

    assert high_perf_totals["monthly_missing"] == 0.0
    assert high_perf_totals["monthly_with_estimates"] == 10.0
    assert high_perf_totals["comparable"] is False
    assert high_perf_totals["delta_vs_baseline"]["status"] == "not_comparable"
    assert high_perf_totals["compare_skip_reason"] == "missing_pricing"
