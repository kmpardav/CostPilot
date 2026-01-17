"""Declarative charge-model schema.

This is the first step toward a *Charge Model Registry* that can be extended
without writing Python per-service.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class MetricDef:
    key: str
    required: bool = True
    kind: str = "float"
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    description: str = ""


@dataclass(frozen=True)
class UnitsDef:
    kind: str = "quantity"  # quantity | fixed | metric
    value: Any = None
    metric_key: Optional[str] = None
    scale: Optional[float] = None
    units_override_kind: Optional[str] = None  # raw_count | billed_units | per_hour_units


@dataclass(frozen=True)
class ComponentDef:
    key: str
    label: str
    pricing_hints: Dict[str, Any] = field(default_factory=dict)
    hours_behavior: str = "inherit"  # inherit | ignore | multiply
    units: UnitsDef = field(default_factory=UnitsDef)


@dataclass(frozen=True)
class ChargeModelDefinition:
    id: str
    category_prefixes: List[str]
    description: str = ""
    required_metrics: List[MetricDef] = field(default_factory=list)
    components: List[ComponentDef] = field(default_factory=list)
    source_file: str = ""
