#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Azure Personal Cost Architect – CLI (catalog-first version)

Ροή:
- Διαβάζει free-text περιγραφή αρχιτεκτονικής.
- Καλεί LLM Planner -> JSON plan (scenarios + resources).
- ΠΡΙΝ το pricing:
  - Βρίσκει όλες τις κατηγορίες resources στο plan.
  - Για κάθε (category, region) χτίζει/ανανεώνει τοπικό catalog (JSONL)
    μέσω pricing.catalog.ensure_catalog.
- Το pricing/enrichment δουλεύει ΜΟΝΟ πάνω σε local catalogs.
- Καλεί LLM Reporter για να φτιάξει τελικό Markdown report.
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

from openai import OpenAI
from rich.console import Console

from .config import (
    DEFAULT_LLM_BACKEND,
    DEFAULT_REGION,
    DEFAULT_CURRENCY,
    CATALOG_DIR,
    CACHE_FILE,
    DEFAULT_COMPARE_POLICY,
    DEFAULT_REQUIRED_CATEGORIES,
)
from .utils.categories import normalize_required_categories
from .pricing.cache import load_price_cache, save_price_cache
from .pricing.enrich import enrich_plan_with_prices
from .pricing.catalog import ensure_catalog
from .llm.planner import plan_architecture_chat, plan_architecture_responses
from .llm.reporter import generate_report_chat, generate_report_responses



console = Console()
DEBUG: bool = False


# --------------------------------------------------------------------
# Argument parsing
# --------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="azure-cost",
        description=(
            "Azure Personal Cost Architect – LLM + Local Azure Retail Catalogs\n\n"
            "Δίνεις μια περιγραφή αρχιτεκτονικής (στα ελληνικά ή αγγλικά) και το εργαλείο:\n"
            "- Σχεδιάζει 1–3 σενάρια αρχιτεκτονικής (baseline / cost_optimized / high_performance)\n"
            "- Χτίζει/ανανεώνει τοπικούς καταλόγους τιμών ανά service/region/currency\n"
            "- Υπολογίζει κόστη με βάση τους τοπικούς καταλόγους (όχι per-resource API calls)\n"
            "- Βγάζει αναλυτικό FinOps report σε Markdown και enriched JSON plan.\n"
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "--mode",
        choices=["recommend", "exact", "auto"],
        default="recommend",
        help=(
            "Πόσο αυστηρά θα σεβαστεί ο LLM τις επιλογές που έχεις γράψει.\n"
            "  - recommend: o LLM προτείνει ελεύθερα αρχιτεκτονική και SKUs.\n"
            "  - exact: προσπαθεί να τηρήσει SKUs/tiers που έχεις γράψει.\n"
            "  - auto: αποφασίζει μόνος του ανάλογα με το πόσο detailed είναι η περιγραφή."
        ),
    )

    parser.add_argument(
        "--region",
        type=str,
        default=None,
        help="Default Azure region (armRegionName) όταν δεν αναφέρεται στην περιγραφή.",
    )

    parser.add_argument(
        "--currency",
        type=str,
        default=None,
        help="Currency code για το Azure Retail Prices API (π.χ. EUR, USD, GBP).",
    )

    parser.add_argument(
        "--compare-policy",
        choices=["hard_stop", "soft_compare"],
        default=DEFAULT_COMPARE_POLICY,
        help=(
            "Πώς να συμπεριφέρεται το εργαλείο όταν το pricing είναι ελλιπές.\n"
            "- hard_stop: σταματά με μη μηδενικό exit code αν κάποιο σενάριο είναι ατελές.\n"
            "- soft_compare: συνεχίζει αλλά οι συγκρίσεις/δείκτες απενεργοποιούνται."
        ),
    )

    parser.add_argument(
        "--required-categories",
        type=str,
        default=",".join(DEFAULT_REQUIRED_CATEGORIES),
        help=(
            "CSV λίστα κατηγοριών που θεωρούνται απαραίτητες για συγκρίσεις "
            "(π.χ. compute,db,cache,network,storage). Μόνο για αυτές οι ελλείψεις "
            "μπλοκάρουν τις συγκρίσεις."
        ),
    )


    parser.add_argument(
        "--llm-backend",
        choices=["chat", "responses"],
        default=os.getenv("AZURECOST_LLM_BACKEND", DEFAULT_LLM_BACKEND),
        help=(
            "Ποιο backend της OpenAI θα χρησιμοποιηθεί:\n"
            "  - chat: κλασικό Chat Completions API.\n"
            "  - responses: Responses API με web_search εργαλείο."
        ),
    )

    parser.add_argument(
        "--output-format",
        choices=["markdown", "json", "both"],
        default="markdown",
        help=(
            "Τι output θέλεις:\n"
            "  - markdown: μόνο το αναλυτικό report (.md).\n"
            "  - json: μόνο το enriched JSON plan.\n"
            "  - both: και markdown report και enriched JSON."
        ),
    )

    parser.add_argument(
        "--output-prefix",
        type=str,
        default="azure_cost",
        help=(
            "Prefix για τα αρχεία που θα γραφτούν.\n"
            "Παράδειγμα: --output-prefix myproj => myproj_report.md, myproj_plan.json."
        ),
    )

    parser.add_argument(
        "--log-level",
        choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"],
        default=os.getenv("AZURECOST_LOG_LEVEL", "INFO"),
        help="Επίπεδο logging για εσωτερικά μηνύματα (DEBUG = πιο φλύαρο).",
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        help="Ενεργοποίηση verbose debug output (χρήσιμο για ανάπτυξη / troubleshooting).",
    )

    parser.add_argument(
        "--debug-file",
        type=str,
        default=os.getenv("AZCOST_DEBUG_FILE", ""),
        help=(
            "Αν δοθεί, γράφει αναλυτικό JSONL trace του scoring των Retail meters "
            "(π.χ. debug_scoring.jsonl)."
        ),
    )

    parser.add_argument(
        "--reset-cache",
        action="store_true",
        help=f"Σβήνει το τοπικό price cache ({CACHE_FILE}) πριν τρέξει.",
    )

    # --- Νέα flags για catalogs ---
    parser.add_argument(
        "-r",
        "--refresh-catalog",
        action="append",
        default=[],
        help=(
            "Force refresh τοπικού καταλόγου για συγκεκριμένη category.\n"
            "Μπορείς να το δώσεις πολλές φορές, π.χ.:\n"
            "  -r compute.vm -r db.sql -r appservice"
        ),
    )

    parser.add_argument(
        "--refresh-all-catalogs",
        action="store_true",
        help=(
            "Αν δοθεί, θα γίνει refresh ΟΛΩΝ των catalogs που χρειάζονται "
            "για τα resources του τρέχοντος plan."
        ),
    )

    return parser.parse_args()


# --------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------
def _read_architecture_description() -> str:
    """
    Διαβάζει την περιγραφή αρχιτεκτονικής από stdin ή interactive input.
    """
    if not sys.stdin.isatty():
        text = sys.stdin.read().strip()
    else:
        console.print(
            "Enter architecture description (multi-line allowed). "
            "Finish with Ctrl+Z + Enter (Windows) ή Ctrl+D (Linux/macOS).\n"
        )
        buf = []
        try:
            while True:
                line = input("> ")
                buf.append(line)
        except EOFError:
            pass
        text = "\n".join(buf).strip()

    return text


def _warm_catalogs_for_plan(
    plan: dict,
    default_region: str,
    currency: str,
    refresh_all: bool,
    refresh_categories: list[str],
) -> None:
    """
    Βρίσκει όλες τις (category, region) από τα resources του plan και
    φροντίζει να υπάρχει τοπικός κατάλογος για καθεμία.
    Αν refresh_all=True ή η category είναι μέσα στα refresh_categories,
    ξαναχτίζει τον κατάλογο, αλλιώς τον αφήνει ως έχει.
    """
    refresh_set = {c.strip().lower() for c in refresh_categories if c.strip()}
    scenarios = plan.get("scenarios") or []

    pairs: set[tuple[str, str]] = set()

    for sc in scenarios:
        for res in sc.get("resources", []):
            cat = (res.get("category") or "other").strip()
            # Αν το resource έχει δικό του region το σεβόμαστε, αλλιώς default_region
            reg = (res.get("region") or default_region or DEFAULT_REGION).strip() or DEFAULT_REGION
            pairs.add((cat, reg))

    if not pairs:
        return

    console.print(
        f"[cyan]Ensuring local catalogs in '{CATALOG_DIR}' "
        f"for currency='{currency}'...[/cyan]"
    )

    for cat, reg in sorted(pairs):
        cat_key = cat.lower()
        do_refresh = refresh_all or (cat_key in refresh_set)
        msg = f"  - {cat} @ {reg} (refresh={do_refresh})..."
        console.print(msg, end="")
        try:
            fp = ensure_catalog(
                base_dir=CATALOG_DIR,
                category=cat,
                region=reg,
                currency=currency,
                refresh=do_refresh,
            )
            console.print(f" [green]OK[/green] → {fp}")
        except Exception as ex:
            console.print(f" [red]FAILED[/red] ({ex})")


def _collect_compare_blockers(plan: Dict[str, Any]) -> List[Tuple[str, str]]:
    blockers: List[Tuple[str, str]] = []
    for sc in plan.get("scenarios", []):
        totals = sc.get("totals") or {}
        comparable = totals.get("comparable")
        reason = totals.get("compare_skip_reason") or "incomplete"
        if comparable is False:
            blockers.append(((sc.get("id") or sc.get("label") or "scenario"), reason))
    return blockers


def _apply_compare_policy(plan: Dict[str, Any], compare_policy: str) -> List[Tuple[str, str]]:
    blockers = _collect_compare_blockers(plan)
    if compare_policy == "hard_stop" and blockers:
        raise SystemExit(2)
    return blockers


# --------------------------------------------------------------------
# Main
# --------------------------------------------------------------------
def main() -> None:
    global DEBUG
    args = parse_args()

    required_categories = [
        c.strip() for c in (args.required_categories or "").split(",") if c.strip()
    ]
    if not required_categories:
        required_categories = list(DEFAULT_REQUIRED_CATEGORIES)
    args.required_categories = normalize_required_categories(required_categories)

    run_dir = Path("runs") / args.output_prefix
    run_dir.mkdir(parents=True, exist_ok=True)

    log_handlers: list[logging.Handler] = [logging.StreamHandler()]
    console_log_path = run_dir / "console.log"
    log_handlers.append(logging.FileHandler(console_log_path, encoding="utf-8"))

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        handlers=log_handlers,
    )
    logger = logging.getLogger("azure_cost_architect")

    DEBUG = args.debug or (args.log_level.upper() == "DEBUG")
    logger.debug("CLI arguments: %s", args)

    # Αν ο χρήστης θέλει JSONL scoring log, περνάμε το path στα env
    debug_file = args.debug_file
    if not debug_file and DEBUG:
        debug_file = str(run_dir / "debug_scoring.jsonl")

    if debug_file:
        os.environ["AZCOST_DEBUG_FILE"] = debug_file

    console.print("[bold]Azure Personal Cost Architect – Local Tool[/bold]\n")

    # ----- read architecture text -----
    arch_text = _read_architecture_description()
    if not arch_text:
        console.print("[red]No architecture description provided. Exiting.[/red]")
        sys.exit(1)

    input_path = run_dir / "input.txt"
    with open(input_path, "w", encoding="utf-8") as f:
        f.write(arch_text)
    logger.info("Saved architecture input to %s", input_path)

    # ----- OpenAI client -----
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
    if not OPENAI_API_KEY:
        console.print(
            "[red]Environment variable OPENAI_API_KEY is not set. "
            "Set it before running the tool.[/red]"
        )
        sys.exit(1)

    client = OpenAI(api_key=OPENAI_API_KEY)

    # ----- cache handling -----
    if args.reset_cache and os.path.exists(CACHE_FILE):
        logger.info("Resetting local price cache %s", CACHE_FILE)
        os.remove(CACHE_FILE)

    load_price_cache()

    # --------------------
    # 1) LLM Planner
    # --------------------
    backend = args.llm_backend
    logger.info("Using LLM backend: %s", backend)

    if backend == "responses":
        console.print(
            "[cyan]Designing architecture with LLM (Responses API + web_search, "
            f"mode={args.mode})…[/cyan]"
        )
        plan = plan_architecture_responses(client, arch_text, mode=args.mode)
    else:
        console.print(
            "[cyan]Designing architecture with LLM (Chat Completions, "
            f"mode={args.mode})…[/cyan]"
        )
        plan = plan_architecture_chat(client, arch_text, mode=args.mode)

    # Αν δώσεις region/currency στο CLI, γράφονται στο metadata του plan
    plan.setdefault("metadata", {})
    metadata = plan["metadata"]

    # Ρύθμιση currency/region με προτεραιότητα: CLI > plan > defaults
    currency = args.currency or metadata.get("currency") or DEFAULT_CURRENCY
    default_region = args.region or metadata.get("default_region") or DEFAULT_REGION

    metadata["currency"] = currency
    metadata["default_region"] = default_region
    metadata["compare_policy"] = args.compare_policy
    metadata["required_categories"] = required_categories

    logger.debug("Plan after metadata normalization: %s", plan)

    # --------------------
    # 2) Warm local catalogs (για τις κατηγορίες του plan)
    # --------------------
    _warm_catalogs_for_plan(
        plan=plan,
        default_region=default_region,
        currency=currency,
        refresh_all=args.refresh_all_catalogs,
        refresh_categories=args.refresh_catalog,
    )

    # --------------------
    # 3) Pricing enrichment (μόνο από local catalogs)
    # --------------------
    console.print("[cyan]Enriching scenarios with local Azure Retail catalogs…[/cyan]")
    logger.debug("Plan before enrichment: %s", plan)

    enriched_plan = asyncio.run(enrich_plan_with_prices(plan, debug=DEBUG))
    save_price_cache()

    json_filename = run_dir / "plan.json"
    with open(json_filename, "w", encoding="utf-8") as f:
        json.dump(enriched_plan, f, indent=2, ensure_ascii=False)
    logger.info("Saved enriched plan JSON to %s", json_filename)

    blockers = _collect_compare_blockers(enriched_plan)
    if blockers:
        console.print(
            "[yellow]Scenario comparisons are suppressed because pricing is incomplete for required categories.[/yellow]"
        )
        for sc_id, reason in blockers:
            console.print(f"  - {sc_id}: {reason}")
        if args.compare_policy == "hard_stop":
            console.print(
                "[red]--compare-policy=hard_stop is set; exiting before report generation.[/red]"
            )
            try:
                _apply_compare_policy(enriched_plan, args.compare_policy)
            except SystemExit as exc:
                sys.exit(exc.code)
    else:
        _apply_compare_policy(enriched_plan, args.compare_policy)

    # --------------------
    # 4) Report generation (Markdown)
    # --------------------
    md_filename = run_dir / "report.md"
    if args.output_format in ("markdown", "both"):
        console.print(
            "[cyan]Generating final architecture + FinOps report (Markdown)…[/cyan]"
        )

        if backend == "responses":
            report_md = generate_report_responses(client, arch_text, enriched_plan)
        else:
            report_md = generate_report_chat(client, arch_text, enriched_plan)

        with open(md_filename, "w", encoding="utf-8") as f:
            f.write(report_md)

        console.rule("[bold green]Cost Report[/bold green]")
        console.print(report_md)
        console.print(f"[green]Saved report to {md_filename}[/green]")
    else:
        console.print(
            "[yellow]Skipping Markdown report generation because "
            "--output-format is set to 'json'.[/yellow]"
        )
        logger.info("Markdown report skipped due to --output-format=json")

    metadata_path = run_dir / "metadata.json"
    metadata_payload = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "command": " ".join(sys.argv),
        "working_directory": os.getcwd(),
        "cli_args": vars(args),
        "derived": {
            "currency": currency,
            "default_region": default_region,
            "llm_backend": backend,
            "compare_policy": args.compare_policy,
            "required_categories": required_categories,
        },
        "output_files": {
            "input": str(input_path),
            "plan": str(json_filename),
            "report": str(md_filename if args.output_format in ("markdown", "both") else ""),
            "debug_scoring": debug_file or "",
            "console_log": str(console_log_path),
        },
    }

    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata_payload, f, indent=2, ensure_ascii=False)
    logger.info("Saved run metadata to %s", metadata_path)


if __name__ == "__main__":
    main()
