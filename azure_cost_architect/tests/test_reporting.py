from textwrap import dedent

from azure_cost_architect.pricing.enrich import (
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
        ],
    }

    totals = aggregate_scenario_costs(scenario, currency="USD")

    assert totals["monthly_priced"] == 100.0
    assert totals["monthly_estimated"] == 25.0
    assert totals["monthly_with_estimates"] == 125.0
    assert totals["yearly_estimated"] == 300.0
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
        ## Scenario totals
        | Scenario | Monthly (priced) | Monthly (est.) | Monthly (total) | Yearly (total) | Est. Ratio |
        |---|---|---|---|---|---|
        | baseline | 110.00 USD | 25.00 USD | 135.00 USD | 1,620.00 USD | 18.52% |
        | cost_optimized | 78.00 USD | 15.00 USD | 93.00 USD | 1,116.00 USD | 16.13% |

        ## Deltas vs baseline
        | Scenario | Δ Monthly (priced) | Δ Monthly (total) | Δ Yearly (total) |
        |---|---|---|---|
        | baseline | +0.00 USD (+0.00%) | +0.00 USD (+0.00%) | +0.00 USD (+0.00%) |
        | cost_optimized | -32.00 USD (-29.09%) | -42.00 USD (-31.11%) | -504.00 USD (-31.11%) |

        ## Category rollups
        ### baseline
        | Category | Monthly (priced) | Monthly (est.) | Monthly (total) |
        |---|---|---|---|
        | compute | 100.00 USD | 0.00 USD | 100.00 USD |
        | network | 10.00 USD | 0.00 USD | 10.00 USD |
        | storage | 0.00 USD | 25.00 USD | 25.00 USD |

        ### cost_optimized
        | Category | Monthly (priced) | Monthly (est.) | Monthly (total) |
        |---|---|---|---|
        | compute | 70.00 USD | 0.00 USD | 70.00 USD |
        | network | 8.00 USD | 0.00 USD | 8.00 USD |
        | storage | 0.00 USD | 15.00 USD | 15.00 USD |

        ## Category deltas vs baseline
        ### cost_optimized
        | Category | Δ Monthly (priced) | Δ Monthly (total) |
        |---|---|---|
        | compute | -30.00 USD (-30.00%) | -30.00 USD (-30.00%) |
        | network | -2.00 USD (-20.00%) | -2.00 USD (-20.00%) |
        | storage | +0.00 USD | -10.00 USD (-40.00%) |
        """
    ).strip()
