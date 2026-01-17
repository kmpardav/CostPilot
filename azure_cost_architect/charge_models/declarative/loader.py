"""Definition loader for declarative charge models.

Loads YAML/JSON definitions from azure_cost_architect/charge_models/definitions.

The loader is intentionally conservative:
- it validates required fields
- it normalizes the schema into dataclasses

If a definition is invalid, it raises ValueError with a readable message,
so CI/test runs fail fast.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List

import yaml

from .schema import ChargeModelDefinition, ComponentDef, MetricDef, UnitsDef


def _as_list(x: Any) -> List[Any]:
    if x is None:
        return []
    if isinstance(x, list):
        return x
    return [x]


def _require(obj: Dict[str, Any], key: str, *, ctx: str) -> Any:
    if key not in obj:
        raise ValueError(f"Missing required key '{key}' in {ctx}")
    return obj[key]


def _load_one(path: Path) -> Dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    if path.suffix.lower() in (".yaml", ".yml"):
        data = yaml.safe_load(raw) or {}
        if not isinstance(data, dict):
            raise ValueError(f"Top-level YAML must be a mapping in {path}")
        return data
    if path.suffix.lower() == ".json":
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError(f"Top-level JSON must be an object in {path}")
        return data
    raise ValueError(f"Unsupported definition file type: {path}")


def _parse_units(obj: Any, *, ctx: str) -> UnitsDef:
    if obj is None:
        return UnitsDef()
    if not isinstance(obj, dict):
        raise ValueError(f"units must be an object in {ctx}")
    return UnitsDef(
        kind=str(obj.get("kind") or "quantity").strip().lower(),
        value=obj.get("value"),
        metric_key=obj.get("metric_key") or obj.get("metricKey"),
        scale=obj.get("scale"),
        units_override_kind=(obj.get("units_override_kind") or obj.get("unitsKind") or obj.get("units_kind")),
    )


def _parse_metrics(items: Iterable[Any], *, ctx: str) -> List[MetricDef]:
    out: List[MetricDef] = []
    for i, it in enumerate(items):
        mctx = f"{ctx}.required_metrics[{i}]"
        if isinstance(it, str):
            out.append(MetricDef(key=it))
            continue
        if not isinstance(it, dict):
            raise ValueError(f"metric def must be string or object in {mctx}")
        key = str(_require(it, "key", ctx=mctx)).strip()
        if not key:
            raise ValueError(f"metric key cannot be empty in {mctx}")
        out.append(
            MetricDef(
                key=key,
                required=bool(it.get("required", True)),
                kind=str(it.get("kind") or "float").strip().lower(),
                min_value=it.get("min_value"),
                max_value=it.get("max_value"),
                description=str(it.get("description") or ""),
            )
        )
    return out


def _parse_components(items: Iterable[Any], *, ctx: str) -> List[ComponentDef]:
    out: List[ComponentDef] = []
    for i, it in enumerate(items):
        cctx = f"{ctx}.components[{i}]"
        if not isinstance(it, dict):
            raise ValueError(f"component must be an object in {cctx}")
        key = str(_require(it, "key", ctx=cctx)).strip()
        if not key:
            raise ValueError(f"component key cannot be empty in {cctx}")
        out.append(
            ComponentDef(
                key=key,
                label=str(it.get("label") or key),
                pricing_hints=dict(it.get("pricing_hints") or {}),
                hours_behavior=str(it.get("hours_behavior") or "inherit").strip().lower(),
                units=_parse_units(it.get("units"), ctx=cctx),
            )
        )
    return out


def load_definitions(definitions_dir: Path | None = None) -> List[ChargeModelDefinition]:
    base = definitions_dir or (Path(__file__).resolve().parents[1] / "definitions")
    if not base.exists():
        return []
    paths = sorted([p for p in base.iterdir() if p.is_file() and p.suffix.lower() in (".yaml", ".yml", ".json")])
    out: List[ChargeModelDefinition] = []
    for p in paths:
        data = _load_one(p)
        ctx = f"definition({p.name})"
        cm_id = str(_require(data, "id", ctx=ctx)).strip()
        prefixes = [str(x).strip() for x in _as_list(data.get("category_prefixes") or data.get("category_prefix") or [])]
        if not prefixes:
            raise ValueError(f"Missing category_prefixes in {ctx}")
        description = str(data.get("description") or "")
        required_metrics = _parse_metrics(_as_list(data.get("required_metrics")), ctx=ctx)
        components = _parse_components(_as_list(data.get("components")), ctx=ctx)
        out.append(
            ChargeModelDefinition(
                id=cm_id,
                category_prefixes=prefixes,
                description=description,
                required_metrics=required_metrics,
                components=components,
                source_file=p.name,
            )
        )
    return out
