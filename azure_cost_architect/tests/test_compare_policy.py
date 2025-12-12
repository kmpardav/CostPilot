import pytest

from azure_cost_architect.cli import _apply_compare_policy, _collect_compare_blockers
from azure_cost_architect.pricing.enrich import aggregate_scenario_costs, attach_baseline_deltas


def test_optional_missing_not_blocking_when_not_required():
    scenario = {
        "id": "baseline",
        "resources": [
            {
                "id": "kv",
                "category": "security.keyvault",
                "monthly_cost": None,
                "yearly_cost": None,
                "pricing_status": "missing",
            }
        ],
    }

    totals = aggregate_scenario_costs(
        scenario, currency="USD", required_categories=["compute"]
    )

    assert totals["missing_count"] == 1
    assert totals["required_missing_count"] == 0
    assert totals["is_complete"] is True
    assert totals["comparable"] is True


def test_collect_compare_blockers_reports_incomplete():
    plan = {
        "scenarios": [
            {
                "id": "baseline",
                "totals": {"comparable": False, "compare_skip_reason": "missing_pricing"},
            },
            {"id": "other", "totals": {"comparable": True}},
        ]
    }

    blockers = _collect_compare_blockers(plan)
    assert ("baseline", "missing_pricing") in blockers
    assert all(isinstance(entry, tuple) and len(entry) == 2 for entry in blockers)


def test_required_missing_sets_incomparable_and_skip_reason():
    scenario = {
        "id": "baseline",
        "resources": [
            {"id": "vm1", "category": "compute.vm", "monthly_cost": None, "yearly_cost": None, "pricing_status": "missing"}
        ],
    }

    totals = aggregate_scenario_costs(
        scenario, currency="USD", required_categories=["compute", "db"]
    )

    assert totals["missing_total"] > 0
    assert totals["missing_count"] == 1
    assert totals["required_missing_count"] == 1
    assert totals["comparable"] is False
    assert totals["compare_skip_reason"] == "missing_pricing"


def test_attach_deltas_blocked_when_required_missing():
    scenarios = [
        {
            "id": "baseline",
            "totals": aggregate_scenario_costs(
                {
                    "id": "baseline",
                    "resources": [
                        {
                            "id": "vm1",
                            "category": "compute.vm",
                            "monthly_cost": None,
                            "yearly_cost": None,
                            "pricing_status": "missing",
                        }
                    ],
                },
                currency="USD",
                required_categories=["compute"],
            ),
        },
        {
            "id": "other",
            "totals": aggregate_scenario_costs(
                {
                    "id": "other",
                    "resources": [
                        {
                            "id": "vm2",
                            "category": "compute.vm",
                            "monthly_cost": 10.0,
                            "yearly_cost": 120.0,
                            "pricing_status": "priced",
                        }
                    ],
                },
                currency="USD",
                required_categories=["compute"],
            ),
        },
    ]

    attach_baseline_deltas(scenarios)

    assert scenarios[0]["totals"]["comparable"] is False
    assert scenarios[1]["totals"]["delta_vs_baseline"]["status"] == "not_comparable"
    assert scenarios[1]["totals"]["delta_vs_baseline"]["reason"] == "missing_pricing"


def test_apply_compare_policy_hard_stop_exits():
    plan = {
        "scenarios": [
            {"id": "baseline", "totals": {"comparable": False, "compare_skip_reason": "missing_pricing"}}
        ]
    }

    with pytest.raises(SystemExit) as exc:
        _apply_compare_policy(plan, "hard_stop")

    assert exc.value.code == 2


def test_appservice_is_treated_as_compute_required():
    scenario = {
        "id": "baseline",
        "resources": [
            {
                "id": "asp1",
                "category": "appservice.plan",
                "monthly_cost": None,
                "yearly_cost": None,
                "pricing_status": "missing",
            }
        ],
    }

    totals = aggregate_scenario_costs(
        scenario,
        currency="USD",
        required_categories=["compute", "db"],
    )

    assert totals["required_missing_count"] == 1
    assert totals["comparable"] is False
