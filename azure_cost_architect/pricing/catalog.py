# azure_cost_architect/pricing/catalog.py
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx

from .catalog_sources import CatalogSource, get_catalog_sources
from .retail_api import fetch_all_for_service
from .normalize import normalize_service_name
from ..config import RETAIL_API_URL

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


def _resolve_region(mode: str, requested_region: str) -> Tuple[str, str]:
    mode = (mode or "regional").lower()
    region = (requested_region or "").strip()

    if mode == "global":
        return "Global", "global"
    if mode == "empty":
        return "", "all"
    return region, region or "global"


def _existing_item_count(jsonl_path: str) -> Optional[int]:
    meta_path = _meta_path(jsonl_path)
    if os.path.exists(meta_path):
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            if "item_count" in meta:
                return int(meta.get("item_count") or 0)
        except Exception:
            pass

    if not os.path.exists(jsonl_path):
        return None

    try:
        with open(jsonl_path, "r", encoding="utf-8") as f:
            return sum(1 for _ in f if _.strip())
    except Exception:
        return None


def _discover_service_names_by_keyword(keyword: str, currency: str) -> List[str]:
    """Lightweight discovery query to locate serviceNames for a keyword."""

    if not keyword:
        return []

    filter_str = (
        f"startswith(tolower(productName),'%s') or startswith(tolower(meterName),'%s')"
        % (keyword.lower(), keyword.lower())
    )

    url = f"{RETAIL_API_URL}?$filter={filter_str}&$top=200"
    if currency and "currencyCode=" not in url:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}currencyCode={currency}"

    client = httpx.Client(timeout=httpx.Timeout(30.0, connect=10.0))
    try:
        resp = client.get(url)
        resp.raise_for_status()
        data = resp.json()
        items = data.get("Items") or data.get("items") or []
        return sorted({it.get("serviceName") for it in items if it.get("serviceName")})
    except Exception:
        return []
    finally:
        client.close()


def _discover_additional_sources(
    category: str, currency: str, attempted: set[str]
) -> List[CatalogSource]:
    cat = (category or "").lower()
    hints: List[str] = []
    for src in get_catalog_sources(cat):
        if src.product_name_hint:
            hints.append(src.product_name_hint)

    if cat.startswith("network.gateway") or cat.startswith("network.frontdoor"):
        hints.append("front door")
    if cat.startswith("cache.redis"):
        hints.append("redis")
    if cat.startswith("network.public_ip"):
        hints.append("ip address")
    if cat.startswith("network.private_endpoint"):
        hints.append("private endpoint")

    discovered: List[CatalogSource] = []
    for hint in hints:
        for svc in _discover_service_names_by_keyword(hint, currency):
            if not svc or svc in attempted:
                continue
            mode = "global" if cat.startswith("network.") else "regional"
            discovered.append(CatalogSource(svc, arm_region_mode=mode, product_name_hint=hint))
            attempted.add(svc)
    return discovered


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
    ensure_dir(base_dir)

    sources = get_catalog_sources(category)
    attempts: List[Tuple[str, str, int]] = []
    attempted_services: set[str] = set()

    chosen_fp: Optional[str] = None
    chosen_rows: Optional[List[Dict[str, Any]]] = None
    chosen_source: Optional[CatalogSource] = None
    chosen_region_label = region
    chosen_warning: Optional[str] = None
    existing_item_count: Optional[int] = None

    def _try_sources(candidates: List[CatalogSource]) -> bool:
        nonlocal chosen_fp, chosen_rows, chosen_source, chosen_region_label, chosen_warning, existing_item_count
        for src in candidates:
            attempted_services.add(src.service_name)
            query_region, region_label = _resolve_region(src.arm_region_mode, region)
            fp_local = _catalog_path(base_dir, src.service_name, region_label, currency)
            current_count = _existing_item_count(fp_local)
            if current_count and current_count > 0 and not refresh:
                chosen_fp = fp_local
                chosen_source = src
                chosen_region_label = region_label
                existing_item_count = current_count
                return True

            rows: List[Dict[str, Any]] = []
            warning: Optional[str] = None
            try:
                rows = fetch_all_for_service(
                    service_name=src.service_name,
                    region=query_region,
                    currency=currency,
                )
            except Exception as ex:
                warning = f"fetch_failed: {ex}"
                _LOGGER.error(
                    "Failed to fetch Retail prices for serviceName='%s', region='%s', currency='%s': %s",
                    src.service_name,
                    query_region,
                    currency,
                    ex,
                )
                rows = []

            attempts.append((src.service_name, query_region, len(rows)))
            if rows:
                chosen_fp = fp_local
                chosen_rows = rows
                chosen_source = src
                chosen_region_label = region_label
                chosen_warning = warning
                return True
        return False

    success = _try_sources(sources)
    if not success:
        discovered = _discover_additional_sources(category, currency, attempted_services)
        if discovered:
            success = _try_sources(discovered)

    if not success:
        # Fallback to first mapping for path consistency
        fallback_source = sources[0] if sources else CatalogSource(normalize_service_name(category, None))
        _, chosen_region_label = _resolve_region(fallback_source.arm_region_mode, region)
        chosen_fp = _catalog_path(base_dir, fallback_source.service_name, chosen_region_label, currency)
        chosen_source = fallback_source
        chosen_rows = chosen_rows or []

    if existing_item_count and chosen_fp:
        return chosen_fp

    rows_to_write = chosen_rows or []
    item_count = 0
    if chosen_fp:
        with open(chosen_fp, "w", encoding="utf-8") as f:
            for r in rows_to_write:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
                item_count += 1

    warning = chosen_warning
    if attempts and item_count > 0 and any(cnt == 0 for _, _, cnt in attempts):
        failed = ", ".join(f"{svc}@{reg}" for svc, reg, cnt in attempts if cnt == 0)
        warning = (warning + "; " if warning else "") + f"fallback_used:{failed}"

    if item_count == 0 and warning is None:
        warning = "no_items_returned"
        _LOGGER.warning(
            "Retail API returned 0 items for serviceName='%s' (category='%s', region='%s', currency='%s'). "
            "Tried sources: %s",
            chosen_source.service_name if chosen_source else normalize_service_name(category, None),
            category,
            chosen_region_label,
            currency,
            attempts,
        )
    else:
        _LOGGER.info(
            "Catalog built for serviceName='%s' (category='%s', region='%s', currency='%s') with %d items.",
            chosen_source.service_name if chosen_source else normalize_service_name(category, None),
            category,
            chosen_region_label,
            currency,
            item_count,
        )

    if chosen_fp:
        _write_meta(
            chosen_fp,
            service_name=chosen_source.service_name if chosen_source else normalize_service_name(category, None),
            category=category,
            region=chosen_region_label,
            currency=currency,
            item_count=item_count,
            warning=warning,
        )
        _LOGGER.info(
            "Catalog result: category='%s' -> serviceName='%s' (region_mode=%s region='%s') items=%s attempts=%s",
            category,
            chosen_source.service_name if chosen_source else normalize_service_name(category, None),
            chosen_source.arm_region_mode if chosen_source else "regional",
            chosen_region_label,
            item_count,
            attempts,
        )
        return chosen_fp

    return _catalog_path(base_dir, normalize_service_name(category, None), region, currency)


def load_catalog(base_dir: str, category: str, region: str, currency: str) -> List[Dict[str, Any]]:
    """
    Φορτώνει έναν local catalog για (category, region, currency).

    - Αν δεν υπάρχει JSONL αρχείο, θα προσπαθήσει να το δημιουργήσει με ensure_catalog().
    - Αν παρ' όλα αυτά δεν υπάρχει (π.χ. αποτυχία στο fetch), επιστρέφει empty list.
    """
    fp = ensure_catalog(base_dir, category, region, currency, refresh=False)

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
