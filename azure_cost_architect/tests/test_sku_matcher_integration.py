from __future__ import annotations

import importlib
from pathlib import Path

import pytest


FIXTURE_DIR = Path(__file__).parent / "fixtures"
ALIAS_INDEX = FIXTURE_DIR / "sku_alias_index.json"


def _reload_contract(monkeypatch, alias_path: Path | None):
    if alias_path:
        monkeypatch.setenv("AZCOST_SKU_ALIAS_INDEX", str(alias_path))
    else:
        monkeypatch.delenv("AZCOST_SKU_ALIAS_INDEX", raising=False)

    import azure_cost_architect.planner.contract as contract_module

    return importlib.reload(contract_module)


@pytest.mark.parametrize(
    "category,requested,expected",
    [
        ("appservice", "P1v3", "P1 v3"),
        ("compute.vm", "Standard_D2s_v3", "Standard_D2s_v3"),
    ],
)
def test_validate_pricing_contract_matches_alias(monkeypatch, category, requested, expected):
    contract_module = _reload_contract(monkeypatch, ALIAS_INDEX)

    try:
        plan = {
            "metadata": {},
            "scenarios": [
                {
                    "resources": [
                        {
                            "id": "res1",
                            "category": category,
                            "service_name": "Azure App Service" if category == "appservice" else "Virtual Machines",
                            "arm_sku_name": requested,
                        }
                    ]
                }
            ],
        }

        result = contract_module.validate_pricing_contract(plan)
        resource = result.plan["scenarios"][0]["resources"][0]

        assert resource["arm_sku_name"] == expected
        assert (resource.get("sku_match_diagnostics") or {}).get("matched") == expected
        assert not result.errors
    finally:
        _reload_contract(monkeypatch, None)


def test_validate_pricing_contract_flags_unknown_sku(monkeypatch):
    contract_module = _reload_contract(monkeypatch, ALIAS_INDEX)

    try:
        plan = {
            "metadata": {},
            "scenarios": [
                {
                    "resources": [
                        {
                            "id": "vm1",
                            "category": "compute.vm",
                            "service_name": "Virtual Machines",
                            "arm_sku_name": "NonExistentSKU",
                        }
                    ]
                }
            ],
        }

        result = contract_module.validate_pricing_contract(plan)
        assert any(err.get("type") == "unknown_sku" for err in result.errors)
        resource = result.plan["scenarios"][0]["resources"][0]
        assert (resource.get("sku_match_diagnostics") or {}).get("matched") is None
    finally:
        _reload_contract(monkeypatch, None)
