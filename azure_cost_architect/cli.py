#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Azure Personal Cost Architect – CLI (catalog-first version)

Ροή (high level, δηλαδή τι κάνει αυτό το αρχείο ως "entrypoint"):
- Διαβάζει free-text περιγραφή αρχιτεκτονικής.
- Καλεί LLM Planner -> JSON plan (scenarios + resources).
- ΠΡΙΝ το pricing:
  - Βρίσκει όλες τις κατηγορίες resources στο plan.
  - Για κάθε (category, region) χτίζει/ανανεώνει τοπικό catalog (JSONL)
    μέσω pricing.catalog.ensure_catalog.
- Το pricing/enrichment δουλεύει ΜΟΝΟ πάνω σε local catalogs.
- Καλεί LLM Reporter για να φτιάξει τελικό Markdown report.

Σχόλιο: Αυτό το αρχείο είναι το “CLI orchestrator”.
Δηλαδή δεν κάνει μόνο ένα πράγμα: οργανώνει όλη τη ροή (plan → catalogs → enrich → report),
γράφει outputs σε runs/<prefix>/..., και χειρίζεται flags/arguments.
"""

# -----------------------------
# Standard library imports
# -----------------------------
import argparse          # Για να φτιάξουμε CLI flags (π.χ. --region, --debug κλπ)
import asyncio           # Για να τρέχουμε async enrichment με asyncio.run(...)
import json              # Για read/write JSON (plan, debug files, metadata)
import logging           # Logging σε console + file
import os                # Environment variables, paths, file checks, cwd
import sys               # stdin reading, argv, exit codes, isatty()
import hashlib           # Για hash του knowledgepack (integrity / trace)
from datetime import datetime, timezone  # Timestamps, UTC metadata
from importlib import metadata           # Για να πάρουμε version του installed package
from pathlib import Path                 # “Safe” path handling (runs/<id>/...)
from typing import Any, Dict, List, Tuple  # Type hints (βοηθά στο readability & IDE)

# -----------------------------
# Third-party imports
# -----------------------------
from openai import OpenAI               # OpenAI Python SDK client
from rich.console import Console        # Rich console για pretty output / colors

# -----------------------------
# Local package imports (δικά σου modules)
# -----------------------------
from .config import (
    # DEFAULT_* : default ρυθμίσεις του εργαλείου
    DEFAULT_LLM_BACKEND,
    DEFAULT_REGION,
    DEFAULT_CURRENCY,
    HOURS_PROD,                 # Τυπικές ώρες/μήνα (π.χ. 730) για costing
    CATALOG_DIR,                # Φάκελος αποθήκευσης catalogs
    CACHE_FILE,                 # Αρχείο local price cache
    DEFAULT_COMPARE_POLICY,     # "hard_stop" ή "soft_compare"
    DEFAULT_REQUIRED_CATEGORIES,# ποιες κατηγορίες θεωρούνται required για comparisons
    DEFAULT_ADJUDICATE_TOPN,    # πόσα top candidates στέλνουμε σε adjudicator
    MODEL_PLANNER,              # model name για planner (chat)
    MODEL_PLANNER_RESPONSES,    # model name για planner (responses)
)

# kp = knowledgepack: βοηθητικά δεδομένα (service metadata, context file, hints)
from .utils import knowledgepack as kp

# normalize_required_categories: canonicalize categories list (π.χ. trim/lower/aliases)
from .utils.categories import normalize_required_categories

# validate_plan_schema: βεβαιώνει ότι το plan έχει canonical schema (contracts)
from .planner import validate_plan_schema

# Planner repair pipeline: βρίσκει προβλήματα pricing-hints και τα διορθώνει via LLM
from .planner.repair import apply_repairs, build_category_candidates, build_repair_targets, call_repair_llm

# Price cache: load/save cache (ώστε να μην ξανα-υπολογίζεις/ξαναφορτώνεις άσκοπα)
from .pricing.cache import load_price_cache, save_price_cache

# enrich_plan_with_prices: core enrichment (match meters από catalogs, totals κλπ)
from .pricing.enrich import enrich_plan_with_prices

# ensure_catalog: φτιάχνει/ανανεώνει τοπικό catalog για (category, region, currency)
from .pricing.catalog import ensure_catalog

# Planner LLM calls:
# - chat / responses / iterative: διαφορετικές υλοποιήσεις για plan generation
from .llm.planner import plan_architecture_chat, plan_architecture_responses, plan_architecture_iterative

# Reporter LLM calls: markdown report generation
from .llm.reporter import generate_report_chat, generate_report_responses

# build_trace_logger: JSONL trace (observability για κάθε run)
from .utils.trace import build_trace_logger


# -----------------------------
# Global objects / flags
# -----------------------------
console = Console()      # Rich console instance (for pretty printing)
DEBUG: bool = False      # Global debug toggle (διαβάζεται από args)


# --------------------------------------------------------------------
# Argument parsing
# --------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    """
    Χτίζει το argparse CLI interface και επιστρέφει τα parsed args.
    Επιστρέφει argparse.Namespace (ένα αντικείμενο με πεδία: args.mode, args.region, ...)
    """
    # Δημιουργούμε parser object που ξέρει να “διαβάζει” τα command-line args.
    parser = argparse.ArgumentParser(
        prog="azure-cost",  # Το “όνομα” του CLI (φαίνεται στο help)
        description=(
            # description: κείμενο που εμφανίζεται όταν κάνεις --help
            "Azure Personal Cost Architect – LLM + Local Azure Retail Catalogs\n\n"
            "Δίνεις μια περιγραφή αρχιτεκτονικής (στα ελληνικά ή αγγλικά) και το εργαλείο:\n"
            "- Σχεδιάζει 1–3 σενάρια αρχιτεκτονικής (baseline / cost_optimized / high_performance)\n"
            "- Χτίζει/ανανεώνει τοπικούς καταλόγους τιμών ανά service/region/currency\n"
            "- Υπολογίζει κόστη με βάση τους τοπικούς καταλόγους (όχι per-resource API calls)\n"
            "- Βγάζει αναλυτικό FinOps report σε Markdown και enriched JSON plan.\n"
        ),
        # formatter_class: για να δείχνει defaults στα help messages
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    # --------------- mode ---------------
    parser.add_argument(
        "--mode",
        # choices: περιορίζει τις τιμές (άρα αποφεύγεις invalid input)
        choices=["recommend", "exact", "auto"],
        default="recommend",  # default αν δεν δοθεί
        help=(
            "Πόσο αυστηρά θα σεβαστεί ο LLM τις επιλογές που έχεις γράψει.\n"
            "  - recommend: o LLM προτείνει ελεύθερα αρχιτεκτονική και SKUs.\n"
            "  - exact: προσπαθεί να τηρήσει SKUs/tiers που έχεις γράψει.\n"
            "  - auto: αποφασίζει μόνος του ανάλογα με το πόσο detailed είναι η περιγραφή."
        ),
    )

    # --------------- region ---------------
    parser.add_argument(
        "--region",
        type=str,         # το CLI argument θα είναι string
        default=None,     # None σημαίνει: “αν δεν δοθεί, θα βγει από metadata/defaults”
        help="Default Azure region (armRegionName) όταν δεν αναφέρεται στην περιγραφή.",
    )

    # --------------- currency ---------------
    parser.add_argument(
        "--currency",
        type=str,
        default=None,
        help="Currency code για το Azure Retail Prices API (π.χ. EUR, USD, GBP).",
    )

    # --------------- compare-policy ---------------
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

    # --------------- required-categories ---------------
    parser.add_argument(
        "--required-categories",
        type=str,
        # default: παίρνει λίστα DEFAULT_REQUIRED_CATEGORIES και τη μετατρέπει σε CSV string
        default=",".join(DEFAULT_REQUIRED_CATEGORIES),
        help=(
            "CSV λίστα κατηγοριών που θεωρούνται απαραίτητες για συγκρίσεις "
            "(π.χ. compute,db,cache,network,storage). Μόνο για αυτές οι ελλείψεις "
            "μπλοκάρουν τις συγκρίσεις."
        ),
    )

    # --------------- llm-backend ---------------
    parser.add_argument(
        "--llm-backend",
        choices=["chat", "responses"],
        # default: environment variable override αν υπάρχει, αλλιώς DEFAULT_LLM_BACKEND
        default=os.getenv("AZURECOST_LLM_BACKEND", DEFAULT_LLM_BACKEND),
        help=(
            "Ποιο backend της OpenAI θα χρησιμοποιηθεί:\n"
            "  - chat: κλασικό Chat Completions API.\n"
            "  - responses: Responses API με web_search εργαλείο."
        ),
    )

    # --------------- adjudication flags ---------------
    parser.add_argument(
        "--adjudicate",
        action="store_true",  # boolean flag: False αν δεν δοθεί, True αν δοθεί
        help="Enable catalog-grounded adjudication step before final pricing (LLM chooses among top-N local meters).",
    )

    parser.add_argument(
        "--adjudicate-topn",
        type=int,
        default=DEFAULT_ADJUDICATE_TOPN,
        help="How many top-scored catalog candidates to send to the adjudicator (when --adjudicate is enabled).",
    )

    # --------------- output-format ---------------
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

    # --------------- output-prefix ---------------
    parser.add_argument(
        "--output-prefix",
        type=str,
        default="azure_cost",
        help=(
            "Prefix για τα αρχεία που θα γραφτούν.\n"
            "Παράδειγμα: --output-prefix myproj => myproj_report.md, myproj_plan.json."
        ),
    )

    # --------------- log-level ---------------
    parser.add_argument(
        "--log-level",
        choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"],
        default=os.getenv("AZURECOST_LOG_LEVEL", "INFO"),
        help="Επίπεδο logging για εσωτερικά μηνύματα (DEBUG = πιο φλύαρο).",
    )

    # --------------- debug flag ---------------
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Ενεργοποίηση verbose debug output (χρήσιμο για ανάπτυξη / troubleshooting).",
    )

    # --------------- debug-file ---------------
    parser.add_argument(
        "--debug-file",
        type=str,
        default=os.getenv("AZCOST_DEBUG_FILE", ""),
        help=(
            "Αν δοθεί, γράφει αναλυτικό JSONL trace του scoring των Retail meters "
            "(π.χ. debug_scoring.jsonl)."
        ),
    )

    # --------------- trace flags ---------------
    parser.add_argument(
        "--trace",
        action="store_true",
        help="Force writing a run trace JSONL (enabled by default).",
    )
    parser.add_argument(
        "--trace-path",
        type=str,
        default=None,
        help="Override trace output path (default: runs/<prefix>/trace.jsonl)",
    )

    # --------------- reset-cache ---------------
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
        # action="append": κάθε φορά που δίνεις -r κάτι, προστίθεται στη λίστα
        # π.χ. -r compute.vm -r db.sql => args.refresh_catalog = ["compute.vm", "db.sql"]
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

    # parse_args(): διαβάζει τα sys.argv και επιστρέφει Namespace με όλα τα πεδία.
    return parser.parse_args()


# --------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------
def _read_architecture_description() -> str:
    """
    Διαβάζει την περιγραφή αρχιτεκτονικής από stdin ή interactive input.

    Λογική:
    - Αν το πρόγραμμα “παίρνει pipe” (stdin όχι TTY): διαβάζει όλο το stdin.
    - Αλλιώς: ζητά input γραμμή-γραμμή μέχρι EOF (Ctrl+Z/Ctrl+D).
    """
    # sys.stdin.isatty() == False σημαίνει ότι η είσοδος έρχεται από pipe/redirect.
    if not sys.stdin.isatty():
        # sys.stdin.read() διαβάζει ΟΛΟ το input μέχρι EOF.
        text = sys.stdin.read().strip()
    else:
        # console.print: εκτυπώνει όμορφα (Rich)
        console.print(
            "Enter architecture description (multi-line allowed). "
            "Finish with Ctrl+Z + Enter (Windows) ή Ctrl+D (Linux/macOS).\n"
        )
        buf = []  # λίστα γραμμών που θα ενώσουμε μετά
        try:
            while True:
                # input("> "): διαβάζει μία γραμμή από τον χρήστη
                line = input("> ")
                buf.append(line)
        except EOFError:
            # EOFError σημαίνει ότι ο χρήστης έστειλε EOF (Ctrl+D / Ctrl+Z)
            pass
        # join: μετατρέπει τη λίστα σε ενιαίο string με newlines
        text = "\n".join(buf).strip()

    # Επιστρέφουμε το τελικό κείμενο
    return text


def _warm_catalogs_for_plan(
    plan: dict,                 # plan = το JSON plan (dict)
    default_region: str,         # region fallback
    currency: str,               # currency code (EUR, USD, ...)
    refresh_all: bool,           # αν True: refresh όλα
    refresh_categories: list[str],  # λίστα categories που ζητήθηκαν για refresh
    trace=None,                  # trace logger (προαιρετικό)
) -> None:
    """
    Βρίσκει όλες τις (category, region) από τα resources του plan και
    φροντίζει να υπάρχει τοπικός κατάλογος για καθεμία.

    - pairs: set από (category, region) ώστε να μην διπλο-τρέξεις ίδιο catalog.
    - ensure_catalog: φτιάχνει ή κάνει refresh αν ζητηθεί.
    """
    # refresh_set: normalizes categories σε lowercase set για γρήγορο membership check.
    refresh_set = {c.strip().lower() for c in refresh_categories if c.strip()}

    # scenarios: list με τα σενάρια του plan (ή [] αν δεν υπάρχει / None)
    scenarios = plan.get("scenarios") or []

    # pairs: set of tuples (category, region)
    pairs: set[tuple[str, str]] = set()

    # Περνάμε όλα τα scenarios και όλα τα resources για να μαζέψουμε categories/regions.
    for sc in scenarios:
        for res in sc.get("resources", []):
            # Category: αν λείπει, βάζουμε "other"
            cat = (res.get("category") or "other").strip()

            # Region: αν resource έχει region, το κρατάμε.
            # αλλιώς default_region, αλλιώς DEFAULT_REGION.
            reg = (res.get("region") or default_region or DEFAULT_REGION).strip() or DEFAULT_REGION

            # Προσθέτουμε το (cat, reg) στο set (άρα dedupe αυτόματα)
            pairs.add((cat, reg))

    # Αν δεν βρέθηκαν καθόλου pairs, δεν έχουμε catalogs να ζεστάνουμε.
    if not pairs:
        return

    console.print(
        f"[cyan]Ensuring local catalogs in '{CATALOG_DIR}' "
        f"for currency='{currency}'...[/cyan]"
    )

    # sorted(pairs): για deterministic output order (ευανάγνωστα logs)
    for cat, reg in sorted(pairs):
        cat_key = cat.lower()  # normalization
        do_refresh = refresh_all or (cat_key in refresh_set)  # boolean: refresh ή όχι
        msg = f"  - {cat} @ {reg} (refresh={do_refresh})..."
        console.print(msg, end="")  # end="" -> να συνεχίσει στην ίδια γραμμή

        try:
            # ensure_catalog: επιστρέφει πιθανόν file path (fp) του catalog
            fp = ensure_catalog(
                base_dir=CATALOG_DIR,  # root folder catalogs
                category=cat,          # category key
                region=reg,            # Azure armRegionName
                currency=currency,     # EUR/USD etc
                refresh=do_refresh,    # whether to re-fetch/rebuild
                trace=trace,           # trace logger για observability
            )
            console.print(f" [green]OK[/green] → {fp}")
        except Exception as ex:
            # Δεν κάνουμε raise εδώ: απλώς δείχνουμε FAILED και συνεχίζουμε.
            # (Μπορεί να θέλεις εδώ future policy: hard-stop on catalog failure.)
            console.print(f" [red]FAILED[/red] ({ex})")


def _collect_compare_blockers(plan: Dict[str, Any]) -> List[Tuple[str, str]]:
    """
    Μαζεύει “blockers” για scenario comparisons.
    Επιστρέφει λίστα από tuples (scenario_id, reason).

    Πού το βρίσκει:
    - plan["scenarios"][i]["totals"]["comparable"] == False → blocker
    - totals["compare_skip_reason"] → reason (default "incomplete")
    """
    blockers: List[Tuple[str, str]] = []  # τελικό αποτέλεσμα

    # Για κάθε scenario στο plan...
    for sc in plan.get("scenarios", []):
        totals = sc.get("totals") or {}         # totals dict
        comparable = totals.get("comparable")   # μπορεί True/False/None
        reason = totals.get("compare_skip_reason") or "incomplete"

        # Αν είναι explicit False, σημαίνει “μη συγκρίσιμο”
        if comparable is False:
            # scenario identifier fallback chain: id -> label -> "scenario"
            blockers.append(((sc.get("id") or sc.get("label") or "scenario"), reason))
    return blockers


def _collect_blocker_details(plan: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Πιο αναλυτικά από το _collect_compare_blockers.
    Επιστρέφει λίστα dicts με:
      scenario_id, reason, resource_id, category, requested_sku, meter

    Αυτό είναι χρήσιμο για debug: “ποιο resource ακριβώς δεν τιμολογήθηκε”.
    """
    details: List[Dict[str, Any]] = []

    for sc in plan.get("scenarios", []):
        totals = sc.get("totals") or {}
        required = totals.get("required") or {}

        # required["comparable"] == False σημαίνει ότι required categories έχουν έλλειψη.
        if required.get("comparable") is False:
            for blk in required.get("blockers") or []:
                details.append(
                    {
                        "scenario_id": sc.get("id") or sc.get("label"),
                        "reason": blk.get("reason") or required.get("compare_skip_reason"),
                        "resource_id": blk.get("resource_id"),
                        "category": blk.get("category"),
                        "requested_sku": blk.get("requested_sku"),
                        "meter": blk.get("meter"),
                    }
                )
    return details


def _knowledgepack_hash() -> tuple[str, str]:
    """
    Υπολογίζει SHA256 hash ενός “context/knowledgepack” αρχείου.
    Επιστρέφει (hash_hex, path_string).

    Χρήση:
    - για trace/metadata ώστε να ξέρεις “με ποιο knowledgepack έτρεξε αυτό το run”.
    """
    # Παίρνει path από env AZURECOST_LLM_CONTEXT, αλλιώς kp._DEFAULT_CONTEXT_PATH
    ctx_path = Path(os.getenv("AZURECOST_LLM_CONTEXT", kp._DEFAULT_CONTEXT_PATH))
    try:
        data = ctx_path.read_bytes()                    # διαβάζει bytes από αρχείο
        return hashlib.sha256(data).hexdigest(), str(ctx_path)  # sha256 hex digest + path
    except Exception:
        # Αν κάτι πάει στραβά (δεν υπάρχει file, perms κλπ) επιστρέφει "unknown"
        return "unknown", str(ctx_path)


def _apply_compare_policy(plan: Dict[str, Any], compare_policy: str) -> List[Tuple[str, str]]:
    """
    Εφαρμόζει compare policy.

    - Αν compare_policy == "hard_stop" και υπάρχουν blockers → exit code 2.
    - Αλλιώς επιστρέφει blockers (για ενημέρωση/printing).
    """
    blockers = _collect_compare_blockers(plan)
    if compare_policy == "hard_stop" and blockers:
        # raise SystemExit: τερματίζει αμέσως το πρόγραμμα.
        # code=2: convention για “incomplete pricing / policy stop”.
        raise SystemExit(2)
    return blockers


# --------------------------------------------------------------------
# Main
# --------------------------------------------------------------------
def main() -> None:
    """
    Το κύριο entrypoint της εφαρμογής (όταν τρέχεις `python -m ...cli` ή `azure-cost`).

    Στάδια:
      0) args/logging/trace setup
      1) read input text
      2) LLM planning (iterative)
      1b) optional repair loop
      2) warm local catalogs for resources in plan
      3) pricing enrichment (local catalogs)
      4) report generation (markdown) + metadata files
    """
    global DEBUG  # δηλώνουμε ότι θα αλλάξουμε το global DEBUG

    # Διαβάζουμε τα CLI arguments
    args = parse_args()

    # required_categories: παίρνει CSV string και το κάνει list
    required_categories = [
        c.strip() for c in (args.required_categories or "").split(",") if c.strip()
    ]
    if not required_categories:
        required_categories = list(DEFAULT_REQUIRED_CATEGORIES)

    # normalize_required_categories: canonicalize categories (συνήθως lower/aliases)
    args.required_categories = normalize_required_categories(required_categories)

    # run_id: χρησιμοποιείται ως “prefix” για το folder του run
    run_id = args.output_prefix

    # run_dir: runs/<run_id>
    run_dir = Path("runs") / run_id

    # mkdir(parents=True): φτιάχνει και ενδιάμεσους φακέλους αν χρειάζεται
    # exist_ok=True: δεν σκάει αν υπάρχει ήδη
    run_dir.mkdir(parents=True, exist_ok=True)

    # trace_path: αν ο χρήστης δώσει --trace-path, το παίρνουμε. αλλιώς default runs/<id>/trace.jsonl
    trace_path = Path(args.trace_path) if args.trace_path else run_dir / "trace.jsonl"

    # trace_enabled: default True, αλλά μπορεί να απενεργοποιηθεί από env AZURECOST_TRACE
    trace_env = os.getenv("AZURECOST_TRACE")
    trace_enabled = True
    if trace_env is not None and trace_env.strip().lower() in {"0", "false", "no"}:
        trace_enabled = False
    if args.trace:
        trace_enabled = True  # CLI flag έχει προτεραιότητα και το ξανα-ενεργοποιεί

    # log_handlers: λίστα handlers για logging
    log_handlers: list[logging.Handler] = [logging.StreamHandler()]  # console handler

    # console log file: runs/<id>/console.log
    console_log_path = run_dir / "console.log"
    log_handlers.append(logging.FileHandler(console_log_path, encoding="utf-8"))

    # logging.basicConfig: global logging config
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),  # map string -> numeric level
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",   # log format
        handlers=log_handlers,                                         # write to console + file
    )

    # Παίρνουμε logger για αυτό το tool
    logger = logging.getLogger("azure_cost_architect")

    # trace_logger: δικό σου JSONL tracer (γράφει structured events)
    trace_logger = build_trace_logger(trace_path, enabled=trace_enabled)

    # tool_version: version του installed python package (αν υπάρχει)
    try:
        tool_version = metadata.version("azure-cost-architect")
    except Exception:
        tool_version = "dev"

    # knowledgepack hash & path: για reproducibility
    kp_hash, kp_path = _knowledgepack_hash()

    # trace_logger.log: γράφουμε ένα event “phase0_setup” με βασικές ρυθμίσεις
    trace_logger.log(
        "phase0_setup",
        {
            "tool_version": tool_version,
            "region": args.region or DEFAULT_REGION,
            "currency": args.currency or DEFAULT_CURRENCY,
            "hours_per_month": HOURS_PROD,
            "knowledgepack_hash": kp_hash,
            "knowledgepack_path": kp_path,
            "llm_backend": args.llm_backend,
            "models": {
                "planner": MODEL_PLANNER,
                "planner_responses": MODEL_PLANNER_RESPONSES,
            },
        },
    )

    # DEBUG: ενεργό αν --debug ή αν log-level == DEBUG
    DEBUG = args.debug or (args.log_level.upper() == "DEBUG")
    logger.debug("CLI arguments: %s", args)

    # debug_file: αν ο χρήστης δεν έδωσε --debug-file αλλά DEBUG ενεργό,
    # τότε γράφουμε default σε runs/<id>/debug_scoring.jsonl
    debug_file = args.debug_file
    if not debug_file and DEBUG:
        debug_file = str(run_dir / "debug_scoring.jsonl")

    # Αν υπάρχει debug_file, το περνάμε με env var για να το δουν άλλα modules.
    if debug_file:
        os.environ["AZCOST_DEBUG_FILE"] = debug_file

    console.print("[bold]Azure Personal Cost Architect – Local Tool[/bold]\n")

    # ----- read architecture text -----
    arch_text = _read_architecture_description()  # παίρνει input από stdin ή interactive
    if not arch_text:
        console.print("[red]No architecture description provided. Exiting.[/red]")
        sys.exit(1)  # exit code 1: “bad input / missing input”

    # input_path: γράφουμε το raw input στο runs/<id>/input.txt για auditability
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

    # OpenAI client instance (used by planner, repair, adjudicator, reporter)
    client = OpenAI(api_key=OPENAI_API_KEY)

    # ----- cache handling -----
    if args.reset_cache and os.path.exists(CACHE_FILE):
        logger.info("Resetting local price cache %s", CACHE_FILE)
        os.remove(CACHE_FILE)

    # load_price_cache: φορτώνει cache στη μνήμη (για reuse μεταξύ resources)
    load_price_cache()

    # --------------------
    # 1) LLM Planner
    # --------------------
    backend = args.llm_backend
    logger.info("Using LLM backend: %s", backend)

    try:
        console.print(
            "[cyan]Designing architecture with LLM (multi-pass, enforcing Pricing Contract)…[/cyan]"
        )

        # plan_architecture_iterative:
        # - κάνει multi-pass planning ώστε να βγει plan που “σέβεται” pricing contract
        # - το backend μπορεί να είναι chat ή responses (και να κάνει web_search)
        plan = plan_architecture_iterative(
            client,              # OpenAI client
            arch_text,           # input text
            mode=args.mode,      # recommend/exact/auto
            backend=backend,     # chat/responses
            trace=trace_logger,  # trace για observability
        )
    except Exception as ex:
        logger.error("Planner failed to produce a valid plan: %s", ex)
        console.print(f"[red]Planner failed: {ex}[/red]")
        sys.exit(1)

    # validate_plan_schema: canonicalizes/validates ότι plan έχει σωστό schema
    plan = validate_plan_schema(plan)

    # Αν δώσεις region/currency στο CLI, γράφονται στο metadata του plan
    plan.setdefault("metadata", {})  # αν δεν υπάρχει metadata, το δημιουργεί
    metadata = plan["metadata"]      # metadata dict (προσοχή: αυτό “κρύβει” το importlib.metadata όνομα)

    # Ρύθμιση currency/region με προτεραιότητα: CLI > plan > defaults
    currency = args.currency or metadata.get("currency") or DEFAULT_CURRENCY
    default_region = args.region or metadata.get("default_region") or DEFAULT_REGION

    # Γράφουμε canonical metadata values ώστε downstream να είναι consistent
    metadata["currency"] = currency
    metadata["default_region"] = default_region
    metadata["compare_policy"] = args.compare_policy
    metadata["required_categories"] = required_categories
    metadata["adjudication_enabled"] = args.adjudicate
    metadata["adjudication_topn"] = args.adjudicate_topn
    metadata["repair_iterations"] = metadata.get("repair_iterations", 0)

    # --------------------
    # 1b) Auto-repair pricing hints (LLM-guided)
    # --------------------
    repair_inputs: list[dict] = []   # θα γράψουμε debug input σε JSON
    repair_outputs: list[dict] = []  # θα γράψουμε debug output σε JSON

    # service_hint_samples: compact metadata για services (help στον repair LLM)
    service_hint_samples = kp.get_compact_service_metadata(common_limit=25)

    # for iteration in range(2): έως 2 repair passes (fixed)
    for iteration in range(2):
        # build_repair_targets: εντοπίζει resources που έχουν αδύναμα/λάθος pricing hints
        repair_targets = build_repair_targets(plan, required_categories=required_categories)
        if not repair_targets:
            break  # αν δεν υπάρχουν targets, σταματάμε το loop

        # categories: set με categories που εμφανίζονται στα repair targets
        categories = {t["category"] for t in repair_targets}

        # category_candidates: dict category->candidate list
        # build_category_candidates: φτιάχνει πιθανές canonical τιμές για fields της κατηγορίας
        category_candidates = {cat: build_category_candidates(cat) for cat in categories}

        # κρατάμε debug input για αναπαραγωγή
        repair_inputs.append(
            {
                "iteration": iteration + 1,
                "validated_plan": plan,
                "repair_targets": repair_targets,
                "category_candidates": category_candidates,
                "service_hint_samples": service_hint_samples,
            }
        )

        # call_repair_llm: καλεί LLM για να προτείνει repairs (patches)
        repair_response = call_repair_llm(
            client,
            plan,
            repair_targets,
            category_candidates,
            service_hint_samples,
            backend=backend,
        )

        # κρατάμε debug output
        repair_outputs.append({"iteration": iteration + 1, "response": repair_response})

        # apply_repairs: εφαρμόζει τις suggested αλλαγές πάνω στο plan
        plan = apply_repairs(plan, repair_response.get("repairs"))

        # διασφαλίζουμε ότι metadata υπάρχει
        plan.setdefault("metadata", {})
        # αυξάνουμε counter iterations
        plan["metadata"]["repair_iterations"] = plan["metadata"].get("repair_iterations", 0) + 1

    # Αν τρέξαμε repair loop, γράφουμε debug αρχεία
    if repair_inputs:
        with open(run_dir / "debug_repair_input.json", "w", encoding="utf-8") as f:
            json.dump(repair_inputs, f, indent=2, ensure_ascii=False)
    if repair_outputs:
        with open(run_dir / "debug_repair_output.json", "w", encoding="utf-8") as f:
            json.dump(repair_outputs, f, indent=2, ensure_ascii=False)

    logger.debug("Plan after metadata normalization: %s", plan)

    # final_plan_path: canonical plan written (μετά repairs, πριν enrichment)
    final_plan_path = run_dir / "final_plan.json"
    with open(final_plan_path, "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=2, ensure_ascii=False)

    # trace: καταγραφή ότι γράφτηκε canonical plan
    trace_logger.log(
        "phase2_validation",
        {"message": "final canonical plan written", "path": str(final_plan_path)},
    )

    # --------------------
    # 2) Warm local catalogs (για τις κατηγορίες του plan)
    # --------------------
    _warm_catalogs_for_plan(
        plan=plan,
        default_region=default_region,
        currency=currency,
        refresh_all=args.refresh_all_catalogs,
        refresh_categories=args.refresh_catalog,
        trace=trace_logger,
    )

    # --------------------
    # 3) Pricing enrichment (μόνο από local catalogs)
    # --------------------
    console.print("[cyan]Enriching scenarios with local Azure Retail catalogs…[/cyan]")
    logger.debug("Plan before enrichment: %s", plan)

    # asyncio.run: τρέχει async function σε νέο event loop
    enriched_plan = asyncio.run(
        enrich_plan_with_prices(
            plan,
            debug=DEBUG,
            adjudicate=args.adjudicate,
            adjudicate_topn=args.adjudicate_topn,
            adjudicator_client=client,   # ίδιο OpenAI client για adjudicator step
            trace=trace_logger,
        )
    )

    # Αποθήκευση cache μετά το enrichment (ώστε επόμενα runs να είναι πιο γρήγορα)
    save_price_cache()

    # blocker_details: λεπτομέρειες για missing pricing
    blocker_details = _collect_blocker_details(enriched_plan)
    if blocker_details:
        # Προσθέτουμε στο enriched_plan για εύκολη κατανάλωση από reporter/ops
        enriched_plan["compare_blockers"] = blocker_details

    # json_filename: runs/<id>/plan.json (enriched plan)
    json_filename = run_dir / "plan.json"
    with open(json_filename, "w", encoding="utf-8") as f:
        json.dump(enriched_plan, f, indent=2, ensure_ascii=False)
    logger.info("Saved enriched plan JSON to %s", json_filename)

    # trace event: reporting phase started / enriched plan path
    trace_logger.log(
        "phase7_reporting",
        {"enriched_plan_path": str(json_filename)},
    )

    # blockers: αν υπάρχουν, σημαίνει comparisons disabled
    blockers = _collect_compare_blockers(enriched_plan)
    if blockers:
        console.print(
            "[yellow]Scenario comparisons are suppressed because pricing is incomplete for required categories.[/yellow]"
        )

        # Εκτυπώνουμε συνοπτικά (scenario_id, reason)
        for sc_id, reason in blockers:
            console.print(f"  - {sc_id}: {reason}")

        # Αν έχουμε λεπτομέρειες, εκτυπώνουμε ανά resource
        if blocker_details:
            for blk in blocker_details:
                console.print(
                    f"    • {blk.get('scenario_id')}: {blk.get('resource_id')} "
                    f"[{blk.get('category')}] → {blk.get('reason')} "
                    f"(requested={blk.get('requested_sku')}, meter={blk.get('meter')})"
                )

        # Αν policy = hard_stop, σταματάμε πριν κάνουμε report
        if args.compare_policy == "hard_stop":
            console.print(
                "[red]--compare-policy=hard_stop is set; exiting before report generation.[/red]"
            )
            try:
                _apply_compare_policy(enriched_plan, args.compare_policy)
            except SystemExit as exc:
                sys.exit(exc.code)
    else:
        # Αν δεν υπάρχουν blockers, εφαρμόζουμε policy (συνήθως no-op)
        _apply_compare_policy(enriched_plan, args.compare_policy)

    # --------------------
    # 4) Report generation (Markdown)
    # --------------------
    md_filename = run_dir / "report.md"

    # Αν output-format επιτρέπει markdown, το παράγουμε
    if args.output_format in ("markdown", "both"):
        console.print(
            "[cyan]Generating final architecture + FinOps report (Markdown)…[/cyan]"
        )

        # Επιλογή reporter ανά backend:
        # - responses: generate_report_responses
        # - chat: generate_report_chat
        if backend == "responses":
            report_md = generate_report_responses(client, arch_text, enriched_plan)
        else:
            report_md = generate_report_chat(client, arch_text, enriched_plan)

        # Γράφουμε report σε αρχείο
        with open(md_filename, "w", encoding="utf-8") as f:
            f.write(report_md)

        # Pretty print στην κονσόλα
        console.rule("[bold green]Cost Report[/bold green]")
        console.print(report_md)
        console.print(f"[green]Saved report to {md_filename}[/green]")

        # trace event: report path
        trace_logger.log(
            "phase7_reporting",
            {"report_path": str(md_filename)},
        )
    else:
        # Αν output-format=json: δεν παράγουμε markdown
        console.print(
            "[yellow]Skipping Markdown report generation because "
            "--output-format is set to 'json'.[/yellow]"
        )
        logger.info("Markdown report skipped due to --output-format=json")

    # --------------------
    # 5) Run metadata file
    # --------------------
    metadata_path = run_dir / "metadata.json"

    # metadata_payload: “run manifest” με timestamp, args, derived config, outputs
    metadata_payload = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "command": " ".join(sys.argv),        # πλήρης command line
        "working_directory": os.getcwd(),     # current directory
        "cli_args": vars(args),               # Namespace -> dict
        "derived": {
            "currency": currency,
            "default_region": default_region,
            "llm_backend": backend,
            "compare_policy": args.compare_policy,
            "required_categories": required_categories,
            "adjudication_enabled": args.adjudicate,
            "adjudication_topn": args.adjudicate_topn,
        },
        "output_files": {
            "input": str(input_path),
            "plan": str(json_filename),
            "report": str(md_filename if args.output_format in ("markdown", "both") else ""),
            "debug_scoring": debug_file or "",
            "console_log": str(console_log_path),
        },
    }

    # Γράφουμε metadata.json
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata_payload, f, indent=2, ensure_ascii=False)
    logger.info("Saved run metadata to %s", metadata_path)


# Python convention:
# Αυτό το block τρέχει ΜΟΝΟ όταν εκτελείται αυτό το αρχείο ως script,
# όχι όταν γίνεται import ως module.
if __name__ == "__main__":
    main()
