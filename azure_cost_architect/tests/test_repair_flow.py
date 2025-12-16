from azure_cost_architect.planner import validate_plan_schema
from azure_cost_architect.planner.repair import apply_repairs


def _first_resource(plan: dict) -> dict:
    return plan["scenarios"][0]["resources"][0]


def test_repair_loop_only_changes_allowed_fields():
    plan = validate_plan_schema(
        {
            "metadata": {},
            "scenarios": [
                {
                    "id": "baseline",
                    "resources": [
                        {
                            "id": "vm1",
                            "category": "compute.vm",
                            "service_name": "UNKNOWN_SERVICE",
                            "quantity": 2,
                            "hours_per_month": 123,
                            "billing_model": "payg",
                            "product_name_contains": [],
                            "sku_name_contains": [],
                            "meter_name_contains": [],
                            "arm_sku_name_contains": [],
                            "metrics": {"storage_gb": 50},
                        }
                    ],
                }
            ],
        }
    )

    repairs = [
        {
            "scenario_id": "baseline",
            "resource_id": "vm1",
            "service_name": "Virtual Machines",
            "arm_sku_name": "Standard_D2s_v3",
            "product_name_contains": ["D2s v3"],
            "sku_name_contains": [],
            "meter_name_contains": [],
            "arm_sku_name_contains": [],
            "service_name_suggestions": [],
            # Attempted forbidden change should be ignored
            "hours_per_month": 999,
        }
    ]

    updated = apply_repairs(plan, repairs)
    res = _first_resource(updated)

    assert res["service_name"] == "Virtual Machines"
    assert res["arm_sku_name"] == "Standard_D2s_v3"
    assert res["quantity"] == 2
    assert res["hours_per_month"] == 123
    assert res["billing_model"] == "payg"


def test_unknown_service_suggestions_are_category_scoped():
    plan = validate_plan_schema(
        {
            "metadata": {},
            "scenarios": [
                {
                    "id": "baseline",
                    "resources": [
                        {
                            "id": "ip1",
                            "category": "network.public_ip",
                            "service_name": "unknown",
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

    res = _first_resource(plan)
    assert res["service_name"] == "Virtual Network"
    assert res["service_name_suggestions"] == ["Virtual Network"]
