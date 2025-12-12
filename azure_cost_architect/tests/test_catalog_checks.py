import json
from pathlib import Path

import pytest

from azure_cost_architect.pricing.catalog import _catalog_filename
from azure_cost_architect.pricing.normalize import normalize_service_name
from azure_cost_architect.pricing.catalog_checks import (
    assert_catalog_has_capacity_meters,
    assert_catalog_has_expected_tier,
)


def _write_catalog(tmp_path: Path, category: str, region: str, currency: str, rows: list[dict]):
    service_name = normalize_service_name(category, None)
    path = tmp_path / _catalog_filename(service_name, region, currency)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")
    return path


def test_assert_catalog_has_capacity_meters_pass(tmp_path: Path):
    region = "westeurope"
    currency = "EUR"
    _write_catalog(
        tmp_path,
        "storage",
        region,
        currency,
        [
            {
                "productName": "Blob Data Stored",
                "skuName": "Hot_LRS",
                "meterName": "Data Stored",
                "unitOfMeasure": "1 GB/Month",
            },
            {"productName": "Blob Ops", "meterName": "Data Scanned"},
        ],
    )

    assert_catalog_has_capacity_meters(
        category="storage",
        patterns=["Data", "Stored", "GB", "Month"],
        exclude=["Scanned"],
        catalog_dir=str(tmp_path),
        region=region,
        currency=currency,
    )


def test_assert_catalog_has_capacity_meters_fail(tmp_path: Path):
    region = "westeurope"
    currency = "EUR"
    _write_catalog(
        tmp_path,
        "storage",
        region,
        currency,
        [
            {"productName": "Blob Ops", "meterName": "Data Scanned", "unitOfMeasure": "1 GB"},
        ],
    )

    with pytest.raises(AssertionError):
        assert_catalog_has_capacity_meters(
            category="storage",
            patterns=["Data", "Stored"],
            exclude=["Scanned"],
            catalog_dir=str(tmp_path),
            region=region,
            currency=currency,
        )


def test_assert_catalog_has_expected_tier(tmp_path: Path):
    region = "westeurope"
    currency = "EUR"
    _write_catalog(
        tmp_path,
        "appservice",
        region,
        currency,
        [
            {"productName": "App Service", "skuName": "P1v3", "meterName": "App Service"},
            {"productName": "App Service", "skuName": "P0v3", "meterName": "App Service"},
        ],
    )

    assert_catalog_has_expected_tier(
        category="appservice",
        patterns=["P1v3"],
        fields=["skuName", "meterName", "productName"],
        catalog_dir=str(tmp_path),
        region=region,
        currency=currency,
    )

