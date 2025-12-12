import json
from pathlib import Path
from pathlib import Path

import pytest

from azure_cost_architect.pricing.enrich import (
    DEFAULT_MISSING_MONTHLY_PENALTY,
    aggregate_scenario_costs,
    attach_baseline_deltas,
    fetch_price_for_resource,
)
from azure_cost_architect.reporting.format import render_totals_table


def test_reservation_unit_of_measure_ambiguous(monkeypatch):
    # Reservation with hourly UoM must be treated as ambiguous to avoid underpricing
    resource = {
        "id": "sql-resv",
        "category": "db.sql",
        "billing_model": "reserved",
        "hours_per_month": 730,
        "quantity": 1,
        "metrics": {},
    }
    scenario = {"id": "baseline"}

    monkeypatch.setattr(
        "azure_cost_architect.pricing.enrich.load_catalog",
        lambda base_dir, category, region, currency: [
            {
                "skuName": "GP_Gen5_1",
                "meterName": "vCore (Reservation)",
                "productName": "SQL Database",
                "unitPrice": 200.0,
                "unitOfMeasure": "1 Hour (vCore)",
                "currencyCode": "EUR",
                "type": "Reservation",
                "reservationTerm": "1 Year",
            }
        ],
    )

    import asyncio

    asyncio.run(
        fetch_price_for_resource(
            scenario,
            resource,
            default_region="westeurope",
            currency="EUR",
        )
    )

    assert resource["pricing_status"] == "reservation_uom_ambiguous"
    assert resource["monthly_cost"] == DEFAULT_MISSING_MONTHLY_PENALTY
    assert resource["yearly_cost"] == DEFAULT_MISSING_MONTHLY_PENALTY * 12


def test_sku_mismatch_detected(monkeypatch):
    resource = {
        "id": "appsvc-plan",
        "category": "appservice",
        "arm_sku_name": "P1v3",
        "hours_per_month": 730,
        "quantity": 1,
        "metrics": {},
    }
    scenario = {"id": "baseline"}

    monkeypatch.setattr(
        "azure_cost_architect.pricing.enrich.load_catalog",
        lambda base_dir, category, region, currency: [
            {
                "skuName": "P0v3",
                "meterName": "P0v3 App",
                "productName": "Azure App Service Premium v3 Plan",
                "unitPrice": 0.05,
                "unitOfMeasure": "1 Hour",
                "currencyCode": "EUR",
                "type": "Consumption",
            }
        ],
    )

    import asyncio

    asyncio.run(
        fetch_price_for_resource(
            scenario,
            resource,
            default_region="westeurope",
            currency="EUR",
        )
    )

    assert resource["pricing_status"] == "sku_mismatch"
    assert resource.get("sku_mismatch") is True


def test_blob_storage_prefers_capacity(monkeypatch):
    resource = {
        "id": "blob1",
        "category": "storage.blob",
        "arm_sku_name": "Standard_GRS",
        "region": "westeurope",
        "metrics": {"hot_gb": 100},
    }
    scenario = {"id": "baseline"}

    catalog_items = [
        {
            "skuName": "Standard_GRS",
            "meterName": "Delete Operations, Cool Data Scanned for Query Acceleration",
            "productName": "Azure Data Lake Storage Gen2 Hierarchical Namespace",
            "unitPrice": 0.001,
            "unitOfMeasure": "10K",
            "currencyCode": "EUR",
        },
        {
            "skuName": "Standard_GRS",
            "meterName": "Hot LRS Data Stored",
            "productName": "General Block Blob",
            "unitPrice": 0.02,
            "unitOfMeasure": "1 GB",
            "currencyCode": "EUR",
        },
    ]

    monkeypatch.setattr(
        "azure_cost_architect.pricing.enrich.load_catalog",
        lambda base_dir, category, region, currency: catalog_items,
    )

    import asyncio

    asyncio.run(
        fetch_price_for_resource(
            scenario,
            resource,
            default_region="westeurope",
            currency="EUR",
        )
    )

    assert resource["pricing_status"] == "estimated"
    assert "Hot LRS Data Stored" in (resource.get("meter_name") or "")


def test_incomplete_scenarios_block_deltas():
    plan = {
        "metadata": {"currency": "EUR"},
        "scenarios": [
            {
                "id": "baseline",
                "label": "Baseline",
                "resources": [
                    {
                        "category": "appservice",
                        "monthly_cost": 50.0,
                        "yearly_cost": 600.0,
                        "pricing_status": "priced",
                    }
                ],
            },
            {
                "id": "high_performance",
                "label": "High Performance",
                "resources": [
                    {
                        "category": "cache.redis",
                        "monthly_cost": None,
                        "yearly_cost": None,
                        "pricing_status": "missing",
                    }
                ],
            },
        ],
    }

    for scenario in plan["scenarios"]:
        scenario["totals"] = aggregate_scenario_costs(scenario, currency="EUR")
    attach_baseline_deltas(plan["scenarios"])

    report = render_totals_table(plan)

    assert plan["scenarios"][1]["totals"]["delta_vs_baseline"]["status"] == "not_comparable"
    assert "⚠️" in report
    assert plan["scenarios"][1]["totals"]["comparable"] is False
    assert plan["scenarios"][1]["totals"]["compare_skip_reason"] == "missing_pricing"


def test_fixture_report_mentions_placeholders():
    enriched = json.loads(
        (Path(__file__).parent / "fixtures" / "debug_enriched.json").read_text()
    )
    table = render_totals_table({"metadata": {"currency": "EUR"}, "scenarios": enriched["scenarios"]})
    assert "Monthly (modeled)" in table
    assert "Display totals include missing placeholders" in table


def test_run10_incomplete_plan_marks_not_comparable():
    plan_path = Path(__file__).resolve().parents[2] / "runs" / "run10_incomplete" / "plan.json"
    plan = json.loads(plan_path.read_text())

    assert any(not sc.get("totals", {}).get("comparable") for sc in plan.get("scenarios", []))
    totals = plan["scenarios"][0]["totals"]
    assert totals.get("missing_total", 0) > 0
    assert totals.get("compare_skip_reason") in {"sku_mismatch", "missing_pricing"}
