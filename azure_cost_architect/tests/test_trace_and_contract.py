import json
from pathlib import Path

import pytest

from azure_cost_architect.llm.planner import plan_architecture_iterative
from azure_cost_architect.planner.contract import PlanValidationResult
from azure_cost_architect.utils.trace import build_trace_logger
from azure_cost_architect.pricing.enrich import fetch_price_for_resource
from azure_cost_architect.pricing.cache import _price_cache_best


class _StubClient:
    """Minimal stub to satisfy planner signatures."""

    pass


def _planner_invalid(_prompt: str):
    return "stub-model", json.dumps(
        {
            "metadata": {},
            "scenarios": [
                {
                    "id": "baseline",
                    "resources": [
                        {
                            "id": "r1",
                            "category": "compute.vm",
                            "service_name": "MadeUpService",
                            "product_name_contains": [],
                            "sku_name_contains": [],
                            "meter_name_contains": [],
                            "arm_sku_name_contains": [],
                        }
                    ],
                }
            ],
        }
    )


def _planner_fixed(_prompt: str):
    return "stub-model", json.dumps(
        {
            "metadata": {},
            "scenarios": [
                {
                    "id": "baseline",
                    "resources": [
                        {
                            "id": "r1",
                            "category": "compute.vm",
                            "service_name": "Virtual Machines",
                            "product_name_contains": ["D2s_v3"],
                            "sku_name_contains": ["D2s"],
                            "meter_name_contains": ["Compute"],
                            "arm_sku_name_contains": ["Standard_D2s_v3"],
                        }
                    ],
                }
            ],
        }
    )


def test_planner_contract_enforced(tmp_path: Path):
    trace = build_trace_logger(tmp_path / "trace.jsonl")
    plan = plan_architecture_iterative(
        _StubClient(),
        "test",
        planner_callable=_planner_invalid,
        repair_callable=lambda prompt: _planner_fixed(prompt)[1],
        trace=trace,
    )

    svc = plan["scenarios"][0]["resources"][0]["service_name"]
    assert svc != "UNKNOWN_SERVICE"


def test_trace_written(tmp_path: Path):
    trace_path = tmp_path / "trace.jsonl"
    trace = build_trace_logger(trace_path)
    trace.log("phase0_setup", {"ok": True})
    plan_architecture_iterative(
        _StubClient(),
        "test",
        planner_callable=_planner_fixed,
        repair_callable=lambda prompt: _planner_fixed(prompt)[1],
        trace=trace,
        max_iters=1,
    )

    phases = [json.loads(line)["phase"] for line in trace_path.read_text().splitlines()]
    assert "phase0_setup" in phases
    assert "phase1_planner" in phases
    assert "phase2_validation" in phases


def test_no_retail_before_valid_plan(monkeypatch):
    invoked = False

    def _fake_catalog(*_args, **_kwargs):
        nonlocal invoked
        invoked = True
        return []

    monkeypatch.setattr(
        "azure_cost_architect.pricing.catalog.ensure_catalog",
        _fake_catalog,
    )

    def _always_invalid(_prompt: str):
        return "stub-model", json.dumps({"scenarios": []})

    def _fake_validate(plan):
        return PlanValidationResult(plan=plan, errors=[{"type": "unknown_service"}], rule_changes=[], canonical_mappings=[])

    monkeypatch.setattr(
        "azure_cost_architect.llm.planner.validate_pricing_contract", _fake_validate
    )

    with pytest.raises(ValueError):
        plan_architecture_iterative(
            _StubClient(),
            "bad",
            planner_callable=_always_invalid,
            repair_callable=lambda prompt: _always_invalid(prompt)[1],
            max_iters=1,
        )

    assert invoked is False


def test_no_cache_poison(monkeypatch, tmp_path: Path):
    import asyncio

    _price_cache_best.clear()
    calls = []

    def fake_set_cache(key, value):
        calls.append(key)

    monkeypatch.setattr("azure_cost_architect.pricing.enrich.set_cached_price", fake_set_cache)

    def fake_load_catalog(**kwargs):
        return [
            {
                "unitPrice": 10.0,
                "unitOfMeasure": "3 Year",
                "currencyCode": "EUR",
                "skuName": "reserved",
                "meterName": "Reserved",
                "ProductName": "VM",
                "type": "Reservation",
                "reservationTerm": "3 Year",
            }
        ]

    monkeypatch.setattr("azure_cost_architect.pricing.enrich.load_catalog", fake_load_catalog)

    scenario = {"id": "s1"}
    resource = {
        "id": "vm1",
        "category": "compute.vm",
        "service_name": "Virtual Machines",
        "billing_model": "reserved",
        "quantity": 1,
        "hours_per_month": 730,
        "metrics": {},
        "arm_sku_name": "Standard_D2s_v3",
    }

    asyncio.run(
        fetch_price_for_resource(
            scenario,
            resource,
            default_region="westeurope",
            currency="EUR",
            debug=False,
            adjudicator=None,
        )
    )

    assert resource.get("pricing_status") == "sku_mismatch"
    assert calls == []
