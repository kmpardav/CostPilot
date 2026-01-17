import re

from ..config import HOURS_DEVTEST, HOURS_PROD


_PACK_PATTERNS = [
    # common explicit forms
    re.compile(r"(?:per\s*)?(?:1\s*m|1\s*million|1,?000,?000)\b"),
    re.compile(r"(?:per\s*)?(?:100\s*k|100,?000)\b"),
    re.compile(r"(?:per\s*)?(?:10\s*k|10,?000)\b"),
    re.compile(r"(?:per\s*)?(?:1\s*k|1,?000)\b"),
]

# Generic pack token: 10M, 50M, 250K, 1.5M ...
_PACK_TOKEN_RE = re.compile(r"(?:per\s*)?(\d+(?:\.\d+)?)\s*([km])\b")

# Numeric pack token with commas: per 1,000 / 10,000 / 100,000 / 1,000,000 ...
_PACK_NUMERIC_RE = re.compile(r"(?:per\s*)?(\d{1,3}(?:,\d{3})+)\b")


def _parse_per_pack_divisor(uom: str, meter_text: str) -> float:
    """Return divisor for 'per N' meters (e.g., per 10K requests).

    Supports:
      - explicit forms: 1K/10K/100K/1M
      - compact tokens: 10M, 50M, 250K, 1.5M
      - comma numerics: 10,000 / 1,000,000

    Deterministic rule: planner metrics represent *raw* counts, so units are
    divided by the pack size when the meter is priced per-pack.
    """

    blob = f"{uom} {meter_text}".lower()

    # Fast path: classic explicit patterns.
    if _PACK_PATTERNS[0].search(blob):
        return 1_000_000.0
    if _PACK_PATTERNS[1].search(blob):
        return 100_000.0
    if _PACK_PATTERNS[2].search(blob):
        return 10_000.0
    if _PACK_PATTERNS[3].search(blob):
        return 1_000.0

    # Generic K/M tokens (10M, 250K, ...).
    m = _PACK_TOKEN_RE.search(blob)
    if m:
        try:
            n = float(m.group(1))
            suffix = m.group(2)
            mul = 1_000_000.0 if suffix == "m" else 1_000.0
            div = n * mul
            if div > 1.0:
                return div
        except Exception:
            pass

    # Numeric comma packs.
    m = _PACK_NUMERIC_RE.search(blob)
    if m:
        try:
            div = float(m.group(1).replace(",", ""))
            if div > 1.0:
                return div
        except Exception:
            pass

    return 1.0


def _monthly_count_for_meter(metrics: dict, meter_text: str) -> float:
    """Pick the right canonical monthly counter based on meter text."""
    mt = (meter_text or "").lower()

    def _f(key: str) -> float:
        try:
            return float(metrics.get(key) or 0.0)
        except (TypeError, ValueError):
            return 0.0

    if "query" in mt:
        return _f("queries_per_month") or _f("operations_per_month")
    if "transaction" in mt:
        return _f("transactions_per_month") or _f("operations_per_month")
    if "request" in mt:
        return _f("requests_per_month") or _f("operations_per_month")
    if "message" in mt:
        return _f("messages_per_month") or _f("operations_per_month")
    if "operation" in mt or "call" in mt:
        return _f("operations_per_month") or _f("requests_per_month") or _f(
            "transactions_per_month"
        )
    return (
        _f("operations_per_month")
        or _f("requests_per_month")
        or _f("transactions_per_month")
        or _f("queries_per_month")
        or _f("messages_per_month")
    )


def compute_units(resource: dict, unit_of_measure: str) -> float:
    # ------------------------------------------------------------------
    # If component expansion provided a deterministic units_override,
    # prefer it. Still apply pack divisors (1K/10K/1M) when the meter
    # is priced per N operations/requests/messages.
    # ------------------------------------------------------------------
    override = resource.get("units_override")
    override_kind = resource.get("units_override_kind") or resource.get("unitsKind") or "raw_count"
    override_kind = str(override_kind).strip().lower()
    if override is not None:
        try:
            base = float(override)
        except (TypeError, ValueError):
            base = None
        if base is not None:
            # If override already represents billed units (post-pack / post-normalization),
            # do NOT apply per-pack divisors. This prevents double-scaling.
            if override_kind in ("billed_units", "billed", "final"):
                return max(base, 0.0)
            uom_low = (unit_of_measure or "").lower().strip()
            meter_text = " ".join(
                [
                    (resource.get("product_name") or ""),
                    (resource.get("meter_name") or ""),
                    (resource.get("sku_name") or ""),
                    uom_low,
                ]
            ).lower()

            # per-pack meters (1K/10K/100K/1M) frequently encode only the pack size
            # in unitOfMeasure (e.g. "1M"), without mentioning operations/requests.
            # Deterministic assumption: planner metrics represent RAW counts.
            divisor = _parse_per_pack_divisor(uom_low, meter_text)
            if divisor > 1.0:
                return max(base, 0.0) / divisor

            # Heuristic: if unitOfMeasure mentions ops/req/msg/query/txn, still apply divisors.
            if any(
                tok in uom_low
                for tok in (
                    "operation",
                    "operations",
                    "request",
                    "requests",
                    "message",
                    "messages",
                    "query",
                    "queries",
                    "transaction",
                    "transactions",
                )
            ):
                divisor = _parse_per_pack_divisor(uom_low, meter_text)
                if divisor > 1.0:
                    return max(base, 0.0) / divisor
                return max(base, 0.0)

            if "gb" in uom_low:
                m = re.search(r"([\d,.]+)\s*gb", uom_low)
                if m:
                    try:
                        pack = float(m.group(1).replace(",", ""))
                        if pack > 0:
                            return max(base, 0.0) / pack
                    except ValueError:
                        pass
                return max(base, 0.0)

            # Hour-based meters: interpretation depends on override_kind.
            # - raw_count: planner already provided total hours (e.g., 730)
            # - per_hour_units: planner provided a per-hour quantity (e.g., CU/hour)
            #   and we must multiply by hours_per_month.
            if "hour" in uom_low or "/hour" in uom_low:
                if override_kind in ("per_hour_units", "per_hour", "rate_per_hour"):
                    try:
                        h = float(resource.get("hours_per_month") or 730.0)
                    except Exception:
                        h = 730.0
                    return max(base, 0.0) * max(h, 0.0)
                return max(base, 0.0)

            return max(base, 0.0)

    qty = float(resource.get("quantity", 1.0))
    hours = float(resource.get("hours_per_month", 0.0) or 0.0)
    criticality = (resource.get("criticality") or "prod").lower()

    if hours <= 0:
        hours = HOURS_DEVTEST if criticality in ("devtest", "poc", "nonprod") else HOURS_PROD

    metrics = resource.get("metrics") or {}
    storage_gb = float(metrics.get("storage_gb", 0.0) or 0.0)
    egress_gb = float(metrics.get("egress_gb_per_month") or metrics.get("egress_gb") or 0.0)
    data_processed_gb = float(
        metrics.get("data_processed_gb_per_month") or metrics.get("data_processed_gb") or 0.0
    )
    ingress_gb = float(metrics.get("ingress_gb_per_month") or metrics.get("ingress_gb") or 0.0)
    ops = float(metrics.get("operations_per_month", 0.0) or 0.0)
    msgs = float(metrics.get("messages_per_month", 0.0) or 0.0)
    requests = float(metrics.get("requests_per_month", 0.0) or 0.0)
    transactions = float(metrics.get("transactions_per_month", 0.0) or 0.0)
    queries = float(metrics.get("queries_per_month", 0.0) or 0.0)
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
        if data_processed_gb > 0 and (
            "processed" in meter_text
            or "data processed" in meter_text
            or ("data" in meter_text and category.startswith("network"))
        ):
            base = data_processed_gb

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

    # ---- per N operations/requests/messages (1K / 10K / 1M) ----
    if any(
        tok in uom
        for tok in (
            "operation",
            "operations",
            "request",
            "requests",
            "message",
            "messages",
            "query",
            "queries",
            "transaction",
            "transactions",
        )
    ):
        divisor = _parse_per_pack_divisor(uom, meter_text)
        count = _monthly_count_for_meter(metrics, meter_text)
        if divisor > 1.0:
            return max(count, 0.0) / divisor
        return max(count, 0.0)

    # ---- per-pack meters without explicit tokens in unitOfMeasure (e.g. unitOfMeasure == "1M") ----
    divisor = _parse_per_pack_divisor(uom, meter_text)
    if divisor > 1.0:
        count = _monthly_count_for_meter(metrics, meter_text)
        return max(count, 0.0) / divisor

    # Public IP / Private Link – default to hourly if nothing else matched
    if category.startswith("network.public_ip") or category.startswith("network.private_endpoint"):
        return qty * hours

    # Fallback: απλά quantity
    return qty
