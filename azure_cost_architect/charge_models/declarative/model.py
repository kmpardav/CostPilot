"""DeclarativeChargeModel.

Wraps a ChargeModelDefinition and exposes the standard BaseChargeModel interface.

This is meant to coexist with the current Python-per-service models.
Over time, services can be migrated one-by-one to declarative YAML.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict, List

from ..base import BaseChargeModel
from ..types import MetricSpec
from .schema import ChargeModelDefinition


class DeclarativeChargeModel(BaseChargeModel):
    def __init__(self, definition: ChargeModelDefinition):
        super().__init__(service=definition.id, friendly_name=definition.description or definition.id)
        self.definition = definition

    def required_metrics(self) -> List[MetricSpec]:
        out: List[MetricSpec] = []
        for m in self.definition.required_metrics:
            out.append(
                MetricSpec(
                    key=m.key,
                    kind=m.kind,
                    required=m.required,
                    min_value=m.min_value,
                    max_value=m.max_value,
                    description=m.description,
                )
            )
        return out

    def pricing_components(self, resource: Dict[str, Any]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for c in self.definition.components:
            out.append(
                {
                    "key": c.key,
                    "label": c.label,
                    "pricing_hints": dict(c.pricing_hints or {}),
                    "hours_behavior": c.hours_behavior,
                    "units": {
                        "kind": c.units.kind,
                        "value": c.units.value,
                        "metric_key": c.units.metric_key,
                        "scale": c.units.scale,
                        "units_override_kind": c.units.units_override_kind,
                    },
                    "debug": {
                        "source": "declarative",
                        "definition_id": self.definition.id,
                        "definition_file": self.definition.source_file,
                        "component": asdict(c),
                    },
                }
            )
        return out
