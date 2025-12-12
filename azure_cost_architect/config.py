import os

# Azure Retail Prices API
RETAIL_API_URL = "https://prices.azure.com/api/retail/prices"

# Defaults (region/currency)
DEFAULT_REGION = os.getenv("AZURECOST_DEFAULT_REGION", "westeurope")
DEFAULT_CURRENCY = os.getenv("AZURECOST_DEFAULT_CURRENCY", "EUR")

# Monthly hours
HOURS_PROD = 730
HOURS_DEVTEST = 160

# Cache file
CACHE_FILE = os.getenv("AZURECOST_CACHE_FILE", "azure_price_cache.json")

# Optional JSONL αρχείο για λεπτομερές scoring/debug (ένα candidate ανά γραμμή)
# Μπορείς να το δώσεις και με CLI: --debug-file PATH (βλ. cli.py)
DEBUG_SCORING_FILE = os.getenv("AZCOST_DEBUG_FILE", "").strip()

# LLM models (chat)
MODEL_PLANNER = os.getenv("AZURECOST_PLANNER_MODEL", "gpt-5.1")
MODEL_REPORTER = os.getenv("AZURECOST_REPORTER_MODEL", "gpt-5.1")

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

# Local catalog directory (full Azure Retail dumps per service/region/currency)
# Συνήθως είναι ο φάκελος "catalog" στο root του project.
CATALOG_DIR = os.getenv("AZURECOST_CATALOG_DIR", "catalog")
