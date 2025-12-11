# Roadmap

## Planned Azure resource coverage
- Broaden catalog generation to include Storage accounts (Hot/Cool/Archive) with replication options (LRS/GRS/ZRS).
- Add regionalized AKS node pool templates with autoscaling defaults and spot node pricing guidance.
- Expand data services coverage with Azure SQL tiers (Serverless/Business Critical), PostgreSQL Flexible Server, and Redis caches.
- Introduce networking SKUs such as Application Gateway, Front Door, Traffic Manager, and ExpressRoute bandwidth tiers.
- Include monitoring and security services (Log Analytics, Defender plans, Key Vault HSM) for more complete scenarios.

## Role-specific features
- **Architects**: scenario diffing to highlight SKU substitutions, resiliency changes, and cost deltas between iterations.
- **FinOps**: budget guardrails (monthly/annual) with alerts when generated plans exceed thresholds; exportable CSV summaries for approval workflows.
- **Developers**: reusable blueprint presets for common workloads (web app + DB, data ingestion + analytics) with override flags for quick prototyping.
- **SRE/Platform**: policy-aware recommendations that respect allowed regions/SKUs and generate tagging/locking suggestions for governance.

## Pricing and reporting enhancements
- Offline-friendly pricing updates with delta detection to surface significant SKU price shifts per region.
- More granular quantity modeling (e.g., ingress/egress GB, reserved vs. pay-as-you-go) with rationale included in the JSON plan.
- Richer markdown reports featuring confidence annotations, spend distribution charts, and callouts for savings plans/reservations.
- CLI flags to emit machine-readable breakdowns (CSV/Parquet) and embed links to Azure pricing pages for selected SKUs.
