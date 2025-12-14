# Retail Prices API — LLM Steering Pack

## Goal
Design architectures whose resources can be priced deterministically via Azure Retail Prices API.

## Non-negotiable rules
1) Output serviceName EXACTLY from the allowed list.
2) Provide hint tokens for productName/skuName/meterName/armSkuName so the orchestrator can query/score.
3) If unsure, output UNKNOWN_SERVICE and propose 2 closest allowed services.

## Query recipe (the orchestrator will follow)
- Start with: serviceName eq '<service>'
- Add: armRegionName eq '<region>' when regional pricing
- Use: meterRegion='primary' for consistency
- Narrow with contains() using hint tokens
- Rank candidates with token overlap + unitOfMeasure + priceType sanity

## Allowed serviceName list + metadata
See llm_context.json (allowed_service_names + service_metadata).
