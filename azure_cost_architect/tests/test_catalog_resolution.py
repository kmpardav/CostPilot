import json

from azure_cost_architect.pricing import catalog as catalog_mod


def _public_ip_meter(currency: str) -> dict:
    return {
        "serviceName": "Virtual Network",
        "armRegionName": "Global",
        "productName": "IP Addresses",
        "meterName": "Static Public IP",
        "skuName": "IP_Address",
        "unitPrice": 0.01,
        "unitOfMeasure": "1 Hour",
        "currencyCode": currency,
    }


def _redis_meter(currency: str) -> dict:
    return {
        "serviceName": "Azure Cache for Redis",
        "productName": "Redis Cache Hours",
        "meterName": "Redis Cache",
        "skuName": "P1",
        "unitPrice": 0.05,
        "unitOfMeasure": "1 Hour",
        "currencyCode": currency,
    }


def test_public_ip_uses_virtual_network_global(monkeypatch, tmp_path):
    currency = "EUR"
    calls: list[tuple[str, str]] = []

    def fake_fetch(service_name: str, region: str, currency: str, debug: bool = False):
        calls.append((service_name, region))
        if service_name == "Virtual Network" and region.lower() == "global":
            return [_public_ip_meter(currency)]
        return []

    monkeypatch.setattr(catalog_mod, "fetch_all_for_service", fake_fetch)

    path = catalog_mod.ensure_catalog(
        str(tmp_path), "network.public_ip", "westeurope", currency, refresh=True
    )
    items = catalog_mod.load_catalog(
        str(tmp_path), "network.public_ip", "westeurope", currency
    )

    assert calls and calls[0][0] == "Virtual Network"
    assert calls[0][1].lower() == "global"
    assert items

    with open(path + ".meta", "r", encoding="utf-8") as handle:
        meta = json.load(handle)
    assert meta.get("region") == "global"


def test_cache_redis_falls_back_without_region(monkeypatch, tmp_path):
    currency = "USD"
    calls: list[tuple[str, str]] = []

    def fake_fetch(service_name: str, region: str, currency: str, debug: bool = False):
        calls.append((service_name, region))
        if region == "":
            return [_redis_meter(currency)]
        return []

    monkeypatch.setattr(catalog_mod, "fetch_all_for_service", fake_fetch)

    path = catalog_mod.ensure_catalog(
        str(tmp_path), "cache.redis", "westeurope", currency, refresh=True
    )
    items = catalog_mod.load_catalog(str(tmp_path), "cache.redis", "westeurope", currency)

    assert len(calls) >= 2  # regional attempt + fallback without region
    assert any(call[1] == "" for call in calls)
    assert items

    with open(path + ".meta", "r", encoding="utf-8") as handle:
        meta = json.load(handle)
    assert meta.get("warning", "").startswith("fallback_used")
