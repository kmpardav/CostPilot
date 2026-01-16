from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .base import BaseChargeModel
from .types import MetricIssue, MetricSpec


class SqlChargeModel(BaseChargeModel):
    """SQL Database / SQL Managed Instance pricing (v1).

    v1 behavior:
    - Enforces vcores (+ hours implied).
    - For SQL MI (db.sqlmi), also enforces storage_gb to avoid silent under-pricing.
    - Computes units for vCore-hour style meters when detectable.
    """

    category = "db.sql"

    def required_metrics(self) -> Dict[str, MetricSpec]:
        return {
            "vcores": MetricSpec("vcores", type="float", required=True, default=None, description="Requested vCores"),
            "hours_per_month": MetricSpec("hours_per_month", type="float", required=False, default=730, description="Monthly hours"),
            "storage_gb": MetricSpec("storage_gb", type="float", required=False, default=None, description="Allocated storage in GB"),
        }

    def validate_metrics(self, metrics: Dict[str, Any]) -> List[MetricIssue]:
        issues = super().validate_metrics(metrics)

        # Allow alias key vcore -> vcores
        if metrics.get("vcores") is None and metrics.get("vcore") is not None:
            # treat as present
            issues = [i for i in issues if i.key != "vcores"]

        cat = str(metrics.get("_category") or "").lower()
        if cat.startswith("db.sqlmi"):
            if metrics.get("storage_gb") in (None, ""):
                issues.append(
                    MetricIssue(
                        key="storage_gb",
                        issue="missing",
                        message="Missing required metric for SQL MI: storage_gb",
                    )
                )

        return issues

    def candidate_filter(self, items: List[Dict[str, Any]], resource: Dict[str, Any]) -> List[Dict[str, Any]]:
        preferred: List[Dict[str, Any]] = []
        for it in items:
            blob = f"{it.get('meterName','')} {it.get('productName','')} {it.get('skuName','')}".lower()
            if "vcore" in blob or "compute" in blob:
                preferred.append(it)
        return preferred or items

    def compute_units(self, resource: Dict[str, Any], item: Dict[str, Any]) -> Optional[Tuple[float, str]]:
        uom = (item.get("unitOfMeasure") or "").lower()
        blob = f"{item.get('meterName','')} {item.get('productName','')} {item.get('skuName','')}".lower()

        if "hour" not in uom and "hrs" not in uom:
            return None
        if "vcore" not in blob and "vcore" not in uom:
            return None

        metrics = resource.get("metrics") or {}
        v = resource.get("vcores", metrics.get("vcores", metrics.get("vcore")))
        h = resource.get("hours_per_month", metrics.get("hours_per_month", 730))
        try:
            return (float(v) * float(h), "vcore-hours")
        except Exception:
            return None
