import re

from ..config import HOURS_DEVTEST, HOURS_PROD


def compute_units(resource: dict, unit_of_measure: str) -> float:
    qty = float(resource.get("quantity", 1.0))
    hours = float(resource.get("hours_per_month", 0.0) or 0.0)
    criticality = (resource.get("criticality") or "prod").lower()

    if hours <= 0:
        hours = HOURS_DEVTEST if criticality in ("devtest", "poc", "nonprod") else HOURS_PROD

    metrics = resource.get("metrics") or {}
    storage_gb = float(metrics.get("storage_gb", 0.0) or 0.0)
    egress_gb = float(metrics.get("egress_gb", 0.0) or 0.0)
    ops = float(metrics.get("operations_per_month", 0.0) or 0.0)
    msgs = float(metrics.get("messages_per_month", 0.0) or 0.0)
    ru = float(metrics.get("throughput_ru", 0.0) or 0.0)

    uom = (unit_of_measure or "").lower().strip()

    # ---- Hour-based meters (compute, reserved, κλπ) ----
    if "hour" in uom:
        return qty * hours

    # ---- GB-based meters (storage / egress) ----
    if "gb" in uom:
        base = egress_gb if (resource.get("category") or "").lower().startswith("network") else storage_gb
        base = base or storage_gb or egress_gb
        m = re.search(r"([\d,.]+)\s*gb", uom)
        if m:
            try:
                pack = float(m.group(1).replace(",", ""))
                if pack > 0:
                    return max(base, 0.0) / pack
            except ValueError:
                pass
        return max(base, 0.0)

    # ---- RU/s (Cosmos, κλπ) ----
    if "ru/s" in uom.replace(" ", ""):
        factor = 100.0 if "100" in uom else 1.0
        effective_ru = ru if ru > 0 else factor
        return (effective_ru / factor) * hours

    # ---- per million / 10k operations ----
    if "1m" in uom or "1 million" in uom or "1,000,000" in uom:
        return max(msgs, ops, 0.0) / 1_000_000.0
    if "10k" in uom or "10 k" in uom:
        return max(msgs, ops, 0.0) / 10_000.0
    if "operation" in uom or "request" in uom or "message" in uom:
        return max(msgs, ops, 0.0)

    # Fallback: απλά quantity
    return qty
