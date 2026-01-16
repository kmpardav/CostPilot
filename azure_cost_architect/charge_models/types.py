from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class MetricSpec:
    """Specifies a metric required for deterministic pricing."""

    name: str
    type: str = "any"  # "int" | "float" | "str" | "bool" | "any"
    required: bool = True
    default: Optional[Any] = None
    description: str = ""


@dataclass(frozen=True)
class MetricIssue:
    key: str
    issue: str  # "missing" | "invalid"
    message: str


@dataclass(frozen=True)
class Blocker:
    scenario_id: str
    resource_id: str
    resource_name: str
    category: str
    missing: List[str]
    severity: str = "error"
    details: Optional[Dict[str, Any]] = None
