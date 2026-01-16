from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, Tuple

from .types import MetricIssue, MetricSpec


class ChargeModel(Protocol):
    """A service-specific pricing policy (incremental v1)."""

    category: str

    def required_metrics(self) -> Dict[str, MetricSpec]: ...

    def validate_metrics(self, metrics: Dict[str, Any]) -> List[MetricIssue]: ...

    def candidate_filter(self, items: List[Dict[str, Any]], resource: Dict[str, Any]) -> List[Dict[str, Any]]: ...

    def compute_units(self, resource: Dict[str, Any], item: Dict[str, Any]) -> Optional[Tuple[float, str]]: ...


class BaseChargeModel:
    """Default helpers for early-iteration charge models."""

    category: str = "other"

    def required_metrics(self) -> Dict[str, MetricSpec]:
        return {}

    def validate_metrics(self, metrics: Dict[str, Any]) -> List[MetricIssue]:
        issues: List[MetricIssue] = []
        for k, spec in (self.required_metrics() or {}).items():
            if spec.required and (metrics.get(k) is None or metrics.get(k) == ""):
                issues.append(MetricIssue(key=k, issue="missing", message=f"Missing required metric: {k}"))
        return issues

    def candidate_filter(self, items: List[Dict[str, Any]], resource: Dict[str, Any]) -> List[Dict[str, Any]]:
        return items

    def compute_units(self, resource: Dict[str, Any], item: Dict[str, Any]) -> Optional[Tuple[float, str]]:
        return None
