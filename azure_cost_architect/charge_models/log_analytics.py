from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .base import BaseChargeModel
from .types import MetricIssue, MetricSpec


class LogAnalyticsChargeModel(BaseChargeModel):
    """Log Analytics / Azure Monitor Logs (v1)."""

    category = "monitor.loganalytics"

    def required_metrics(self) -> Dict[str, MetricSpec]:
        return {
            # We accept either:
            # - ingestion_gb_per_day  (explicit)
            # - data_processed_gb_per_month (already used by the planner/pricing_components)
            "ingestion_gb_per_day": MetricSpec("ingestion_gb_per_day", type="float", required=False, default=None, description="Average ingestion in GB/day"),
            "data_processed_gb_per_month": MetricSpec("data_processed_gb_per_month", type="float", required=False, default=None, description="Ingestion/processed data in GB/month"),
            "days_per_month": MetricSpec(
                "days_per_month",
                type="int",
                required=False,
                default=30,
                description="Days per month used for normalization",
            ),
        }

    def validate_metrics(self, metrics: Dict[str, Any]) -> List[MetricIssue]:
        issues = super().validate_metrics(metrics)

        ing_day = metrics.get("ingestion_gb_per_day")
        gb_month = metrics.get("data_processed_gb_per_month")

        # Require one of them
        if (ing_day is None or ing_day == "") and (gb_month is None or gb_month == ""):
            issues.append(
                MetricIssue(
                    key="ingestion_gb_per_day",
                    issue="missing",
                    message="Missing Log Analytics ingestion volume: provide ingestion_gb_per_day or data_processed_gb_per_month",
                )
            )

        return issues

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

        metrics = resource.get("metrics") or {}

        # Prefer monthly if present (planner already expresses it)
        gb_month = resource.get("data_processed_gb_per_month", metrics.get("data_processed_gb_per_month"))
        if gb_month not in (None, ""):
            try:
                return (float(gb_month), "gb")
            except Exception:
                return None

        ing = resource.get("ingestion_gb_per_day", metrics.get("ingestion_gb_per_day"))
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
