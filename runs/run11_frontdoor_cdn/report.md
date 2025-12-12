## 1. Baseline / Recommended – Short Narrative

The **baseline** scenario is a globally distributed media delivery site built on **Azure Front Door Premium** with integrated CDN. End users connect to Front Door, which provides global anycast entry, WAF, rules engine, and caching. Front Door pulls:

- **Dynamic content** from a **Linux App Service Premium v3 plan** in West Europe (2 instances for HA).
- **Media files** from a **GRS Blob Storage** account (10 TB total, mostly Hot/Cool) via **Private Endpoint**, so origin is not publicly exposed.

The app tier uses **Azure Cache for Redis** to offload session/metadata, and is integrated with a **VNet** for private endpoints and a **NAT Gateway** for controlled outbound internet access.

Security and operations are handled by:

- **Azure Key Vault** for TLS certificates and application secrets.
- **Log Analytics** as a central workspace for App Service, Front Door, and platform logs/metrics.
- **Recovery Services Vault (Backup)** for App Service content/config backups.
- **Azure Site Recovery (ASR)** placeholder for any IaaS-based components that might be added.

The design targets ~**50 TB/month global egress** via Front Door, with ~200M requests/month, and provides a balanced mix of performance, security (private origin, WAF, Key Vault), and observability (Log Analytics) suitable for a production media site.

> Important: Many prices in the JSON are missing or placeholder “100 USD” category totals. Treat the numeric totals below as **order-of-magnitude** only and validate with the Azure Pricing Calculator for final estimates.

---

## 2. Other Scenarios – High-Level Differences

### Cost Optimized

- **Front Door Standard** instead of Premium: fewer advanced rules/features, still supports CDN and 50 TB/month egress.
- **Smaller App Service footprint**: single Premium v3 instance, using **1‑year reserved capacity** (but the reservation pricing in the JSON is clearly malformed; treat as “cheaper than PAYG” but re‑price).
- **LRS Blob Storage** with slightly less total capacity and more aggressive Cool/Archive usage.
- **Smaller Redis (Basic C0)**: cheaper but no SLA and no replication.
- **Reduced Log Analytics ingestion** (~200 GB/month) and smaller backup footprint.
- Same general pattern: Front Door + App Service + Blob + Redis + Key Vault + Log Analytics + Backup, but tuned down for cost and with lower HA/DR guarantees.

### High Performance / Scale

- **Front Door Premium** with higher throughput assumptions: ~75 TB/month egress and 400M requests.
- **Scaled-out App Service**: Premium v3 P2v3 with 3 instances (1‑year reserved), more CPU/RAM for spikes and complex logic.
- **Premium ZRS Blob Storage** with more Hot data and higher total capacity (15 TB) for low latency and higher throughput.
- **Premium Redis (P1)** with persistence and VNet integration for high QPS and resilience.
- **More NAT Gateways** (2) and larger backup/ASR footprint.
- **Premium Key Vault** for HSM-backed keys and higher security.
- **Higher Log Analytics ingestion** (~800 GB/month) and more frequent backups.

This scenario prioritizes performance, resilience, and security over cost, and is intended for heavy global traffic and frequent spikes beyond 50 TB/month.

---

## 3. Scenario Details

### 3.1 Baseline Scenario

#### Main Components (Baseline)

- **Compute**
  - App Service Plan: Premium v3 (Linux), 2 instances (P0v3 resolved), West Europe.
  - Web App(s) running on that plan.

- **Data & Storage**
  - Media Blob Storage: Standard GRS, ~10 TB (Hot/Cool/Archive mix).
  - Log Storage: Separate Standard LRS account (~1 TB, mostly Cool).

- **Network**
  - Azure Front Door Premium (global) with CDN, WAF, rules engine.
  - VNet for App Service integration and private endpoints.
  - NAT Gateway + Standard Public IP for outbound traffic.
  - Private Endpoint for Blob media origin.

- **Security**
  - Azure Key Vault (Standard) for secrets, keys, and certificates.
  - WAF on Front Door.

- **Monitoring & Operations**
  - Log Analytics workspace (PerGB2018) ~500 GB/month ingestion.
  - Recovery Services Vault (Backup) for App Service content/config.
  - Azure Site Recovery (ASR) placeholder for any IaaS components.

#### Pricing Table – Baseline

> Note: Many items are missing prices or are estimated. “100.00” category totals in `totals.by_category` are placeholders, not actual resource prices.

| Scenario  | Resource ID           | Category               | Service          | SKU (requested / resolved)                         | Region     | Billing | Unit Price | Unit          | Units  | Monthly Cost (USD) | Yearly Cost (USD) | Notes |
|-----------|-----------------------|------------------------|------------------|----------------------------------------------------|------------|---------|-----------:|---------------|-------:|--------------------:|-------------------:|-------|
| baseline  | afd-premium-global    | network.gateway        | Azure Front Door | Premium_AzureFrontDoor / (missing)                | global     | payg    |    n/a     | n/a           |  n/a  | n/a                | n/a               | 50 TB/mo egress, 200M req; WAF + CDN. Must price manually. |
| baseline  | appsvc-plan-prod      | appservice             | App Service      | P1v3 (req) / P0v3 (resolved)                      | westeurope | payg    |   0.089    | 1 Hour        | 1460  | 129.94             | 1559.28           | 2× Linux Premium v3 instances; HA across AZs. |
| baseline  | appsvc-webapp-prod    | appservice             | App Service      | (logical) / included                               | westeurope | payg    |   0.000    | Included      |    1  | 0.00               | 0.00              | Web app billed via plan. |
| baseline  | storage-media-blob    | storage.blob           | Storage          | Standard_GRS / (tiered est.)                      | westeurope | payg    |   est      | GB mix        |  –    | 10.90              | 130.80            | 8 TB Hot, 2 TB Cool, 240 GB Archive; **storage only**, egress not modeled. |
| baseline  | storage-logs-blob     | storage.blob           | Storage          | Standard_LRS / (tiered est.)                      | westeurope | payg    |   est      | GB mix        |  –    | 2.01               | 24.17             | Log storage; mostly Cool. |
| baseline  | redis-cache-session   | cache.redis            | Cache for Redis  | Standard_C1 / (missing)                           | westeurope | payg    |    n/a     | n/a           |  n/a  | n/a                | n/a               | Session/metadata cache; must price manually. |
| baseline  | vnet-app-prod         | network.vnet           | Virtual Network  | (logical) / Virtual Network                        | westeurope | payg    |   0.000    | VNet          |    1  | 0.00               | 0.00              | No direct VNet charge; data transfer billed elsewhere. |
| baseline  | natgw-egress          | network.nat            | Bandwidth        | Standard / Standard Inter-AZ Data Transfer Out    | westeurope | payg    |   0.010    | 1 GB          | 1000  | 10.00              | 120.00            | 1 TB/mo outbound via NAT. Does not include NAT hourly fee. |
| baseline  | publicip-natgw        | network.public_ip      | Public IP        | Standard / (missing)                               | westeurope | payg    |    n/a     | n/a           |  n/a  | n/a                | n/a               | Standard Public IP for NAT; must price manually. |
| baseline  | pe-blob-media         | other                  | Private Link     | Standard_PrivateEndpoint / (missing)              | westeurope | payg    |    n/a     | n/a           |  n/a  | n/a                | n/a               | Private Endpoint + data processed; must price manually. |
| baseline  | kv-prod               | security.keyvault      | Key Vault        | standard / Standard                                | westeurope | payg    |   0.03     | 10K ops       |   50  | 1.50               | 18.00             | ~500k ops/mo. No HSM. |
| baseline  | loganalytics-prod     | monitoring.loganalytics| Log Analytics    | PerGB2018 / Analytics Logs (retention meter)      | westeurope | payg    |   0.13     | 1 GB/Month    |  500  | 65.00              | 780.00            | 500 GB/mo retention; ingestion priced separately in reality. |
| baseline  | backup-vault-prod     | backup.vault           | Backup           | Standard / ADLS Gen2 Vaulted LRS Writes           | westeurope | payg    |   0.054    | 10K ops       |  100  | 5.40               | 64.80             | 250 GB protected; this is only write ops, not full backup storage. |
| baseline  | asr-dr-app            | dr.asr                 | Site Recovery    | ASR / System Center                               | westeurope | payg    |  16.00     | 1 / Month     |    1  | 16.00              | 192.00            | 1 protected instance placeholder. |

**Baseline totals (from JSON, with caveats):**

- **Modeled (priced + estimated) resources**:  
  ≈ **24.41 USD/month** (this is only the subset with explicit/estimated prices).
- **Total with placeholders**:  
  ≈ **854.35 USD/month** and **10,252.25 USD/year** (includes large “missing” buckets; not reliable).
- **Missing pricing** dominates: ≈ **830 USD/month** is marked as missing.

#### Aggregated by Category – Baseline

Mapping to higher-level categories:

- **Compute**: `appservice`
- **Storage**: `storage.blob`
- **Network**: `network.gateway`, `network.nat`, `network.public_ip`, `network.vnet`, `other` (Private Link)
- **Security**: `security.keyvault`
- **Monitoring/Analytics**: `monitoring.loganalytics`
- **Backup/DR**: `backup.vault`, `dr.asr`
- **Other**: anything uncategorized (none beyond Private Link here)

Using `totals.by_category` (note: many are placeholder 100 USD):

| Scenario | High-Level Category | Included JSON Categories                            | Monthly (USD) | Of which Priced | Estimated | Missing | Est. Ratio (est / (priced+est)) |
|----------|---------------------|-----------------------------------------------------|--------------:|----------------:|----------:|--------:|---------------------------------:|
| baseline | Compute             | appservice                                          | 129.94        | 0.00            | 0.00      | 129.94  | 0% (but 100% missing)           |
| baseline | Storage             | storage.blob                                        | 12.91         | 0.00            | 12.91     | 0.00    | 100%                             |
| baseline | Network             | network.gateway, network.nat, network.public_ip, network.vnet, other | 210.00       | 10.00           | 0.00      | 200.00 | ~0% (almost all missing)        |
| baseline | Security            | security.keyvault                                   | 1.50          | 1.50            | 0.00      | 0.00    | 0%                              |
| baseline | Monitoring          | monitoring.loganalytics                             | 100.00        | 0.00            | 0.00      | 100.00 | n/a (all missing)               |
| baseline | Backup/DR           | backup.vault, dr.asr                                | 200.00        | 21.40           | 0.00      | 178.60 | ~0% (mostly missing)            |
| baseline | Other               | – (none beyond above)                               | 0.00          | 0.00            | 0.00      | 0.00    | n/a                             |

> Interpretation: Only **storage.blob**, **Key Vault**, **NAT egress**, and **ASR/Backup ops** have meaningful prices. Front Door, Redis, Public IP, Private Link, and most backup/monitoring are effectively **unpriced** in this dataset.

---

### 3.2 Cost Optimized Scenario

#### Main Components (Cost Optimized)

- **Compute**
  - App Service Plan: Premium v3 (Linux), 1 instance, 1‑year **reserved** (reservation pricing ambiguous in JSON).
  - One web app on that plan.

- **Data & Storage**
  - Media Blob Storage: Standard LRS, ~8 TB (more Cool/Archive).
  - No separate explicit log storage account (logs assumed to go to Log Analytics).

- **Network**
  - Azure Front Door **Standard** (global) with CDN.
  - VNet (optional) for private endpoints.
  - NAT Gateway + Public IP (same pattern, lower egress).

- **Security**
  - Key Vault (Standard) with lower transaction volume.

- **Monitoring & Operations**
  - Log Analytics with reduced ingestion (~200 GB/month).
  - Smaller backup footprint (150 GB protected).

#### Pricing Table – Cost Optimized

| Scenario       | Resource ID             | Category               | Service          | SKU (requested / resolved)                         | Region     | Billing   | Unit Price | Unit          | Units | Monthly Cost (USD) | Yearly Cost (USD) | Notes |
|----------------|-------------------------|------------------------|------------------|----------------------------------------------------|------------|-----------|-----------:|---------------|------:|--------------------:|-------------------:|-------|
| cost_optimized | afd-standard-global     | network.gateway        | Azure Front Door | Standard_AzureFrontDoor / (missing)               | global     | payg      |    n/a     | n/a           | n/a  | n/a                | n/a               | 50 TB/mo egress, 150M req; must price manually. |
| cost_optimized | appsvc-plan-cost        | appservice             | App Service      | P1v3 (req) / P0v3 (reservation)                   | westeurope | reserved  | 508.00\*  | 1 Hour\*      | 1    | 100.00             | 1200.00           | 1‑year reserved; JSON cost is normalized to 100/mo (placeholder). Re‑price in calculator. |
| cost_optimized | appsvc-webapp-cost      | appservice             | App Service      | (logical) / included                               | westeurope | reserved  | 0.000     | Included      | 1    | 0.00               | 0.00              | Web app billed via plan. |
| cost_optimized | storage-media-blob-cost | storage.blob           | Storage          | Standard_LRS / (tiered est.)                      | westeurope | payg      | est       | GB mix        | –    | 9.30               | 111.60            | 6 TB Hot, 2 TB Cool, 192 GB Archive; storage only. |
| cost_optimized | redis-cache-small       | cache.redis            | Cache for Redis  | Basic_C0 / (missing)                              | westeurope | payg      | n/a       | n/a           | n/a  | n/a                | n/a               | No SLA; must price manually. |
| cost_optimized | vnet-app-cost           | network.vnet           | Virtual Network  | (logical) / Virtual Network                        | westeurope | payg      | 0.000     | VNet          | 1    | 0.00               | 0.00              | No direct VNet charge. |
| cost_optimized | natgw-egress-cost       | network.nat            | Bandwidth        | Standard / Standard Inter-AZ Data Transfer Out    | westeurope | payg      | 0.010     | 1 GB          | 500  | 5.00               | 60.00             | 0.5 TB/mo outbound via NAT. |
| cost_optimized | publicip-natgw-cost     | network.public_ip      | Public IP        | Standard / (missing)                               | westeurope | payg      | n/a       | n/a           | n/a  | n/a                | n/a               | Must price manually. |
| cost_optimized | kv-cost                 | security.keyvault      | Key Vault        | standard / Standard                                | westeurope | payg      | 0.03      | 10K ops       | 20   | 0.60               | 7.20              | ~200k ops/mo. |
| cost_optimized | loganalytics-cost       | monitoring.loganalytics| Log Analytics    | PerGB2018 / Analytics Logs (retention meter)      | westeurope | payg      | 0.13      | 1 GB/Month    | 200  | 26.00              | 312.00            | 200 GB/mo retention; ingestion separate. |
| cost_optimized | backup-vault-cost       | backup.vault           | Backup           | Standard / ADLS Gen2 Vaulted LRS Writes           | westeurope | payg      | 0.054     | 10K ops       | 50   | 2.70               | 32.40             | 150 GB protected; write ops only. |

\*Reservation unit price is clearly not “per hour” in reality; treat the 100 USD/month as a **placeholder** for a 1‑year reserved P0v3 plan.

**Cost Optimized totals (from JSON):**

- Modeled (priced + estimated) subset: ≈ **14.9 USD/month**.
- Total with placeholders: ≈ **614.9 USD/month**, **7,378.8 USD/year**.
- Missing pricing: ≈ **600 USD/month** (Front Door, Redis, Public IP, etc.).

#### Aggregated by Category – Cost Optimized

| Scenario       | High-Level Category | Included JSON Categories                            | Monthly (USD) | Priced | Estimated | Missing | Est. Ratio |
|----------------|---------------------|-----------------------------------------------------|--------------:|-------:|----------:|--------:|-----------:|
| cost_optimized | Compute             | appservice                                          | 100.00        | 0.00   | 0.00      | 100.00 | 0% (all missing/placeholder) |
| cost_optimized | Storage             | storage.blob                                        | 9.30          | 0.00   | 9.30      | 0.00   | 100%       |
| cost_optimized | Network             | network.gateway, network.nat, network.public_ip, network.vnet | 205.00       | 5.00  | 0.00      | 200.00 | ~0% (almost all missing) |
| cost_optimized | Security            | security.keyvault                                   | 0.60          | 0.60  | 0.00      | 0.00   | 0%         |
| cost_optimized | Monitoring          | monitoring.loganalytics                             | 100.00        | 0.00  | 0.00      | 100.00 | n/a        |
| cost_optimized | Backup/DR           | backup.vault                                        | 100.00        | 2.70  | 0.00      | 97.30  | ~0%        |
| cost_optimized | Other               | –                                                   | 0.00          | 0.00  | 0.00      | 0.00   | n/a        |

---

### 3.3 High Performance / Scale Scenario

#### Main Components (High Performance)

- **Compute**
  - App Service Plan: Premium v3 P2v3 (Linux), 3 instances, 1‑year reserved (reservation pricing ambiguous).
  - Two web apps sharing the plan.

- **Data & Storage**
  - Media Blob Storage: Premium ZRS, ~15 TB (more Hot data for low latency).
  - No separate explicit log storage account (logs assumed to go to Log Analytics).

- **Network**
  - Azure Front Door Premium with higher throughput and egress (75 TB/mo).
  - VNet for App Service, Redis, and private endpoints.
  - Two NAT Gateways + two Public IPs for higher outbound throughput and resiliency.

- **Security**
  - Premium Key Vault with HSM-backed keys.
  - WAF on Front Door.

- **Monitoring & Operations**
  - Log Analytics with higher ingestion (~800 GB/month).
  - Larger backup footprint (300 GB) and more frequent backups.
  - ASR for two protected instances.

#### Pricing Table – High Performance

| Scenario        | Resource ID             | Category               | Service          | SKU (requested / resolved)                         | Region     | Billing   | Unit Price | Unit          | Units | Monthly Cost (USD) | Yearly Cost (USD) | Notes |
|-----------------|-------------------------|------------------------|------------------|----------------------------------------------------|------------|-----------|-----------:|---------------|------:|--------------------:|-------------------:|-------|
| high_performance| afd-premium-global-hp   | network.gateway        | Azure Front Door | Premium_AzureFrontDoor / (missing)                | global     | payg      | n/a       | n/a           | n/a  | n/a                | n/a               | 75 TB/mo egress, 400M req; must price manually. |
| high_performance| appsvc-plan-hp          | appservice             | App Service      | P2v3 (req) / P0v3 reservation (resolved)          | westeurope | reserved  | 508.00\*  | 1 Hour\*      | 1    | 100.00             | 1200.00           | 3 instances; 1‑year reserved; JSON cost is placeholder. |
| high_performance| appsvc-webapp-hp        | appservice             | App Service      | (logical) / included                               | westeurope | reserved  | 0.000     | Included      | 2    | 0.00               | 0.00              | Two web apps on the plan. |
| high_performance| storage-media-blob-hp   | storage.blob           | Storage          | Premium_ZRS / (tiered est.)                       | westeurope | payg      | est       | GB mix        | –    | 16.35              | 196.20            | 12 TB Hot, 3 TB Cool, 360 GB Archive; storage only. |
| high_performance| redis-cache-hp          | cache.redis            | Cache for Redis  | Premium_P1 / (missing)                            | westeurope | reserved  | n/a       | n/a           | n/a  | n/a                | n/a               | 1‑year reserved; must price manually. |
| high_performance| vnet-app-hp             | network.vnet           | Virtual Network  | (logical) / Virtual Network                        | westeurope | payg      | 0.000     | VNet          | 1    | 0.00               | 0.00              | No direct VNet charge. |
| high_performance| natgw-egress-hp         | network.nat            | Bandwidth        | Standard / Standard Inter-AZ Data Transfer Out    | westeurope | payg      | 0.010     | 1 GB          | 3000 | 30.00              | 360.00            | 3 TB/mo outbound via NAT (2 gateways). |
| high_performance| publicip-natgw-hp       | network.public_ip      | Public IP        | Standard / (missing)                               | westeurope | payg      | n/a       | n/a           | n/a  | n/a                | n/a               | 2 Standard Public IPs; must price manually. |
| high_performance| kv-hp                   | security.keyvault      | Key Vault        | premium / Premium                                  | westeurope | payg      | 0.03      | 10K ops       | 100  | 3.00               | 36.00             | ~1M ops/mo; HSM options extra. |
| high_performance| loganalytics-hp         | monitoring.loganalytics| Log Analytics    | PerGB2018 / Analytics Logs (retention meter)      | westeurope | payg      | 0.13      | 1 GB/Month    | 800  | 104.00             | 1248.00           | 800 GB/mo retention; ingestion separate. |
| high_performance| backup-vault-hp         | backup.vault           | Backup           | Standard / ADLS Gen2 Vaulted LRS Writes           | westeurope | payg      | 0.054     | 10K ops       | 150  | 8.10               | 97.20             | 300 GB protected; write ops only. |
| high_performance| asr-dr-hp               | dr.asr                 | Site Recovery    | ASR / System Center                               | westeurope | payg      | 16.00     | 1 / Month     | 2    | 32.00              | 384.00            | 2 protected instances. |

\*Again, reservation unit price is not truly “per hour”; treat the 100 USD/month as a placeholder.

**High Performance totals (from JSON):**

- Modeled subset: ≈ **49.35 USD/month**.
- Total with placeholders: ≈ **753.35 USD/month**, **9,040.2 USD/year**.
- Missing pricing: ≈ **704 USD/month** (Front Door, Redis, Public IPs, etc.).

#### Aggregated by Category – High Performance

| Scenario        | High-Level Category | Included JSON Categories                            | Monthly (USD) | Priced | Estimated | Missing | Est. Ratio |
|-----------------|---------------------|-----------------------------------------------------|--------------:|-------:|----------:|--------:|-----------:|
| high_performance| Compute             | appservice                                          | 100.00        | 0.00   | 0.00      | 100.00 | 0% (all missing/placeholder) |
| high_performance| Storage             | storage.blob                                        | 16.35         | 0.00   | 16.35     | 0.00   | 100%       |
| high_performance| Network             | network.gateway, network.nat, network.public_ip, network.vnet | 230.00       | 30.00  | 0.00      | 200.00 | ~0% (almost all missing) |
| high_performance| Security            | security.keyvault                                   | 3.00          | 3.00   | 0.00      | 0.00   | 0%         |
| high_performance| Monitoring          | monitoring.loganalytics                             | 104.00        | 0.00   | 0.00      | 104.00 | n/a        |
| high_performance| Backup/DR           | backup.vault, dr.asr                                | 200.00        | 40.10  | 0.00      | 159.90 | ~0%        |
| high_performance| Other               | –                                                   | 0.00          | 0.00   | 0.00      | 0.00   | n/a        |

---

## 4. Resources Where Pricing Failed – Manual Checks

Across all scenarios, the following resources have **missing or clearly unreliable pricing** and must be checked manually in the Azure Pricing Calculator or Rate Card API:

### Common / Baseline

1. **Azure Front Door Premium** (`afd-premium-global`, `afd-premium-global-hp`)
   - Check:
     - Front Door Standard vs Premium base fee.
     - **Data transfer out** by region (50–75 TB/month).
     - **Requests** (200–400M/month).
     - WAF policies and rules (if billed separately).
   - Pricing is **region-band** and **zone-based**; ensure correct geographies.

2. **Azure Front Door Standard** (`afd-standard-global` in cost_optimized)
   - Same checks as above, but Standard tier SKUs.

3. **Azure Cache for Redis**
   - Baseline: `redis-cache-session` (Standard C1).
   - Cost Optimized: `redis-cache-small` (Basic C0).
   - High Performance: `redis-cache-hp` (Premium P1).
   - Check:
     - Hourly price per SKU and region.
     - Whether you need **zone redundancy** or **clustered** SKUs.
     - For Premium: persistence and VNet integration options.

4. **Public IP Addresses (Standard)**
   - Baseline: `publicip-natgw`.
   - Cost Optimized: `publicip-natgw-cost`.
   - High Performance: `publicip-natgw-hp` (2 IPs).
   - Check:
     - Hourly price per Standard Public IP in West Europe.
     - Data processed charges (if any) for NAT association.

5. **Private Endpoint / Private Link**
   - Baseline: `pe-blob-media`.
   - Check:
     - Hourly price per Private Endpoint.
     - **Data processed via Private Link** (per GB) for Blob Storage.

6. **App Service Reservations**
   - `appsvc-plan-cost` and `appsvc-plan-hp`:
     - JSON shows reservation unit price as “508 USD / 1 Hour” with 100 USD/month total – clearly inconsistent.
   - Check:
     - 1‑year reserved price for **Premium v3 P0v3/P1v3/P2v3** in West Europe.
     - Compare to PAYG (0.089 USD/hour for P0v3 in baseline).

7. **Backup Vault & Site Recovery**
   - Backup:
     - `backup-vault-prod`, `backup-vault-cost`, `backup-vault-hp` only model **write operations**, not full backup storage.
   - ASR:
     - `asr-dr-app`, `asr-dr-hp` use **System Center** meter; for Azure‑to‑Azure DR you likely want **VM Replicated to Azure**.
   - Check:
     - Protected instance pricing (per VM / per workload).
     - Backup storage (LRS/GRS) per GB.
     - ASR replication traffic and storage.

8. **Log Analytics**
   - All scenarios (`loganalytics-*`) use the **retention** meter at 0.13 USD/GB/month.
   - Check:
     - **Ingestion** pricing (PerGB2018) – typically the main cost driver.
     - Retention beyond 31 days (if required).
     - Data export or archive costs.

---

## 5. FinOps Recommendations

### 5.1 Quick Wins

1. **Front Door & CDN Egress**
   - This is likely the **largest cost driver** at 50–75 TB/month.
   - Actions:
     - Optimize **cache hit ratio** (longer TTLs for static media, versioned URLs).
     - Use **compression** where applicable (text assets).
     - Consider **regional origin placement** to reduce inter-region bandwidth.

2. **Blob Storage Tiering**
   - Baseline: 8 TB Hot, 2 TB Cool, 240 GB Archive.
   - Cost Optimized: more Cool/Archive; High Performance: more Hot.
   - Actions:
     - Implement **lifecycle policies** to move older media from Hot → Cool → Archive automatically.
     - Validate access patterns; many media assets are “write once, read few” and can move to Cool quickly.

3. **Log Analytics Volume Control**
   - Baseline: 500 GB/mo; Cost Optimized: 200 GB; High Performance: 800 GB.
   - Actions:
     - Turn off **noisy diagnostic categories** (e.g., verbose HTTP logs you don’t use).
     - Use **sampling** for high-volume telemetry.
     - Shorten retention in non‑prod; consider **archive** for long-term compliance instead of hot retention.

4. **Right-size Redis**
   - Confirm actual **memory and throughput** needs.
   - If session data is small and non-critical, Basic C0 may be enough; if you need SLA and persistence, Standard/Premium is justified.
   - Avoid over-provisioning Premium P1 if cache hit rate is low or usage is bursty.

5. **Backup & ASR Scope**
   - For a **PaaS-heavy** architecture, you may not need ASR for many components.
   - Actions:
     - Ensure you’re not backing up ephemeral or easily re‑deployable resources.
     - Use **App Service backup** and **infrastructure-as-code** for fast redeploy instead of heavy ASR where possible.

### 5.2 Spot vs PAYG vs Reserved

- **App Service**
  - Baseline uses **PAYG**; cost_optimized and high_performance assume **1‑year reserved**.
  - Recommendation:
    - If workloads are **steady-state** and you commit to 1–3 years, use **Reserved Instances** for App Service plans.
    - For spiky or uncertain workloads, keep some capacity on PAYG and only reserve the **baseline** capacity.

- **Redis**
  - Premium Redis in high_performance is modeled as reserved but not priced.
  - Recommendation:
    - Reserve only if you have **consistent high usage**; otherwise, PAYG may be safer.
    - There is no “spot” Redis; consider **scaling down at off-peak** if your pattern allows.

- **Front Door**
  - No spot/reservation; purely **consumption-based**.
  - Focus on **traffic optimization** rather than pricing model.

- **Compute Spot**
  - Not applicable here (no VM scale sets). If you introduce VMs (e.g., for transcoding), consider **Spot VMs** for non-critical batch workloads.

### 5.3 Right-Sizing Ideas

- **App Service**
  - Baseline: 2× P0v3; Cost Optimized: 1× P0v3; High Performance: 3× P2v3.
  - Actions:
    - Use **Autoscale** on App Service (scale out/in by CPU, requests, or custom metrics).
    - Start with **P0v3** and monitor CPU/memory; only move to P1v3/P2v3 if you see sustained pressure.
    - Consider **Premium v4** if you need better perf/price, but re‑price carefully.

- **Storage Performance**
  - High Performance uses Premium ZRS; ensure you actually need **IOPS/throughput** beyond Standard.
  - For media delivery, often **Front Door + Standard Blob** is sufficient; Premium is more relevant for high IOPS workloads.

- **NAT Gateway**
  - Baseline: 1 TB/mo; Cost Optimized: 0.5 TB; High Performance: 3 TB.
  - Actions:
    - Confirm if you really need NAT for all outbound traffic; some services can use **service tags** or **private endpoints** instead.
    - If outbound is minimal, consider whether a NAT Gateway is needed vs. basic outbound from App Service.

### 5.4 Region & Egress Considerations

- **Region Choice**
  - All origins are in **West Europe**; Front Door is global.
  - If your audience is global, consider:
    - Keeping origin in a region close to **content owners** (uploaders) to reduce **ingress latency**.
    - For very large egress, evaluate **multi-region origins** to reduce **inter-region bandwidth** from Front Door to origin.

- **Egress Billing**
  - **Front Door → Internet** egress is billed by region band and volume.
  - **Origin → Front Door** is billed as **inter-region bandwidth** if origin is in a different region than the POP’s origin region.
  - Use **Private Link** and **same-region origins** where possible to minimize cross-region data charges.

---

## 6. Delta Tables vs Baseline

Because of SKU mismatches and placeholders, the JSON marks scenarios as **“not_comparable”**. Still, we can compare the **reported totals** at a high level, with strong caveats.

### 6.1 Overall Totals – Monthly/Yearly (Reported)

Using `totals.total_monthly` and `totals.total_yearly`:

| Scenario        | Monthly Total (USD) | Yearly Total (USD) | Δ vs Baseline Monthly (USD) | Δ vs Baseline Monthly (%) | Δ vs Baseline Yearly (USD) | Δ vs Baseline Yearly (%) |
|-----------------|--------------------:|--------------------:|----------------------------:|---------------------------:|---------------------------:|--------------------------:|
| baseline        | 854.35              | 10,252.25           | –                           | –                          | –                          | –                         |
| cost_optimized  | 614.90              | 7,378.80            | -239.45                     | -28.0%                     | -2,873.45                  | -28.0%                    |
| high_performance| 753.35              | 9,040.20            | -101.00                     | -11.8%                     | -1,212.05                  | -11.8%                    |

> These deltas are **not reliable** because:
> - Large portions of each scenario are marked as **missing** or **placeholder 100 USD**.
> - Front Door, Redis, Public IPs, and reservations are not consistently priced.

### 6.2 Category-Level Monthly Deltas vs Baseline

Using `totals.by_category.monthly` (again, many are placeholders):

#### Cost Optimized vs Baseline – Monthly by Category

| High-Level Category | Baseline Monthly (USD) | Cost Opt Monthly (USD) | Δ (USD) | Δ (%)        |
|---------------------|-----------------------:|------------------------:|--------:|-------------:|
| Compute (appservice)| 129.94                | 100.00                 | -29.94  | -23.0%       |
| Storage (blob)      | 12.91                 | 9.30                   | -3.61   | -28.0%       |
| Network             | 210.00                | 205.00                 | -5.00   | -2.4%        |
| Security (Key Vault)| 1.50                  | 0.60                   | -0.90   | -60.0%       |
| Monitoring          | 100.00                | 100.00                 | 0.00    | 0%           |
| Backup/DR           | 200.00                | 100.00                 | -100.00 | -50.0%       |

#### High Performance vs Baseline – Monthly by Category

| High-Level Category | Baseline Monthly (USD) | High Perf Monthly (USD) | Δ (USD) | Δ (%)        |
|---------------------|-----------------------:|-------------------------:|--------:|-------------:|
| Compute (appservice)| 129.94                | 100.00                  | -29.94  | -23.0%       |
| Storage (blob)      | 12.91                 | 16.35                   | +3.44   | +26.7%       |
| Network             | 210.00                | 230.00                  | +20.00  | +9.5%        |
| Security (Key Vault)| 1.50                  | 3.00                    | +1.50   | +100.0%      |
| Monitoring          | 100.00                | 104.00                  | +4.00   | +4.0%        |
| Backup/DR           | 200.00                | 200.00                  | 0.00    | 0%           |

> Again, treat these as **directional only**:
> - Cost Optimized reduces compute, storage, Key Vault, and backup footprint.
> - High Performance increases storage, network, Key Vault, and monitoring, but compute appears lower only because of placeholder reservation modeling.

---

## 7. Summary

- The **baseline** architecture is sound for a production media site: Front Door Premium + App Service + Blob + Redis + Key Vault + Log Analytics + Backup/ASR, with private origins and WAF.
- The **cost_optimized** variant trades off HA, observability, and redundancy for lower cost (Front Door Standard, smaller App Service, LRS storage, smaller Redis, less logging/backup).
- The **high_performance** variant scales out compute, storage, Redis, and monitoring, and uses Premium Key Vault and Premium ZRS storage to handle higher throughput and stricter security.

From a FinOps perspective:

- **Front Door egress and Blob storage** are likely the main cost drivers; focus on **caching, tiering, and lifecycle policies**.
- **Log Analytics** can quietly become expensive; tune ingestion and retention.
- Use **Reserved Instances** for App Service and Redis only where workloads are steady and predictable.
- Validate all **missing/placeholder prices** (Front Door, Redis, Public IPs, Private Link, reservations, backup storage, ASR) in the Azure Pricing Calculator before committing to budgets.