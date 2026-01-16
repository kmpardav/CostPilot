from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .base import BaseChargeModel
from .types import MetricSpec


class BandwidthChargeModel(BaseChargeModel):
    """Bandwidth / data transfer out pricing (v1)."""

    category = "network.bandwidth"

    def required_metrics(self) -> Dict[str, MetricSpec]:
        return {
            "egress_gb_per_month": MetricSpec(
                "egress_gb_per_month",
                type="float",
                required=True,
                default=None,
                description="Outbound data transfer per month in GB",
            )
        }

    def candidate_filter(self, items: List[Dict[str, Any]], resource: Dict[str, Any]) -> List[Dict[str, Any]]:
        preferred: List[Dict[str, Any]] = []
        for it in items:
            blob = f"{it.get('meterName','')} {it.get('productName','')} {it.get('skuName','')}".lower()
            if "transfer" in blob and "out" in blob:
                preferred.append(it)
        return preferred or items

    def compute_units(self, resource: Dict[str, Any], item: Dict[str, Any]) -> Optional[Tuple[float, str]]:
        uom = (item.get("unitOfMeasure") or "").lower()
        if "gb" not in uom:
            return None
        eg = resource.get("egress_gb_per_month")
        if eg is None:
            eg = (resource.get("metrics") or {}).get("egress_gb_per_month")
        try:
            return (float(eg), "gb")
        except Exception:
            return None
