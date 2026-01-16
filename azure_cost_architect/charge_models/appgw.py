from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .base import BaseChargeModel


class AppGatewayChargeModel(BaseChargeModel):
    """Azure Application Gateway charge model (minimal v1).

    The core pricing issue for AppGW is *meter selection* because the service
    uses multiple meters (gateway hours + capacity units). This model only
    narrows candidates; units are typically supplied via pricing_components.
    """

    category = "network.appgw"

    def candidate_filter(
        self, items: List[Dict[str, Any]], resource: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        key = (
            resource.get("pricing_component_key")
            or resource.get("pricingComponentKey")
            or resource.get("pricing_component")
            or ""
        )
        key = str(key).strip().lower()

        def blob(it: Dict[str, Any]) -> str:
            return " ".join(
                [
                    str(it.get("meterName") or it.get("meter_name") or ""),
                    str(it.get("productName") or it.get("product_name") or ""),
                    str(it.get("skuName") or it.get("sku_name") or ""),
                    str(it.get("unitOfMeasure") or it.get("unit_of_measure") or ""),
                ]
            ).lower()

        if key == "gateway_hours":
            preferred = [it for it in items if "gateway" in blob(it) and "capacity" not in blob(it)]
            return preferred or items

        if key == "capacity_units":
            preferred = [it for it in items if "capacity" in blob(it) and "gateway" not in blob(it)]
            return preferred or items

        return items

    def compute_units(self, resource: Dict[str, Any], item: Dict[str, Any]) -> Optional[Tuple[float, str]]:
        # Typically provided via pricing_components.units_override; fallback to global unit logic.
        return None
