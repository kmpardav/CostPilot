from azure_cost_architect.pricing.units import compute_units


def test_compute_units_hour_override_raw_count_is_not_multiplied():
    # Planner already gave monthly hours (e.g., 730). We must NOT multiply again.
    resource = {
        "category": "network.nat",
        "hours_per_month": 730,
        "units_override": 730,
        "units_override_kind": "raw_count",
        "unit_of_measure": "1 Hour",
    }
    u = compute_units(resource, resource["unit_of_measure"])
    assert u == 730


def test_compute_units_hour_override_per_hour_units_is_multiplied():
    # Planner gives a per-hour quantity (e.g., 2 CU/hour) and expects hours to be applied.
    resource = {
        "category": "network.appgw",
        "hours_per_month": 730,
        "units_override": 2,
        "units_override_kind": "per_hour_units",
        "unit_of_measure": "1 Hour",
    }
    u = compute_units(resource, resource["unit_of_measure"])
    assert u == 1460


def test_compute_units_pack_divisor_applied_for_raw_count():
    # For pack meters, raw_count should be divided by the pack size.
    resource = {
        "category": "security.keyvault",
        "units_override": 50000,
        "units_override_kind": "raw_count",
        "unit_of_measure": "10,000 Operations",
    }
    assert compute_units(resource, resource["unit_of_measure"]) == 5.0


def test_compute_units_pack_divisor_not_applied_for_billed_units():
    # If planner already provided billed units, do NOT divide again.
    resource = {
        "category": "security.keyvault",
        "units_override": 5,
        "units_override_kind": "billed_units",
        "unit_of_measure": "10,000 Operations",
    }
    assert compute_units(resource, resource["unit_of_measure"]) == 5.0
