# azure_cost_architect/pricing/normalize.py
import re
from typing import Dict, Optional


def normalize_service_name(category: str, service_name: Optional[str]) -> str:
    """
    Normalize / infer Azure Retail 'serviceName' από λογικό category + υπάρχουσα τιμή.

    Σημαντικό:
    - Για App Service πρέπει να χρησιμοποιούμε **Azure App Service** (όχι "App Service"),
      γιατί έτσι εμφανίζεται στο Azure Retail Prices API.
    """
    cat = (category or "").lower()
    svc = (service_name or "").strip()

    # Αν ήδη είναι "σωστό" serviceName, το κρατάμε
    known = {
        "Virtual Machines",
        "SQL Database",
        "Storage",
        "Azure Cosmos DB",
        "Azure Cache for Redis",
        "Azure App Service",
        "Event Hubs",
        "Service Bus",
        "Event Grid",
        "Log Analytics",
        "Key Vault",
        "Application Gateway",
        "Azure Front Door",
        "Azure Front Door Service",
        "VPN Gateway",
        "ExpressRoute",
        "Bandwidth",
        "Azure Container Apps",
        "Azure Databricks",
        "Azure Data Factory",
        "Azure Data Explorer",
        "Microsoft Fabric",
        "Azure Database for PostgreSQL",
        "Azure Database for MySQL",
        "Azure Database for MariaDB",
        "Azure Firewall",
        "Load Balancer",
        "Virtual Network",
        "API Management",
        "Azure Bastion",
        "Backup",
        "Azure Site Recovery",
        "Public IP Addresses",
        "Azure Machine Learning",
        "Private Link",
    }
    if svc in known:
        return svc

    # Compute / Container
    if cat.startswith("compute.vm") or cat.startswith("compute.vmss") or cat.startswith("compute.aks"):
        return "Virtual Machines"
    if cat.startswith("appservice") or cat.startswith("function"):
        return "Azure App Service"
    if cat.startswith("containerapps"):
        return "Azure Container Apps"

    # Storage
    if cat.startswith("storage.blob") or cat.startswith("storage.files") or cat.startswith("storage.disk"):
        return "Storage"

    # Databases
    if cat.startswith("db.sql") or cat.startswith("db.sqlmi"):
        return "SQL Database"
    if cat.startswith("db.cosmos"):
        return "Azure Cosmos DB"
    if cat.startswith("db.postgres"):
        return "Azure Database for PostgreSQL"
    if cat.startswith("db.mysql"):
        return "Azure Database for MySQL"
    if cat.startswith("db.maria"):
        return "Azure Database for MariaDB"

    # Cache
    if cat.startswith("cache.redis"):
        return "Azure Cache for Redis"

    # Analytics
    if cat.startswith("analytics.databricks"):
        return "Azure Databricks"
    if cat.startswith("analytics.datafactory"):
        return "Azure Data Factory"
    if cat.startswith("analytics.dataexplorer"):
        return "Azure Data Explorer"
    if cat.startswith("analytics.fabric"):
        return "Microsoft Fabric"

    # Messaging & Integration
    if cat.startswith("messaging.eventhubs"):
        return "Event Hubs"
    if cat.startswith("messaging.servicebus"):
        return "Service Bus"
    if cat.startswith("messaging.eventgrid"):
        return "Event Grid"
    if "api management" in cat or cat.startswith("integration.apim"):
        return "API Management"
    
    # ML / AI
    if cat.startswith("ml.azureml") or cat.startswith("ml.aml"):
        return "Azure Machine Learning"

    # Monitoring / Security / Network / Backup / DR
    if cat.startswith("monitoring.loganalytics"):
        return "Log Analytics"
    if cat.startswith("security.keyvault"):
        return "Key Vault"
    if cat.startswith("backup.vault"):
        return "Backup"
    if cat.startswith("dr.asr"):
        return "Azure Site Recovery"
    if cat.startswith("network.vnet"):
        return "Virtual Network"
    if cat.startswith("network.appgw"):
        return "Application Gateway"
    if cat.startswith("network.lb"):
        return "Load Balancer"
    if cat.startswith("network.vpngw"):
        return "VPN Gateway"
    if cat.startswith("network.er"):
        return "ExpressRoute"
    if cat.startswith("network.nat") or cat.startswith("network.egress"):
        return "Bandwidth"
    if cat.startswith("network.firewall"):
        return "Azure Firewall"
    if cat.startswith("network.gateway"):
        return "Azure Front Door"
    if cat.startswith("network.bastion"):
        return "Azure Bastion"
    if cat.startswith("network.public_ip"):
        return "Public IP Addresses"
    if cat.startswith("network.private_endpoint"):
        return "Private Link"

    return svc or "Other"


def sku_keyword_match(requested_sku: str, item: Dict[str, str]) -> bool:
    """
    Lightweight keyword-based matching between a requested SKU hint and a Retail item.

    The goal is not strict equality but to ensure that high-signal hints such as
    reservation term (1y/3y), payg vs reservation, or blob tier (hot/cool/archive)
    are visible in the candidate's metadata (reservationTerm / productName / skuName).
    """

    hint = (requested_sku or "").lower()
    if not hint:
        return True

    # Only keep "safe" tokens we know how to interpret
    tokens = [
        t
        for t in re.split(r"[^a-z0-9]+", hint)
        if t
        in (
            "payg",
            "consumption",
            "reserved",
            "reservation",
            "1y",
            "1yr",
            "1year",
            "3y",
            "3yr",
            "3year",
            "hot",
            "cool",
            "archive",
        )
    ]

    if not tokens:
        return True

    text = " ".join(
        (
            (item.get("reservationTerm") or ""),
            (item.get("productName") or item.get("ProductName") or ""),
            (item.get("skuName") or ""),
            (item.get("armSkuName") or ""),
        )
    ).lower()

    # Normalise reservation tokens
    text = text.replace("one year", "1y").replace("three year", "3y")
    if "1 year" in text:
        text += " 1y"
    if "3 year" in text:
        text += " 3y"

    return all(tok in text for tok in tokens)
