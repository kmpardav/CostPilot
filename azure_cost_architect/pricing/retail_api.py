# azure_cost_architect/pricing/retail_api.py
import asyncio
import random
import time
from typing import Any, Dict, List, Optional, Tuple, Set

import httpx
from urllib.parse import urlencode, urlparse, urlunparse, parse_qsl, quote
from rich.console import Console

from ..config import RETAIL_API_URL
from .http_policy import HttpRetryPolicy

console = Console()
_retry_policy = HttpRetryPolicy()

# --------------------------------------------------------------------
# Resilience helpers (429/5xx retries, exponential backoff)
# --------------------------------------------------------------------


def _is_transient_status(status_code: int) -> bool:
    return status_code in {408, 429, 500, 502, 503, 504}


def _parse_retry_after_seconds(headers: Dict[str, Any]) -> Optional[float]:
    """Return Retry-After seconds if present and parseable."""
    try:
        ra = headers.get("Retry-After") or headers.get("retry-after")
    except Exception:
        ra = None
    if ra is None:
        return None
    try:
        return float(str(ra).strip())
    except Exception:
        return None


def _sleep_seconds_with_jitter(seconds: float) -> None:
    seconds = max(0.0, float(seconds))
    jitter = random.uniform(0.0, min(1.0, seconds * 0.1))
    time.sleep(seconds + jitter)


async def _async_sleep_seconds_with_jitter(seconds: float) -> None:
    seconds = max(0.0, float(seconds))
    jitter = random.uniform(0.0, min(1.0, seconds * 0.1))
    await asyncio.sleep(seconds + jitter)


def _encode_filter_value(filter_str: str) -> str:
    """Encode $filter value safely while keeping OData punctuation readable."""
    return quote(filter_str, safe="()'$,=_-./:")


def _sync_get_json_with_retries(
    client: httpx.Client, url: str, *, max_attempts: int = 6
) -> Dict[str, Any]:
    last_exc: Optional[Exception] = None
    for attempt in range(1, max_attempts + 1):
        try:
            resp = client.get(url)
            if resp.status_code == 429:
                _retry_policy.wait(attempt - 1, _parse_retry_after_seconds(resp.headers))
                continue
            if _is_transient_status(resp.status_code):
                ra = _parse_retry_after_seconds(resp.headers) or 0.0
                backoff = min(30.0, (2 ** (attempt - 1)) * 0.5)
                _sleep_seconds_with_jitter(max(ra, backoff))
                continue
            resp.raise_for_status()
            return resp.json()
        except Exception as ex:
            last_exc = ex
            if attempt >= max_attempts:
                raise
            backoff = min(30.0, (2 ** (attempt - 1)) * 0.5)
            _sleep_seconds_with_jitter(backoff)
    raise last_exc or RuntimeError("Retail API request failed")


async def _async_get_json_with_retries(
    client: httpx.AsyncClient, url: str, *, max_attempts: int = 6
) -> Dict[str, Any]:
    last_exc: Optional[Exception] = None
    for attempt in range(1, max_attempts + 1):
        try:
            resp = await client.get(url)
            if resp.status_code == 429:
                await _retry_policy.wait_async(attempt - 1, _parse_retry_after_seconds(resp.headers))
                continue
            if _is_transient_status(resp.status_code):
                ra = _parse_retry_after_seconds(resp.headers) or 0.0
                backoff = min(30.0, (2 ** (attempt - 1)) * 0.5)
                await _async_sleep_seconds_with_jitter(max(ra, backoff))
                continue
            resp.raise_for_status()
            return resp.json()
        except Exception as ex:
            last_exc = ex
            if attempt >= max_attempts:
                raise
            backoff = min(30.0, (2 ** (attempt - 1)) * 0.5)
            await _async_sleep_seconds_with_jitter(backoff)
    raise last_exc or RuntimeError("Retail API request failed")


def _sanitize_top_param(url: str) -> str:
    """Clamp $top to the API-supported 1..1000 range and avoid non-positive values."""

    if not url:
        return url

    parsed = urlparse(url)
    query_pairs = []
    has_top = False
    for key, val in parse_qsl(parsed.query, keep_blank_values=True):
        if key.lower() == "$top":
            has_top = True
            try:
                top_int = int(val)
            except Exception:
                top_int = 100
            top_int = max(1, min(1000, top_int))
            val = str(top_int)
        query_pairs.append((key, val))

    if has_top:
        parsed = parsed._replace(query=urlencode(query_pairs, doseq=True))
        return urlunparse(parsed)
    return url


# --------------------------------------------------------------------
# Async helper – generic Retail API query with pagination (by filter)
# --------------------------------------------------------------------
async def query_azure_retail(
    filter_str: str,
    currency: Optional[str],
    debug_label: str = "",
    max_pages: int = 1,
    debug: bool = False,
) -> List[Dict[str, Any]]:
    """
    Κάνει async κλήση στο Azure Retail Prices API με $filter και προαιρετικό currency,
    με πλήρη διαχείριση NextPageLink.

    Χρησιμοποιείται κυρίως σε παλιό κώδικα (enrich παλιάς έκδοσης).
    Στη νέα φιλοσοφία βασιζόμαστε σε fetch_all_for_service για catalogs.
    """
    if not filter_str:
        return []

    # Χτίζουμε URL. Κάνουμε safe encoding του $filter value.
    url = f"{RETAIL_API_URL}?$filter={_encode_filter_value(filter_str)}"
    if currency:
        # Αν δεν έχει currencyCode, το βάζουμε.
        if "currencyCode=" not in url:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}currencyCode={currency}"

    items: List[Dict[str, Any]] = []
    page = 0

    timeout = httpx.Timeout(60.0, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        while url and page < max_pages:
            page += 1
            if debug:
                console.print(
                    f"[cyan]query_azure_retail[{debug_label}]: page {page}, url={url}[/cyan]"
                )
            url = _sanitize_top_param(url)
            data = await _async_get_json_with_retries(client, url)
            page_items = data.get("Items") or data.get("items") or []
            items.extend(page_items)

            next_url = data.get("NextPageLink") or data.get("nextPageLink")
            next_url = _sanitize_top_param(next_url)
            if next_url and currency and "currencyCode=" not in next_url:
                sep = "&" if "?" in next_url else "?"
                next_url = f"{next_url}{sep}currencyCode={currency}"
            url = next_url

    if debug:
        console.print(
            f"[cyan]query_azure_retail[{debug_label}]: total {len(items)} items[/cyan]"
        )

    return items


# --------------------------------------------------------------------
# Optional helper – candidates από πολλαπλά φίλτρα (συμβατότητα)
# --------------------------------------------------------------------
async def query_azure_retail_candidates(
    resource: Dict[str, Any],
    currency: Optional[str],
    debug_label: str = "",
    max_pages: int = 2,
    debug: bool = False,
) -> List[Dict[str, Any]]:
    """
    Προσπαθεί να βρει candidates items για ένα resource με λίγο πιο χαλαρά κριτήρια.
    Χρησιμοποιείται κυρίως από παλιότερο κώδικα. Στη νέα λογική catalogs-first
    δεν βασιζόμαστε σε αυτό, αλλά το κρατάμε για συμβατότητα.

    Η προσέγγιση εδώ είναι "best-effort" – αν δεν βρεθεί τίποτα, γυρίζει [].
    """
    service_name = (resource.get("service_name") or resource.get("serviceName") or "").strip()
    region = (resource.get("region") or resource.get("armRegionName") or "").strip()
    category = (resource.get("category") or "").lower()

    if not service_name:
        return []

    filters: List[str] = []

    # Βασικό φίλτρο: serviceName + region (αν υπάρχει)
    if region:
        filters.append(
            f"serviceName eq '{service_name}' and armRegionName eq '{region}'"
        )
    else:
        filters.append(f"serviceName eq '{service_name}'")

    # Για κάποια categories, προσθέτουμε 1-2 έξτρα φίλτρα για fallback
    if category.startswith("storage.blob"):
        filters.append(f"serviceName eq '{service_name}' and skuName ne 'Premium_LRS'")

    all_items: List[Dict[str, Any]] = []
    seen: Set[Tuple[str, str, str, str, str]] = set()

    for f in filters:
        items = await query_azure_retail(
            filter_str=f,
            currency=currency,
            debug_label=f"{debug_label}:{f}",
            max_pages=max_pages,
            debug=debug,
        )
        for it in items:
            arm = it.get("armSkuName") or ""
            meter = it.get("meterName") or ""
            sku = it.get("skuName") or ""
            prod = it.get("productName") or it.get("ProductName") or ""
            typ = it.get("type") or it.get("Type") or ""
            key = (str(arm), str(meter), str(sku), str(prod), str(typ))
            if key in seen:
                continue
            seen.add(key)
            all_items.append(it)

    if debug:
        console.print(
            f"[cyan]query_azure_retail_candidates[{debug_label}]: merged "
            f"{len(all_items)} unique items[/cyan]"
        )

    return all_items


# --------------------------------------------------------------------
# NEW: fetch_all_for_service – πλήρης κατάλογος ανά service/region/currency
# --------------------------------------------------------------------
def fetch_all_for_service(
    service_name: str,
    region: str,
    currency: str,
    debug: bool = False,
    trace=None,
) -> List[Dict[str, Any]]:
    """
    Φέρνει ΟΛΑ τα Retail items για ένα συγκεκριμένο serviceName + region + currency.

    - Χρησιμοποιείται από το pricing.catalog.ensure_catalog για να χτίσει
      JSONL τοπικούς καταλόγους (ένας κατάλογος ανά service/region/currency).
    - Είναι SYNC function (όχι async), γιατί οι κατάλογοι χτίζονται εκτός
      async loop και συνήθως σporadically, όχι ανά resource.
    """
    if not service_name:
        return []

    # Χτίζουμε βασικό φίλτρο: serviceName (& region αν υπάρχει).
    if region:
        filter_str = f"serviceName eq '{service_name}' and armRegionName eq '{region}'"
    else:
        filter_str = f"serviceName eq '{service_name}'"

    # Πλήρες URL με φίλτρο (safe encoding).
    url = f"{RETAIL_API_URL}?$filter={_encode_filter_value(filter_str)}"

    # Προσθέτουμε currencyCode αν δεν υπάρχει ήδη.
    if currency:
        if "currencyCode=" not in url:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}currencyCode={currency}"

    timeout = httpx.Timeout(60.0, connect=10.0)
    client = httpx.Client(timeout=timeout)
    items: List[Dict[str, Any]] = []
    page = 0
    first_url = url

    if debug:
        console.print(
            f"[cyan]fetch_all_for_service: service='{service_name}', "
            f"region='{region}', currency='{currency}'[/cyan]"
        )

    try:
        while url:
            page += 1
            if debug:
                console.print(
                    f"[cyan]fetch_all_for_service: page {page}, url={url}[/cyan]"
                )

            url = _sanitize_top_param(url)
            data = _sync_get_json_with_retries(client, url)

            page_items = data.get("Items") or data.get("items") or []
            items.extend(page_items)

            next_url = data.get("NextPageLink") or data.get("nextPageLink")
            next_url = _sanitize_top_param(next_url) if next_url else None
            if next_url and currency and "currencyCode=" not in next_url:
                sep = "&" if "?" in next_url else "?"
                next_url = f"{next_url}{sep}currencyCode={currency}"
            url = next_url
    finally:
        client.close()

    # Προαιρετικό dedup (μερικές φορές υπάρχουν διπλά meters).
    out: List[Dict[str, Any]] = []
    seen: Set[Tuple[str, str, str, str, str]] = set()
    for it in items:
        arm = it.get("armSkuName") or ""
        meter = it.get("meterName") or ""
        sku = it.get("skuName") or ""
        prod = it.get("productName") or it.get("ProductName") or ""
        typ = it.get("type") or it.get("Type") or ""
        key = (str(arm), str(meter), str(sku), str(prod), str(typ))
        if key in seen:
            continue
        seen.add(key)
        out.append(it)

    if debug:
        console.print(
            f"[cyan]fetch_all_for_service: fetched {len(items)} raw items, "
            f"{len(out)} unique[/cyan]"
        )

    if trace:
        try:
            trace.log(
                "phase3_retail_api",
                {
                    "service_name": service_name,
                    "region": region,
                    "currency": currency,
                    "url": first_url,
                    "page_count": page,
                    "raw_count": len(items),
                    "unique_count": len(out),
                },
            )
        except Exception:
            pass

    return out
