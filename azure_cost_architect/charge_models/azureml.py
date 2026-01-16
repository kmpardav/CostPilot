from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .base import BaseChargeModel


class AzureMLChargeModel(BaseChargeModel):
    """Azure Machine Learning charge model (minimal v1)."""

    category = "ml.azureml"

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
            "machine learning",
            "azure ml",
            "azure machine learning",
            "compute",
            "training",
            "inference",
        )
        bad = (
            "cognitive",
            "search",
        )

        preferred: List[Dict[str, Any]] = []
        for it in items:
            b = blob(it)
            if any(g in b for g in good) and not any(x in b for x in bad):
                preferred.append(it)

        return preferred or items

    def compute_units(self, resource: Dict[str, Any], item: Dict[str, Any]) -> Optional[Tuple[float, str]]:
        return None
