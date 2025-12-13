import json
from pathlib import Path

from azure_cost_architect.catalog_audit import build_catalog_audit_report
from azure_cost_architect.pricing.catalog import _catalog_filename


def _write_catalog(dir_path: Path, service_name: str, region: str, currency: str, rows: list[dict]):
    dir_path.mkdir(parents=True, exist_ok=True)
    fp = dir_path / _catalog_filename(service_name, region, currency)
    with fp.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")
    meta = fp.with_suffix(fp.suffix + ".meta")
    meta.write_text(
        json.dumps(
            {
                "serviceName": service_name,
                "category": "compute",
                "region": region,
                "currency": currency,
                "item_count": len(rows),
            }
        )
    )
    return fp


def _write_plan(run_dir: Path):
    run_dir.mkdir(parents=True, exist_ok=True)
    plan = {
        "scenarios": [
            {
                "scenario_id": "baseline",
                "resources": [
                    {
                        "id": "vm1",
                        "category": "compute.vm",
                        "region": "westeurope",
                        "currency_code": "EUR",
                        "arm_sku_name": "Standard_D2s_v5",
                        "billing_model": "payg",
                    }
                ],
            }
        ]
    }
    (run_dir / "plan.json").write_text(json.dumps(plan))


def test_build_catalog_audit_report(tmp_path: Path):
    catalog_dir = tmp_path / "catalog"
    runs_dir = tmp_path / "runs"

    _write_catalog(
        catalog_dir,
        "Virtual Machines",
        "westeurope",
        "EUR",
        [
            {
                "productName": "Virtual Machines",
                "skuName": "Standard_D2s_v5",
                "meterName": "D2s v5",
                "armSkuName": "Standard_D2s_v5",
                "unitPrice": 0.1,
                "unitOfMeasure": "1 Hour",
                "currencyCode": "EUR",
                "serviceName": "Virtual Machines",
                "armRegionName": "westeurope",
            }
        ],
    )

    _write_plan(runs_dir / "run1")

    report = build_catalog_audit_report(runs_dir, catalog_dir)

    assert "Catalog inventory by category" in report
    assert "Suggested mapping changes" in report
    assert "No empty or missing catalogs detected" in report
    assert "Run: run1" in report
    assert "Standard_D2s_v5" in report
    assert "Correct meter" in report

