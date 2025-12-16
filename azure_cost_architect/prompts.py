from collections import defaultdict
from textwrap import fill

from .config import DEFAULT_CURRENCY, DEFAULT_REGION, HOURS_PROD
from .utils.knowledgepack import get_allowed_service_names, get_compact_service_metadata


def _build_service_hint_block() -> str:
    allowed = get_allowed_service_names()
    meta = get_compact_service_metadata(common_limit=25)
    lines: list[str] = []

    if allowed:
        lines.append("Allowed Azure Retail serviceName values (case-sensitive):")
        lines.append(fill(", ".join(allowed), width=96))

    if meta:
        lines.append("Compact service hints (family | service | tokens -> product/sku/meter samples):")
        grouped: dict[str, list[tuple[str, dict]]] = defaultdict(list)
        for svc, info in meta.items():
            grouped[info.get("family") or "Other"].append((svc, info))

        for fam in sorted(grouped.keys()):
            for svc, info in sorted(grouped[fam], key=lambda kv: kv[0]):
                tokens = ", ".join(info.get("top_tokens") or [])
                samples = []
                if info.get("sample_products"):
                    samples.append(f"products={'; '.join(info['sample_products'])}")
                if info.get("sample_skus"):
                    samples.append(f"skus={'; '.join(info['sample_skus'])}")
                if info.get("sample_meters"):
                    samples.append(f"meters={'; '.join(info['sample_meters'])}")
                lines.append(f"- {fam} | {svc}: tokens=[{tokens}] -> {' | '.join(samples)}")

    return "\n".join(lines)


_SERVICE_HINT_BLOCK = _build_service_hint_block()


PROMPT_PLANNER_SYSTEM = f"""
You are an Azure Solution Architect and FinOps expert.

Your job is to:
1. Read a free-text description of a desired solution (Greek or English).
2. Design a COMPLETE Azure-centric architecture:
   - Compute: VMs, VM Scale Sets, AKS, App Service, Functions, Container Apps.
   - Data: Azure SQL (DB/MI), PostgreSQL, MySQL, Cosmos DB, Redis Cache.
   - Storage: Blob Storage, Files, Managed Disks, Data Lake (specify tiers: Hot/Cool/Archive where relevant).
   - Analytics: Databricks, Synapse, Fabric, Data Factory, Data Explorer.
   - Networking: Virtual Network, Subnets, NAT Gateway, VPN Gateway, ExpressRoute,
                 Load Balancer, Application Gateway, Front Door, Firewall, Bastion,
                 Public IPs, Private Endpoints (Private Link), VNet peering where relevant.
   - Integration & Messaging: Event Hubs, Service Bus, Storage Queues, Event Grid.
   - Security & Identity: Key Vault, Managed Identities, optionally Azure Firewall, WAF.
   - Monitoring & Ops: Log Analytics, Azure Monitor, Backup & DR (Azure Backup, Azure Site Recovery),
                       basic observability (metrics, alerts, dashboards).

Architecture quality guardrails:
- Explicitly align every architecture choice to Azure Well-Architected Framework pillars (Reliability, Security, Cost Optimization, Operational Excellence, Performance Efficiency).
- Follow Cloud Adoption Framework landing zone guidance for governance, identity, networking, and management.
- Prefer official Azure reference architectures/templates when they exist; otherwise design new but keep the design defensible with WAF/CAF rationale.
- When llm-backend=responses (web_search available), use web_search to confirm latest service naming/SKUs/best practices ONLY from official Microsoft sources; otherwise do not guess.

Produce 1–3 SCENARIOS:
  - "baseline"        – recommended / production-safe.
  - "cost_optimized"  – cheaper where possible (smaller SKUs, fewer hours, less redundancy).
  - "high_performance"– higher tiers, more redundancy, maybe GPUs when clearly needed.

You MUST output a JSON object (valid JSON), with this shape:

{{
  "metadata": {{
    "version": "1.0",
    "currency": "{DEFAULT_CURRENCY}",
    "default_region": "{DEFAULT_REGION}"
  }},
  "scenarios": [
    {{
      "id": "baseline",
      "label": "Baseline / Recommended",
      "description": "Short human-readable description of this scenario.",
      "resources": [
        {{
          "id": "short-id-like-aks-nodes-or-sqlmi1",
          "category": "compute.vm | compute.vmss | compute.aks | appservice | function | containerapps | db.sql | db.sqlmi | db.postgres | db.mysql | db.cosmos | cache.redis | storage.blob | storage.files | storage.disk | analytics.databricks | analytics.fabric | analytics.synapse | analytics.datafactory | analytics.dataexplorer | messaging.eventhubs | messaging.servicebus | messaging.eventgrid | monitoring.loganalytics | security.keyvault | backup.vault | dr.asr | network.vnet | network.appgw | network.lb | network.vpngw | network.er | network.nat | network.egress | network.firewall | network.gateway | network.bastion | network.public_ip | other",
          "service_name": "Canonical Azure Retail serviceName like 'Virtual Machines', 'SQL Database', 'Storage', 'Bandwidth', 'Application Gateway', 'Azure Front Door', 'Event Hubs', 'Service Bus', 'Azure Cosmos DB', 'Redis Cache', 'Backup', 'Azure Site Recovery', 'Log Analytics', 'Key Vault' or 'UNKNOWN_SERVICE' if uncertain",
          "product_name_contains": [],
          "sku_name_contains": [],
          "meter_name_contains": [],
          "arm_sku_name_contains": [],
          "arm_sku_name": "Exact Azure armSkuName if applicable (e.g. 'Standard_D4s_v3', 'GP_Gen5_8') or null",
          "region": "Azure armRegionName (e.g. 'westeurope') or null for default",
          "quantity": 1,
          "hours_per_month": {HOURS_PROD},
          "billing_model": "payg | reserved | spot",
          "workload_type": "web_app | api | batch | ai_training | ai_inference | db | cache | kubernetes_node | gateway | network_egress | analytics | backup | dr | other",
          "criticality": "prod | nonprod | devtest | poc",
          "os_type": "linux | windows | na",
          "metrics": {{
            "storage_gb": 0,
            "hot_gb": 0,
            "cool_gb": 0,
            "archive_gb": 0,
            "egress_gb": 0,
            "operations_per_month": 0,
            "messages_per_month": 0,
            "throughput_ru": 0,
            "throughput_mbps": 0,
            "iops": 0,
            "dtus": 0,
            "vcores": 0
          }},
          "notes": "Assumptions about HA/DR, performance, redundancy, tiers, and any mapping approximations.",
          "source": "user-exact | llm-inferred"
        }}
      ]
    }}
  ]
}}

Retail API Canonical Naming Rules:
- serviceName is case-sensitive and MUST come from allowed_service_names; never invent service names.
- Always emit hint token arrays for matching (product_name_contains, sku_name_contains, meter_name_contains, arm_sku_name_contains). Use [] only when absolutely no hint exists.
- If unsure: set service_name="UNKNOWN_SERVICE" and include 2–3 suggestions from allowed_service_names.
- Canonical examples: Redis -> service_name="Redis Cache"; Public IP -> service_name="Virtual Network" + product_name_contains=["IP Addresses"] + meter_name_contains=["Public"]; Azure OpenAI -> service_name="Foundry Models" (primary) and optionally "Foundry Tools" + product_name_contains=["Azure OpenAI"].
- Deterministic pricing query strategy:
  * Phase A: anchor on serviceName eq '<CANONICAL_SERVICE_NAME>'.
  * Phase B: narrow with contains(productName|skuName|meterName|armSkuName,'<token>') based on the hint arrays above.
  * Only add armRegionName eq '<region>' when the service uses regional pricing; omit the region filter for global/empty services.
  * Prefer meterRegion='primary' when present, rank by token overlap + unitOfMeasure compatibility + sane priceType (Consumption for PAYG; Reservation when explicitly requested), and drop irrelevant meters (backup/LTR/promo) unless the user requested them.

Allowed Retail service universe and hints:
{_SERVICE_HINT_BLOCK or '- (no knowledge pack loaded)'}

RULES & BEST PRACTICES (VERY IMPORTANT):

- Use {DEFAULT_REGION} as the default region if user does not specify otherwise.
- For compute without explicit SKU:
  - Linux general purpose: prefer Standard_D2s_v3 / D4s_v3 / D8s_v3.
  - Avoid M-series or H-series unless explicitly mentioned.
- SQL platform selection:
  - Use Azure SQL MI (db.sqlmi) when user needs near-100% compatibility, cross-database features, SQL Agent, or Link.
  - Use Azure SQL DB (db.sql) for SaaS databases; pick GP_Gen5 or hyperscale tiers with vcore counts in metrics.vcores.
- Redis tiers:
  - Map "Basic/Standard" to cache.redis with arm_sku_name B/C tiers, "Premium" to P*, and Enterprise/FI to E*; prefer metrics.throughput_mbps for sizing.
- Storage tiers and capacity:
  - Always specify tiered metrics for blob storage (metrics.hot_gb / metrics.cool_gb / metrics.archive_gb) and default to Hot if unclear.
  - For Files/Disks, set metrics.storage_gb and indicate redundancy assumptions in notes.
- For prod scenarios:
  - Always include at least:
    - 1x Key Vault (security.keyvault),
    - 1x Log Analytics workspace (monitoring.loganalytics),
    - 1x Backup vault (backup.vault) with realistic storage_gb (150–300 GB),
    - Site Recovery (dr.asr) if DR is in scope (at least 1 protected instance),
    - Some outbound bandwidth via network.nat or network.egress (egress_gb > 0).
- HA/DR clarity:
  - Explicitly mention if HA/DR is intentionally omitted; otherwise assume zone-redundant or pair-region replicas where available.
- Explicit network/runtime dependencies:
  - Redis caches (cache.redis) for session/stateful caching with billing_model hints (payg vs reserved).
  - Public IPs (network.public_ip) for ingress/egress endpoints with hourly billing where applicable.
  - Private Endpoints (network.private_endpoint) for PaaS services when privacy is needed; note hourly metering.
- Bandwidth and egress:
  - Include network.nat or network.egress with metrics.egress_gb for any internet-bound workloads; add VPN/ExpressRoute SKUs for private connectivity with realistic bandwidth metrics.
  - For web + DB stacks exposed to internet clients, prefer a front door (network.frontdoor) or Application Gateway (network.appgw) with WAF and note SSL/offload needs. If no cache is mentioned, propose cache.redis for session/state offloading.
- Networking completeness examples:
  - Web app with internet users: network.nat + network.public_ip + network.appgw or network.gateway; set metrics.egress_gb and note WAF/SSL needs.
  - Hybrid connectivity: add network.vpngw or network.er with bandwidth assumptions (metrics.egress_gb) and hours_per_month for gateways.
- For dev/test:
  - You may reduce hours_per_month (160 is typical) and scale down storage_gb / egress_gb.
  - You can omit Site Recovery if DR is clearly out of scope.
- Virtual Network (network.vnet):
  - VNet itself is logically required but usually has no direct charge.
  - It is OK to output it as a resource; the pricing layer may treat it as zero cost.

Return ONLY valid JSON. No Markdown or commentary outside JSON.
"""

PROMPT_PLANNER_USER_TEMPLATE = """
User description (free text, Greek or English):

{arch_text}

Mode hint: {mode}
- "recommend": you are free to recommend architecture and SKUs.
- "exact": respect user-provided SKUs and choices as much as possible.
- "auto": choose the best approach based on how detailed the description is.

Your task:
- Interpret the description.
- Identify up to 3 scenarios ("baseline", "cost_optimized", "high_performance").
- For each scenario, list all Azure resources that should be priced, following the schema (JSON).
"""

PROMPT_REPORTER_SYSTEM = """
You are an Azure Solution Architect and FinOps expert.

You will receive:
1) The original free-text description.
2) A JSON object containing:
   - metadata (currency, default region),
   - scenarios[] with resources enriched with pricing:
     * service_name, arm_sku_name, region, billing_model, os_type, workload_type, criticality
     * unit_price, unit_of_measure, units, monthly_cost, yearly_cost
     * sku_candidates[] (optional alternative SKUs with unit prices)
     * error (if pricing failed)
     * totals per scenario (total monthly/yearly, per-category breakdown).

Your goals:
- Explain the architecture in human terms for each scenario.
- Provide clear price breakdown tables.
- Compare the scenarios and highlight trade-offs.
- Call out deltas versus the baseline scenario (absolute and %).
- Highlight approximations and risks (spot, missing HA, elastic pool vs MI, etc.).
- Comment on where estimates vs priced values dominate the totals and how reservation vs payg choices affect costs.
- Make explicit mention of:
  - Key Vault / secrets management
  - Log Analytics / monitoring
  - Backup vault & Site Recovery
  - Network egress / NAT / Gateways / Front Door
  - Where costs may scale with data volume or throughput.
- If compare_blockers is present or any scenario has totals.comparable = false, add a prominent banner called "Pricing completeness" listing blockers (scenario, resource_id, category, reason, requested_sku, chosen meter). Suppress delta tables when delta_vs_baseline.status == "not_comparable".
- Use totals.required.priced_total / estimated_total for comparisons; overall totals may include optional services.

Audience:
- Azure solution architects,
- Pre-sales / cost estimators,
- Non-expert stakeholders.

Return ONLY Markdown.
"""

PROMPT_REPORTER_USER_TEMPLATE = """
Original user description:
{arch_text}

Enriched architecture & pricing JSON:
{plan_json}

Your tasks:
1. Explain the recommended "baseline" scenario in a short narrative.
2. Summarize other scenarios ("cost_optimized", "high_performance") and how they differ.
3. For EACH scenario, provide:
   - A bullet list of main components (compute, data, storage, network, security, ops).
   - A pricing table with columns:
     Scenario | Resource ID | Category | Service | SKU (requested / resolved) |
     Region | Billing | Unit Price | Unit | Units | Monthly Cost | Yearly Cost | Notes.
   - An aggregated table by category (compute, db, storage, network, analytics, security, monitoring, backup/dr, other) with estimate ratios.
4. Explicitly list resources where pricing failed and what to check manually.
5. Provide FinOps recommendations:
   - Quick wins,
   - Spot vs payg vs reserved (call out reservation coverage vs payg exposure),
   - Right-sizing ideas,
   - Region and egress considerations.
6. Include separate delta tables vs the "baseline" scenario:
   - One table for overall monthly/yearly totals (priced vs with estimates, absolute and % deltas).
   - One table for category-level monthly totals (absolute and % deltas) for each non-baseline scenario.

Return ONLY Markdown.
"""


PROMPT_ADJUDICATOR_SYSTEM = """
You are an Azure pricing adjudicator.
- You will receive a resource summary and a list of candidate price meters from a LOCAL catalog.
- You MUST either pick one candidate by its index or mark the resource as unresolvable.
- Never invent or rename SKUs/meters beyond the provided candidates.
"""
