#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
config.py

This module defines configuration constants and defaults for the CostPilot / AzureCost tool.

Key idea: INTERNAL "canonical guardrail families"
-------------------------------------------------
Your tool uses a *small* set of internal canonical category families for validation/guardrails.

These are NOT the same as the Azure Retail Prices taxonomy "serviceFamily" values you see in Excel.

Why do we do this?
- The Retail API taxonomy is large and changes over time (many families/services).
- For scenario completeness checks, you want a stable set of "must-have" building blocks.
- So you keep a small internal abstraction and normalize real-world names into it.

Example mapping:
- Excel family: "Databases"
- Internal canonical family: "db"

The normalization from user/LLM labels to your canonical families is implemented in categories.py
(aliases + normalization functions).
"""

import os  # Standard library: access environment variables (os.getenv) and other OS features.

# ---------------------------------------------------------------------
# Azure Retail Prices API
# ---------------------------------------------------------------------
# Base endpoint used by your scripts to query Azure Retail Prices.
RETAIL_API_URL = "https://prices.azure.com/api/retail/prices"

# ---------------------------------------------------------------------
# Defaults: region / currency
# ---------------------------------------------------------------------
# DEFAULT_REGION:
# - Used when user does not specify a region explicitly (CLI arg missing).
# - Also can be overridden by environment variable AZURECOST_DEFAULT_REGION.
# - Example value: "westeurope"
DEFAULT_REGION = os.getenv("AZURECOST_DEFAULT_REGION", "westeurope")

# DEFAULT_CURRENCY:
# - Used when user does not specify currency explicitly (CLI arg missing).
# - Also can be overridden by environment variable AZURECOST_DEFAULT_CURRENCY.
# - Example value: "EUR"
DEFAULT_CURRENCY = os.getenv("AZURECOST_DEFAULT_CURRENCY", "EUR")

# ---------------------------------------------------------------------
# Standard monthly hours (used for cost calculations)
# ---------------------------------------------------------------------
# HOURS_PROD:
# - Typical “always-on” monthly hours (365 days / year approximation).
# - 730 = 365 * 24 / 12 (approx)
HOURS_PROD = 730

# HOURS_DEVTEST:
# - Typical dev/test “working hours only” month approximation.
# - 160 = ~20 working days * 8 hours
HOURS_DEVTEST = 160

# ---------------------------------------------------------------------
# Cache file (local pricing cache)
# ---------------------------------------------------------------------
# CACHE_FILE:
# - Local JSON file used to cache chosen "best match" pricing results.
# - Speeds up repeated runs (avoid re-query / re-ranking).
# - Can be overridden via env var AZURECOST_CACHE_FILE.
CACHE_FILE = os.getenv("AZURECOST_CACHE_FILE", "azure_price_cache.json")

# ---------------------------------------------------------------------
# Optional debug JSONL file for detailed scoring traces
# ---------------------------------------------------------------------
# DEBUG_SCORING_FILE:
# - If set, your pricing/scoring layer can write one candidate meter per line (JSONL).
# - Useful for post-mortem analysis of why a SKU/meter was selected.
# - Can be set via env var AZCOST_DEBUG_FILE
# - CLI can override too (e.g. --debug-file PATH) depending on your cli.py implementation.
DEBUG_SCORING_FILE = os.getenv("AZCOST_DEBUG_FILE", "").strip()

# ---------------------------------------------------------------------
# LLM models (Chat Completions path)
# ---------------------------------------------------------------------
# These are the model names used when your backend is "chat" (Chat Completions).
# Keep them in environment variables so you can swap models without code changes.
MODEL_PLANNER = os.getenv("AZURECOST_PLANNER_MODEL", "gpt-5.1")
MODEL_REPORTER = os.getenv("AZURECOST_REPORTER_MODEL", "gpt-5.1")
MODEL_ADJUDICATOR = os.getenv("AZURECOST_ADJUDICATOR_MODEL", MODEL_PLANNER)

# ---------------------------------------------------------------------
# LLM models (Responses API path or alternative backend naming)
# ---------------------------------------------------------------------
# If you use a different API path for some backends (e.g. "responses"),
# you might want separate env vars or reuse the same ones.
MODEL_PLANNER_RESPONSES = os.getenv("AZURECOST_PLANNER_RESP_MODEL", MODEL_PLANNER)
MODEL_REPORTER_RESPONSES = os.getenv("AZURECOST_REPORTER_RESP_MODEL", MODEL_REPORTER)

# ---------------------------------------------------------------------
# Backend default
# ---------------------------------------------------------------------
# DEFAULT_LLM_BACKEND:
# - Which LLM calling path your tool uses by default.
# - Common pattern:
#   - "chat"      -> Chat Completions
#   - "responses" -> Responses API (or another internal adapter)
DEFAULT_LLM_BACKEND = os.getenv("AZURECOST_LLM_BACKEND", "chat")

# ---------------------------------------------------------------------
# Scenario comparison safeguards (guardrails)
# ---------------------------------------------------------------------
# DEFAULT_COMPARE_POLICY:
# - Defines how strict you want to be when comparing scenarios (baseline vs optimized vs perf).
# - Example policies:
#   - "soft_compare": warn when something is missing/misaligned
#   - "hard_compare": fail/repair until alignment is achieved
DEFAULT_COMPARE_POLICY = os.getenv("AZURECOST_COMPARE_POLICY", "soft_compare")

# DEFAULT_REQUIRED_CATEGORIES:
# - Your INTERNAL canonical guardrail families that must appear in a scenario plan.
# - These are NOT Excel serviceFamily names.
# - They are short stable keys that categories.py can normalize to.
#
# Why these 5 are common “must-haves”:
# - compute  : something must run the workload
# - db       : a database tier exists (if the app stores relational/NoSQL state)
# - cache    : caching layer (if performance / scale patterns need it)
# - network  : connectivity / ingress / egress components exist
# - storage  : persistent storage (object/file/disk) exists
#
# IMPORTANT:
# - Keep this list minimal to avoid false negatives.
# - If you expand it, do it only if your LLM planner + repair loop can reliably satisfy it.
DEFAULT_REQUIRED_CATEGORIES = [
    "compute",
    "db",
    "cache",
    "network",
    "storage",
]

# DEFAULT_ADJUDICATE_TOPN:
# - When selecting a "best meter" from Retail API candidates, you may rank candidates.
# - This controls how many top candidates you keep for adjudication/voting.
# - Kept as 5 here because that’s what your original config uses.
DEFAULT_ADJUDICATE_TOPN = int(os.getenv("AZURECOST_ADJUDICATE_TOPN", "15"))

# ---------------------------------------------------------------------
# Local catalog directory (your own Azure Retail dumps per service/region/currency)
# ---------------------------------------------------------------------
# CATALOG_DIR:
# - Root folder where you store “catalog dumps” (your own extracted SKU universe).
# - Typically "catalog" in project root.
# - Your pricing engine reads from here to resolve SKU/meter matches deterministically.
CATALOG_DIR = os.getenv("AZURECOST_CATALOG_DIR", "catalog")
