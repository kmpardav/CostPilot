# azure_cost_architect/pricing/catalog.py
from __future__ import annotations

import json
import os
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .retail_api import fetch_all_for_service
from .normalize import normalize_service_name

META_SUFFIX = ".meta"
_LOGGER = logging.getLogger(__name__)


def _slug(s: str) -> str:
    """
    Κάνει ένα "ασφαλές" slug από serviceName (χαμηλά, underscores).
    Π.χ. "Azure App Service" -> "azure_app_service"
    """
    s = (s or "").strip().lower().replace(" ", "_")
    return "".join(ch for ch in s if ch.isalnum() or ch in ("_", "-", "_"))


def _catalog_filename(service_name: str, region: str, currency: str) -> str:
    """
    Όνομα JSONL αρχείου για συγκεκριμένο service/region/currency.
    Δεν περιλαμβάνει τον κατάλογο, μόνο το filename.
    """
    return f"{_slug(service_name)}__{region.lower()}__{currency.upper()}.jsonl"


def _catalog_path(base_dir: str, service_name: str, region: str, currency: str) -> str:
    """
    Πλήρες path στο JSONL αρχείο του catalog.
    """
    return os.path.join(base_dir, _catalog_filename(service_name, region, currency))


def _meta_path(jsonl_path: str) -> str:
    """
    Πλήρες path στο .meta αρχείο (δίπλα στο JSONL).
    π.χ. storage__westeurope__EUR.jsonl.meta
    """
    return jsonl_path + META_SUFFIX


def ensure_dir(path: str) -> None:
    """
    Δημιουργεί τον κατάλογο αν δεν υπάρχει (και intermediate dirs).
    """
    os.makedirs(path, exist_ok=True)


def _write_meta(
    jsonl_path: str,
    *,
    service_name: str,
    category: Optional[str],
    region: str,
    currency: str,
    item_count: int,
    warning: Optional[str] = None,
) -> None:
    """
    Γράφει .meta αρχείο με βασικές πληροφορίες για τον catalog.
    """
    meta = {
        "serviceName": service_name,
        "category": category,
        "region": region,
        "currency": currency,
        "item_count": item_count,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "source": "azure-retail-prices-api",
        "file": os.path.basename(jsonl_path),
    }
    if warning:
        meta["warning"] = warning

    meta_path = _meta_path(jsonl_path)
    try:
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)
    except Exception:
        # Δεν θέλουμε αποτυχία meta να μπλοκάρει το κύριο flow
        _LOGGER.exception("Failed to write meta file '%s'.", meta_path)


def ensure_catalog(
    base_dir: str,
    category: str,
    region: str,
    currency: str,
    refresh: bool = False,
) -> str:
    """
    Δημιουργεί/ανανεώνει τοπικό catalog αρχείο για το συγκεκριμένο category.

    - Χρησιμοποιεί normalize_service_name για να βρει το σωστό serviceName.
    - Αν το αρχείο υπάρχει και refresh=False, το αφήνει ως έχει.
    - Αν δεν υπάρχει ή refresh=True, φέρνει ΟΛΑ τα items για το service από
      το Azure Retail Prices API και τα γράφει σε JSONL (ένας meter ανά γραμμή).
    - Γράφει επίσης ένα .meta αρχείο με βασικές πληροφορίες.

    Επιστρέφει πάντοτε το path του JSONL αρχείου (μπορεί να είναι κενό αν
    αποτύχει το fetch, αλλά το path θα είναι συνεπές).
    """
    service_name = normalize_service_name(category, None)
    ensure_dir(base_dir)
    fp = _catalog_path(base_dir, service_name, region, currency)

    if os.path.exists(fp) and not refresh:
        # Ήδη υπάρχει και δεν θέλουμε refresh -> επιστροφή
        return fp

    _LOGGER.info(
        "Fetching Azure Retail Prices for serviceName='%s', category='%s', region='%s', currency='%s'...",
        service_name,
        category,
        region,
        currency,
    )

    rows: List[Dict[str, Any]] = []
    warning: Optional[str] = None

    try:
        rows = fetch_all_for_service(
            service_name=service_name,
            region=region,
            currency=currency,
        )
    except Exception as ex:
        warning = f"fetch_failed: {ex}"
        _LOGGER.error(
            "Failed to fetch Retail prices for serviceName='%s', region='%s', currency='%s': %s",
            service_name,
            region,
            currency,
            ex,
        )
        rows = []

    item_count = 0
    with open(fp, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
            item_count += 1

    if item_count == 0 and warning is None:
        warning = "no_items_returned"
        _LOGGER.warning(
            "Retail API returned 0 items for serviceName='%s' (category='%s', region='%s', currency='%s'). "
            "Check query / filters (e.g. serviceName eq '%s').",
            service_name,
            category,
            region,
            currency,
            service_name,
        )
    else:
        _LOGGER.info(
            "Catalog built for serviceName='%s' (category='%s', region='%s', currency='%s') with %d items.",
            service_name,
            category,
            region,
            currency,
            item_count,
        )

    # Γράφουμε/ενημερώνουμε το .meta αρχείο
    _write_meta(
        fp,
        service_name=service_name,
        category=category,
        region=region,
        currency=currency,
        item_count=item_count,
        warning=warning,
    )

    return fp


def load_catalog(base_dir: str, category: str, region: str, currency: str) -> List[Dict[str, Any]]:
    """
    Φορτώνει έναν local catalog για (category, region, currency).

    - Αν δεν υπάρχει JSONL αρχείο, θα προσπαθήσει να το δημιουργήσει με ensure_catalog().
    - Αν παρ' όλα αυτά δεν υπάρχει (π.χ. αποτυχία στο fetch), επιστρέφει empty list.
    """
    service_name = normalize_service_name(category, None)
    fp = _catalog_path(base_dir, service_name, region, currency)

    if not os.path.exists(fp):
        # best-effort: try to create
        ensure_catalog(base_dir, category, region, currency, refresh=False)

    items: List[Dict[str, Any]] = []
    if os.path.exists(fp):
        with open(fp, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    items.append(json.loads(line))
                except json.JSONDecodeError:
                    # Αγνοούμε χαλασμένες γραμμές αντί να σκάμε
                    continue
    return items


def list_catalogs(base_dir: str) -> List[Dict[str, Any]]:
    """
    Επιστρέφει λίστα με όλες τις διαθέσιμες εγγραφές catalog
    στον δοθέντα κατάλογο.
    """
    if not os.path.isdir(base_dir):
        return []

    entries: List[Dict[str, Any]] = []
    for name in os.listdir(base_dir):
        if not name.endswith(".jsonl"):
            continue
        path = os.path.join(base_dir, name)
        if not os.path.isfile(path):
            continue

        # Αναλύουμε το filename: <slug>__<region>__<currency>.jsonl
        core = name[:-6]  # κόβουμε το ".jsonl"
        parts = core.split("__")
        if len(parts) != 3:
            # Δεν είναι στο αναμενόμενο format, το αγνοούμε
            continue

        service_slug, region, currency = parts[0], parts[1], parts[2]
        meta_path = _meta_path(path)
        meta: Dict[str, Any] = {}
        if os.path.exists(meta_path):
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
            except Exception:
                meta = {}

        # Αν δεν έχουμε item_count στο meta, μπορούμε να το υπολογίσουμε
        item_count = meta.get("item_count")
        if item_count is None:
            try:
                cnt = 0
                with open(path, "r", encoding="utf-8") as f:
                    for _ in f:
                        cnt += 1
                item_count = cnt
            except Exception:
                item_count = None

        entries.append(
            {
                "service_slug": service_slug,
                "serviceName": meta.get("serviceName"),
                "region": region,
                "currency": currency,
                "path": path,
                "item_count": item_count,
                "fetched_at": meta.get("fetched_at"),
                "warning": meta.get("warning"),
            }
        )

    # Για ευκολία, ταξινομούμε αλφαβητικά
    entries.sort(key=lambda e: (e["service_slug"], e["region"], e["currency"]))
    return entries


def get_catalog_info(
    base_dir: str,
    *,
    category: Optional[str] = None,
    service_name: Optional[str] = None,
    region: Optional[str] = None,
    currency: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Δίνει info για συγκεκριμένο catalog (αν υπάρχει).
    """
    if service_name:
        svc = service_name
    elif category:
        svc = normalize_service_name(category, None)
    else:
        # Δεν έχουμε αρκετές πληροφορίες για lookup
        return None

    slug = _slug(svc)

    if not os.path.isdir(base_dir):
        return None

    candidates: List[Dict[str, Any]] = []
    for entry in list_catalogs(base_dir):
        if entry["service_slug"] != slug:
            continue
        if region and entry["region"] != region.lower():
            continue
        if currency and entry["currency"] != currency.upper():
            continue
        candidates.append(entry)

    if not candidates:
        return None

    # Αν έχουμε περισσότερους από έναν, επέλεξε arbitrarily τον πρώτο
    return candidates[0]
