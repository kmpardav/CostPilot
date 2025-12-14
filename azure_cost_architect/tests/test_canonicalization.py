import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from azure_cost_architect.utils.knowledgepack import canonicalize_service_name
from azure_cost_architect.planner.validation import validate_plan_schema


def test_canonicalize_service_name_synonyms():
    assert canonicalize_service_name("Azure Cache for Redis")["canonical"] == "Redis Cache"
    assert canonicalize_service_name("Public IP Addresses")["canonical"] == "Virtual Network"
    azure_openai = canonicalize_service_name("Azure OpenAI")
    assert azure_openai["canonical"] == "Foundry Models"
    assert "Foundry Tools" in azure_openai.get("suggestions", [])


def test_validation_sets_hints_and_canonical_names():
    plan = {
        "scenarios": [
            {
                "resources": [
                    {
                        "id": "redis",
                        "category": "cache.redis",
                        "service_name": "Azure Cache for Redis",
                        "product_name_contains": ["Redis Cache Hours"],
                    },
                    {
                        "id": "pip",
                        "category": "network.public_ip",
                        "service_name": "Public IP Addresses",
                        "meter_name_contains": ["Public"],
                    },
                    {
                        "id": "openai",
                        "category": "ml.azureml",
                        "service_name": "Azure OpenAI",
                        "product_name_contains": ["Azure OpenAI"],
                    },
                ]
            }
        ]
    }

    validated = validate_plan_schema(plan)
    resources = {r["id"]: r for r in validated["scenarios"][0]["resources"]}

    assert resources["redis"]["service_name"] == "Redis Cache"
    assert resources["pip"]["service_name"] == "Virtual Network"
    assert resources["openai"]["service_name"] == "Foundry Models"
    assert "Foundry Tools" in (resources["openai"].get("service_name_suggestions") or [])

    for res in resources.values():
        assert isinstance(res.get("product_name_contains"), list)
        assert isinstance(res.get("sku_name_contains"), list)
        assert isinstance(res.get("meter_name_contains"), list)
        assert isinstance(res.get("arm_sku_name_contains"), list)
