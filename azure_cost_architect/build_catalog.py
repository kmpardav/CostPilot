# azure_cost_architect/build_catalog.py
"""
Μικρό CLI εργαλείο για να χτίζεις / ανανεώνεις / βλέπεις local catalogs
χωρίς να τρέχεις ολόκληρο το architect flow.
"""

import argparse
import logging
from typing import List

from .config import DEFAULT_REGION, DEFAULT_CURRENCY, CATALOG_DIR
from .pricing.catalog import ensure_catalog, list_catalogs, get_catalog_info
from .pricing.normalize import normalize_service_name

# Μία εμπλουτισμένη λίστα με "συχνά" categories για --all-supported
DEFAULT_SUPPORTED_CATEGORIES: List[str] = [
    # Compute / App Service
    "compute.vm",
    "appservice.plan",

    # Databases
    "db.sql.single",
    "db.sqlmi",
    "db.cosmos",
    "db.postgres",
    "db.mysql",

    # Storage
    "storage.blob",
    "storage.files",

    # Cache
    "cache.redis",

    # Analytics
    "analytics.databricks",
    "analytics.datafactory",
    "analytics.fabric",

    # Networking
    "network.appgw",
    "network.vnet",
    "network.public_ip",
    "network.private_endpoint",
    "network.nat",
    "network.vpngw",
    "network.er",
    "network.lb",
    "network.firewall",

    # Monitoring / Security / Backup / DR
    "monitoring.loganalytics",
    "security.keyvault",
    "backup.vault",
    "dr.asr",
]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="azure_cost_architect.build_catalog",
        description="Χτίζει/ανανεώνει local Azure Retail catalogs.",
    )

    parser.add_argument(
        "--catalog-dir",
        default=CATALOG_DIR,
        help=f"Κατάλογος για τα local catalogs (default: {CATALOG_DIR}).",
    )

    parser.add_argument(
        "--region",
        default=DEFAULT_REGION,
        help=f"Azure region (default: {DEFAULT_REGION}).",
    )

    parser.add_argument(
        "--currency",
        default=DEFAULT_CURRENCY,
        help=f"Νόμισμα (default: {DEFAULT_CURRENCY}).",
    )

    parser.add_argument(
        "--categories",
        type=str,
        default="",
        help=(
            "Λίστα κατηγοριών (comma-separated) π.χ. "
            "'storage.blob,appservice.plan,db.sql.single'. "
            "Αν δεν δοθεί και δεν χρησιμοποιηθεί --all-supported, "
            "δεν θα χτιστεί τίποτα."
        ),
    )

    parser.add_argument(
        "--all-supported",
        action="store_true",
        help="Χτίζει/ανανεώνει όλα τα DEFAULT_SUPPORTED_CATEGORIES.",
    )

    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Αναγκαστικό refresh (αγνοεί υπάρχοντα JSONL και τα ξαναφέρει όλα).",
    )

    parser.add_argument(
        "--list",
        action="store_true",
        help="Εμφανίζει λίστα των υπαρχόντων catalogs και τερματίζει.",
    )

    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Επίπεδο logging (default: INFO).",
    )

    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    catalog_dir = args.catalog_dir
    region = args.region
    currency = args.currency

    if args.list:
        entries = list_catalogs(catalog_dir)
        if not entries:
            print(f"(κανένας catalog στο '{catalog_dir}')")
            return

        print(f"Βρέθηκαν {len(entries)} catalogs στο '{catalog_dir}':\n")
        for e in entries:
            svc = e["serviceName"] or e["service_slug"]
            warn = f" warning={e.get('warning')}" if e.get("warning") else ""
            print(
                f"- {svc} "
                f"[{e['region']}/{e['currency']}] "
                f"items={e['item_count']} "
                f"fetched_at={e.get('fetched_at')}{warn}"
            )
        return

    # Αν είμαστε εδώ, σημαίνει ότι θέλουμε να χτίσουμε/ανανεώσουμε catalogs
    categories: List[str] = []

    if args.all_supported:
        categories.extend(DEFAULT_SUPPORTED_CATEGORIES)

    if args.categories:
        extra = [c.strip() for c in args.categories.split(",") if c.strip()]
        categories.extend(extra)

    # Αφαιρούμε duplicates και κενά
    categories = sorted(set(c for c in categories if c))

    if not categories:
        logging.warning(
            "Δεν δόθηκαν categories και δεν χρησιμοποιήθηκε το --all-supported. "
            "Δεν υπάρχει τίποτα για build."
        )
        return

    logging.info(
        "Θα χτίσουμε/ανανεώσουμε catalogs για τις κατηγορίες: %s",
        ", ".join(categories),
    )

    for cat in categories:
        svc_name = normalize_service_name(cat, None)
        logging.info(
            "Building catalog για category='%s' (serviceName='%s'), region='%s', currency='%s'...",
            cat,
            svc_name,
            region,
            currency,
        )
        try:
            path = ensure_catalog(
                base_dir=catalog_dir,
                category=cat,
                region=region,
                currency=currency,
                refresh=args.refresh,
            )
            info = get_catalog_info(
                base_dir=catalog_dir,
                category=cat,
                region=region,
                currency=currency,
            )
            if info:
                warn = info.get("warning")
                logging.info(
                    "OK: %s (items=%s%s)",
                    path,
                    info.get("item_count"),
                    f", warning={warn}" if warn else "",
                )
                if info.get("item_count") == 0:
                    logging.warning(
                        "Catalog για category='%s' (serviceName='%s') έχει 0 items. "
                        "Ελέγξτε το Retail API query (serviceName='%s', region='%s', currency='%s').",
                        cat,
                        svc_name,
                        svc_name,
                        region,
                        currency,
                    )
            else:
                logging.info("OK: %s (no meta info found)", path)
        except Exception as ex:
            logging.error("Αποτυχία για category='%s': %s", cat, ex)


if __name__ == "__main__":
    main()
