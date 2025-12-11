import asyncio
import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from azure_cost_architect.pricing.catalog import _catalog_filename
from azure_cost_architect.pricing.enrich import enrich_plan_with_prices
from azure_cost_architect.pricing.normalize import normalize_service_name


def _write_catalog(dir_path: Path, service_name: str, region: str, currency: str, items: list[dict]):
    dir_path.mkdir(parents=True, exist_ok=True)
    fp = dir_path / _catalog_filename(service_name, region, currency)
    with fp.open("w", encoding="utf-8") as f:
        for row in items:
            f.write(json.dumps(row) + "\n")


@pytest.mark.anyio
async def test_enrich_with_small_catalog(monkeypatch, tmp_path):
    region = "westeurope"
    currency = "EUR"
    catalog_dir = tmp_path / "catalog"

    def write(cat: str, items: list[dict]):
        service = normalize_service_name(cat, None)
        _write_catalog(catalog_dir, service, region, currency, items)

    # SQL Database catalog (payg vs reservation)
    write(
        "db.sql",
        [
            {
                "productName": "SQL DB Gen5 Compute PayG",
                "meterName": "SQL DB Compute Gen5",
                "skuName": "GP_Gen5",
                "armSkuName": "GP_Gen5",
                "unitPrice": 2.0,
                "unitOfMeasure": "1 Hour",
                "currencyCode": currency,
                "type": "Consumption",
            },
            {
                "productName": "SQL DB Gen5 Reservation",
                "meterName": "SQL DB Gen5 Reserved 1Y",
                "skuName": "GP_Gen5",
                "armSkuName": "GP_Gen5",
                "unitPrice": 120.0,
                "unitOfMeasure": "1 Year",
                "currencyCode": currency,
                "type": "Reservation",
                "reservationTerm": "1 Year",
            },
        ],
    )

    # Blob storage catalog (hot/cool + noisy ops meter)
    write(
        "storage.blob",
        [
            {
                "productName": "Hot Block Blob Data Stored",
                "meterName": "Hot LRS Data Stored",
                "skuName": "Hot_LRS",
                "unitPrice": 0.02,
                "unitOfMeasure": "1 GB/Month",
                "currencyCode": currency,
                "type": "Consumption",
            },
            {
                "productName": "Cool Block Blob Data Stored",
                "meterName": "Cool LRS Data Stored",
                "skuName": "Cool_LRS",
                "unitPrice": 0.01,
                "unitOfMeasure": "1 GB/Month",
                "currencyCode": currency,
                "type": "Consumption",
            },
            {
                "productName": "Archive Retrieval",
                "meterName": "Archive Retrieval Transactions",
                "skuName": "Archive_LRS",
                "unitPrice": 0.5,
                "unitOfMeasure": "10k operations",
                "currencyCode": currency,
                "type": "Consumption",
            },
        ],
    )

    # Redis catalog
    write(
        "cache.redis",
        [
            {
                "productName": "Redis Cache Throughput",
                "meterName": "Redis Premium Throughput",
                "skuName": "P1",
                "unitPrice": 0.1,
                "unitOfMeasure": "50 MB/s",
                "currencyCode": currency,
                "type": "Consumption",
            },
            {
                "productName": "Redis Cache Hours",
                "meterName": "Redis Cache",
                "skuName": "P1",
                "unitPrice": 0.05,
                "unitOfMeasure": "1 Hour",
                "currencyCode": currency,
                "type": "Consumption",
            },
        ],
    )

    # Public IP & Private Link catalogs
    write(
        "network.public_ip",
        [
            {
                "productName": "Public IP",
                "meterName": "Public IP Address",
                "skuName": "Basic",
                "unitPrice": 0.02,
                "unitOfMeasure": "1 Hour",
                "currencyCode": currency,
                "type": "Consumption",
            }
        ],
    )
    write(
        "network.private_endpoint",
        [
            {
                "productName": "Private Endpoint",
                "meterName": "Private Endpoint Connection",
                "skuName": "Base",
                "unitPrice": 0.05,
                "unitOfMeasure": "1 Hour",
                "currencyCode": currency,
                "type": "Consumption",
            }
        ],
    )

    # Force enrich to use the temp catalog path
    from azure_cost_architect.pricing import enrich as enrich_mod

    monkeypatch.setattr(enrich_mod, "CATALOG_DIR", str(catalog_dir))

    plan = {
        "metadata": {"currency": currency, "default_region": region},
        "scenarios": [
            {
                "id": "baseline",
                "resources": [
                    {
                        "id": "sql-reserved",
                        "category": "db.sql",
                        "billing_model": "reserved",
                        "reservation_term": "1y",
                    },
                    {
                        "id": "sql-payg",
                        "category": "db.sql",
                        "billing_model": "payg",
                    },
                    {
                        "id": "blob-hot",
                        "category": "storage.blob",
                        "arm_sku_name": "Hot_LRS",
                        "metrics": {"hot_gb": 500},
                    },
                    {
                        "id": "blob-cool",
                        "category": "storage.blob",
                        "arm_sku_name": "Cool_LRS",
                        "metrics": {"cool_gb": 200},
                    },
                    {
                        "id": "redis-cache",
                        "category": "cache.redis",
                        "metrics": {"throughput_mbps": 75},
                    },
                    {"id": "public-ip", "category": "network.public_ip"},
                    {"id": "private-link", "category": "network.private_endpoint"},
                ],
            }
        ],
    }

    enriched = await enrich_plan_with_prices(plan, debug=False)
    scenario = enriched["scenarios"][0]
    resources = {r["id"]: r for r in scenario["resources"]}

    # SQL reserved should pick reservation meter and convert yearly price
    sql_res = resources["sql-reserved"]
    assert sql_res["type"].lower() == "reservation"
    assert sql_res.get("reservationTerm", "").startswith("1")
    assert pytest.approx(sql_res["monthly_cost"], rel=1e-3) == 10.0

    # SQL payg should stay consumption
    sql_payg = resources["sql-payg"]
    assert sql_payg["type"].lower() == "consumption"
    assert sql_payg["monthly_cost"] == pytest.approx(2.0 * 730, rel=1e-3)

    # Blob tiers: ensure matching hot vs cool capacity meters
    hot_blob = resources["blob-hot"]
    assert "hot" in hot_blob["product_name"].lower()
    assert hot_blob["monthly_cost"] == pytest.approx(500 * 0.02, rel=1e-3)

    cool_blob = resources["blob-cool"]
    assert "cool" in cool_blob["product_name"].lower()
    assert cool_blob["monthly_cost"] == pytest.approx(200 * 0.01, rel=1e-3)

    # Redis throughput should prefer throughput meter
    redis_res = resources["redis-cache"]
    assert "throughput" in redis_res["meter_name"].lower()
    assert redis_res["monthly_cost"] == pytest.approx((75 / 50) * 730 * 0.1, rel=1e-3)

    # Public IP & Private Link default to hourly usage
    public_ip = resources["public-ip"]
    private_link = resources["private-link"]
    assert public_ip["units"] == pytest.approx(730)
    assert private_link["units"] == pytest.approx(730)

    # Totals should include all components
    totals = scenario["totals"]
    assert totals["monthly_with_estimates"] == pytest.approx(
        sql_res["monthly_cost"]
        + sql_payg["monthly_cost"]
        + hot_blob["monthly_cost"]
        + cool_blob["monthly_cost"]
        + redis_res["monthly_cost"]
        + public_ip["monthly_cost"]
        + private_link["monthly_cost"],
        rel=1e-4,
    )


@pytest.mark.anyio
async def test_blob_storage_defaults_to_hot_when_metrics_missing(monkeypatch, tmp_path):
    region = "westeurope"
    currency = "EUR"
    catalog_dir = tmp_path / "catalog"

    _write_catalog(
        catalog_dir,
        normalize_service_name("storage.blob", None),
        region,
        currency,
        [
            {
                "productName": "Hot Block Blob Data Stored",
                "meterName": "Hot LRS Data Stored",
                "skuName": "Hot_LRS",
                "unitPrice": 0.02,
                "unitOfMeasure": "1 GB/Month",
                "currencyCode": currency,
                "type": "Consumption",
            }
        ],
    )

    from azure_cost_architect.pricing import enrich as enrich_mod

    monkeypatch.setattr(enrich_mod, "CATALOG_DIR", str(catalog_dir))

    plan = {
        "metadata": {"currency": currency, "default_region": region},
        "scenarios": [
            {
                "id": "baseline",
                "resources": [
                    {"id": "blob-default", "category": "storage.blob", "metrics": {}},
                ],
            }
        ],
    }

    enriched = await enrich_plan_with_prices(plan, debug=False)
    blob = enriched["scenarios"][0]["resources"][0]

    assert blob["pricing_status"] == "estimated"
    assert blob["monthly_cost"] == pytest.approx(100 * 0.02, rel=1e-3)
