from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .base import BaseChargeModel
from .types import MetricSpec


class StorageBlobChargeModel(BaseChargeModel):
    """Azure Storage Blob capacity pricing (v1)."""

    category = "storage.blob"

    def required_metrics(self) -> Dict[str, MetricSpec]:
        return {
            "storage_gb": MetricSpec("storage_gb", type="float", required=True, default=None, description="Storage capacity in GB"),
            "tier": MetricSpec("tier", type="str", required=False, default="Hot", description="Hot/Cool/Archive"),
            "redundancy": MetricSpec("redundancy", type="str", required=False, default="LRS", description="LRS/ZRS/GRS/RA-GRS"),
        }

    def candidate_filter(self, items: List[Dict[str, Any]], resource: Dict[str, Any]) -> List[Dict[str, Any]]:
        tier = (resource.get("tier") or (resource.get("metrics") or {}).get("tier") or "").strip()
        red = (resource.get("redundancy") or (resource.get("metrics") or {}).get("redundancy") or "").strip()
        tier_low = tier.lower() if tier else ""
        red_low = red.lower() if red else ""

        if not tier_low and not red_low:
            return items

        filtered: List[Dict[str, Any]] = []
        for it in items:
            blob = f"{it.get('productName','')} {it.get('skuName','')} {it.get('meterName','')}".lower()
            ok = True
            if tier_low:
                ok = ok and (tier_low in blob)
            if red_low:
                ok = ok and (red_low in blob)
            if ok:
                filtered.append(it)

        return filtered or items

    def compute_units(self, resource: Dict[str, Any], item: Dict[str, Any]) -> Optional[Tuple[float, str]]:
        uom = (item.get("unitOfMeasure") or "").lower()
        if "gb" in uom and "month" in uom:
            cap = resource.get("storage_gb")
            if cap is None:
                cap = (resource.get("metrics") or {}).get("storage_gb")
            try:
                return (float(cap), "gb-month")
            except Exception:
                return None
        if uom.strip() == "1 gb":
            cap = resource.get("storage_gb")
            if cap is None:
                cap = (resource.get("metrics") or {}).get("storage_gb")
            try:
                return (float(cap), "gb")
            except Exception:
                return None
        return None
