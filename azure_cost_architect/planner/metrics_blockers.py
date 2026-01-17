from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from typing import Any, Dict, List, Optional

from ..charge_models import Blocker, ChargeModelRegistry, build_default_registry


def collect_missing_metrics(
    plan: Dict[str, Any],
    *,
    registry: Optional[ChargeModelRegistry] = None,
) -> List[Blocker]:
    """Collect deterministic missing-metrics blockers using charge models.

    v1 policy: block only when we have a model for a category.
    """

    if registry is None:
        registry = build_default_registry()

    blockers: List[Blocker] = []
    for sc in (plan.get("scenarios") or []):
        sc_id = sc.get("id") or sc.get("label") or "scenario"
        for res in (sc.get("resources") or []):
            raw_category = res.get("category") or "other"
            category = raw_category

            model = registry.get(category)
            if model is None:
                model = registry.get(_normalize_category_for_blockers(category))
            if model is None:
                continue

            # Merge metrics with key top-level fields that the planner may store outside metrics.
            metrics = dict(res.get("metrics") or {})
            metrics["_category"] = category

            # VM: the plan often stores VM size under arm_sku_name / arm_sku_name_contains.
            if metrics.get("vm_size") in (None, ""):
                if res.get("arm_sku_name"):
                    metrics["vm_size"] = res.get("arm_sku_name")
                else:
                    contains = res.get("arm_sku_name_contains") or []
                    if isinstance(contains, list) and contains:
                        metrics["vm_size"] = contains[0]

            # Log Analytics: the plan already uses data_processed_gb_per_month frequently.
            # Keep it available for model aliasing.
            if metrics.get("data_processed_gb_per_month") is None and res.get("data_processed_gb_per_month") is not None:
                metrics["data_processed_gb_per_month"] = res.get("data_processed_gb_per_month")

            # NAT / hourly resources: planner commonly stores hours_per_month at top-level.
            if metrics.get("hours_per_month") is None and res.get("hours_per_month") is not None:
                metrics["hours_per_month"] = res.get("hours_per_month")

            issues = model.validate_metrics(metrics)
            missing = [i.key for i in issues if i.issue == "missing"]
            if missing:
                blockers.append(
                    Blocker(
                        scenario_id=str(sc_id),
                        resource_id=str(res.get("id") or ""),
                        resource_name=str(res.get("name") or ""),
                        category=str(category),
                        missing=sorted(set(missing)),
                        severity="error",
                        details={"model": model.__class__.__name__},
                    )
                )

    return blockers


def summarize_blockers(blockers: List[Blocker]) -> Dict[str, Any]:
    cat_counts = Counter(b.category for b in blockers)
    metric_counts = Counter(k for b in blockers for k in b.missing)

    return {
        "total": len(blockers),
        "by_category": dict(cat_counts.most_common()),
        "by_metric": dict(metric_counts.most_common()),
        "blockers": [asdict(b) for b in blockers],
    }


def _normalize_category_for_blockers(category: str) -> str:
    c = (category or "").strip().lower()
    # IMPORTANT: service::<name> pseudo-categories must not be normalized into real charge-model categories.
    if c.startswith("service::"):
        return category
    if c in ("vm", "compute", "compute.virtual_machine", "compute.virtualmachine"):
        return "compute.vm"
    if c in ("sql", "db.sql_database"):
        return "db.sql"
    if "sql managed instance" in c or c.endswith("sqlmi"):
        return "db.sqlmi"
    if "loganalytics" in c or "log analytics" in c:
        # support both spellings used by planner/category maps
        return "monitoring.loganalytics"
    if "azure monitor" in c:
        return category
    if "bandwidth" in c or "data transfer" in c:
        return "network.bandwidth"
    if "blob" in c and "storage" in c:
        return "storage.blob"
    return category
