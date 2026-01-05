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
    throughput_mbps = float(
        metrics.get("throughput_mbps")
        or metrics.get("throughput_mb_s")
        or metrics.get("throughput_mb_per_sec")
        or metrics.get("bandwidth_mbps")
        or 0.0
    )
    bandwidth_gbps = float(metrics.get("bandwidth_gbps") or 0.0)
    if bandwidth_gbps and throughput_mbps <= 0:
        throughput_mbps = bandwidth_gbps * 1000.0

    category = (resource.get("category") or "").lower()
    uom = (unit_of_measure or "").lower().strip()
    meter_text = " ".join(
        [
            (resource.get("product_name") or ""),
            (resource.get("meter_name") or ""),
            (resource.get("sku_name") or ""),
            uom,
        ]
    ).lower()

    def _blob_tier_metric(tier: str) -> float:
        for key in (
            f"{tier}_gb",
            f"{tier}_storage_gb",
            f"storage_{tier}_gb",
            f"blob_{tier}_gb",
        ):
            if key in metrics:
                try:
                    return float(metrics.get(key) or 0.0)
                except (TypeError, ValueError):
                    continue
        return 0.0

    # ---- Hour-based meters (compute, reserved, κλπ) ----
    if "hour" in uom:
        # SQL pricing frequently uses vCore-hour meters. In those cases, units must scale by vCores.
        vcores = (
            metrics.get("vcores")
            or metrics.get("vcore")
            or resource.get("vcores")
            or resource.get("vcore")
        )
        try:
            vcores_f = float(vcores) if vcores is not None else 0.0
        except (TypeError, ValueError):
            vcores_f = 0.0

        if vcores_f > 0 and "vcore" in meter_text and category.startswith("db.sql"):
            return qty * hours * vcores_f

        return qty * hours

    # ---- Functions execution time meters (GB-seconds) ----
    # Azure Functions consumption includes a meter for execution time, typically measured in GB-seconds.
    # We derive it from:
    #   executions_per_month * avg_duration_seconds * memory_gb
    if "gb" in uom and ("second" in uom or "sec" in uom) and (
        "gb-second" in uom or "gb second" in uom or "gbsec" in uom
    ):
        execs = float(
            metrics.get("executions_per_month", 0.0)
            or metrics.get("operations_per_month", 0.0)
            or 0.0
        )
        avg_ms = float(metrics.get("avg_duration_ms", 0.0) or 0.0)
        avg_s = avg_ms / 1000.0 if avg_ms > 0 else float(metrics.get("avg_duration_s", 0.0) or 0.0)
        if avg_s <= 0:
            avg_s = 0.5  # conservative default when not provided
        mem_mb = float(metrics.get("memory_mb", 0.0) or 0.0)
        mem_gb = (mem_mb / 1024.0) if mem_mb > 0 else float(metrics.get("memory_gb", 0.0) or 0.0)
        if mem_gb <= 0:
            mem_gb = 0.5  # conservative default 512MB
        gb_seconds = float(metrics.get("gb_seconds", 0.0) or 0.0)
        if gb_seconds > 0:
            return gb_seconds
        return max(execs, 0.0) * max(avg_s, 0.0) * max(mem_gb, 0.0)

    if "gb-month" in uom or ("gb" in uom and "month" in uom):
        return max(storage_gb, 0.0)

    # ---- GB-based meters (storage / egress) ----
    if "gb" in uom:
        base = egress_gb if category.startswith("network") else storage_gb

        if category.startswith("storage.blob"):
            tier = ""
            if "archive" in meter_text:
                tier = "archive"
            elif "cool" in meter_text:
                tier = "cool"
            elif "hot" in meter_text or "standard" in meter_text:
                tier = "hot"

            tier_value = _blob_tier_metric(tier) if tier else 0.0
            base = tier_value or base

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

    # ---- per node / resource ----
    if "node" in uom:
        # Defender for Cloud and some security meters are priced per protected node/resource.
        nodes = metrics.get("nodes") or metrics.get("protected_nodes") or None
        if nodes is not None:
            return float(nodes)
        return float(qty or 1)

    # ---- RU/s (Cosmos, κλπ) ----
    if "ru/s" in uom.replace(" ", ""):
        factor = 100.0 if "100" in uom else 1.0
        effective_ru = ru if ru > 0 else factor
        return (effective_ru / factor) * hours

    # ---- Mbps / Gbps or capacity units for networking ----
    if "mbps" in uom or "gbps" in uom or "capacity unit" in uom:
        base_tp = throughput_mbps if throughput_mbps > 0 else qty
        pack = 1.0
        m = re.search(r"([\d,.]+)\s*(g|m)bps", uom)
        if m:
            try:
                value = float(m.group(1).replace(",", ""))
                unit = m.group(2)
                if unit == "g":
                    value *= 1000.0
                if value > 0:
                    pack = value
            except ValueError:
                pack = 1.0
        return max(base_tp, 0.0) / pack

    # ---- Redis throughput (MB/s or throughput units) ----
    if category.startswith("cache.redis") and (
        "throughput" in uom or "mb/s" in uom or "mbps" in uom
    ):
        base_tp = throughput_mbps if throughput_mbps > 0 else 1.0
        m = re.search(r"([\d,.]+)\s*mb", uom)
        pack = 1.0
        if m:
            try:
                pack = float(m.group(1).replace(",", "")) or 1.0
            except ValueError:
                pack = 1.0
        return (base_tp / pack) * hours

    # ---- per million / 10k operations ----
    if "1m" in uom or "1 million" in uom or "1,000,000" in uom:
        return max(msgs, ops, 0.0) / 1_000_000.0
    if "10k" in uom or "10 k" in uom:
        return max(msgs, ops, 0.0) / 10_000.0
    if "operation" in uom or "request" in uom or "message" in uom:
        return max(msgs, ops, 0.0)

    # Public IP / Private Link – default to hourly if nothing else matched
    if category.startswith("network.public_ip") or category.startswith("network.private_endpoint"):
        return qty * hours

    # Fallback: απλά quantity
    return qty
