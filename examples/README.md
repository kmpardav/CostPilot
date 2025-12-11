# Examples

Sample assets for running Azure Cost Architect from the command line without digging into the test suite. Use them as smoke tests to verify your environment (OpenAI key, pricing catalogs, stdout formatting).

## Layout
- `workloads/`: Free-text architecture briefs fed to the CLI (`azure_cost`).
- `configs/`: Environment templates for secrets/overrides.
- `outputs/`: Offline plan/report/console captures to compare against your own runs.
- `run_eu_webshop.sh`: Convenience wrapper that wires the sample workload into the CLI.

## Quick verification
1. Copy `examples/configs/env.example` to `examples/configs/.env.local` and set `OPENAI_API_KEY` plus any region/currency overrides.
2. Run the sample script:
   ```bash
   ./examples/run_eu_webshop.sh
   ```
3. Inspect the emitted artifacts (by default under `examples/out/`):
   - `eu_webshop_plan.json`
   - `eu_webshop_report.md`

## Expected console output
Your logs should resemble the snippet below (exact SKUs may differ if the LLM chooses alternates). A full captured run lives in [`outputs/eu_webshop_console.md`](outputs/eu_webshop_console.md).

```text
Azure Personal Cost Architect – Local Tool
Designing architecture with LLM (Chat Completions, mode=recommend)…
Ensuring local catalogs in 'catalog' for currency='EUR'...
  - cache.redis @ westeurope (refresh=False)... OK → catalog/cache.redis__westeurope__EUR.jsonl
  - compute.vm @ westeurope (refresh=False)... OK → catalog/compute.vm__westeurope__EUR.jsonl
  - db.sqlmi @ westeurope (refresh=False)... OK → catalog/db.sqlmi__westeurope__EUR.jsonl
  - network.nat @ westeurope (refresh=False)... OK → catalog/network.nat__westeurope__EUR.jsonl
  - storage.blob @ westeurope (refresh=False)... OK → catalog/storage.blob__westeurope__EUR.jsonl
Enriching scenarios with local Azure Retail catalogs…
Generating final architecture + FinOps report (Markdown)…
──────────────────────── Cost Report ────────────────────────
```

## Offline comparison files
- [`outputs/eu_webshop_plan.json`](outputs/eu_webshop_plan.json): Sample enriched plan with per-scenario totals and deltas.
- [`outputs/eu_webshop_report.md`](outputs/eu_webshop_report.md): Markdown report excerpt for the sample workload.
- [`outputs/eu_webshop_console.md`](outputs/eu_webshop_console.md): Full console transcript from a reference run.

These files let you validate parsing/rendering flows without calling the APIs; real runs will rebuild catalogs and may choose different SKUs.
