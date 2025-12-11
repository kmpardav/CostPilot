# Azure Cost Architect

## Product overview
Azure Cost Architect is a CLI assistant that turns free-text architecture descriptions into costed Azure scenarios. It combines LLM planning, Azure Retail Prices catalogs, and markdown reporting so engineers, FinOps teams, and leadership can iterate on cloud designs with transparent pricing assumptions.

## Architecture flow
```
CLI (`azure_cost`)
        ↓ (collects architecture brief, flags)
Planners (LLM -> JSON scenarios)
        ↓ (resource categories per region)
Pricing engine (local catalogs + Retail Prices API + scoring)
        ↓ (enriched plan with SKUs & monthly costs)
Reporting (Markdown + JSON artifacts)
```

## Prerequisites
- Python 3.9+ (tested with the version declared in `pyproject.toml`).
- Access to the Azure Retail Prices API (HTTPS egress required) to refresh local catalogs.
- OpenAI API key available as `OPENAI_API_KEY` (or your configured environment for the selected backend/models).
- Optional: set `AZURECOST_DEFAULT_REGION`, `AZURECOST_DEFAULT_CURRENCY`, and `AZURECOST_CACHE_FILE` to override defaults.

## Installation
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

## Quickstart
```bash
# Inspect available flags
azure_cost --help

# Generate a report from a free-text description (interactive stdin)
azure_cost --output-prefix demo_finops <<'TEXT'
Global web app with EU users, active-active Cosmos DB, and monthly traffic ~50M requests.
TEXT

# View artifacts
cat demo_finops_report.md
jq '.' demo_finops_plan.json
```

## Sample outputs
- **Markdown report**: scenario comparison tables with SKUs, unit prices, monthly estimates, and notes on assumptions.
- **JSON plan**: LLM-produced architecture with pricing enrichment (services, SKUs, meters, quantities, monthly totals).
- **Catalog files**: cached Azure Retail Prices JSONL files per service/region/currency under `catalog/` after the first run.

## Role-based workflows
- **Cloud/solution architects**: iterate on architecture scenarios quickly by switching `--mode` between `recommend` and `exact` to guide the LLM.
- **FinOps/finance**: refresh pricing catalogs (`--refresh-all-catalogs` or `--refresh-catalog <category>`) and export markdown reports for reviews.
- **Developers**: keep a local cache for repeatable estimates and trace scoring with `--debug` or `--debug-file` when tuning SKUs.
- **Platform/SRE**: set defaults via environment variables (`AZURECOST_DEFAULT_REGION`, `AZURECOST_DEFAULT_CURRENCY`) for consistent regional assumptions.

## Troubleshooting
- Enable verbose logs with `--log-level DEBUG` or `--debug` to inspect pricing lookups and LLM prompts.
- If catalogs are stale or missing, run with `--refresh-all-catalogs` or delete the cache file referenced by `AZURECOST_CACHE_FILE`.
- Ensure outbound HTTPS access to `https://prices.azure.com` (Azure Retail Prices API) and to OpenAI endpoints; failures manifest as pricing/LLM errors.
- Check that `OPENAI_API_KEY` is set before running; missing keys will cause authentication errors when calling the planner/reporter models.

## FAQ
- **Which entrypoint should I use?** Installable console scripts include both `azure_cost` (used in the examples) and `azure-cost`; both call the same CLI.
- **What does the tool output?** By default, it writes a markdown report. Use `--output-format json` or `both` to also write the enriched plan.
- **How are prices fetched?** The CLI builds local catalogs from the Azure Retail Prices API and then performs scoring against those catalogs instead of per-resource live calls.
- **Can I control models?** Set `AZURECOST_PLANNER_MODEL` and `AZURECOST_REPORTER_MODEL` (or their `*_RESP_MODEL` equivalents) to override the defaults.

## Additional resources
- Browse the test suite for usage patterns and expectations: [`azure_cost_architect/tests`](azure_cost_architect/tests).
- Core CLI entrypoint and configuration live in [`azure_cost_architect/cli.py`](azure_cost_architect/cli.py) and [`azure_cost_architect/config.py`](azure_cost_architect/config.py).
- Upcoming capabilities and focus areas are tracked in the [`docs/roadmap.md`](docs/roadmap.md).
