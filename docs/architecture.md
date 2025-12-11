# Architecture Overview

## Package layout (`azure_cost_architect/`)
- `cli.py`: CLI entrypoint orchestrating request parsing, planner/report model selection, cache resets, catalog refresh options, and output selection (Markdown/JSON/both).
- `config.py`: Central defaults for region, currency, cache paths, catalog directory, and model names.
- `llm/`: LLM-facing helpers.
  - `planner.py`: Builds the planning prompt, calls OpenAI Chat/Responses backends, repairs JSON if needed, and post-processes through schema validation and planner rules.
  - `reporter.py`: Turns the enriched plan into Markdown via the reporting prompt.
  - `json_repair.py`: Extracts/repairs JSON fragments when the model drifts from strict JSON output.
- `planner/`: Planner-side guardrails.
  - `validation.py`: Enforces the expected schema for scenarios/resources before pricing.
  - `rules.py`: Applies normalization and defaults (e.g., hours, billing hints) to stabilize planner output.
- `pricing/`: Pricing and catalog management.
  - `catalog.py`: Normalizes service names, ensures local JSONL catalogs per service/region/currency (fetching from the Azure Retail Prices API), and writes companion `.meta` files.
  - `retail_api.py`: Retrieves paged retail prices for a normalized service name.
  - `normalize.py`: Maps logical categories (e.g., `compute.vm`, `db.sql`) to Azure Retail `serviceName` values and provides SKU keyword matching.
  - `enrich.py`: Scores catalog rows for each resource, applies cache hits, computes totals/deltas, and emits debug traces when enabled.
  - `cache.py`: Loads/saves the best-price cache keyed by service/SKU/region/currency/billing/os type.
  - `scoring.py`, `units.py`: Compute comparable scores and normalize quantity units to monthly billing.
- `prompts.py`: System/user prompts for planner and reporter, including required services, schema, and reporting expectations.
- `reporting/`: Markdown/JSON helpers (table construction, file output).
- `utils/`: Shared utilities (I/O, formatting, logging helpers).

## End-to-end data flow
1. **CLI ingestion** (`cli.py`): reads free-text architecture input (stdin/interactive), parses flags (region, currency, LLM backend, refresh options), and loads/saves the pricing cache around a run.
2. **Planning** (`llm/planner.py`): submits the planner prompt (system + templated user) to OpenAI Chat or Responses API. Raw text is stored for debugging, JSON is extracted/repaired, validated, and passed through planner rules.
3. **Catalog preparation** (`cli.py` + `pricing/catalog.py`): discovers categories/regions in the plan and ensures local catalogs exist (optionally refreshed) before scoring. Catalogs are fetched from `prices.azure.com` and stored as JSONL plus `.meta` metadata.
4. **Pricing enrichment** (`pricing/enrich.py`): for each resource, normalizes service names, checks the price cache, loads the local catalog, scores candidates, computes unit/monthly/yearly costs, and aggregates totals + deltas vs. the baseline scenario. Optional JSONL debug traces capture top candidates and winners.
5. **Reporting** (`llm/reporter.py` + `reporting/`): feeds the enriched plan and original description into the reporter prompt to generate Markdown; optional JSON output is also written.

## Planner logic & prompt strategy
- **System prompt** (`prompts.py`) defines required Azure domains (compute, data, storage, analytics, networking, security, monitoring, backup/DR) and enforces production defaults (Key Vault, Log Analytics, Backup vault, egress). It specifies the JSON schema (metadata → scenarios → resources) and scenario labels.
- **User template** includes the free-text description and mode hint (`recommend`, `exact`, `auto`) to steer how strictly user SKUs are honored.
- **Validation/rules** (`planner/validation.py`, `planner/rules.py`) enforce schema integrity, fill defaults (hours, billing_model), and align categories to pricing expectations before enrichment.
- **JSON robustness** (`llm/json_repair.py`) extracts or repairs JSON if the model drifts, keeping downstream pricing deterministic.

## Pricing integration
- **Catalog-first**: pricing runs only against local catalogs built from the Azure Retail Prices API; no per-resource live calls during scoring.
- **Service normalization** (`pricing/normalize.py`) ensures planner categories map to retail `serviceName` values so catalog fetches and scoring align.
- **Scoring** (`pricing/enrich.py`, `pricing/scoring.py`): ranks catalog meters against requested SKUs/billing hints, computes quantities with `pricing/units.py`, and records deltas vs. baseline.
- **Outputs**: each resource receives unit price, unit of measure, monthly/yearly costs, SKU candidates, and any pricing error message for transparency.

## Caching strategy
- **Price cache** (`pricing/cache.py`): memoizes the best-priced meter per (service, SKU, region, currency, category, billing model, OS). CLI flags allow cache reset; cache persists between runs via `azure_price_cache.json` by default.
- **Catalog cache** (`pricing/catalog.py`): JSONL catalogs live under `catalog/` (configurable). CLI supports selective (`--refresh-catalog <category>`) or full (`--refresh-all-catalogs`) rebuilds.
- **Debug traces**: when `AZCOST_DEBUG_FILE`/`--debug-file` is set, enrichment appends JSONL scoring snapshots without failing the main flow.

## Error handling & resilience
- **Best-effort catalogs**: catalog fetch failures log warnings and still emit empty JSONL+`.meta` files so downstream steps continue.
- **Cache I/O**: loading/saving cache emits warnings instead of aborting runs.
- **Pricing fallback**: resources with missing prices are marked as `estimated` with notes; aggregates distinguish priced vs. estimated totals.
- **JSON recovery**: malformed planner responses trigger repair attempts before validation to avoid hard failures.

## Extensibility for new Azure services
1. **Categorization**: add or adjust logical categories in planner prompts (`prompts.py`) and planner rules if new telemetry is needed (e.g., metrics fields).
2. **Normalization**: extend `pricing/normalize.py` with mappings from the new category to the correct Azure Retail `serviceName` and SKU hints.
3. **Catalogs**: ensure the new service name is supported by `pricing/catalog.py` (no code change usually needed once normalized); refresh catalogs to populate JSONL files.
4. **Scoring/units**: update `pricing/scoring.py` or `pricing/units.py` if the new service uses distinct metering (transactions, bandwidth tiers, etc.).
5. **Reporting**: adjust reporting tables or narratives if new fields should appear; prompts already surface generic columns.

## Roles to features mapping
- **Cloud/Solution Architects**: drive scenario generation (`--mode`), review Markdown reports, and iterate architecture assumptions.
- **FinOps/Finance**: manage catalog freshness (`--refresh-*`), currency/region defaults, and inspect priced vs. estimated totals.
- **Developers**: rely on persistent cache for repeatability and use `--debug`/`--debug-file` to inspect SKU scoring.
- **Platform/SRE**: enforce regional defaults via environment variables, monitor egress/gateway assumptions, and validate HA/DR inclusions mandated by prompts.
