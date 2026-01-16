"""CostPilot regression harness (lightweight).

Dependency-free, designed to run locally or in CI.

Usage:
  python tools/regression_harness.py <run_dir>

Checks:
  1) Snapshot artifacts exist: plan.json, debug_enriched.json, report.md, missing_metrics_report.json.
  2) No cross-service catalog poisoning for service-scoped categories:
     for category 'service::<X>', chosen serviceName must equal X (when present).
  3) Estimated resources stay below a threshold (tune as needed).
  4) Basic AppGW meter sanity for componentized pricing (best-effort).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _fail(msg: str) -> None:
    print(f"FAIL: {msg}")
    raise SystemExit(2)


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python tools/regression_harness.py <run_dir>")
        raise SystemExit(1)

    run_dir = Path(sys.argv[1]).expanduser().resolve()
    if not run_dir.exists():
        _fail(f"run_dir does not exist: {run_dir}")

    required = [
        run_dir / "plan.json",
        run_dir / "debug_enriched.json",
        run_dir / "report.md",
        run_dir / "missing_metrics_report.json",
    ]
    for p in required:
        if not p.exists():
            _fail(f"missing required artifact: {p.name}")

    plan = _read_json(run_dir / "plan.json")

    # 2) No poisoning for service-scoped categories
    for scen in plan.get("scenarios") or []:
        for r in scen.get("resources") or []:
            cat = r.get("category") or ""
            if not (isinstance(cat, str) and cat.startswith("service::")):
                continue
            embedded = cat.split("::", 1)[1].strip()
            chosen = (r.get("pricing") or {}).get("chosen_item") or {}
            svc_name = chosen.get("serviceName") or chosen.get("service_name")
            if not svc_name:
                continue
            if str(svc_name).strip() != embedded:
                _fail(
                    f"service-scoped category poisoned: category='{cat}' priced via serviceName='{svc_name}' (resource_id={r.get('id')})"
                )

    # 3) Estimated threshold (conservative default)
    max_estimated = 10
    estimated = 0
    total = 0
    for scen in plan.get("scenarios") or []:
        for r in scen.get("resources") or []:
            total += 1
            pricing = r.get("pricing") or {}
            if pricing.get("status") == "estimated":
                estimated += 1
    if estimated > max_estimated:
        _fail(f"too many estimated resources: {estimated}/{total} (max {max_estimated})")

    # 4) Minimal AppGW component meter sanity (best-effort).
    for scen in plan.get("scenarios") or []:
        for r in scen.get("resources") or []:
            if (r.get("category") or "").lower() != "network.appgw":
                continue
            pcs = r.get("pricing_components") or []
            for pc in pcs:
                key = (pc.get("key") or "").lower()
                chosen = (pc.get("pricing") or {}).get("chosen_item") or {}
                meter = (chosen.get("meterName") or chosen.get("meter_name") or "").lower()
                if key == "gateway_hours" and meter and "gateway" not in meter:
                    _fail(f"appgw gateway_hours bound to unexpected meter: {meter}")
                if key == "capacity_units" and meter and "capacity" not in meter:
                    _fail(f"appgw capacity_units bound to unexpected meter: {meter}")

    print("OK")


if __name__ == "__main__":
    main()
