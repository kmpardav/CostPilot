#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
config.py

This module holds configuration constants and defaults for the CostPilot / AzureCost tool.

IMPORTANT CONCEPT: "required categories"
---------------------------------------
Your tool uses a small set of INTERNAL "canonical guardrail families" to validate
that a scenario plan is not missing core building blocks.

These canonical families are *NOT* the same as the Azure Retail "serviceFamily" values you see in Excel.
They are an internal abstraction used for completeness checks across scenarios.

Example:
- Excel family: "Databases"
- Internal guardrail family: "db"

The mapping from whatever the user/LLM writes to these canonical guardrail families
is handled in categories.py (aliases + normalization).
"""

import os

# ---------------------------------------------------------------------
# LLM model names (Chat Completions path)
# ---------------------------------------------------------------------
# Keep these in env so you can switch models without code changes.
MODEL_PLANNER = os.getenv("AZURECOST_PLANNER_MODEL", "gpt-5.1")
MODEL_REPORTER = os.getenv("AZURECOST_REPORTER_MODEL", "gpt-5.1")
MODEL_ADJUDICATOR = os.getenv("AZURECOST_ADJUDICATOR_MODEL", MODEL_PLANNER)

# ---------------------------------------------------------------------
# LLM model names (Responses API path or any alternative backend naming)
# ---------------------------------------------------------------------
MODEL_PLANNER_RESPONSES = os.getenv("AZURECOST_PLANNER_RESP_MODEL", MODEL_PLANNER)
MODEL_REPORTER_RESPONSES = os.getenv("AZURECOST_REPORTER_RESP_MODEL", MODEL_REPORTER)

# ---------------------------------------------------------------------
# Backend default: "chat" vs "responses" (or any internal backend enum you use)
# ---------------------------------------------------------------------
DEFAULT_LLM_BACKEND = os.getenv("AZURECOST_LLM_BACKEND", "chat")

# ---------------------------------------------------------------------
# Scenario comparison safeguards
# ---------------------------------------------------------------------
DEFAULT_COMPARE_POLICY = os.getenv("AZURECOST_COMPARE_POLICY", "soft_compare")

# INTERNAL guardrail families you want to always be present (at least once) in a scenario plan.
#
# These are NOT Azure Retail "serviceFamily" strings.
# They are YOUR canonical keys that categories.py will normalize into.
#
# Why these 5?
# - compute   : something runs the workload
# - db        : a database tier exists (when needed)
# - cache     : caching tier exists (when needed)
# - network   : connectivity components exist
# - storage   : persistent object/block/file storage exists
#
# NOTE:
# - You can keep this list minimal to avoid false negatives.
# - If you expand it, do it only when you are sure the planner/repair loop can satisfy it.
DEFAULT_REQUIRED_CATEGORIES = [
    "compute",
    "db",
    "cache",
    "network",
    "storage",
]

# How many candidate items to consider during adjudication (if you do ranking/voting)
DEFAULT_ADJUDICATE_TOPN = int(os.getenv("AZURECOST_ADJUDICATE_TOPN", "15"))

# ---------------------------------------------------------------------
# Local catalog directory (your own Azure Retail dumps per service/region/currency)
# ---------------------------------------------------------------------
# Usually this is a folder named "catalog" in the project root.
# The tool reads catalog JSON/CSV/etc from here to resolve and price SKUs.
CATALOG_DIR = os.getenv("AZURECOST_CATALOG_DIR", "catalog")
