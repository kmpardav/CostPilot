"""Catalog source mapping helpers.

This module defines the single source of truth for mapping logical CostPilot
categories to Azure Retail `serviceName` lookups and region handling rules.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List

from ..utils.knowledgepack import canonicalize_service_name, get_allowed_service_names


@dataclass(frozen=True)
class CatalogSource:
    service_name: str
    arm_region_mode: str = "regional"  # regional | global | empty | any
    product_name_hint: str | None = None
    sku_hint: str | None = None


def _legacy_service_name(category: str, service_name: str) -> str:
    """Fallback inference matching the historic normalize_service_name logic."""

    cat = (category or "").lower()
    svc = (service_name or "").strip()

    known = {
        "Virtual Machines",
        "SQL Database",
        "SQL Managed Instance",
        "Storage",
        "Azure Cosmos DB",
        "Redis Cache",
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
        "Traffic Manager",
        "Foundry Models",
        "Foundry Tools",
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
    if cat.startswith("db.sqlmi"):
        return "SQL Managed Instance"
    if cat.startswith("db.sql"):
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
        return "Redis Cache"

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
    if cat.startswith("network.nat"):
        return "NAT Gateway"
    if cat.startswith("network.egress"):
        return "Bandwidth"
    if cat.startswith("network.firewall"):
        return "Azure Firewall"
    if cat.startswith("network.gateway") or cat.startswith("network.frontdoor"):
        return "Azure Front Door"
    if cat.startswith("network.traffic_manager"):
        return "Traffic Manager"
    if cat.startswith("network.bastion"):
        return "Azure Bastion"
    if cat.startswith("network.public_ip"):
        return "Virtual Network"
    if cat.startswith("network.private_endpoint"):
        return "Virtual Network"

    return svc or "Other"


CATEGORY_CATALOG_SOURCES: Dict[str, List[CatalogSource]] = {
    # Compute / containers
    "compute.vm": [CatalogSource("Virtual Machines")],
    "compute.vmss": [CatalogSource("Virtual Machines")],
    "compute.aks": [CatalogSource("Virtual Machines")],
    "containerapps": [CatalogSource("Azure Container Apps")],
    # App Service
    "appservice": [CatalogSource("Azure App Service")],
    "appservice.plan": [CatalogSource("Azure App Service")],
    # Functions
    "function": [CatalogSource("Functions")],
    # Storage
    "storage.blob": [CatalogSource("Storage")],
    "storage.files": [CatalogSource("Storage")],
    "storage.disk": [CatalogSource("Storage")],
    # Databases
    "db.sql": [CatalogSource("SQL Database")],
    "db.sqlmi": [CatalogSource("SQL Managed Instance")],
    "db.cosmos": [CatalogSource("Azure Cosmos DB")],
    "db.postgres": [CatalogSource("Azure Database for PostgreSQL")],
    "db.mysql": [CatalogSource("Azure Database for MySQL")],
    "db.maria": [CatalogSource("Azure Database for MariaDB")],
    # Analytics
    "analytics.databricks": [CatalogSource("Azure Databricks")],
    "analytics.datafactory": [CatalogSource("Azure Data Factory")],
    "analytics.dataexplorer": [CatalogSource("Azure Data Explorer")],
    "analytics.fabric": [CatalogSource("Microsoft Fabric")],
    # Messaging & integration
    "messaging.eventhubs": [CatalogSource("Event Hubs")],
    "messaging.servicebus": [CatalogSource("Service Bus")],
    "messaging.eventgrid": [CatalogSource("Event Grid")],
    "integration.apim": [CatalogSource("API Management")],

    # (Optional) Security/Governance — will resolve only if in allowed serviceName universe
    "security.sentinel": [CatalogSource("Microsoft Sentinel")],
    "security.defender": [CatalogSource("Microsoft Defender for Cloud")],
    "governance.purview": [CatalogSource("Microsoft Purview")],
    # Security / monitoring / mgmt
    "monitoring.loganalytics": [CatalogSource("Log Analytics")],
    "security.keyvault": [CatalogSource("Key Vault")],
    "backup.vault": [CatalogSource("Backup")],
    "dr.asr": [CatalogSource("Azure Site Recovery")],
    # Networking
    "network.vnet": [CatalogSource("Virtual Network", arm_region_mode="global")],
    "network.appgw": [CatalogSource("Application Gateway")],
    "network.lb": [CatalogSource("Load Balancer", arm_region_mode="empty")],
    "network.vpngw": [CatalogSource("VPN Gateway")],
    "network.er": [CatalogSource("ExpressRoute")],
    "network.nat": [CatalogSource("NAT Gateway")],
    "network.egress": [CatalogSource("Bandwidth", arm_region_mode="empty")],
    "network.firewall": [CatalogSource("Azure Firewall")],
    "network.gateway": [CatalogSource("Azure Front Door", arm_region_mode="global", product_name_hint="front door")],
    "network.frontdoor": [CatalogSource("Azure Front Door", arm_region_mode="global", product_name_hint="front door")],
    "network.traffic_manager": [CatalogSource("Traffic Manager", arm_region_mode="global")],
    "network.bastion": [CatalogSource("Azure Bastion")],
    "network.public_ip": [
        CatalogSource("Virtual Network", arm_region_mode="global", product_name_hint="ip address"),
    ],
    "network.private_endpoint": [
        CatalogSource("Virtual Network", product_name_hint="private link"),
        CatalogSource("Virtual Network", arm_region_mode="global", product_name_hint="private link"),
    ],
    # Cache
    "cache.redis": [
        CatalogSource("Redis Cache"),
        CatalogSource("Redis Cache", arm_region_mode="empty", product_name_hint="redis"),
    ],
    # ML / AI
    "ai.openai": [
        # Prefer Foundry, but include Cognitive Services fallback for services that still
        # price under "Cognitive Services" (e.g., Azure OpenAI / token-based models).
        CatalogSource("Foundry Models", arm_region_mode="global", product_name_hint="openai"),
        CatalogSource("Foundry Tools", arm_region_mode="global", product_name_hint="openai"),
        CatalogSource("Cognitive Services", arm_region_mode="regional", product_name_hint="openai"),
        CatalogSource("Cognitive Services", arm_region_mode="empty", product_name_hint="openai"),
    ],
    "ml.azureml": [CatalogSource("Azure Machine Learning")],
}


def _matching_prefix(category: str, keys: Iterable[str]) -> str | None:
    cat = (category or "").lower()
    matches = [k for k in keys if cat.startswith(k)]
    if not matches:
        return None
    return max(matches, key=len)


def get_catalog_sources(category: str) -> List[CatalogSource]:
    """Return the ordered catalog sources for a given category."""

    # --------------------------------------------------------------------
    # Generic service-scoped category:
    #   category = "service::<Retail Prices API serviceName>"
    #
    # This unlocks full coverage for services present in taxonomy.json,
    # without needing to maintain CATEGORY_CATALOG_SOURCES mappings for
    # every single Azure service.
    # --------------------------------------------------------------------
    if isinstance(category, str) and category.startswith("service::"):
        service_name = category.split("::", 1)[1].strip()
        if not service_name:
            return []
        # Try regional first (armRegionName=<requested region>), then fallback to
        # empty/global (no armRegionName filter) because some services are global.
        return [
            CatalogSource(service_name, arm_region_mode="regional"),
            CatalogSource(service_name, arm_region_mode="empty"),
        ]

    prefix = _matching_prefix(category, CATEGORY_CATALOG_SOURCES.keys())
    sources: List[CatalogSource] = []
    if prefix:
        sources = CATEGORY_CATALOG_SOURCES[prefix]

    if not sources:
        inferred = _legacy_service_name(category, "")
        sources = [CatalogSource(inferred)]

    allowed = set(get_allowed_service_names())
    canonical_sources: List[CatalogSource] = []
    for src in sources:
        canonical = canonicalize_service_name(src.service_name)
        service_name = canonical.get("canonical") or src.service_name
        if not allowed and service_name == "UNKNOWN_SERVICE":
            service_name = src.service_name

        if allowed and service_name not in allowed:
            for suggestion in canonical.get("suggestions") or []:
                if suggestion in allowed:
                    service_name = suggestion
                    break

        if service_name == "UNKNOWN_SERVICE" or (allowed and service_name not in allowed):
            service_name = "UNKNOWN_SERVICE"

        canonical_sources.append(
            CatalogSource(
                service_name,
                arm_region_mode=src.arm_region_mode,
                product_name_hint=src.product_name_hint,
                sku_hint=src.sku_hint,
            )
        )
    return canonical_sources


__all__ = ["CatalogSource", "CATEGORY_CATALOG_SOURCES", "get_catalog_sources", "_legacy_service_name"]
