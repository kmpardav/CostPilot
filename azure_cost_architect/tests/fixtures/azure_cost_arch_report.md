## 1. Baseline / Recommended scenario – short narrative

The baseline design is a small but production‑grade web application for ~50k monthly active users in West Europe with 99.9% availability:

- **Frontend**: A Linux Azure App Service Plan (Premium v3–class capacity, but priced as P0v3) running a single Web App with **2 always‑on instances** behind an **Application Gateway v2 with WAF** and a Standard Public IP. This provides SSL termination, WAF protection, and layer‑7 routing.
- **Data**: A single **Azure SQL Database (General Purpose, Gen5, 2 vCores, 128 GB)** as the main transactional store, plus **Azure Cache for Redis (Standard C1)** for session and hot data caching, and **Blob Storage (GRS)** for static content and files.
- **Network**: A **hub VNet** with subnets for App Service integration and **private endpoints** for SQL, Redis, and Storage. Outbound traffic goes via a **NAT Gateway**, and there is explicit accounting for **internet egress**.
- **Security & secrets**: **Azure Key Vault (Standard)** for secrets, keys, and certificates; **Application Gateway WAF** for basic web protection.
- **Ops, monitoring & resilience**: **Log Analytics** for central logging and metrics, a **Recovery Services vault** placeholder for backups (cost not yet modeled), **Azure Site Recovery** placeholder for DR, and **Azure Bastion** for secure admin access.

Baseline total (including estimates and placeholders, EUR, West Europe):

- **~€436/month** (of which ~€231 is priced, ~€5 estimated, and **€200 is a placeholder for missing Redis + Public IP pricing**).
- **~€5,230/year** with the same caveats.

---

## 2. Other scenarios – summary and key differences

### Cost Optimized scenario

Goal: reduce cost while keeping ~99.9% availability.

Key changes vs baseline:

- **Compute**: Move from Premium v3‑class App Service to **Standard S1** (2 instances), using **“Dev/Test” pricing** in the catalog (cheaper but not valid for production billing). This is modeled as “reserved” but actually uses DevTestConsumption pricing.
- **Database**: **Downsize SQL** to **1 vCore GP Gen5, 64 GB** and assume **1‑year reserved capacity** (but the reservation unit price in the JSON is clearly wrong; see risks).
- **Redis**: **Basic C0** (no replica) instead of Standard C1 – cheaper but no HA at cache layer.
- **Storage**: **LRS instead of GRS**, and lower volumes (100 GB hot, 50 GB cool).
- **Network & egress**: Slightly lower egress and NAT volumes.
- **Monitoring & backup**: **Reduced Log Analytics ingestion** (80 GB vs 200 GB) and leaner backup retention.

Modeled totals (with same missing‑price placeholders):

- **~€325/month** (vs baseline €436) → **~€111/month lower (~25% cheaper)**.
- **~€3,898/year** (vs €5,230) → **~€1,332/year lower**.

But note: a significant part of the “saving” is driven by:
- Dev/Test App Service pricing (not valid for prod),
- A suspicious SQL reservation unit price,
- Same €200/month placeholder for Redis + Public IP as baseline.

### High Performance / Scalable scenario

Goal: more headroom and resilience for growth beyond 50k MAU.

Key changes vs baseline:

- **Compute**: Larger **Premium v3 App Service (P2v3‑class)** with **3 instances**, using **1‑year reserved pricing**.
- **Database**: **4 vCore GP Gen5, 256 GB** SQL Database with reserved capacity.
- **Redis**: **Standard C2** with replica for higher throughput and HA.
- **Storage**: **GZRS** (zone‑redundant) with higher volumes (400 GB hot, 200 GB cool).
- **Network & egress**: Higher NAT and internet egress assumptions.
- **Monitoring & backup**: More Log Analytics ingestion (350 GB) and larger backup footprint; **Bastion Standard** with more hours.

Modeled totals (with same missing‑price placeholders):

- **~€385/month** (vs baseline €436) → **~€51/month lower (~12% cheaper)** despite being “bigger”, because:
  - App Service and SQL are on **1‑year reservations** with very low catalog prices.
- **~€4,622/year** (vs €5,230) → **~€608/year lower**.

Again, these numbers are dominated by:
- The **€200/month placeholder** for Redis + Public IP,
- Aggressive reservation pricing in the catalog.

---

## 3. Scenario details

### 3.1 Baseline scenario

#### Main components (baseline)

- **Compute**
  - Azure App Service Plan (Linux, Premium v3‑class, P0v3 priced) with 2 instances.
  - Web App running on that plan.
- **Database**
  - Azure SQL Database, General Purpose, Gen5, 2 vCores, 128 GB.
- **Storage & data**
  - Azure Cache for Redis, Standard C1 (1 GB, HA).
  - Azure Storage (Blob, GPv2, GRS) – 200 GB hot, 100 GB cool.
- **Network**
  - VNet with subnets and private endpoints.
  - Application Gateway v2 with WAF.
  - Standard Public IP for App Gateway.
  - NAT Gateway for outbound.
  - Internet egress (500 GB/month).
- **Security**
  - Key Vault (Standard) for secrets/keys/certs.
  - WAF on Application Gateway.
- **Monitoring & operations**
  - Log Analytics workspace (200 GB/month ingestion).
  - Recovery Services vault (backups placeholder).
  - Azure Site Recovery placeholder.
  - Azure Bastion Basic for secure access.

#### Pricing table – baseline

_All prices in EUR, West Europe. “Requested / Resolved” shows your intended SKU vs what the catalog matched. Missing/estimated rows are highlighted in Notes._

| Scenario | Resource ID           | Category              | Service           | SKU (requested / resolved)                         | Region     | Billing | Unit Price | Unit              | Units  | Monthly Cost | Yearly Cost | Notes |
|----------|----------------------|-----------------------|-------------------|----------------------------------------------------|-----------|---------|-----------|-------------------|--------|-------------:|------------:|-------|
| baseline | vnet-main            | network.vnet          | Virtual Network   | Virtual Network / Virtual Network                  | westeurope| payg    | 0.0000    | VNet              | 1      | 0.00         | 0.00        | No direct VNet charge. |
| baseline | appsvc-plan-prod     | appservice            | Azure App Service | P1v3 (2 vCPU, 8 GB) / P0v3 App (Premium v3 Linux)  | westeurope| payg    | 0.0770    | 1 Hour            | 730    | 56.21        | 674.52      | 2 instances assumed at plan level; price is for plan, not per app. |
| baseline | appsvc-webapp-prod   | appservice            | Azure App Service | Web App / Included                                 | westeurope| payg    | 0.0000    | Included           | 1      | 0.00         | 0.00        | Logical app, cost in plan. |
| baseline | sql-db-prod          | db.sql                | SQL Database      | GP_Gen5_2 / GP Gen5 vCore                          | westeurope| payg    | 0.2896    | 1 Hour (2 vCores) | 730    | 105.70       | 1268.45     | 2 vCores GP Gen5. Storage not itemized here. |
| baseline | redis-cache-prod     | cache.redis           | Azure Cache Redis | Standard_C1 / —                                    | westeurope| payg    | —         | —                 | —      | **100.00***  | **1200.00***| **Missing price; €100/month placeholder in totals.** |
| baseline | blob-storage-prod    | storage.blob          | Storage           | Standard_GRS / ADLS Gen2 ops proxy                 | westeurope| payg    | 0.0019    | 1 GB (cool scan)  | 100    | 0.19         | 2.28        | **Estimated**; only cool tier scan modeled, storage & egress not fully priced. |
| baseline | appgw-waf-prod       | network.appgw         | Application GW    | WAF_v2 / Standard Capacity Units                   | westeurope| payg    | 0.0069    | 1/Hour            | 730    | 5.04         | 60.44       | **Estimated**; ignores per‑capacity/throughput components. |
| baseline | publicip-appgw-prod  | network.public_ip     | Public IP         | Standard / —                                       | westeurope| payg    | —         | —                 | —      | **100.00***  | **1200.00***| **Missing price; €100/month placeholder in totals.** |
| baseline | natgw-prod           | network.nat           | Bandwidth         | NAT / Std Inter‑AZ Data Out                        | westeurope| payg    | 0.0086    | 1 GB              | 150    | 1.29         | 15.48       | Only data component modeled; NAT hourly fee not included. |
| baseline | egress-internet-prod | network.egress        | Bandwidth         | Internet / Std Inter‑AZ Data Out                   | westeurope| payg    | 0.0086    | 1 GB              | 500    | 4.30         | 51.60       | Internet egress proxy; actual SKU is “Data Transfer Out”. |
| baseline | keyvault-prod        | security.keyvault     | Key Vault         | standard / Operations                              | westeurope| payg    | 0.0259    | 10K ops           | 20     | 0.52         | 6.22        | 200k operations/month. |
| baseline | loganalytics-prod    | monitoring.loganalytics| Log Analytics    | PerGB2018 / Analytics Logs Retention              | westeurope| payg    | 0.1124    | 1 GB/Month        | 200    | 22.48        | 269.76      | **Only retention priced; ingestion priced as 0 in catalog snapshot.** |
| baseline | backup-vault-prod    | backup.vault          | Backup            | — / ADLS Gen2 Vaulted LRS Ops                      | westeurope| payg    | 0.0467    | 10K ops           | 0      | 0.00         | 0.00        | Backup storage not modeled; effectively missing. |
| baseline | asr-dr-prod          | dr.asr                | Site Recovery     | — / VM Replicated to System Center                 | westeurope| payg    | 13.8378   | 1/Month           | 1      | 13.84        | 166.05      | Placeholder for DR coverage. |
| baseline | bastion-prod         | network.bastion       | Azure Bastion     | Basic / Basic Gateway                              | westeurope| payg    | 0.1643    | 1 Hour            | 160    | 26.29        | 315.46      | 160 active hours/month assumed. |

\* Redis and Public IP costs are not actually calculated; €100/month each is a **scenario‑level placeholder** in the totals.

#### Aggregated by category – baseline

I’ll map Azure categories into higher‑level buckets:

- **Compute**: `appservice`
- **DB**: `db.sql`, `cache.redis`
- **Storage**: `storage.blob`
- **Network**: `network.appgw`, `network.public_ip`, `network.nat`, `network.egress`, `network.vnet`, `network.bastion`
- **Security**: `security.keyvault`
- **Monitoring/Analytics**: `monitoring.loganalytics`
- **Backup/DR**: `backup.vault`, `dr.asr`
- **Other**: anything else (none here)

For each: Monthly total, and share that is priced vs estimated vs missing.

| Bucket            | Monthly Total (€) | Priced (€) | Estimated (€) | Missing (€) | % Priced | % Est. | % Missing |
|-------------------|------------------:|-----------:|--------------:|------------:|---------:|-------:|----------:|
| Compute (AppSvc)  | 56.21             | 56.21      | 0.00          | 0.00        | 100%     | 0%     | 0%        |
| DB (SQL + Redis)  | 205.70            | 105.70     | 0.00          | 100.00      | 51%      | 0%     | 49%       |
| Storage (Blob)    | 0.19              | 0.00       | 0.19          | 0.00        | 0%       | 100%   | 0%        |
| Network           | 137.17            | 37.98      | 5.04          | 94.15       | 28%      | 4%     | 69%       |
| Security          | 0.52              | 0.52       | 0.00          | 0.00        | 100%     | 0%     | 0%        |
| Monitoring        | 22.48             | 22.48      | 0.00          | 0.00        | 100%     | 0%     | 0%        |
| Backup/DR         | 13.84             | 13.84      | 0.00          | 0.00        | 100%     | 0%     | 0%        |
| Other             | 0.00              | 0.00       | 0.00          | 0.00        | —        | —      | —         |
| **Total**         | **435.86**        | **230.63** | **5.23**      | **200.00**  | **53%**  | **1%** | **46%**   |

> **Key risk:** Almost half of the baseline monthly total is **missing or placeholder** (Redis + Public IP + partial storage/network modeling). Use this as a **directional** estimate only.

---

### 3.2 Cost Optimized scenario

#### Main components (cost_optimized)

- **Compute**
  - Azure App Service Plan **Standard S1** (Linux, 2 instances), using **Dev/Test pricing** in catalog (not production).
  - Single Web App on that plan.
- **Database**
  - Azure SQL Database GP Gen5, **1 vCore, 64 GB**, with **1‑year reservation** (but unit price looks wrong).
- **Storage & data**
  - Azure Cache for Redis **Basic C0** (no replica).
  - Azure Storage (Blob, GPv2, **LRS**), 100 GB hot, 50 GB cool.
- **Network**
  - VNet with private endpoints.
  - Application Gateway **Standard v2 (no WAF)**.
  - Standard Public IP.
  - NAT Gateway with 100 GB outbound.
  - Internet egress 350 GB/month.
- **Security**
  - Key Vault (Standard) with fewer operations.
- **Monitoring & operations**
  - Log Analytics with **80 GB/month** ingestion.
  - Recovery Services vault with **150 GB** backup storage (not priced).
  - No Bastion or ASR explicitly modeled here (only baseline and HP have Bastion/ASR).

#### Pricing table – cost_optimized

| Scenario       | Resource ID          | Category              | Service           | SKU (requested / resolved)                         | Region     | Billing   | Unit Price | Unit              | Units | Monthly Cost | Yearly Cost | Notes |
|----------------|----------------------|-----------------------|-------------------|----------------------------------------------------|-----------|-----------|-----------|-------------------|-------|-------------:|------------:|-------|
| cost_optimized | vnet-main-co         | network.vnet          | Virtual Network   | Virtual Network / Virtual Network                  | westeurope| payg      | 0.0000    | VNet              | 1     | 0.00         | 0.00        | No direct VNet charge. |
| cost_optimized | appsvc-plan-co       | appservice            | Azure App Service | S1 / S1 App (Standard Plan, Dev/Test)             | westeurope| reserved* | 0.0519    | 1 Hour            | 730   | 37.89        | 454.64      | Uses DevTestConsumption pricing; **not valid for prod**. |
| cost_optimized | appsvc-webapp-co     | appservice            | Azure App Service | Web App / Included                                 | westeurope| reserved* | 0.0000    | Included           | 1     | 0.00         | 0.00        | Logical app. |
| cost_optimized | sql-db-co            | db.sql                | SQL Database      | GP_Gen5_1 / vCore (Reservation)                    | westeurope| reserved  | 824.2162  | 1 Hour (vCore)    | 1     | 68.68        | 824.22      | Catalog shows reservation unit price; monthly cost is pre‑computed. Treat with caution. |
| cost_optimized | redis-cache-co       | cache.redis           | Azure Cache Redis | Basic_C0 / —                                       | westeurope| payg      | —         | —                 | —     | **100.00***  | **1200.00***| **Missing price; €100/month placeholder in totals.** |
| cost_optimized | blob-storage-co      | storage.blob          | Storage           | Standard_LRS / ADLS Gen2 ops proxy                 | westeurope| payg      | 0.0019    | 1 GB (cool scan)  | 50    | 0.10         | 1.14        | **Estimated**; storage & egress not fully modeled. |
| cost_optimized | appgw-basic-co       | network.appgw         | Application GW    | Standard_v2 / Standard Capacity Units              | westeurope| payg      | 0.0069    | 1/Hour            | 730   | 5.04         | 60.44       | **Estimated**; no WAF. |
| cost_optimized | publicip-appgw-co    | network.public_ip     | Public IP         | Standard / —                                       | westeurope| payg      | —         | —                 | —     | **100.00***  | **1200.00***| **Missing price; €100/month placeholder.** |
| cost_optimized | natgw-co             | network.nat           | Bandwidth         | NAT / Std Inter‑AZ Data Out                        | westeurope| payg      | 0.0086    | 1 GB              | 100   | 0.86         | 10.32       | NAT hourly fee not modeled. |
| cost_optimized | egress-internet-co   | network.egress        | Bandwidth         | Internet / Std Inter‑AZ Data Out                   | westeurope| payg      | 0.0086    | 1 GB              | 350   | 3.01         | 36.12       | Internet egress proxy. |
| cost_optimized | keyvault-co          | security.keyvault     | Key Vault         | standard / Operations                              | westeurope| payg      | 0.0259    | 10K ops           | 10    | 0.26         | 3.11        | 100k operations/month. |
| cost_optimized | loganalytics-co      | monitoring.loganalytics| Log Analytics    | PerGB2018 / Analytics Logs Retention              | westeurope| payg      | 0.1124    | 1 GB/Month        | 80    | 8.99         | 107.90      | **Only retention priced; ingestion priced as 0.** |
| cost_optimized | backup-vault-co      | backup.vault          | Backup            | — / ADLS Gen2 Vaulted LRS Ops                      | westeurope| payg      | 0.0467    | 10K ops           | 0     | 0.00         | 0.00        | Backup storage not modeled. |

\* Billing is marked “reserved” in JSON, but the App Service SKU is Dev/Test. Treat as **conceptual “long‑term” usage**, not a real reservation.

#### Aggregated by category – cost_optimized

| Bucket            | Monthly Total (€) | Priced (€) | Estimated (€) | Missing (€) | % Priced | % Est. | % Missing |
|-------------------|------------------:|-----------:|--------------:|------------:|---------:|-------:|----------:|
| Compute (AppSvc)  | 37.89             | 37.89      | 0.00          | 0.00        | 100%     | 0%     | 0%        |
| DB (SQL + Redis)  | 168.68            | 68.68      | 0.00          | 100.00      | 41%      | 0%     | 59%       |
| Storage (Blob)    | 0.10              | 0.00       | 0.10          | 0.00        | 0%       | 100%   | 0%        |
| Network           | 108.91            | 7.88       | 5.04          | 96.00       | 7%       | 5%     | 88%       |
| Security          | 0.26              | 0.26       | 0.00          | 0.00        | 100%     | 0%     | 0%        |
| Monitoring        | 8.99              | 8.99       | 0.00          | 0.00        | 100%     | 0%     | 0%        |
| Backup/DR         | 0.00              | 0.00       | 0.00          | 0.00        | —        | —      | —         |
| Other             | 0.00              | 0.00       | 0.00          | 0.00        | —        | —      | —         |
| **Total**         | **324.83**        | **119.69** | **5.14**      | **200.00**  | **37%**  | **2%** | **62%**   |

> **Observation:** Cost‑optimized scenario has **even more of its total as missing/placeholder (62%)** than baseline. The “savings” are therefore indicative, not precise.

---

### 3.3 High Performance / Scalable scenario

#### Main components (high_performance)

- **Compute**
  - Azure App Service Plan **Premium v3 P2v3‑class** (Linux) with **3 instances**, using **1‑year reserved pricing**.
  - Single Web App on that plan.
- **Database**
  - Azure SQL Database GP Gen5, **4 vCores, 256 GB**, with **1‑year reserved capacity**.
- **Storage & data**
  - Azure Cache for Redis **Standard C2** (2.5 GB, HA).
  - Azure Storage (Blob, GPv2, **GZRS**), 400 GB hot, 200 GB cool.
- **Network**
  - VNet with private endpoints.
  - Application Gateway **WAF v2** with autoscaling.
  - Standard Public IP.
  - NAT Gateway with 250 GB outbound.
  - Internet egress 900 GB/month.
- **Security**
  - **Key Vault Premium** for HSM‑backed keys and higher throughput.
- **Monitoring & operations**
  - Log Analytics with **350 GB/month** ingestion and longer retention.
  - Recovery Services vault with 350 GB backup storage (not priced).
  - Azure Bastion **Standard** with 200 hours/month.

#### Pricing table – high_performance

| Scenario        | Resource ID          | Category              | Service           | SKU (requested / resolved)                         | Region     | Billing   | Unit Price | Unit              | Units | Monthly Cost | Yearly Cost | Notes |
|----------------|----------------------|-----------------------|-------------------|----------------------------------------------------|-----------|-----------|-----------|-------------------|-------|-------------:|------------:|-------|
| high_perf      | vnet-main-hp         | network.vnet          | Virtual Network   | Virtual Network / Virtual Network                  | westeurope| payg      | 0.0000    | VNet              | 1     | 0.00         | 0.00        | No direct VNet charge. |
| high_perf      | appsvc-plan-hp       | appservice            | Azure App Service | P2v3 / P0v3 App (Premium v3 Linux, reserved)       | westeurope| reserved  | 439.3514  | 1 Hour            | 1     | 36.61        | 439.35      | 1‑year reservation; monthly cost pre‑computed. |
| high_perf      | appsvc-webapp-hp     | appservice            | Azure App Service | Web App / Included                                 | westeurope| reserved  | 0.0000    | Included           | 1     | 0.00         | 0.00        | Logical app. |
| high_perf      | sql-db-hp            | db.sql                | SQL Database      | GP_Gen5_4 / vCore (Reservation)                    | westeurope| reserved  | 824.2162  | 1 Hour (vCore)    | 1     | 68.68        | 824.22      | 4 vCores GP Gen5; reservation pricing. |
| high_perf      | redis-cache-hp       | cache.redis           | Azure Cache Redis | Standard_C2 / —                                    | westeurope| reserved  | —         | —                 | —     | **100.00***  | **1200.00***| **Missing price; €100/month placeholder.** |
| high_perf      | blob-storage-hp      | storage.blob          | Storage           | Standard_GZRS / Blob & ADLS ops proxy              | westeurope| payg      | 0.0019    | 1 GB (cool scan)  | 200   | 0.38         | 4.56        | **Estimated**; storage & egress not fully modeled. |
| high_perf      | appgw-waf-hp         | network.appgw         | Application GW    | WAF_v2 / Standard Capacity Units                   | westeurope| payg      | 0.0069    | 1/Hour            | 730   | 5.04         | 60.44       | **Estimated**; autoscaling & WAF extras not modeled. |
| high_perf      | publicip-appgw-hp    | network.public_ip     | Public IP         | Standard / —                                       | westeurope| payg      | —         | —                 | —     | **100.00***  | **1200.00***| **Missing price; €100/month placeholder.** |
| high_perf      | natgw-hp             | network.nat           | Bandwidth         | NAT / Std Inter‑AZ Data Out                        | westeurope| payg      | 0.0086    | 1 GB              | 250   | 2.15         | 25.80       | NAT hourly fee not modeled. |
| high_perf      | egress-internet-hp   | network.egress        | Bandwidth         | Internet / Std Inter‑AZ Data Out                   | westeurope| payg      | 0.0086    | 1 GB              | 900   | 7.74         | 92.88       | Internet egress proxy. |
| high_perf      | keyvault-hp          | security.keyvault     | Key Vault         | premium / Operations                               | westeurope| payg      | 0.0259    | 10K ops           | 40    | 1.04         | 12.43       | 400k operations/month; Premium SKU. |
| high_perf      | loganalytics-hp      | monitoring.loganalytics| Log Analytics    | PerGB2018 / Analytics Logs Retention              | westeurope| payg      | 0.1124    | 1 GB/Month        | 350   | 39.34        | 472.08      | **Only retention priced; ingestion priced as 0.** |
| high_perf      | backup-vault-hp      | backup.vault          | Backup            | — / ADLS Gen2 Vaulted LRS Ops                      | westeurope| payg      | 0.0467    | 10K ops           | 0     | 0.00         | 0.00        | Backup storage not modeled. |
| high_perf      | bastion-hp           | network.bastion       | Azure Bastion     | Standard / Standard Additional Gateway             | westeurope| payg      | 0.1211    | 1 Hour            | 200   | 24.22        | 290.64      | 200 hours/month. |

#### Aggregated by category – high_performance

| Bucket            | Monthly Total (€) | Priced (€) | Estimated (€) | Missing (€) | % Priced | % Est. | % Missing |
|-------------------|------------------:|-----------:|--------------:|------------:|---------:|-------:|----------:|
| Compute (AppSvc)  | 36.61             | 36.61      | 0.00          | 0.00        | 100%     | 0%     | 0%        |
| DB (SQL + Redis)  | 168.68            | 68.68      | 0.00          | 100.00      | 41%      | 0%     | 59%       |
| Storage (Blob)    | 0.38              | 0.00       | 0.38          | 0.00        | 0%       | 100%   | 0%        |
| Network           | 139.15            | 39.11      | 5.04          | 95.00       | 28%      | 4%     | 68%       |
| Security          | 1.04              | 1.04       | 0.00          | 0.00        | 100%     | 0%     | 0%        |
| Monitoring        | 39.34             | 39.34      | 0.00          | 0.00        | 100%     | 0%     | 0%        |
| Backup/DR         | 0.00              | 0.00       | 0.00          | 0.00        | —        | —      | —         |
| Other             | 0.00              | 0.00       | 0.00          | 0.00        | —        | —      | —         |
| **Total**         | **385.20**        | **179.78** | **5.42**      | **200.00**  | **47%**  | **1%** | **52%**   |

---

## 4. Resources where pricing failed – manual checks

Across all scenarios, the following resources have **missing or clearly incomplete pricing** and should be checked manually in the Azure Pricing Calculator or your EA/Marketplace price sheet:

1. **Azure Cache for Redis**
   - Baseline: `redis-cache-prod` (Standard_C1) – missing; placeholder **€100/month**.
   - Cost Optimized: `redis-cache-co` (Basic_C0) – missing; placeholder **€100/month** (but real C0 is much cheaper).
   - High Performance: `redis-cache-hp` (Standard_C2) – missing; placeholder **€100/month** (real C2 is more than C1).

   **What to check**:
   - Correct SKU (Basic vs Standard, C0/C1/C2).
   - Region: West Europe.
   - HA (Standard includes replica; Basic does not).
   - Any reserved capacity or Enterprise discounts.

2. **Public IP (Standard)**
   - Baseline: `publicip-appgw-prod`.
   - Cost Optimized: `publicip-appgw-co`.
   - High Performance: `publicip-appgw-hp`.

   All three are missing and modeled as **€100/month** each, which is far above real Standard Public IP pricing (typically a few €/month + data).  
   **What to check**:
   - Standard Public IP (zone‑redundant or not) in West Europe.
   - Data processed (if using global services like Front Door instead, pricing differs).

3. **Blob Storage**
   - All scenarios (`blob-storage-prod`, `blob-storage-co`, `blob-storage-hp`) use **operation‑based proxies** (ADLS Gen2 “data scanned”) and **do not fully price**:
     - Capacity (GB/month) for hot/cool tiers.
     - Read/write/transaction costs.
     - Egress from storage.

   **What to check**:
   - GPv2 Storage, Blob, Hot/Cool, GRS/LRS/GZRS in West Europe.
   - Capacity: 200/100 GB (baseline), 100/50 GB (CO), 400/200 GB (HP).
   - Egress: 200/150/400 GB per scenario.

4. **Application Gateway v2 / WAF v2**
   - All scenarios (`appgw-waf-prod`, `appgw-basic-co`, `appgw-waf-hp`) only price a **single “capacity unit” hourly** and ignore:
     - Fixed hourly cost.
     - Additional capacity units for throughput and connections.
     - WAF policy charges.

   **What to check**:
   - App Gateway v2 / WAF v2 pricing model: fixed + capacity units + data processed.
   - Autoscaling configuration and expected peak RPS.

5. **NAT Gateway**
   - `natgw-*` resources only price **data transfer** (Std Inter‑AZ Data Out), not:
     - NAT Gateway hourly fee.
     - Per‑IP charges.

   **What to check**:
   - NAT Gateway hourly cost in West Europe.
   - Number of public IPs attached.

6. **Log Analytics**
   - All scenarios (`loganalytics-*`) price **Analytics Logs Data Retention** only; **ingestion is priced as 0** in this catalog snapshot.
   - Real cost is dominated by **ingestion GB**.

   **What to check**:
   - Log Analytics PerGB2018 ingestion price in West Europe.
   - Ingestion volumes: 200 GB (baseline), 80 GB (CO), 350 GB (HP).
   - Retention beyond 31 days, and archive pricing.

7. **Backup vault**
   - `backup-vault-*` resources have **0 units**, so no cost is modeled.
   - Real cost is:
     - Protected instances (per DB/VM).
     - Backup storage (GB/month).
     - Read/restore operations.

   **What to check**:
   - Recovery Services vault pricing for SQL DB backups and App Service content backups.
   - Retention policy (daily/weekly/monthly/yearly).

8. **SQL reservations**
   - `sql-db-co` and `sql-db-hp` show **reservation unit prices (824.2162 €/hour)** but then a **much lower monthly cost** (68.68 €/month). This is inconsistent.
   - Treat the **monthly cost as the intended estimate**, but verify.

   **What to check**:
   - 1‑year reserved capacity for SQL Database GP Gen5, 1 vCore and 4 vCores, West Europe.
   - Compare vs pay‑as‑you‑go vCore pricing.

9. **App Service reservations / Dev/Test**
   - `appsvc-plan-co` uses **DevTestConsumption** pricing but is labeled “reserved”.
   - `appsvc-plan-hp` uses a reservation SKU but with a very low monthly cost.

   **What to check**:
   - Production App Service pricing (Standard S1, Premium v3 P1v3/P2v3) in West Europe.
   - 1‑year reserved App Service plan savings (if applicable).
   - Ensure you’re not mixing Dev/Test with production.

---

## 5. FinOps recommendations

### 5.1 Quick wins

1. **Fix Redis and Public IP pricing**
   - Replace the **€100/month placeholders** with real prices:
     - Basic C0 Redis is likely **<€20/month**.
     - Standard C1/C2 Redis will be more, but still far from €100 in many cases.
     - Standard Public IP is typically **single‑digit €/month**.
   - This will **significantly reduce** the apparent monthly totals and change the relative differences between scenarios.

2. **Right‑size App Service**
   - For 50k MAU, a **Standard S1 with 2 instances** may be enough if:
     - You use Redis effectively.
     - You optimize CPU and memory usage.
   - But ensure you use **production pricing**, not Dev/Test.
   - Consider **Premium v3 P0v3** as a middle ground: better performance, still relatively cheap.

3. **Right‑size SQL**
   - Start with **1–2 vCores GP Gen5** and monitor:
     - DTU/vCore utilization.
     - Query performance and wait stats.
   - If CPU < 40% and IO is fine, **1 vCore** may be enough (cost_optimized).
   - If you expect growth, **2 vCores** (baseline) is a safer starting point.

4. **Tune Log Analytics ingestion**
   - Baseline 200 GB/month is reasonable; cost_optimized 80 GB is lean.
   - Use:
     - **Sampling** for verbose logs.
     - **Diagnostic settings** to send only necessary categories.
   - This is a **direct linear cost driver**.

5. **Storage redundancy choices**
   - For a small app, **LRS vs GRS vs GZRS**:
     - If RPO/RTO can be met with backups and DR, **LRS** may be enough (cost_optimized).
     - If you need cross‑region durability, keep **GRS/GZRS** (baseline/HP).
   - This can save **30–50%** on storage line items.

### 5.2 Spot vs Pay‑as‑you‑go vs Reserved

- **Spot**:
  - Not applicable to App Service, SQL DB, Redis, or managed PaaS here.
  - Would only apply if you moved to VM‑based architecture (AKS/VMSS).

- **Pay‑as‑you‑go (baseline)**:
  - Baseline uses **payg** for App Service and SQL.
  - Good for **initial months** while you validate sizing.
  - Once stable, consider **1‑year reservations**:
    - SQL DB vCores.
    - App Service plan (where supported).
  - Typical savings: **30–40%** vs payg.

- **Reserved (cost_optimized & high_performance)**:
  - Both scenarios conceptually assume **1‑year reservations** for SQL and App Service.
  - But catalog data is inconsistent; verify real reservation prices.
  - Strategy:
    - Start baseline on payg.
    - After 1–3 months of stable usage, **buy reservations** for:
      - SQL vCores (1–2 vCores baseline; 4 vCores HP).
      - App Service plan instances (2–3 instances).
    - Keep **network, storage, Log Analytics** on payg (usage‑based).

### 5.3 Right‑sizing ideas

- **App Service**
  - Start with **P0v3 (2 instances)** or **S1 (2 instances)**.
  - Use **autoscale** based on CPU/RPS to add a 3rd instance at peak.
  - If CPU is consistently low (<30%), consider:
    - Reducing instance size (S1 → B3 or P0v3 → S1).
    - Reducing instance count (2 → 1) only if SLA and maintenance windows allow.

- **SQL Database**
  - Monitor:
    - CPU, IO, log write throughput.
    - Query performance.
  - If underutilized, **scale down vCores** or use **serverless** for spiky workloads.
  - For multiple DBs in future, consider **elastic pools** or **Azure SQL Managed Instance** (but MI has higher base cost).

- **Redis**
  - For non‑critical caching:
    - **Basic C0** is fine (cost_optimized).
  - For session state or critical cache:
    - Use **Standard C1/C2** with replica (baseline/HP).
  - Monitor:
    - Cache hit ratio.
    - Memory usage.
    - Connection count.

- **Log Analytics**
  - Use **data collection rules** to:
    - Drop noisy logs.
    - Shorten retention for low‑value logs.
  - Consider **archive tier** for long‑term retention.

### 5.4 Region and egress considerations

- All scenarios are in **West Europe**, which is appropriate for EU users.
- **Egress costs**:
  - 500 GB (baseline), 350 GB (CO), 900 GB (HP) are **linear cost drivers**.
  - To reduce:
    - Use **CDN/Front Door** to cache content closer to users (may shift cost from egress to CDN, but often cheaper and faster).
    - Compress responses (gzip/br).
    - Optimize payload sizes (images, JSON).
- **Cross‑region DR**:
  - If you add a secondary region, expect:
    - Additional SQL/Redis/Storage/App Service costs.
    - Inter‑region data transfer charges.

---

## 6. Delta tables vs baseline

Because all three scenarios share the same **€200/month placeholder** for Redis + Public IP and have similar modeling gaps, these deltas are **directional only**.

### 6.1 Overall totals – monthly & yearly

#### Monthly totals (priced vs with estimates)

| Scenario        | Metric                    | Baseline (€) | Scenario (€) | Δ Abs (€) | Δ % vs Baseline |
|----------------|---------------------------|-------------:|-------------:|----------:|----------------:|
| cost_optimized | Priced only               | 230.63       | 119.69       | -110.94   | -48.1%          |
| cost_optimized | With estimates + missing  | 435.86       | 324.83       | -111.03   | -25.5%          |
| high_perf      | Priced only               | 230.63       | 179.78       | -50.85    | -22.0%          |
| high_perf      | With estimates + missing  | 435.86       | 385.20       | -50.66    | -11.6%          |

#### Yearly totals

| Scenario        | Metric                    | Baseline (€) | Scenario (€) | Δ Abs (€) | Δ % vs Baseline |
|----------------|---------------------------|-------------:|-------------:|----------:|----------------:|
| cost_optimized | Priced only               | 2767.54      | 1436.31      | -1331.23  | -48.1%          |
| cost_optimized | With estimates + missing  | 5230.26      | 3897.89      | -1332.37  | -25.5%          |
| high_perf      | Priced only               | 2767.54      | 2157.40      | -610.14   | -22.0%          |
| high_perf      | With estimates + missing  | 5230.26      | 4622.40      | -607.86   | -11.6%          |

> Note: The **% savings on “priced only”** are inflated because reservations and Dev/Test pricing are cheaper in the catalog snapshot. Use real production prices for a final business case.

### 6.2 Category‑level monthly deltas vs baseline

#### Cost Optimized vs Baseline – monthly by bucket

| Bucket            | Baseline (€) | Cost Opt (€) | Δ Abs (€) | Δ % vs Baseline |
|-------------------|------------:|-------------:|----------:|----------------:|
| Compute (AppSvc)  | 56.21       | 37.89        | -18.32    | -32.6%          |
| DB (SQL + Redis)  | 205.70      | 168.68       | -37.02    | -18.0%          |
| Storage (Blob)    | 0.19        | 0.10         | -0.09     | -47.4%          |
| Network           | 137.17      | 108.91       | -28.26    | -20.6%          |
| Security          | 0.52        | 0.26         | -0.26     | -50.0%          |
| Monitoring        | 22.48       | 8.99         | -13.49    | -60.0%          |
| Backup/DR         | 13.84       | 0.00         | -13.84    | -100.0%         |
| Other             | 0.00        | 0.00         | 0.00      | —               |
| **Total**         | **435.86**  | **324.83**   | **-111.03**| **-25.5%**     |

Key drivers of savings:
- Smaller App Service plan.
- Smaller SQL DB.
- No WAF, lower egress, reduced Log Analytics, and no ASR/Bastion in this scenario.

#### High Performance vs Baseline – monthly by bucket

| Bucket            | Baseline (€) | High Perf (€) | Δ Abs (€) | Δ % vs Baseline |
|-------------------|------------:|--------------:|----------:|----------------:|
| Compute (AppSvc)  | 56.21       | 36.61         | -19.60    | -34.9%          |
| DB (SQL + Redis)  | 205.70      | 168.68        | -37.02    | -18.0%          |
| Storage (Blob)    | 0.19        | 0.38          | +0.19     | +100.0%         |
| Network           | 137.17      | 139.15        | +1.98     | +1.4%           |
| Security          | 0.52        | 1.04          | +0.52     | +100.0%         |
| Monitoring        | 22.48       | 39.34         | +16.86    | +75.0%          |
| Backup/DR         | 13.84       | 0.00          | -13.84    | -100.0%         |
| Other             | 0.00        | 0.00          | 0.00      | —               |
| **Total**         | **435.86**  | **385.20**    | **-50.66**| **-11.6%**     |

Key observations:
- Despite being “high performance”, the scenario appears **cheaper** on compute and DB due to **reservation pricing**.
- Costs increase in:
  - Storage (GZRS, more GB).
  - Network (more egress).
  - Security (Key Vault Premium).
  - Monitoring (more Log Analytics ingestion).
- Backup/DR (ASR) is not modeled here, which also reduces apparent cost.

---

### Final guidance

- Use the **baseline** as your functional reference architecture.
- Use **cost_optimized** and **high_performance** as **what‑if envelopes**, not as exact quotes.
- Before committing:
  1. Re‑price Redis, Public IP, Storage, App Gateway, NAT, Log Analytics, and Backup in the **Azure Pricing Calculator**.
  2. Decide on **reservation strategy** (SQL + App Service) after 1–3 months of real usage.
  3. Confirm **SLA and DR requirements** to choose between LRS/GRS/GZRS and whether ASR or cross‑region deployment is required.