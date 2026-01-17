"""DeclarativeChargeModel.

Wraps a ChargeModelDefinition and exposes the existing BaseChargeModel interface.

NOTE: The current codebase's ChargeModel protocol / BaseChargeModel expects:
- required_metrics() -> Dict[str, MetricSpec]

Earlier iterations of this file returned a list and attempted to pass kwargs
into BaseChargeModel.__init__ (which does not exist), causing runtime failures.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict, List

from ..base import BaseChargeModel
from ..types import MetricSpec
from .schema import ChargeModelDefinition


class DeclarativeChargeModel(BaseChargeModel):
    def __init__(self, definition: ChargeModelDefinition):
        # BaseChargeModel does not implement __init__; do not pass kwargs.
        super().__init__()
        self.definition = definition
        # Keep something meaningful for debugging.
        self.category = (definition.category_prefixes[0] if definition.category_prefixes else "declarative")

    def required_metrics(self) -> Dict[str, MetricSpec]:
        out: Dict[str, MetricSpec] = {}
        for m in self.definition.required_metrics:
            out[m.key] = MetricSpec(
                name=m.key,
                type=m.kind,
                required=m.required,
                default=None,
                description=m.description,
            )
        return out

    # Optional helper for future: let declarative models emit pricing_components deterministically.
    # (Not currently used in the enrichment path unless you wire it in.)
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
