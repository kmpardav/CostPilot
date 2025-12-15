import pytest

from azure_cost_architect.pricing.scoring import select_best_candidate


def _candidate(score: int, sku: str, price_type: str) -> tuple[int, dict]:
    return (
        score,
        {
            "skuName": sku,
            "meterName": sku,
            "productName": f"App Service {sku}",
            "armSkuName": sku,
            "type": price_type,
        },
    )


@pytest.mark.parametrize("billing_model", ["payg", "pay-as-you-go", "pay_as_you_go"])
def test_fallback_to_devtest_when_only_option(billing_model: str) -> None:
    resource = {"arm_sku_name": "P1v3", "category": "appservice"}
    candidates = [
        _candidate(90, "P1v3", "DevTestConsumption"),
        _candidate(100, "P0v3", "Consumption"),
    ]

    result = select_best_candidate(resource, candidates, env="prod", billing_model=billing_model)

    assert result["status"] == "fallback"
    assert result["fallback_priceType_used"] is True
    assert result["chosen_item"]["skuName"] == "P1v3"
    assert result["chosen_item"]["type"] == "DevTestConsumption"


def test_prefers_consumption_when_available() -> None:
    resource = {"arm_sku_name": "P1 v3", "category": "appservice"}
    candidates = [_candidate(50, "P1v3", "Consumption")]

    result = select_best_candidate(resource, candidates, env="prod", billing_model="payg")

    assert result["status"] == "matched"
    assert result["fallback_priceType_used"] is False
    assert result["chosen_item"]["skuName"] == "P1v3"
    assert result["chosen_item"]["type"] == "Consumption"
    assert result["requested_sku_normalized"] == "p1v3"


def test_rejects_wrong_sku_when_absent() -> None:
    resource = {"arm_sku_name": "P1v3", "category": "appservice"}
    candidates = [_candidate(10, "P0v3", "Consumption")]

    result = select_best_candidate(resource, candidates, env="prod", billing_model="payg")

    assert result["status"] == "unresolved"
    assert result["chosen_item"] is None
    assert result["fallback_priceType_used"] is False
