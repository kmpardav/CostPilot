from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .base import BaseChargeModel
from .types import MetricSpec


class VMChargeModel(BaseChargeModel):
    """Compute VM pricing model (v1)."""

    category = "compute.vm"

    def required_metrics(self) -> Dict[str, MetricSpec]:
        # Allow either VM size OR vcpus. In practice, our plans usually have VM size
        # in arm_sku_name / arm_sku_name_contains, not under metrics.vcpus.
        return {
            "hours_per_month": MetricSpec("hours_per_month", type="float", required=False, default=730, description="Monthly hours"),
            "quantity": MetricSpec("quantity", type="float", required=False, default=1.0, description="VM count"),
            "vm_size": MetricSpec("vm_size", type="str", required=False, default=None, description="ARM VM size"),
            "vcpus": MetricSpec("vcpus", type="float", required=False, default=None, description="vCPU count"),
        }

    def validate_metrics(self, metrics: Dict[str, Any]):
        issues = super().validate_metrics(metrics)

        # Accept multiple aliases for VM size.
        vm_size = metrics.get("vm_size") or metrics.get("arm_sku_name")
        if not vm_size:
            contains = metrics.get("arm_sku_name_contains")
            if isinstance(contains, list) and contains:
                vm_size = contains[0]

        vcpus = metrics.get("vcpus") or metrics.get("vcpu") or metrics.get("cpu")

        # Require at least one of (vm_size, vcpus).
        if not vm_size and (vcpus is None or vcpus == ""):
            # Ensure we report vcpus as the missing key for clarity
            # (planner can satisfy this either by emitting vcpus or by providing vm_size).
            if not any(i.key == "vcpus" and i.issue == "missing" for i in issues):
                from .types import MetricIssue
                issues.append(MetricIssue(key="vcpus", issue="missing", message="Missing vcpus (or vm_size) for VM pricing"))

        # If vm_size exists, vcpus is not required.
        if vm_size:
            issues = [i for i in issues if i.key != "vcpus"]

        return issues

    def candidate_filter(self, items: List[Dict[str, Any]], resource: Dict[str, Any]) -> List[Dict[str, Any]]:
        preferred: List[Dict[str, Any]] = []
        for it in items:
            uom = (it.get("unitOfMeasure") or "").lower()
            if "hour" in uom or "hrs" in uom:
                preferred.append(it)
        return preferred or items

    def compute_units(self, resource: Dict[str, Any], item: Dict[str, Any]) -> Optional[Tuple[float, str]]:
        uom = (item.get("unitOfMeasure") or "").lower()
        if "hour" not in uom and "hrs" not in uom:
            return None

        metrics = resource.get("metrics") or {}
        qty = resource.get("quantity", metrics.get("quantity", 1.0))
        h = resource.get("hours_per_month", metrics.get("hours_per_month", 730))
        try:
            return (float(qty) * float(h), "vm-hours")
        except Exception:
            return None
