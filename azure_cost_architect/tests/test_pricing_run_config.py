import asyncio

import pytest

from azure_cost_architect.pricing.enrich import enrich_plan_with_prices


def test_enrich_plan_requires_currency_code_when_pricing_run_present():
    plan = {
        "metadata": {},
        "pricing_run": {},
        "scenarios": [],
    }

    with pytest.raises(ValueError, match="currency_code"):
        asyncio.run(enrich_plan_with_prices(plan))
