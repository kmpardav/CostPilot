import os

# Azure Retail Prices API
RETAIL_API_URL = "https://prices.azure.com/api/retail/prices"

# Defaults (region/currency)
DEFAULT_REGION = os.getenv("AZURECOST_DEFAULT_REGION", "westeurope")
DEFAULT_CURRENCY = os.getenv("AZURECOST_DEFAULT_CURRENCY", "EUR")

# Monthly hours
HOURS_PROD = 730
HOURS_DEVTEST = 160

# -----------------------------------------------------------------------------
# Paths / files controlled via environment (read at runtime!)
# -----------------------------------------------------------------------------
ENV_CACHE_FILE = "AZURECOST_CACHE_FILE"  # JSON file for local price cache
ENV_DEBUG_SCORING_FILE = "AZCOST_DEBUG_FILE"  # scoring debug JSONL
ENV_DEBUG_ENRICHED_FILE = "AZCOST_DEBUG_ENRICHED_FILE"  # enrich debug JSON

# Tracing (feature flags)
ENV_TRACE_ENABLED = "AZURECOST_TRACE"  # 0/false/no disables trace; otherwise enabled by default
ENV_TRACE_LEVEL = "AZURECOST_TRACE_LEVEL"  # pipeline|verbose|debug
ENV_TRACE_STORY = "AZURECOST_TRACE_STORY"  # 1/0 toggles run_story.md generation

DEFAULT_CACHE_FILE = "azure_price_cache.json"
DEFAULT_DEBUG_ENRICHED_FILE = "debug_enriched.json"

# Cache file
CACHE_FILE = os.getenv(ENV_CACHE_FILE, DEFAULT_CACHE_FILE)  # backwards-compat constant (may be stale)

# Optional JSONL αρχείο για λεπτομερές scoring/debug (ένα candidate ανά γραμμή)
# Μπορείς να το δώσεις και με CLI: --debug-file PATH (βλ. cli.py)
DEBUG_SCORING_FILE = os.getenv(ENV_DEBUG_SCORING_FILE, "").strip()

# Debug enriched plan (JSON)
DEBUG_ENRICHED_FILE = os.getenv(ENV_DEBUG_ENRICHED_FILE, DEFAULT_DEBUG_ENRICHED_FILE).strip()


def get_cache_file() -> str:
    """Return the active price-cache file path (env-aware)."""
    return os.getenv(ENV_CACHE_FILE, DEFAULT_CACHE_FILE)


def get_debug_scoring_file() -> str:
    """Return the active scoring debug JSONL path (env-aware)."""
    return os.getenv(ENV_DEBUG_SCORING_FILE, "").strip()


def get_debug_enriched_file() -> str:
    """Return the active debug enriched JSON path (env-aware)."""
    return os.getenv(ENV_DEBUG_ENRICHED_FILE, DEFAULT_DEBUG_ENRICHED_FILE).strip()

# LLM models (chat)
MODEL_PLANNER = os.getenv("AZURECOST_PLANNER_MODEL", "gpt-5.2-pro")
MODEL_REPORTER = os.getenv("AZURECOST_REPORTER_MODEL", "gpt-5.2-pro")
MODEL_ADJUDICATOR = os.getenv("AZURECOST_ADJUDICATOR_MODEL", MODEL_PLANNER)

# LLM models (responses)
MODEL_PLANNER_RESPONSES = os.getenv("AZURECOST_PLANNER_RESP_MODEL", MODEL_PLANNER)
MODEL_REPORTER_RESPONSES = os.getenv("AZURECOST_REPORTER_RESP_MODEL", MODEL_REPORTER)

# Backend default
DEFAULT_LLM_BACKEND = os.getenv("AZURECOST_LLM_BACKEND", "chat")

# Scenario comparison safeguards
DEFAULT_COMPARE_POLICY = os.getenv("AZURECOST_COMPARE_POLICY", "soft_compare")
DEFAULT_REQUIRED_CATEGORIES = [
    "compute",
    "db",
    "cache",
    "network",
    "storage",
]

DEFAULT_ADJUDICATE_TOPN = int(os.getenv("AZURECOST_ADJUDICATE_TOPN", "15"))

# Local catalog directory (full Azure Retail dumps per service/region/currency)
# Συνήθως είναι ο φάκελος "catalog" στο root του project.
CATALOG_DIR = os.getenv("AZURECOST_CATALOG_DIR", "catalog")
