from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .base import BaseChargeModel
from .types import MetricSpec


class LogAnalyticsChargeModel(BaseChargeModel):
    """Log Analytics / Azure Monitor Logs (v1)."""

    category = "monitor.loganalytics"

    def required_metrics(self) -> Dict[str, MetricSpec]:
        return {
            "ingestion_gb_per_day": MetricSpec(
                "ingestion_gb_per_day",
                type="float",
                required=True,
                default=None,
                description="Average ingestion in GB/day",
            ),
            "days_per_month": MetricSpec(
                "days_per_month",
                type="int",
                required=False,
                default=30,
                description="Days per month used for normalization",
            ),
        }

    def candidate_filter(self, items: List[Dict[str, Any]], resource: Dict[str, Any]) -> List[Dict[str, Any]]:
        preferred: List[Dict[str, Any]] = []
        for it in items:
            blob = f"{it.get('meterName','')} {it.get('productName','')} {it.get('skuName','')}".lower()
            if "ingestion" in blob or "data" in blob:
                preferred.append(it)
        return preferred or items

    def compute_units(self, resource: Dict[str, Any], item: Dict[str, Any]) -> Optional[Tuple[float, str]]:
        uom = (item.get("unitOfMeasure") or "").lower()
        blob = f"{item.get('meterName','')} {item.get('productName','')}".lower()

        if "gb" not in uom:
            return None
        if "ingestion" not in blob and "data" not in blob:
            return None

        ing = resource.get("ingestion_gb_per_day")
        if ing is None:
            ing = (resource.get("metrics") or {}).get("ingestion_gb_per_day")
        days = resource.get("days_per_month")
        if days is None:
            days = (resource.get("metrics") or {}).get("days_per_month")
        if days is None:
            days = 30

        try:
            ing_f = float(ing)
            days_i = int(days)
        except Exception:
            return None

        # Normalize to "monthly GB" quantity for GB-based meters.
        return (ing_f * float(days_i), "gb")
