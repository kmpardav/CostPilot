# CostPilot – App Service adjudication exact-match fixture

- **Scenario**: Baseline (Premium v3 App Service)
- **Adjudication**: Enabled (top 1 requested; forced exact-match added). The adjudicator selected **P1v3** over cheaper **P0v3**, honoring the requested tier.
- **Required monthly total** (compute/db/cache/network/storage): **EUR 211.70**
- **Overall monthly total**: **EUR 211.70**

## Resources
| Scenario | Resource ID | Category | Service | SKU (requested/resolved) | Region | Billing | Unit Price | Unit | Units | Monthly Cost |
|---|---|---|---|---|---|---|---|---|---|---|
| baseline | appsvc-plan-prod | appservice.plan | Azure App Service | P1v3 / P1v3 Windows App Service | westeurope | payg | EUR 0.29 | 1 Hour | 730 | EUR 211.70 |

## Comparability
- All required categories are fully priced; adjudication matched the requested SKU without manual overrides.
- No blockers present.
