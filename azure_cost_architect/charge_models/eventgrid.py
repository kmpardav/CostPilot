from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .base import BaseChargeModel


class EventGridChargeModel(BaseChargeModel):
    """Azure Event Grid charge model (minimal v1)."""

    category = "messaging.eventgrid"

    def candidate_filter(
        self, items: List[Dict[str, Any]], resource: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        def blob(it: Dict[str, Any]) -> str:
            return " ".join(
                [
                    str(it.get("serviceName") or it.get("service_name") or ""),
                    str(it.get("productName") or it.get("product_name") or ""),
                    str(it.get("skuName") or it.get("sku_name") or ""),
                    str(it.get("meterName") or it.get("meter_name") or ""),
                    str(it.get("unitOfMeasure") or it.get("unit_of_measure") or ""),
                ]
            ).lower()

        good = (
            "event grid",
            "operations",
            "events",
            "delivery",
        )
        bad = (
            "event hub",
            "service bus",
        )

        preferred: List[Dict[str, Any]] = []
        for it in items:
            b = blob(it)
            if any(g in b for g in good) and not any(x in b for x in bad):
                preferred.append(it)

        return preferred or items

    def compute_units(self, resource: Dict[str, Any], item: Dict[str, Any]) -> Optional[Tuple[float, str]]:
        return None
