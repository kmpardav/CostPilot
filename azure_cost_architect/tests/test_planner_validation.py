import json
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from azure_cost_architect.planner.validation import validate_plan_schema
from azure_cost_architect.planner.rules import apply_planner_rules


def test_validate_plan_matches_golden():
    raw_plan = {
        "metadata": {},
        "scenarios": [
            {
                "resources": [
                    {"id": "vm-main", "category": "VM"},
                    {"id": "sql-mi", "category": "SQL MI", "metrics": {"vcores": 4}},
                    {"id": "blob", "category": "blob storage"},
                    {"id": "nat", "category": "NAT Gateway"},
                ]
            },
            {
                "id": "cost_optimized",
                "resources": [
                    {
                        "id": "db-lite",
                        "category": "db.sql",
                        "arm_sku_name": "GP_Gen5_2",
                        "metrics": {"vcores": 2},
                    }
                ],
            },
        ],
    }

    normalized = apply_planner_rules(validate_plan_schema(raw_plan))

    golden_path = Path(__file__).parent / "golden" / "normalized_plan.json"
    expected = json.loads(golden_path.read_text())

    assert normalized == expected


def test_storage_and_network_defaults():
    raw_plan = {
        "scenarios": [
            {
                "resources": [
                    {"id": "blob", "category": "storage.blob"},
                    {"id": "egress", "category": "network.egress", "metrics": {}},
                ]
            }
        ]
    }

    normalized = validate_plan_schema(raw_plan)
    resources = normalized["scenarios"][0]["resources"]

    blob = next(r for r in resources if r["id"] == "blob")
    egress = next(r for r in resources if r["id"] == "egress")

    assert blob["metrics"].get("storage_gb") == 100.0
    assert egress["metrics"].get("egress_gb") == 100.0


def test_presets_add_baseline_controls_and_bandwidth():
    raw_plan = {
        "scenarios": [
            {
                "resources": [
                    {"id": "web", "category": "appservice"},
                    {"id": "db", "category": "db.sql"},
                ]
            }
        ]
    }

    normalized = apply_planner_rules(validate_plan_schema(raw_plan))
    resources = normalized["scenarios"][0]["resources"]
    cats = {r["category"] for r in resources}

    assert "security.keyvault" in cats
    assert "monitoring.loganalytics" in cats
    assert "backup.vault" in cats
    assert any(r for r in resources if r["category"] == "network.nat" and r["source"] == "preset")
    assert any(w.startswith("waf_recommended") for w in normalized["scenarios"][0]["warnings"])
