# config.py
"""
Central configuration for the CostPilot / Azure pricing tool.

IMPORTANT CONCEPT:
- Retail API has its own taxonomy fields:
  - serviceFamily (e.g., "Compute", "Databases", "Networking", "Storage", "Security", "Containers")
  - serviceName   (e.g., "Azure Kubernetes Service", "Azure Container Apps", "SQL Database", "Key Vault")
- OUR TOOL uses *canonical buckets* (a simplified internal vocabulary) to:
  1) Normalize whatever the user/LLM writes into a stable set of categories
  2) Apply guardrails when comparing scenarios (baseline vs cost-optimized vs high-perf)
  3) Drive catalog selection / pricing query strategies

So: do NOT expect canonical buckets to match Retail "serviceFamily" strings 1:1.
We intentionally use stable, code-friendly canonical names such as:
  compute, databases, cache, networking, storage, security, management, analytics, containers, ...

You can extend/modify canonical buckets in categories.py.
"""

import os

# -------------------------------------------------------------------
# Azure Retail Prices API
# -------------------------------------------------------------------

# The official Azure Retail Prices API endpoint.
RETAIL_API_URL = "https://prices.azure.com/api/retail/prices"

# -------------------------------------------------------------------
# Defaults: region / currency
# -------------------------------------------------------------------

# Default region used when the user does not specify --region.
# NOTE: This is *armRegionName* filter value (e.g. "westeurope").
DEFAULT_REGION = os.getenv("AZURECOST_DEFAULT_REGION", "westeurope")

# Default currency used when the user does not specify --currency.
# NOTE: Retail API expects currencyCode (e.g. "EUR", "USD").
DEFAULT_CURRENCY = os.getenv("AZURECOST_DEFAULT_CURRENCY", "EUR")

# -------------------------------------------------------------------
# Time assumptions (used in cost math)
# -------------------------------------------------------------------

# Typical production month in hours (approx 365 days / 12 months * 24h = ~730h).
HOURS_PROD = 730

# Typical dev/test monthly runtime (example assumption).
# You can adjust this if your Dev/Test is 8h/day x 5d/week.
HOURS_DEVTEST = 160

# -------------------------------------------------------------------
# Local cache (simple price cache, not full catalog)
# -------------------------------------------------------------------

# JSON cache used by pricing layer to avoid repeated API calls.
CACHE_FILE = os.getenv("AZURECOST_CACHE_FILE", "azure_price_cache.json")

# Optional JSONL file for detailed scoring/debug output
# (one candidate item per line). If empty -> disabled.
# Also settable via CLI: --debug-file PATH
DEBUG_SCORING_FILE = os.getenv("AZCOST_DEBUG_FILE", "").strip()

# -------------------------------------------------------------------
# LLM model selection
# -------------------------------------------------------------------

# Planner: generates structured plans (resources + scenarios).
MODEL_PLANNER = os.getenv("AZURECOST_PLANNER_MODEL", "gpt-5.1")

# Reporter: produces the final human report (Markdown/summary).
MODEL_REPORTER = os.getenv("AZURECOST_REPORTER_MODEL", "gpt-5.1")

# Adjudicator: optionally judges between multiple candidates / resolves conflicts.
# Defaults to planner model unless explicitly overridden.
MODEL_ADJUDICATOR = os.getenv("AZURECOST_ADJUDICATOR_MODEL", MODEL_PLANNER)

# "Responses API" variants (if you use a different backend/model for responses).
MODEL_PLANNER_RESPONSES = os.getenv("AZURECOST_PLANNER_RESP_MODEL", MODEL_PLANNER)
MODEL_REPORTER_RESPONSES = os.getenv("AZURECOST_REPORTER_RESP_MODEL", MODEL_REPORTER)

# Which LLM backend to use by default (e.g., "chat" vs "responses").
DEFAULT_LLM_BACKEND = os.getenv("AZURECOST_LLM_BACKEND", "chat")

# -------------------------------------------------------------------
# Scenario comparison safeguards (guardrails)
# -------------------------------------------------------------------

# Compare policy defines how strict we are when comparing scenarios:
# - "soft_compare": warn but do not hard-fail when something is missing
# - "strict_compare": treat missing required categories as an error (if implemented)
DEFAULT_COMPARE_POLICY = os.getenv("AZURECOST_COMPARE_POLICY", "soft_compare")

# Canonical buckets that should exist in a "minimum viable" architecture.
# These are NOT Retail families; they are internal buckets.
#
# Why these 5?
# - Most real architectures need: compute + db + cache + network + storage
# - They are "foundation" components; missing them often indicates plan defects
#
# Should we add more? Often we ALSO care about:
# - security (Key Vault / Entra / Defender / Sentinel)
# - management (Monitor / Log Analytics / Policy)
#
# We keep the default as the minimal set, but categories.py supports both buckets.
DEFAULT_REQUIRED_CATEGORIES = [
    "compute",
    "databases",
    "cache",
    "networking",
    "storage",
]

# When using an adjudicator step, only consider top N candidates (performance guard).
DEFAULT_ADJUDICATE_TOPN = int(os.getenv("AZURECOST_ADJUDICATE_TOPN", "15"))

# -------------------------------------------------------------------
# Local catalog directory (full dumps per service/region/currency)
# -------------------------------------------------------------------

# This is the directory where you store built catalog files
# (per category/service, region, currency).
CATALOG_DIR = os.getenv("AZURECOST_CATALOG_DIR", "catalog")
