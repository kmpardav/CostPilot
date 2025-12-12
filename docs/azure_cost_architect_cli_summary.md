# Azure Cost Architect CLI Overview

This document summarizes the main Azure Personal Cost Architect command-line interfaces, their defaults, outputs, environment variables, and side effects.

## Primary CLI (`azure_cost_architect/cli.py`)

- **Purpose**: Generate costed architecture plans from text input using OpenAI, relying on locally cached catalogs.
- **Operation**: Reads user architecture text (from stdin or interactively), plans with the selected LLM backend, warms needed catalogs, enriches pricing strictly from those catalogs, and emits Markdown and/or JSON artifacts.

### Flags and Defaults
- `--mode {recommend|exact|auto}` (default `recommend`): Controls how strictly user-specified SKUs are followed.
- `--region` / `--currency`: Default to `None`; they fall back to plan metadata or config defaults (`westeurope` / `EUR`).
- `--llm-backend {chat|responses}`: Defaults to `AZURECOST_LLM_BACKEND` or `chat`; switches between Chat Completions and Responses API.
- `--output-format {markdown|json|both}`: Defaults to `markdown`.
- `--output-prefix`: Default `azure_cost`; names `{prefix}_plan.json` and `{prefix}_report.md` (Markdown is skipped if format is `json`).
- Logging and debugging: `--log-level` default `AZURECOST_LOG_LEVEL` or `INFO`; `--debug` toggles verbose mode; `--debug-file` defaults to `AZCOST_DEBUG_FILE` and writes a JSONL scoring trace when provided.
- Cache/catalog controls: `--reset-cache` deletes the local price cache before use (`azure_price_cache.json` by default); `-r/--refresh-catalog` (repeatable) refreshes specific categories; `--refresh-all-catalogs` refreshes all categories required by the current plan.

### Environment Variables
- Required: `OPENAI_API_KEY` must be set for API calls.
- Optional defaults: `AZURECOST_LLM_BACKEND`, `AZURECOST_LOG_LEVEL`, `AZCOST_DEBUG_FILE`, plus region/currency/cache overrides via configuration (`AZURECOST_DEFAULT_REGION`, `AZURECOST_DEFAULT_CURRENCY`, `AZURECOST_CACHE_FILE`).

### Outputs and Side Effects
- Artifacts: `{prefix}_plan.json` (always) and `{prefix}_report.md` when `output-format` is `markdown` or `both`; the report is printed to console when generated.
- Catalogs: Builds or refreshes local catalogs in `CATALOG_DIR` for each `(category, region, currency)` encountered; behavior depends on `--refresh-all-catalogs` or matching `--refresh-catalog` entries.
- Cache: Loads and saves the shared price cache; `--reset-cache` removes it before enrichment.

## Catalog Builder (`azure_cost_architect/build_catalog.py`)

- **Purpose**: Standalone helper to list or build local Azure Retail catalogs without running the full architect flow.

### Options and Defaults
- Location/locale: `--catalog-dir` default `CATALOG_DIR`; `--region` default `DEFAULT_REGION`; `--currency` default `DEFAULT_CURRENCY`.
- Selection: `--categories` comma-separated list; `--all-supported` builds a predefined set of common categories with duplicates removed.
- Refresh/list: `--refresh` forces re-fetch even if files exist; `--list` prints existing catalogs (with item counts/warnings) and exits.
- Logging: `--log-level` (default `INFO`).

### Artifacts and Side Effects
- Writes or updates catalog JSONL files under the chosen directory via `ensure_catalog`; logs warnings for empty catalogs and reports metadata via `get_catalog_info`.
- `--list` mode produces console output only and does not modify files.
