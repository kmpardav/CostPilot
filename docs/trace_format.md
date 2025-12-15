# Trace format

Each CLI run writes a structured JSONL trace at `runs/<run_id>/trace.jsonl` (or the `--trace-path` override).

## Envelope
Every line is a standalone JSON object with:

- `timestamp`: ISO 8601 UTC timestamp
- `phase`: pipeline phase label (phase0_setup, phase1_planner, phase2_validation, phase3_retail_api, phase4_scoring, phase5_adjudication, phase6_costing, phase7_reporting)
- `scenario_id` / `resource_id` (when applicable)
- `payload`: structured details for the event

## Required phases

- **phase0_setup**: tool version, region, currency, hours/month, knowledge pack hash, LLM backend/models.
- **phase1_planner**: planner LLM inputs/outputs per attempt (system/user prompts, model, raw response, parsed JSON, parse errors, validation errors). Repairs use `phase1_planner_repair`.
- **phase2_validation**: rule changes, canonical serviceName mapping, validation errors, final canonical plan path.
- **phase3_retail_api**: Retail API/catalog fetch metadata (serviceName, region, URLs, page counts, item counts) and per-resource catalog lookups.
- **phase4_scoring**: top candidate meters and scores per resource.
- **phase5_adjudication**: adjudicator prompt/response and selected candidate details.
- **phase6_costing**: quantity model, unit mapping, unit price, units, monthly/yearly costs.
- **phase7_reporting**: enriched plan path and report path written for the run.

The file is append-only and human-readable. Inspecting it with standard tools (e.g., `jq`, `less`) is sufficient to reconstruct a full end-to-end execution without other artifacts.
