# azure_cost_architect/pricing/scoring.py
from typing import Dict, Any
import re
import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple

# Module-level logger
_LOGGER = logging.getLogger(__name__)


@dataclass
class CandidateSelection:
    score: int
    item: Dict[str, Any]
    matches_sku: bool
    price_type: str
    family_mismatch: bool



def _vm_family_from_arm(arm: str) -> str:
    """
    Extract a rough VM family letter from an ARM SKU, e.g. "Standard_D2s_v5" -> "d".
    Used only as a soft hint when scoring VM meters.
    """
    arm = (arm or "").lower()
    if not arm:
        return ""
    if "standard_" in arm:
        arm = arm.split("standard_", 1)[1]
    for ch in arm:
        if "a" <= ch <= "z":
            return ch
    return ""


# Order of App Service tiers for "upgrade/downgrade" logic
_APP_TIER_ORDER = {
    "free": 0,
    "shared": 1,
    "basic": 2,
    "standard": 3,
    "premium": 4,
    "premiumv2": 5,
    "premiumv3": 6,
    "isolated": 7,
    "functions": 3,  # approx. Standard
}


def _app_tier_from_notes_or_sku(arm_sku_name: str, notes: str) -> str:
    """
    Return a canonical tier keyword like "basic", "standard", "premium", "premiumv3" etc.
    Used to penalise large tier mismatches (e.g. requested S1, got P3mv3).
    """
    text = (arm_sku_name or "") + " " + (notes or "")
    text = text.lower()

    if "premiumv3" in text or "pv3" in text:
        return "premiumv3"
    if "premiumv2" in text or "pv2" in text:
        return "premiumv2"
    if "premium" in text:
        return "premium"
    if "isolated" in text or "i1" in text or "i2" in text:
        return "isolated"
    if "standard" in text or "s1" in text or "s2" in text or "s3" in text:
        return "standard"
    if "basic" in text or "b1" in text or "b2" in text:
        return "basic"
    if "free" in text:
        return "free"
    if "shared" in text:
        return "shared"

    # Fallback: strings with v2/v3/v4 but without explicit "premium" are treated as premium-ish
    if "pv" in text or "v3" in text or "v4" in text:
        return "premium"
    return ""


def _parse_app_size(sku_name: str) -> int:
    """
    Try to extract an App Service "size" from SKU name, e.g.
    P1v3 -> 1, P2v3 -> 2, P3mv4 -> 3, S1 -> 1, B2 -> 2.
    Used to penalise huge oversizing (P5mv4) when the user asked for P1v3.
    """
    sku = (sku_name or "").lower()
    m = re.search(r"[bpsfi](\d+)", sku)
    if not m:
        return 0
    try:
        return int(m.group(1))
    except ValueError:
        return 0


# -------------------------------------------------------------------------
# Extra helpers για storage / redis / backup / public IP
# -------------------------------------------------------------------------


def _looks_like_managed_disk(product_name: str, meter_name: str, sku_name: str) -> bool:
    """
    Heuristic: αν το meter μοιάζει με Managed Disk (Premium/Standard, Pxx/Exx κ.λπ.)
    θέλουμε να το ΑΠΟΦΥΓΟΥΜΕ όταν ψάχνουμε για Blob storage.
    """
    text = (product_name + " " + meter_name + " " + sku_name).lower()

    if "managed disk" in text:
        return True
    if "disk" in text and "blob" not in text:
        return True

    # Common premium SSD patterns: P10, P20, P80, E80 κ.λπ.
    if re.search(r"\bp\d{1,2}\b", text) or re.search(r"\be\d{1,2}\b", text):
        return True

    return False


def _looks_like_blob_data_meter(product_name: str, meter_name: str) -> bool:
    """
    Θέλουμε κάτι σαν:
    - Blob, Block Blob, Data Stored
    - Hot/Cool, LRS/GRS κ.λπ.
    """
    text = (product_name + " " + meter_name).lower()

    if "blob" not in text:
        return False

    keywords = ["data stored", "capacity", "gb stored", "tb stored"]
    if any(k in text for k in keywords):
        return True

    bad = ["snapshot", "backup", "managed disk"]
    if any(b in text for b in bad):
        return False

    return True


def _detect_redis_tier(text: str) -> str:
    """
    Basic / Standard / Premium / Enterprise detection για Redis.
    """
    text = (text or "").lower()
    if "enterprise" in text:
        return "enterprise"
    if "premium" in text:
        return "premium"
    if "standard" in text:
        return "standard"
    if "basic" in text:
        return "basic"
    return ""


def _detect_blob_tier(text: str) -> str:
    """
    Hot / Cool / Archive detection for blob meters & requested SKUs/notes.
    """
    text = (text or "").lower()
    if "archive" in text:
        return "archive"
    if "cool" in text:
        return "cool"
    if "hot" in text:
        return "hot"
    return ""


def _is_backup_vault_meter(product_name: str, meter_name: str) -> bool:
    """
    Εντοπισμός τυπικών Backup Vault meters (Protected Instances, Backup Storage κ.λπ.)
    """
    text = (product_name + " " + meter_name).lower()
    if "backup" in text and ("vault" in text or "protected instance" in text):
        return True
    if "backup" in text and "storage" in text:
        return True
    return False


def _is_log_analytics_capacity_meter(unit_of_measure: str) -> bool:
    """
    Προτιμάμε βάσει GB (Data Ingested) έναντι "per node" όταν υπάρχει.
    """
    uom = (unit_of_measure or "").lower()
    if "gb" in uom and "per gb" in uom:
        return True
    return False


def _is_public_ip_address_meter(product_name: str, meter_name: str) -> bool:
    """
    Χοντρικός εντοπισμός Public IP Address meters.
    """
    text = (product_name + " " + meter_name).lower()
    if "public ip" in text and "address" in text:
        return True
    return False


def _detect_redundancy(text: str) -> str:
    low = (text or "").lower()
    if "ragrs" in low or "ra-grs" in low:
        return "ragrs"
    if "gzrs" in low:
        return "gzrs"
    if "grs" in low:
        return "grs"
    if "zrs" in low:
        return "zrs"
    if "lrs" in low:
        return "lrs"
    return ""


# -------- safe getters (camelCase + snake_case) --------------------------------


def _g(it: Dict[str, Any], *keys: str) -> Any:
    for k in keys:
        if k in it and it[k] is not None:
            return it[k]
    return None


def _low(s: Any) -> str:
    return (s or "").lower()


def _normalize_sku_token(sku: str) -> str:
    """Normalize SKU tokens for comparison (e.g. "P1 v3" -> "p1v3")."""

    return re.sub(r"[^a-z0-9]", "", (sku or "").lower())


def _sku_family_token(norm_sku: str) -> str:
    """Extract a family signature from a normalized SKU (letter(s)+digits)."""

    m = re.match(r"([a-z]+\d+)", norm_sku)
    return m.group(1) if m else ""


def _candidate_matches_sku(requested_norm: str, item: Dict[str, Any]) -> Tuple[bool, bool]:
    """Return (matches, family_mismatch) for a candidate."""

    if not requested_norm:
        return True, False

    fields = [
        item.get("skuName"),
        item.get("armSkuName"),
        item.get("meterName"),
        item.get("productName") or item.get("ProductName"),
    ]
    norm_fields = [_normalize_sku_token(f or "") for f in fields]

    matches = any(
        nf == requested_norm or nf.startswith(requested_norm) for nf in norm_fields if nf
    )

    req_family = _sku_family_token(requested_norm)
    cand_family = ""
    for nf in norm_fields:
        if nf and not cand_family:
            cand_family = _sku_family_token(nf)
    family_mismatch = bool(req_family and cand_family and req_family != cand_family)

    return matches, family_mismatch


def select_best_candidate(
    resource: Dict[str, Any],
    candidates: List[Tuple[int, Dict[str, Any]]],
    env: str,
    billing_model: str,
    *,
    rejected_limit: int = 5,
) -> Dict[str, Any]:
    """
    Select the best candidate respecting strict priceType/SKU intent.

    Returns dict with status, chosen_item, warnings, and debug metadata.
    """

    preferred_price_type = "consumption" if env in ("prod", "production") and billing_model in ("payg", "pay-as-you-go", "pay_as_you_go") else ""

    requested_sku = (
        resource.get("arm_sku_name")
        or resource.get("armSkuName")
        or (resource.get("sku") or {}).get("armSkuName")
        or ""
    )
    requested_norm = _normalize_sku_token(requested_sku)

    annotated: List[CandidateSelection] = []
    for score, item in candidates:
        price_type = _low(_g(item, "type", "Type"))
        matches, family_mismatch = _candidate_matches_sku(requested_norm, item)
        annotated.append(
            CandidateSelection(
                score=score,
                item=item,
                matches_sku=matches and not family_mismatch,
                price_type=price_type,
                family_mismatch=family_mismatch,
            )
        )

    rejected: List[Dict[str, Any]] = []

    def _record_rejection(cand: CandidateSelection, reason: str) -> None:
        if len(rejected) >= rejected_limit:
            return
        rejected.append(
            {
                "skuName": cand.item.get("skuName"),
                "meterName": cand.item.get("meterName"),
                "productName": cand.item.get("ProductName") or cand.item.get("productName"),
                "armSkuName": cand.item.get("armSkuName"),
                "type": cand.item.get("type"),
                "reason": reason,
            }
        )

    matching = [cand for cand in annotated if cand.matches_sku]
    if requested_norm and not matching:
        for cand in annotated:
            reason = "family_mismatch" if cand.family_mismatch else "sku_not_matched"
            _record_rejection(cand, reason)
        return {
            "status": "unresolved",
            "chosen_item": None,
            "warnings": [],
            "requested_sku_normalized": requested_norm,
            "preferred_priceType": preferred_price_type or None,
            "fallback_priceType_used": False,
            "rejected_candidates": rejected,
        }

    chosen: Optional[CandidateSelection] = None
    fallback_used = False

    if preferred_price_type:
        primary = [cand for cand in matching if cand.price_type == preferred_price_type]
        if primary:
            chosen = primary[0]
        else:
            devtest = [cand for cand in matching if cand.price_type == "devtestconsumption"]
            if devtest:
                chosen = devtest[0]
                fallback_used = True
            elif matching:
                chosen = matching[0]
    else:
        if matching:
            chosen = matching[0]
        elif annotated:
            chosen = annotated[0]

    for cand in annotated:
        if cand is chosen:
            continue
        if requested_norm and not cand.matches_sku:
            reason = "family_mismatch" if cand.family_mismatch else "sku_not_matched"
        elif preferred_price_type and cand.price_type != preferred_price_type:
            if fallback_used and cand.price_type == "devtestconsumption":
                reason = "fallback_candidate"
            else:
                reason = "price_type_mismatch"
        else:
            reason = "lower_score"
        _record_rejection(cand, reason)

    warnings: List[str] = []
    if fallback_used and chosen:
        warnings.append(
            f"Fallback to DevTestConsumption for SKU '{requested_sku}' (selected {chosen.item.get('skuName')})"
        )
        _LOGGER.warning(
            "Fallback priceType used for category=%s requested_sku=%s chosen_sku=%s chosen_priceType=%s",
            resource.get("category"),
            requested_sku,
            chosen.item.get("skuName"),
            chosen.item.get("type"),
        )

    status = "unresolved" if chosen is None else ("fallback" if fallback_used else "matched")

    return {
        "status": status,
        "chosen_item": chosen.item if chosen else None,
        "chosen_score": chosen.score if chosen else None,
        "warnings": warnings,
        "requested_sku_normalized": requested_norm,
        "preferred_priceType": preferred_price_type or None,
        "fallback_priceType_used": fallback_used,
        "rejected_candidates": rejected,
    }


def score_price_item(resource: Dict[str, Any], item: Dict[str, Any], hours_prod: int = 730) -> int:
    """
    Υπολογίζει ένα "score" για ένα Retail item σε σχέση με το ζητούμενο resource.
    Υποστηρίζει items από Retail API (camelCase) ΚΑΙ από cache (snake_case).

    Στόχος:
    - Να πετάμε εντελώς λάθος meters (Zone Redundancy, SAP, Free promo κ.λπ.)
    - Να προτιμάμε General Purpose vs Hyperscale/BC όταν ζητείται GP
    - Να προτιμάμε λογικά vCore sizes (όχι 80 vCore add-ons)
    - Να βοηθάμε το sort στο enrich.py να επιλέξει λογικά SKUs.
    """
    score = 0

    meters = resource.get("metrics", {})
    redis_tp = float(
        meters.get("throughput_mbps")
        or meters.get("throughput_mb_s")
        or meters.get("throughput_mb_per_sec")
        or 0.0
    )
    usage = meters.get("baseline", {}).get("usage", {})  # reserved για μελλοντικά fine-tuning
    arm_sku_name = _low(resource.get("arm_sku_name"))
    category = _low(resource.get("category") or "other")
    service_name = _low(resource.get("service_name") or resource.get("serviceName") or "")
    criticality = _low(resource.get("criticality") or "prod")
    billing_model = _low(resource.get("billing_model") or resource.get("billingModel") or "")
    notes = _low(resource.get("notes") or "")
    requested_res_term = _low(resource.get("reservation_term") or resource.get("reservationTerm") or "")

    product_name = _low(_g(item, "product_name", "ProductName", "productName"))
    meter_name = _low(_g(item, "meter_name", "meterName"))
    sku_name = _low(_g(item, "sku_name", "skuName"))
    unit_price = float(_g(item, "unit_price", "unitPrice") or 0.0)
    unit_of_measure = _low(_g(item, "unit_of_measure", "unitOfMeasure"))
    price_type = _low(_g(item, "type", "Type"))  # "Consumption" / "Reservation" ή κενό
    reservation_term = _low(_g(item, "reservationTerm", "ReservationTerm"))

    text_all = product_name + " " + meter_name + " " + sku_name

    # Mild bonus if the requested SKU is referenced in product/meter names
    if arm_sku_name and arm_sku_name in text_all:
        score += 5

    # -------------------------------------------------------------------------
    # 0) Early “hard” guards
    # -------------------------------------------------------------------------

    # Blob: πέτα managed disks όταν ψάχνουμε για blob capacity
    if category.startswith("storage.blob"):
        if _looks_like_managed_disk(product_name, meter_name, sku_name):
            return -999

    # Bandwidth: πέτα "data transfer in" / China κ.λπ.
    if category.startswith("network.nat") or category.startswith("network.egress"):
        if "data transfer in" in text_all:
            return -999
        if "china" in text_all or "gov" in text_all:
            return -999

    # Log Analytics: πέτα free/promotional meters για prod
    if category.startswith("monitoring.loganalytics"):
        if "free" in text_all or "promotion" in text_all:
            if criticality in ("prod", "production"):
                return -999

    # SQL Server license / DevTest things – avoid if we haven't requested specifically
    if category.startswith("db.sql"):
        if "dev/test" in text_all or "dev test" in text_all:
            if criticality in ("prod", "production"):
                return -999

    # -------------------------------------------------------------------------
    # 1) Price type preference (Consumption vs Reservation)
    # -------------------------------------------------------------------------
    # Εδώ δεν "κλειδώνουμε" αλλά δίνουμε προτίμηση/ποινή.
    if billing_model == "reserved" or "reservation" in notes or "reserved" in notes:
        if price_type == "reservation":
            score += 30
            if "3" in requested_res_term and "3" in reservation_term:
                score += 10
            if "1" in requested_res_term and "1" in reservation_term:
                score += 8
        elif price_type == "consumption":
            score -= 15
    else:
        if price_type == "consumption":
            score += 10
        elif price_type == "reservation":
            score -= 10

    # -------------------------------------------------------------------------
    # 2) Βασική ευθυγράμμιση υπηρεσίας
    # -------------------------------------------------------------------------
    if service_name and service_name in product_name:
        score += 10

    # Προτιμάμε meters που είναι "consumption" vs άλλα (π.χ. "dev/test" κ.λπ.)
    if "consumption" in price_type:
        score += 5

    # -------------------------------------------------------------------------
    # 3) VM-specific heuristics
    # -------------------------------------------------------------------------
    if category.startswith("compute.vm") or category.startswith("compute.vmss"):
        vm_family = _vm_family_from_arm(arm_sku_name)
        text = product_name + " " + meter_name + " " + sku_name

        # Αν το item είναι για Windows VM αλλά εμείς ζητάμε Linux (ή αντίστροφα),
        # δώσε ένα penalty.
        is_windows = "windows" in text
        is_linux = "linux" in text

        if "windows" in notes and not is_windows:
            score -= 20
        if "linux" in notes and not is_linux:
            score -= 20

        # Αν το family ταιριάζει (π.χ. D-series), δώσε λίγο bonus.
        if vm_family and vm_family in text:
            score += 20

        # Penalty σε πολύ "exotic" SKUs (SAP, HB, HC κ.λπ.) αν δεν ζητήθηκαν
        if any(word in text for word in ("sap hana", "h-series", "hb", "hc", "nd", "nc")):
            if "sap" not in notes and "hpc" not in notes:
                score -= 80

        # Spot discount: μόνο αν το ζητάμε ρητά στα notes
        if "spot" in text:
            if "spot" in notes:
                score += 30
            else:
                score -= 30

        # "Promo" meters – συνήθως δεν είναι για μακροχρόνια χρήση
        if "promo" in text:
            score -= 20

    # -------------------------------------------------------------------------
    # 4) App Service Plan / Functions
    # -------------------------------------------------------------------------
    if category.startswith("appservice"):
        app_tier_req = _app_tier_from_notes_or_sku(arm_sku_name, notes)
        app_tier_cand = _app_tier_from_notes_or_sku(sku_name, product_name + " " + meter_name)

        # Tier alignment: αν το candidate tier είναι πολύ υψηλότερο, βάλε penalty
        if app_tier_req and app_tier_cand:
            order_req = _APP_TIER_ORDER.get(app_tier_req, 0)
            order_cand = _APP_TIER_ORDER.get(app_tier_cand, 0)
            diff = order_cand - order_req
            if diff > 0:
                # Oversized tier
                score -= 20 * diff
            elif diff < 0:
                # Downsize (π.χ. S αντί για P) – μικρό penalty, αλλά όχι τεράστιο
                score -= 5 * (-diff)

        # Size alignment P1 vs P3 κ.λπ.
        size_req = _parse_app_size(arm_sku_name)
        size_cand = _parse_app_size(sku_name)
        if size_req and size_cand:
            diff = size_cand - size_req
            if diff > 0:
                score -= 10 * diff
            elif diff < 0:
                score -= 5 * (-diff)

        # Αν το meter είναι ξεκάθαρα για "Isolated" plan αλλά δεν έχει ζητηθεί isolated, penalty
        if "isolated" in (product_name + " " + meter_name) and "isolated" not in notes:
            score -= 50

    # -------------------------------------------------------------------------
    # 5) SQL Database heuristics (βελτιωμένο)
    # -------------------------------------------------------------------------
    if category.startswith("db.sql"):
        text = (product_name + " " + meter_name).lower()

        # **ΠΟΤΕ** Free compute για prod DB → σκότωσέ το εντελώς.
        if "free" in meter_name or "free" in product_name:
            if criticality in ("prod", "production"):
                return -999

        # Αν δεν ζητήσαμε ρητά serverless, μην το προτιμάς.
        if "serverless" in text and "serverless" not in notes:
            score -= 60

        is_db_compute = (
            "vcore" in unit_of_measure or
            "vcpu" in unit_of_measure or
            "compute" in meter_name
        )
        is_backup = "backup" in text
        is_geo = "geo" in text and "replica" in text
        is_long_term_retention = "long-term retention" in text or "ltr" in text

        # Compute vs add-ons
        if is_db_compute:
            score += 40
        if is_backup:
            score -= 30
        if is_long_term_retention:
            score -= 40
        if is_geo:
            score -= 25

        # General Purpose / Hyperscale / Business Critical alignment
        has_gp = "general purpose" in text
        has_hyperscale = "hyperscale" in text
        has_bc = "business critical" in text or "bc gen5" in text

        if "gp_" in arm_sku_name or "general purpose" in notes:
            if has_gp:
                score += 30 + 70  # ισχυρή προτίμηση GP όταν ζητάμε GP
            if has_hyperscale and not has_gp:
                score -= 50
            if has_bc and not has_gp:
                score -= 50

        # Προσπάθεια ταιριάσματος vCores: π.χ. GP_Gen5_2 -> 2 vCores
        requested_vc = 0
        parts = arm_sku_name.split("_")
        if len(parts) >= 3 and parts[2].isdigit():
            requested_vc = int(parts[2])

        cand_vc = 0
        # προσπαθούμε να βρούμε π.χ. "2 vCore" ή "8 vCore" στο meter_name
        m = re.search(r"(\d+)\s*vcore", meter_name)
        if m:
            try:
                cand_vc = int(m.group(1))
            except ValueError:
                cand_vc = 0

        if requested_vc and cand_vc:
            diff = cand_vc - requested_vc
            if diff > 0:
                # υπερβολικό oversize: penalty
                score -= 7 * diff
            elif diff < 0:
                # πολύ λίγα vCores – μικρό penalty
                score -= 3 * (-diff)

        # Zone Redundancy add-ons – δεν τα θέλουμε αν δεν έχουν ζητηθεί
        if "zone redundancy" in text or "zone redundant" in text:
            if "zone redundant" not in notes and "zone redundancy" not in notes:
                score -= 150

        # General Purpose vs Hyperscale / Business Critical
        has_gp = "general purpose" in text
        has_hyperscale = "hyperscale" in text
        has_bc = "business critical" in text or "bc gen5" in text

        if "gp_" in arm_sku_name or "general purpose" in notes:
            if has_gp:
                score += 30 + 70  # ισχυρή προτίμηση GP όταν ζητάμε GP
            if has_hyperscale and not has_gp:
                score -= 50
            if has_bc and not has_gp:
                score -= 50

    # -------------------------------------------------------------------------
    # 6) Backup Vault / Site Recovery
    # -------------------------------------------------------------------------
    if category.startswith("backup.vault") or category.startswith("dr.asr"):
        if _is_backup_vault_meter(product_name, meter_name):
            score += 25
        else:
            score -= 10

    # -------------------------------------------------------------------------
    # 7) Blob Storage
    # -------------------------------------------------------------------------
    if category.startswith("storage.blob"):
        # 7.1 Αποφυγή managed disks (π.χ. Premium/Standard SSD) όταν ψάχνουμε capacity για Blob
        if _looks_like_managed_disk(product_name, meter_name, sku_name):
            score -= 300

        low_text = (product_name + " " + meter_name + " " + unit_of_measure).lower()

        req_tier = _detect_blob_tier(arm_sku_name + " " + notes)
        cand_tier = _detect_blob_tier(product_name + " " + meter_name + " " + sku_name)
        if req_tier and cand_tier:
            if req_tier == cand_tier:
                score += 25
            else:
                score -= 40
        elif req_tier and not cand_tier:
            score -= 10

        req_redundancy = _detect_redundancy(arm_sku_name + " " + notes)
        cand_redundancy = _detect_redundancy(product_name + " " + meter_name + " " + sku_name)
        if req_redundancy and cand_redundancy:
            if req_redundancy == cand_redundancy:
                score += 20
            else:
                score -= 35

        # 7.2 Capacity meters – "Data Stored", "capacity", GB/TB stored
        is_capacity = _looks_like_blob_data_meter(product_name, meter_name) or any(
            k in low_text for k in ("data stored", "capacity", "gb stored", "tb stored")
        )
        # 7.3 Early deletion / write-heavy / ops meters – θέλουμε να ΜΗΝ κερδίζουν έναντι capacity
        is_early_delete = "early deletion" in low_text or "early delete" in low_text
        is_write = ("write" in low_text or "data written" in low_text or "put" in low_text)
        is_ops = any(k in low_text for k in ("transaction", "transactions", "operation", "operations", "request", "requests"))
        is_snapshot_or_backup = "snapshot" in low_text or "backup" in low_text

        # Capacity: δυνατή θετική βαθμολογία
        if is_capacity:
            score += 60  # επιπλέον από τη βασική προτίμηση capacity
            # μικρό μπόνους αν το meter φαίνεται καθαρά capacity blob meter
            if _looks_like_blob_data_meter(product_name, meter_name):
                score += 20

        # Snapshot / backup: δεν είναι αυτό που θέλουμε για κύριο capacity
        if is_snapshot_or_backup:
            score -= 80

        # Early deletion ποινή – πολύ αρνητικό για να μην επιλεγεί ως κύριο meter
        if is_early_delete:
            score -= 150

        # Write / operations: να μη νικήσουν τα capacity meters
        if is_write or is_ops:
            score -= 40

        # Redundancy hints – μικρά μπόνους για LRS/GRS όταν ταιριάζουν στην περιγραφή
        if "lrs" in low_text or "locally redundant" in low_text:
            score += 5
        if "grs" in low_text or "geo-redundant" in low_text:
            score += 5

        # Προαιρετικό debug logging για να βλέπουμε γιατί κερδίζει το "Data Stored"
        if _LOGGER.isEnabledFor(logging.DEBUG):
            if is_capacity:
                _LOGGER.debug(
                    "[scoring][%s] Blob capacity meter candidate: product='%s', meter='%s', uom='%s', early_delete=%s, write=%s, ops=%s, snapshot/backup=%s, score=%s",
                    resource.get("id"),
                    product_name,
                    meter_name,
                    unit_of_measure,
                    is_early_delete,
                    is_write,
                    is_ops,
                    is_snapshot_or_backup,
                    score,
                )
            elif is_early_delete or is_write or is_ops or is_snapshot_or_backup:
                _LOGGER.debug(
                    "[scoring][%s] Blob non-capacity meter candidate: product='%s', meter='%s', uom='%s', early_delete=%s, write=%s, ops=%s, snapshot/backup=%s, score=%s",
                    resource.get("id"),
                    product_name,
                    meter_name,
                    unit_of_measure,
                    is_early_delete,
                    is_write,
                    is_ops,
                    is_snapshot_or_backup,
                    score,
                )

    # -------------------------------------------------------------------------
    # 8) Redis
    # -------------------------------------------------------------------------
    if category.startswith("cache.redis"):
        text = (product_name + " " + meter_name + " " + sku_name).lower()

        cand_tier = _detect_redis_tier(text)
        req_tier = _detect_redis_tier(arm_sku_name + " " + notes)

        if req_tier and cand_tier:
            tiers_order = {"basic": 1, "standard": 2, "premium": 3, "enterprise": 4}
            req_o = tiers_order.get(req_tier, 0)
            cand_o = tiers_order.get(cand_tier, 0)
            diff = cand_o - req_o
            if diff > 0:
                score -= 20 * diff  # oversize tier
            elif diff < 0:
                score -= 5 * (-diff)  # undersize tier

        # Basic detection for "Cache" vs "Ops"
        if "cache" in product_name and "throughput" not in meter_name:
            score += 20

        if redis_tp > 0:
            if "throughput" in meter_name:
                score += 25
            else:
                score -= 10

    # -------------------------------------------------------------------------
    # 8b) Application Gateway / Front Door / Traffic Manager
    # -------------------------------------------------------------------------
    if category.startswith("network.appgw") or category.startswith("network.gateway"):
        wants_waf = "waf" in arm_sku_name or "waf" in notes
        if wants_waf and "waf" in meter_name:
            score += 25
        if wants_waf and "basic" in meter_name:
            score -= 50
        if "v2" in arm_sku_name and "v2" in meter_name:
            score += 10
    if category.startswith("network.traffic_manager"):
        if "dns" in product_name or "traffic manager" in product_name:
            score += 10
    if category.startswith("network.egress") or category.startswith("network.nat"):
        if "data transfer out" in meter_name or "egress" in meter_name:
            score += 10

    # -------------------------------------------------------------------------
    # 9) Log Analytics
    # -------------------------------------------------------------------------
    if category.startswith("monitoring.loganalytics"):
        if _is_log_analytics_capacity_meter(unit_of_measure):
            score += 20
        else:
            score -= 5

    # -------------------------------------------------------------------------
    # Databricks (analytics.databricks) – προτίμηση σε DBU meters
    # -------------------------------------------------------------------------
    if category.startswith("analytics.databricks"):
        text = (product_name + " " + meter_name + " " + sku_name).lower()

        # Βασική ιδέα: για cost μοντέλο θέλουμε τυπικά DBU meters
        is_dbu = "dbu" in meter_name or "dbu" in product_name
        if is_dbu:
            score += 25

        # Προτιμάμε "Jobs Compute" ή "All-Purpose Compute" αν αναφέρονται
        if "jobs compute" in text:
            score += 10
        if "all-purpose compute" in text or "all purpose compute" in text:
            score += 10

        # Penalty σε promo / trial / dev-test meters
        if "promo" in text or "trial" in text or "dev/test" in text or "dev test" in text:
            score -= 20

        # Αν unit_price είναι εξωφρενικά υψηλό για DBU (safety guard)
        if unit_price > 20:
            score -= 30

    # -------------------------------------------------------------------------
    # Data Factory (analytics.datafactory) – προτίμηση σε pipeline activity / data movement
    # -------------------------------------------------------------------------
    if category.startswith("analytics.datafactory"):
        text = (product_name + " " + meter_name + " " + sku_name).lower()

        # Τυπικά θέλουμε Activity/Pipeline/Data Movement meters
        if "pipeline activity" in text or "pipeline activities" in text:
            score += 20
        if "data movement" in text or "copy activity" in text:
            score += 15

        # SSIS Integration Runtime vCore – ειδικό case: αν δεν μιλάς για SSIS στα notes, μικρό penalty
        if "ssis integration runtime" in text and "ssis" not in notes:
            score -= 10

        # Promo / trial / dev-test
        if "promo" in text or "trial" in text or "dev/test" in text or "dev test" in text:
            score -= 20

        # Αν unit_price είναι υπερβολικά υψηλό για ώρα, μικρό guard
        if unit_price > 15:
            score -= 20


    # -------------------------------------------------------------------------
    # 10) Public IP Addresses
    # -------------------------------------------------------------------------
    if category.startswith("network.public_ip"):
        if _is_public_ip_address_meter(product_name, meter_name):
            score += 15

    # -------------------------------------------------------------------------
    # 11) Detect Dev/Test promo meters
    # -------------------------------------------------------------------------
    if "dev/test" in text_all or "dev test" in text_all:
        if criticality in ("prod", "production"):
            score -= 40

    # -------------------------------------------------------------------------
    # 12) Simple usage hints (future extension)
    # -------------------------------------------------------------------------
    # Αν στο μέλλον θες να χρησιμοποιήσεις metrics["baseline"]["usage"], εδώ είναι
    # το hook για να βάλεις π.χ. penalties σε εξωφρενικά ακριβά add-ons.

    # -------------------------------------------------------------------------
    # 13) Γενικά heuristics + extra penalty για 0€ σε σοβαρές κατηγορίες
    # -------------------------------------------------------------------------
    if unit_price <= 0:
        score -= 10
        if category.startswith(("db.", "storage.", "network.", "cache.", "monitoring.")):
            # Δεν θέλουμε να κερδίζουν τα μηδενικά meters για primary pricing.
            score -= 100
    else:
        score += 5

    return score
