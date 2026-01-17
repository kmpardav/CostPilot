from azure_cost_architect.pricing.scoring import score_price_item


def test_scoring_prefers_nat_gateway_hours_over_data_processed():
    resource = {
        "category": "network.nat",
        "pricing_component_key": "nat_hours",
        "service_name": "NAT Gateway",
    }

    good = {
        "productName": "NAT Gateway",
        "skuName": "Standard",
        "meterName": "Gateway Hours",
        "unitOfMeasure": "1 Hour",
    }
    bad = {
        "productName": "NAT Gateway",
        "skuName": "Standard",
        "meterName": "Data Processed",
        "unitOfMeasure": "1 GB",
    }

    s_good = score_price_item(resource, good)
    s_bad = score_price_item(resource, bad)
    assert s_good > s_bad
    assert s_bad <= -900


def test_scoring_prefers_keyvault_operations_meter_for_transactions_component():
    resource = {
        "category": "security.keyvault",
        "pricing_component_key": "transactions",
        "service_name": "Key Vault",
    }

    good = {
        "productName": "Key Vault",
        "skuName": "Standard",
        "meterName": "Operations",
        "unitOfMeasure": "10,000 Operations",
    }
    bad = {
        "productName": "Key Vault",
        "skuName": "Standard",
        "meterName": "Certificate Renewal",
        "unitOfMeasure": "1",
    }

    s_good = score_price_item(resource, good)
    s_bad = score_price_item(resource, bad)
    assert s_good > s_bad
    assert s_bad <= -900
