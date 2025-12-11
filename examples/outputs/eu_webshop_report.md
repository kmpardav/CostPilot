# Azure Cost Architect – EU Webshop (sample)

> Sample markdown generated from the example workload. Real runs will vary based on live pricing catalogs and LLM choices.

## Scenario comparison

| Scenario | Monthly (EUR) | Yearly (EUR) | Notes |
| --- | ---: | ---: | --- |
| baseline | 741.10 | 8,893.20 | High availability SQL MI, premium Redis, 2× D2_v2 VMs |
| cost_optimized | 264.10 | 3,169.20 | Smaller burstable VMs, single SQL DB, basic Redis |

## Baseline highlights
- 2× D2_v2 VMs in West Europe for active-active web tier.
- Azure SQL Managed Instance (BC Gen5) for checkout resilience.
- Premium Redis cache for session/state management.
- 200 GB hot blob storage and ~150 GB outbound egress via NAT.

## Optimization notes
- Downgrade to burstable B-series compute for typical traffic periods.
- Swap SQL MI with single Azure SQL DB and geo-restore for DR.
- Lower Redis tier (C1) with cache warming for catalog reads.
- Add CDN in front of blob storage to keep egress closer to 100 GB/month.
