from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .base import BaseChargeModel


class FunctionsChargeModel(BaseChargeModel):
    """Azure Functions charge model (minimal v1).

    Azure Functions can be priced via executions and execution time (GB-s) on
    the Consumption plan, or via dedicated plan SKUs. This model primarily
    helps select meters that look like consumption metrics when the planner
    emitted consumption-style pricing_components.
    """

    category = "function"

    def candidate_filter(
        self, items: List[Dict[str, Any]], resource: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        key = resource.get("pricing_component_key") or resource.get("pricingComponentKey") or ""
        key = str(key).strip().lower()

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

        if key in {"executions", "execution_count", "requests"}:
            preferred = [it for it in items if "execution" in blob(it) or "request" in blob(it)]
            return preferred or items

        if key in {"execution_time", "gb_s", "gb-sec", "gb-s"}:
            preferred = [it for it in items if "gb" in blob(it) and ("sec" in blob(it) or "s" in blob(it))]
            return preferred or items

        preferred2 = [it for it in items if "function" in blob(it)]
        return preferred2 or items

    def compute_units(self, resource: Dict[str, Any], item: Dict[str, Any]) -> Optional[Tuple[float, str]]:
        return None
