## 1. Baseline / Recommended scenario – short narrative

The baseline is a standard two‑tier web application in West Europe:

- **Web tier**: A Linux Azure App Service (Premium v3‑class) hosts the application. It’s fronted by an **Application Gateway WAF v2** with a public IP, providing TLS termination, WAF protection, and HTTP(S) routing.
- **Data tier**: A single **Azure SQL Database, Business Critical, 4 vCores** (BC_Gen5_4) provides high‑availability transactional storage. Automated backups and long‑term retention use underlying blob storage.
- **Networking**: A **VNet** is used for App Service VNet integration and private endpoints to SQL. A **NAT Gateway** handles outbound internet traffic from private resources.
- **Security & secrets**: **Azure Key Vault** stores connection strings, secrets, and certificates, accessed by App Service and automation.
- **Caching**: **Azure Cache for Redis** offloads reads and session state from SQL.
- **Monitoring & logging**: A **Log Analytics workspace** ingests platform logs and metrics from App Service, SQL, networking, and security components.
- **Backup & DR**: A **Recovery Services vault** protects app content/config and future stateful components; **Azure Site Recovery** is modeled for at least one protected instance. SQL relies on built‑in HA and (optionally) geo‑replication.

The key design choice in the baseline is **SQL Database on pay‑as‑you‑go**, which maximizes flexibility (scale up/down, stop, or decommission) at the cost of a higher effective hourly rate compared to a 1‑year reservation.

> Important: The JSON pricing for SQL BC 4 vCores is clearly mismatched (it picked an Elastic Jobs Agent and a GP reservation SKU). For the purpose of comparison, both scenarios assume **~$100/month, $1,200/year** for the SQL DB, but you should re‑price this in the Azure Pricing Calculator with the correct **Business Critical Gen5 4 vCore** SKU.

---

## 2. Other scenarios and how they differ

### Cost Optimized – 1‑year reserved DB

Same logical architecture (two‑tier app, same services), but with cost‑saving measures:

- **Database**: Moves Azure SQL DB to **1‑year reserved capacity** (still 4 vCores, Business Critical intent). This trades flexibility for a lower effective rate.
- **Compute & network**: Assumes **reduced active hours** (600 vs 730) for App Service, Application Gateway, NAT, Redis, etc., representing off‑hours scaling or scheduled shutdowns.
- **Storage & backup**:
  - SQL backup storage uses **LRS instead of GRS**.
  - Slightly lower backup volumes and operations.
- **Monitoring & Key Vault**:
  - **Lower Log Analytics ingestion** (120 GB vs 200 GB).
  - **Fewer Key Vault operations** (30k vs 50k) via better secret caching.
- **DR**: Similar minimal ASR footprint, slightly reduced replicated storage.

Net effect (within this model): **very small total cost difference** (~$0.3/month cheaper), because the SQL DB cost itself is modeled as the same $100/month in both scenarios. In a real pricing run with correct BC 4 vCore SKUs, you should expect **~30–35% savings on the SQL compute portion** with a 1‑year reservation.

> There is no “high_performance” scenario in the JSON; only `baseline` and `cost_optimized` are present. I’ll focus on those two.

---

## 3. Scenario details

### 3.1 Baseline scenario

#### Main components (by concern)

- **Compute**
  - Azure App Service Plan (Premium v3‑class, Linux, 1 instance)
- **Database**
  - Azure SQL Database – Business Critical, Gen5, 4 vCores (PAYG)
- **Storage**
  - Blob storage for SQL automated backups & LTR (GRS, estimated)
- **Network**
  - Virtual Network (no direct charge)
  - Application Gateway WAF v2 + Standard Public IP
  - NAT Gateway / bandwidth for outbound traffic
- **Security / Secrets**
  - Azure Key Vault (Standard) for secrets, keys, certificates
- **Caching**
  - Azure Cache for Redis (Standard C1)
- **Monitoring / Analytics**
  - Log Analytics workspace (PerGB2018)
- **Backup & DR**
  - Recovery Services vault (Backup)
  - Azure Site Recovery (1 protected instance)
- **Other**
  - None beyond the above

#### 3.1.1 Resource‑level pricing table – Baseline

> Note: Many items have placeholder or mismatched SKUs; “Monthly Cost” and “Yearly Cost” are taken from the JSON, even when marked as estimated or missing. Where the catalog failed, the scenario totals inject **$100/month placeholders** per category.

| Scenario | Resource ID                 | Category                 | Service          | SKU (requested / resolved)                            | Region     | Billing | Unit Price | Unit            | Units | Monthly Cost | Yearly Cost | Notes |
|---------|-----------------------------|--------------------------|------------------|--------------------------------------------------------|-----------|--------|-----------|-----------------|-------|-------------|------------|-------|
| baseline | vnet-main                  | network.vnet            | Virtual Network  | n/a / Virtual Network                                  | westeurope | payg   | 0.00      | VNet            | 1     | 0.00        | 0.00       | Logical VNet; no direct charge. |
| baseline | appsvc-plan-prod           | appservice              | Azure App Service | P1v3 / P0v3 App (Premium v3 Linux)                    | westeurope | payg   | 0.089    | 1 Hour          | 730   | 64.97       | 779.64     | 1× Premium v3‑class plan; JSON category total later overrides to $100/month placeholder. |
| baseline | sql-db-bc4-pag             | db.sql                  | SQL Database     | BC_Gen5_4 / JA100 Job Agent (mismatch)                | westeurope | payg   | 0.038    | 1 Hour          | 730   | 27.74       | 332.88     | Intended: SQL DB Business Critical 4 vCores PAYG; pricing here is wrong and underestimates. Category total later forced to $100/month. |
| baseline | sql-db-bc4-backup-storage  | storage.blob            | Storage          | Standard_GRS / ADLS Gen2 hot+cool (estimated)         | westeurope | payg   | —         | —               | —     | 0.39        | 4.62       | Approx. 300 GB (200 GB hot, 100 GB cool) for SQL backups, GRS. |
| baseline | appgw-waf-public           | network.appgw           | Application Gateway | WAF_v2 / Standard Capacity Units (discounted)      | westeurope | payg   | 0.008    | 1/Hour          | 730   | 5.84        | 70.08      | WAF v2; JSON category total later set to $100/month placeholder. |
| baseline | public-ip-appgw            | network.public_ip       | Public IP        | Standard / (missing)                                  | westeurope | payg   | —         | —               | —     | —           | —          | Standard Public IP; pricing missing. Category total later set to $100/month placeholder. |
| baseline | nat-egress                 | network.nat             | Bandwidth        | Standard / Standard Inter‑AZ Data Transfer Out        | westeurope | payg   | 0.01     | 1 GB            | 100   | 1.00        | 12.00      | 100 GB/month outbound via NAT. Cost scales with egress volume. |
| baseline | kv-main                    | security.keyvault       | Key Vault        | standard / Standard Operations                         | westeurope | payg   | 0.03     | 10K operations  | 5     | 0.15        | 1.80       | ~50k operations/month. Cost scales with operation count and advanced key ops. |
| baseline | redis-cache-basic          | cache.redis             | Azure Cache for Redis | C1 / (missing)                                   | westeurope | payg   | —         | —               | —     | —           | —          | Standard C1 Redis; pricing missing. Category total later set to $100/month placeholder. |
| baseline | log-analytics-main         | monitoring.loganalytics | Log Analytics    | PerGB2018 / Analytics Logs Retention                  | westeurope | payg   | 0.13     | 1 GB/Month      | 200   | 26.00       | 312.00     | 200 GB/month ingestion; cost scales with data volume and retention. Category total later set to $100/month placeholder. |
| baseline | backup-vault-main          | backup.vault            | Backup           | Standard / ADLS Gen2 Vaulted LRS Write Ops            | westeurope | payg   | 0.054    | 10K operations  | 10    | 0.54        | 6.48       | 250 GB protected; JSON category total later set to $100/month placeholder. |
| baseline | asr-dr                     | dr.asr                  | Azure Site Recovery | n/a / System Center VM Replicated                  | westeurope | payg   | 16.00    | 1/Month         | 1     | 16.00       | 192.00     | 1 protected instance; DR cost scales with number of protected instances. |

#### 3.1.2 Aggregated by category – Baseline

The totals object injects **placeholder $100/month per category** where pricing is missing or mismatched. That’s why `total_monthly = 717.54` while the sum of explicit resource costs is only ~$142.

I’ll map Azure categories into higher‑level buckets:

- **Compute**: `appservice`
- **DB**: `db.sql`
- **Storage**: `storage.blob`
- **Network**: `network.vnet`, `network.appgw`, `network.public_ip`, `network.nat`
- **Analytics / Monitoring**: `monitoring.loganalytics`
- **Security**: `security.keyvault`
- **Backup/DR**: `backup.vault`, `dr.asr`
- **Caching / Other**: `cache.redis`, plus anything uncategorized

**Baseline – category summary**

| High‑level Category | Underlying JSON Categories                          | Monthly (with estimates) | Of which: Priced | Estimated | Missing (placeholder) | Est. share of modeled cost* |
|---------------------|-----------------------------------------------------|--------------------------|------------------|-----------|------------------------|-----------------------------|
| Compute             | appservice                                          | 100.00                   | 0.00             | 0.00      | 100.00                 | ~0% priced, 100% placeholder |
| DB                  | db.sql                                             | 100.00                   | 0.00             | 0.00      | 100.00                 | ~0% priced, 100% placeholder |
| Storage             | storage.blob                                       | 0.39                     | 0.00             | 0.39      | 0.00                   | 100% estimated              |
| Network             | network.vnet, network.appgw, network.public_ip, network.nat | 201.00 (0 + 100 + 100 + 1) | 1.00 (NAT)      | 0.00      | 200.00                 | ~0.5% priced, 99.5% placeholder |
| Security            | security.keyvault                                  | 0.15                     | 0.15             | 0.00      | 0.00                   | 100% priced                 |
| Caching / Other     | cache.redis                                        | 100.00                   | 0.00             | 0.00      | 100.00                 | 100% placeholder            |
| Analytics / Monitoring | monitoring.loganalytics                         | 100.00                   | 0.00             | 0.00      | 100.00                 | 100% placeholder            |
| Backup              | backup.vault                                       | 100.00                   | 0.00             | 0.00      | 100.00                 | 100% placeholder            |
| DR                  | dr.asr                                             | 16.00                    | 16.00            | 0.00      | 0.00                   | 100% priced                 |
| **Total**           |                                                     | **717.54**               | **17.15**        | **0.39**  | **700.00**             | Priced+estimated ≈ 2.4% of total |

\* “Modeled cost” here means `monthly_with_estimates` (717.54). The vast majority is placeholder/missing.

**Key takeaway**: For the baseline, **SQL, App Service, App Gateway, Redis, Public IP, Log Analytics, Backup vault** are dominated by **placeholders**, not real catalog prices. For any serious estimate, re‑price these in the Azure Pricing Calculator.

---

### 3.2 Cost Optimized scenario

#### Main components (by concern)

- **Compute**
  - Azure App Service Plan (Premium v3‑class, Linux, 1 instance, 600 hours/month)
- **Database**
  - Azure SQL Database – Business Critical 4 vCores, **1‑year reserved capacity** (modeled as $100/month placeholder)
- **Storage**
  - Blob storage for SQL backups & LTR (LRS, slightly lower volume, estimated)
- **Network**
  - Same VNet topology.
  - Application Gateway WAF v2 (600 hours/month).
  - Standard Public IP (pricing missing).
  - NAT Gateway with 80 GB/month outbound.
- **Security / Secrets**
  - Azure Key Vault (Standard) with fewer operations (~30k/month).
- **Caching**
  - Azure Cache for Redis Basic B1 (non‑HA, 600 hours/month; pricing missing).
- **Monitoring / Analytics**
  - Log Analytics workspace with reduced ingestion (120 GB/month).
- **Backup & DR**
  - Recovery Services vault with lower protected volume.
  - Azure Site Recovery (1 protected instance, lower replicated storage).

#### 3.2.1 Resource‑level pricing table – Cost Optimized

| Scenario      | Resource ID               | Category                 | Service          | SKU (requested / resolved)                            | Region     | Billing   | Unit Price | Unit            | Units | Monthly Cost | Yearly Cost | Notes |
|--------------|---------------------------|--------------------------|------------------|--------------------------------------------------------|-----------|----------|-----------|-----------------|-------|-------------|------------|-------|
| cost_optimized | vnet-main-co            | network.vnet            | Virtual Network  | n/a / Virtual Network                                  | westeurope | reserved | 0.00      | VNet            | 1     | 0.00        | 0.00       | No direct cost. |
| cost_optimized | appsvc-plan-co          | appservice              | Azure App Service | P1v3 / P0v3 App (Premium v3 Linux)                    | westeurope | payg     | 0.089    | 1 Hour          | 600   | 53.40       | 640.80     | Reduced runtime hours (600). Category total later set to $100/month placeholder. |
| cost_optimized | sql-db-bc4-res1y        | db.sql                  | SQL Database     | BC_Gen5_4 / SQLDB_GP_Compute_Gen5 vCore (reservation) | westeurope | reserved | 953.00   | 1 Hour (ambig.) | 1     | 100.00      | 1200.00    | Intended: BC 4 vCores 1‑year reserved. JSON uses GP compute SKU and ambiguous UOM; cost forced to $100/month placeholder. |
| cost_optimized | sql-db-bc4-backup-storage-co | storage.blob       | Storage          | Standard_LRS / ADLS Gen2 hot+cool (estimated)         | westeurope | payg     | —         | —               | —     | 0.34        | 4.14       | ~250 GB total (150 GB hot, 100 GB cool), LRS. |
| cost_optimized | appgw-waf-public-co     | network.appgw           | Application Gateway | WAF_v2 / Standard Capacity Units (discounted)      | westeurope | payg     | 0.008    | 1/Hour          | 600   | 4.80        | 57.60      | Reduced active hours. Category total later set to $100/month placeholder. |
| cost_optimized | public-ip-appgw-co      | network.public_ip       | Public IP        | Standard / (missing)                                  | westeurope | payg     | —         | —               | —     | —           | —          | Standard Public IP; pricing missing. |
| cost_optimized | nat-egress-co           | network.nat             | Bandwidth        | Standard / Standard Inter‑AZ Data Transfer Out        | westeurope | payg     | 0.01     | 1 GB            | 80    | 0.80        | 9.60       | 80 GB/month outbound via NAT. |
| cost_optimized | kv-main-co              | security.keyvault       | Key Vault        | standard / Standard Operations                         | westeurope | payg     | 0.03     | 10K operations  | 3     | 0.09        | 1.08       | ~30k operations/month. |
| cost_optimized | redis-cache-co          | cache.redis             | Azure Cache for Redis | B1 / (missing)                                   | westeurope | payg     | —         | —               | —     | —           | —          | Basic B1 Redis (non‑HA); pricing missing. |
| cost_optimized | log-analytics-co        | monitoring.loganalytics | Log Analytics    | PerGB2018 / Analytics Logs Retention                  | westeurope | payg     | 0.13     | 1 GB/Month      | 120   | 15.60       | 187.20     | 120 GB/month ingestion; category total later set to $100/month placeholder. |
| cost_optimized | backup-vault-co         | backup.vault            | Backup           | Standard / ADLS Gen2 Vaulted LRS Write Ops            | westeurope | payg     | 0.054    | 10K operations  | 5     | 0.27        | 3.24       | Lower backup volume and operations; category total later set to $100/month placeholder. |
| cost_optimized | asr-dr-co               | dr.asr                  | Azure Site Recovery | n/a / System Center VM Replicated                  | westeurope | payg     | 16.00    | 1/Month         | 1     | 16.00       | 192.00     | 1 protected instance. |

#### 3.2.2 Aggregated by category – Cost Optimized

Same placeholder pattern as baseline.

| High‑level Category | Underlying JSON Categories                          | Monthly (with estimates) | Of which: Priced | Estimated | Missing (placeholder) | Est. share of modeled cost* |
|---------------------|-----------------------------------------------------|--------------------------|------------------|-----------|------------------------|-----------------------------|
| Compute             | appservice                                          | 100.00                   | 0.00             | 0.00      | 100.00                 | 100% placeholder            |
| DB                  | db.sql                                             | 100.00                   | 0.00             | 0.00      | 100.00                 | 100% placeholder            |
| Storage             | storage.blob                                       | 0.34                     | 0.00             | 0.34      | 0.00                   | 100% estimated              |
| Network             | network.vnet, network.appgw, network.public_ip, network.nat | 200.80 (0 + 100 + 100 + 0.8) | 0.80 (NAT)      | 0.00      | 200.00                 | ~0.4% priced, 99.6% placeholder |
| Security            | security.keyvault                                  | 0.09                     | 0.09             | 0.00      | 0.00                   | 100% priced                 |
| Caching / Other     | cache.redis                                        | 100.00                   | 0.00             | 0.00      | 100.00                 | 100% placeholder            |
| Analytics / Monitoring | monitoring.loganalytics                         | 100.00                   | 0.00             | 0.00      | 100.00                 | 100% placeholder            |
| Backup              | backup.vault                                       | 100.00                   | 0.00             | 0.00      | 100.00                 | 100% placeholder            |
| DR                  | dr.asr                                             | 16.00                    | 16.00            | 0.00      | 0.00                   | 100% priced                 |
| **Total**           |                                                     | **717.23**               | **16.89**        | **0.34**  | **700.00**             | Priced+estimated ≈ 2.4% of total |

\* Based on `monthly_with_estimates` (717.23).

---

## 4. Resources where pricing failed – what to check manually

Across both scenarios, the following resources have **missing or clearly wrong pricing** and must be re‑checked in the Azure Pricing Calculator or Cost Estimator:

### Baseline

1. **Azure SQL Database – Business Critical 4 vCores (sql-db-bc4-pag)**
   - Problem: Resolved to `SQL Database - Elastic Jobs Agent (JA100)` instead of BC Gen5 4 vCores.
   - Action:
     - In the Azure Pricing Calculator, select:
       - Service: **Azure SQL Database**
       - Deployment: **Single database**
       - Compute tier: **Business Critical**
       - Compute: **Gen5, 4 vCores**
       - Region: **West Europe**
       - Billing: **Pay‑as‑you‑go**
     - Include storage (512 GB) and zone redundancy if required.

2. **App Service Plan – Premium v3 (appsvc-plan-prod)**
   - Problem: SKU mismatch (P1v3 requested, P0v3 priced; category total uses $100 placeholder).
   - Action:
     - In the calculator, choose:
       - Service: **App Service**
       - OS: **Linux**
       - Plan: **Premium v3**
       - Size: **P1v3**
       - Instances: **1**
       - Hours: **730/month**

3. **Application Gateway WAF v2 (appgw-waf-public)**
   - Problem: Partial pricing (capacity units only, WAF fixed cost likely missing; category total uses $100 placeholder).
   - Action:
     - In the calculator, choose:
       - Service: **Application Gateway**
       - SKU: **WAF v2**
       - Region: **West Europe**
       - Estimate:
         - **Fixed cost** (gateway hours)
         - **Capacity units** (based on throughput and connections)
         - **Data processed** and **rules** as needed.

4. **Public IP – Standard (public-ip-appgw)**
   - Problem: Pricing missing.
   - Action:
     - In the calculator, choose:
       - Service: **IP Addresses**
       - SKU: **Standard**
       - Region: **West Europe**
       - 1 static IP, 730 hours/month.

5. **Azure Cache for Redis – Standard C1 (redis-cache-basic)**
   - Problem: Pricing missing.
   - Action:
     - In the calculator, choose:
       - Service: **Azure Cache for Redis**
       - Tier: **Standard**
       - Size: **C1**
       - Region: **West Europe**
       - 1 instance, 730 hours/month.

6. **Log Analytics (log-analytics-main)**
   - Problem: SKU mismatch (retention vs ingestion; category total uses $100 placeholder).
   - Action:
     - In the calculator, choose:
       - Service: **Azure Monitor / Log Analytics**
       - Pricing tier: **Pay‑as‑you‑go (PerGB2018)**
       - Region: **West Europe**
       - **Ingestion**: 200 GB/month
       - **Retention**: default 31 days (or your policy)
       - Add archive if needed.

7. **Backup vault (backup-vault-main)**
   - Problem: Only write operations priced; protected instance and storage not modeled; category total uses $100 placeholder.
   - Action:
     - In the calculator, choose:
       - Service: **Backup**
       - Protected workloads (Azure Files, VMs, etc.)
       - Protected data: ~250 GB
       - Region: **West Europe**

### Cost Optimized

1. **Azure SQL Database – 1‑year reserved (sql-db-bc4-res1y)**
   - Problem: Uses **General Purpose** reservation SKU, not Business Critical; unit of measure ambiguous; cost forced to $100/month placeholder.
   - Action:
     - In the calculator, choose:
       - Service: **Azure SQL Database**
       - Tier: **Business Critical**
       - Compute: **Gen5, 4 vCores**
       - Billing: **1‑year reserved capacity**
       - Region: **West Europe**
       - Include storage (512 GB) and zone redundancy.

2. **App Service Plan – Premium v3 (appsvc-plan-co)**
   - Same issue as baseline (P1v3 vs P0v3 mismatch; category placeholder).
   - Action: Same as baseline, but with **600 hours/month** if you want to model off‑hours shutdown.

3. **Application Gateway WAF v2 (appgw-waf-public-co)**
   - Same partial pricing as baseline; category placeholder.
   - Action: Same as baseline, but with **600 hours/month** if you truly scale down.

4. **Public IP – Standard (public-ip-appgw-co)**
   - Pricing missing.
   - Action: Same as baseline.

5. **Azure Cache for Redis – Basic B1 (redis-cache-co)**
   - Pricing missing.
   - Action:
     - Service: **Azure Cache for Redis**
     - Tier: **Basic**
     - Size: **B1**
     - Region: **West Europe**
     - 600 hours/month if you plan to shut down off‑hours (note: Redis is typically always‑on).

6. **Log Analytics (log-analytics-co)**
   - Same ingestion vs retention mismatch; category placeholder.
   - Action: Same as baseline, but with **120 GB/month** ingestion.

7. **Backup vault (backup-vault-co)**
   - Same as baseline; only write ops priced; category placeholder.
   - Action: Same as baseline, but with **180 GB** protected.

---

## 5. FinOps recommendations

### 5.1 Quick wins

1. **Fix SQL Database SKU and apply reservations**
   - Correctly price **Business Critical Gen5 4 vCores**.
   - For a steady 24×7 production workload, **1‑year reserved capacity** typically saves **~30–35%** vs PAYG on the compute portion.
   - If you’re confident in 3‑year commitment, savings can be higher.

2. **Right‑size App Service**
   - Validate whether **P1v3** is required:
     - If CPU/memory utilization is low, consider **P0v3** or even **Premium v2**.
     - Use **Autoscale** instead of fixed 1 instance if load is variable.
   - If non‑production or business‑hours only, implement **scheduled shutdown** or **scale‑to‑zero** patterns (e.g., using Automation or Functions) to realize the 600‑hours assumption in the cost‑optimized scenario.

3. **Optimize Log Analytics ingestion**
   - Current assumptions (200 GB vs 120 GB) are arbitrary; real costs can be significant.
   - Actions:
     - Enable **sampling** and **filtering** for noisy logs (e.g., verbose App Service logs).
     - Use **Diagnostic settings** to send only required categories.
     - Move long‑term logs to **archive** or **storage accounts** with cheaper retention.

4. **Key Vault usage optimization**
   - Cache secrets in the app (e.g., in memory or configuration) to reduce Key Vault calls.
   - Avoid polling; use **managed identities** and configuration reload patterns.

5. **Backup & DR rationalization**
   - Ensure you’re not double‑paying:
     - Azure SQL DB already includes **automated backups** and can use **geo‑replication**.
     - Only back up what you truly need in the Recovery Services vault (e.g., app content, configuration, VMs).
   - Tune **retention policies** to business RPO/RTO, not “keep everything forever”.

### 5.2 Spot vs PAYG vs Reserved

- **Azure SQL Database**
  - No “spot” concept; choice is **PAYG vs reserved capacity**.
  - For a **steady production DB**, reserved capacity is almost always recommended:
    - Start with **1‑year** to keep flexibility.
    - Consider **3‑year** if workload is stable and critical.
  - If you expect major changes (e.g., migration to Azure SQL MI or Hyperscale), keep some portion on PAYG.

- **App Service**
  - No spot; only PAYG.
  - Use **Autoscale** and **scheduled scaling** to mimic “spot‑like” savings by reducing hours and instances.
  - For very stable, always‑on workloads, consider **App Service reserved instances** (separate from SQL reservations) if available in your region.

- **Redis / Application Gateway**
  - No spot; PAYG only.
  - Savings come from:
    - Right‑sizing SKUs (e.g., Basic vs Standard, smaller sizes).
    - Scaling down instances or capacity units off‑peak.
    - Using **Front Door** or **Azure CDN** where appropriate to offload traffic.

### 5.3 Right‑sizing ideas

- **SQL Database**
  - Monitor DTU/vCore utilization, CPU, IO, and wait stats.
  - If average utilization is consistently low (<30%), consider:
    - Dropping from **4 vCores to 2 vCores**.
    - Or moving from **Business Critical** to **General Purpose** if latency and HA requirements allow.
  - Conversely, if you’re saturating CPU/IO, scale up before performance issues hit.

- **App Service**
  - Use **Application Insights** and **Metrics** to track CPU, memory, and response times.
  - If utilization is low:
    - Downsize from **P1v3** to **P0v3** or fewer instances.
  - If you have multiple small apps, consider **consolidating** them into a shared App Service Plan.

- **Redis**
  - For production, **Standard** (HA) is usually preferred over Basic.
  - Right‑size memory and throughput:
    - If hit rate is low or memory is underused, downsize.
    - If you’re evicting keys or seeing high latency, upsize.

- **Log Analytics**
  - Right‑size **retention** (e.g., 30–90 days hot, longer in archive).
  - Use **data caps** and **daily quotas** to avoid runaway ingestion.

### 5.4 Region and egress considerations

- Both scenarios are in **West Europe**:
  - If your users are primarily in another region, consider:
    - Deploying closer to users to reduce latency and possibly egress.
    - Using **Azure Front Door** or **CDN** to cache static content and reduce origin egress.
- **Egress costs**:
  - App Service and Application Gateway outbound traffic to the internet is billed as **Bandwidth**.
  - NAT Gateway egress is modeled at **$0.01/GB** for inter‑AZ; real internet egress pricing is tiered and may differ.
  - For chatty cross‑region or cross‑cloud integrations, consider:
    - Co‑locating services in the same region.
    - Using **ExpressRoute** or **Private Peering** for predictable costs.

---

## 6. Delta tables vs Baseline

Because both scenarios are heavily dominated by **placeholders** and **mismatched SKUs**, these deltas are **illustrative only**. They do not reflect real SQL reservation savings.

### 6.1 Overall monthly/yearly totals

Using the `totals` section:

- Baseline:
  - `monthly_priced`: 17.15
  - `monthly_with_estimates`: 717.54
  - `yearly_priced`: 205.80
  - `yearly_with_estimates`: 8610.42
- Cost Optimized:
  - `monthly_priced`: 16.89
  - `monthly_with_estimates`: 717.23
  - `yearly_priced`: 202.68
  - `yearly_with_estimates`: 8606.82

**Overall totals delta vs baseline**

| Scenario       | Metric                    | Baseline | Cost Optimized | Δ Absolute | Δ % vs Baseline |
|---------------|---------------------------|----------|----------------|-----------:|----------------:|
| cost_optimized | Monthly – priced only     | 17.15    | 16.89          | -0.26      | -1.52%          |
| cost_optimized | Monthly – with estimates  | 717.54   | 717.23         | -0.31      | -0.04%          |
| cost_optimized | Yearly – priced only      | 205.80   | 202.68         | -3.12      | -1.52%          |
| cost_optimized | Yearly – with estimates   | 8610.42  | 8606.82        | -3.60      | -0.04%          |

Interpretation:

- Within this model, the **cost optimized** scenario is only **~$0.31/month cheaper** overall.
- The tiny delta is driven by:
  - Slightly lower NAT, Key Vault, Log Analytics, backup storage.
  - Slightly fewer App Gateway and App Service hours.
- **SQL reservation benefits are not visible** because both scenarios use the same $100/month placeholder for DB.

### 6.2 Category‑level monthly deltas

Using `by_category.monthly_with_estimates`:

#### 6.2.1 High‑level mapping

I’ll compare JSON categories directly (they’re identical across scenarios except for small numeric differences).

**Category‑level monthly delta – Cost Optimized vs Baseline**

| JSON Category          | Baseline Monthly | Cost Opt Monthly | Δ Absolute | Δ % vs Baseline |
|------------------------|-----------------:|-----------------:|-----------:|----------------:|
| network.vnet           | 0.00             | 0.00             | 0.00       | 0.0%            |
| appservice             | 100.00           | 100.00           | 0.00       | 0.0%            |
| db.sql                 | 100.00           | 100.00           | 0.00       | 0.0%            |
| storage.blob           | 0.39             | 0.34             | -0.05      | -12.8%          |
| network.appgw          | 100.00           | 100.00           | 0.00       | 0.0%            |
| network.public_ip      | 100.00           | 100.00           | 0.00       | 0.0%            |
| network.nat            | 1.00             | 0.80             | -0.20      | -20.0%          |
| security.keyvault      | 0.15             | 0.09             | -0.06      | -40.0%          |
| cache.redis            | 100.00           | 100.00           | 0.00       | 0.0%            |
| monitoring.loganalytics| 100.00           | 100.00           | 0.00       | 0.0%            |
| backup.vault           | 100.00           | 100.00           | 0.00       | 0.0%            |
| dr.asr                 | 16.00            | 16.00            | 0.00       | 0.0%            |

Observations:

- **Storage.blob**: -$0.05/month (~‑13%) due to LRS and slightly lower volume.
- **Network.nat**: -$0.20/month (‑20%) due to lower egress (80 GB vs 100 GB).
- **Key Vault**: -$0.06/month (‑40%) due to fewer operations.
- All major categories (App Service, DB, AppGW, Redis, Log Analytics, Backup, DR) remain at **$100/month placeholders**, so deltas are zero.

---

## 7. Summary

- Architecturally, both scenarios are **sound two‑tier Azure designs** with:
  - App Service + WAF‑protected ingress,
  - Azure SQL Database (Business Critical) with backups,
  - VNet integration, NAT, Key Vault, Redis, Log Analytics, Backup vault, and ASR.
- The **real decision point** is:
  - **PAYG vs 1‑year reserved capacity for SQL DB**, plus
  - **Operational optimizations** (reduced hours, lower ingestion, right‑sizing).
- The current JSON is **not suitable for final cost numbers**:
  - SQL, App Service, App Gateway, Redis, Public IP, Log Analytics, and Backup vault are either mismatched or placeholder‑priced.
- From a FinOps perspective:
  - **First priority**: Correctly price SQL BC 4 vCores and apply **1‑year reservation** if this is a steady production workload.
  - **Second priority**: Right‑size App Service and Redis, and tune Log Analytics ingestion/retention.
  - **Third priority**: Validate backup/DR strategy to avoid redundant protection and unnecessary storage.

Once you have corrected catalog prices for the key components, you can re‑run this comparison; you should then see **meaningful savings** from SQL reservations and operational optimizations, rather than the negligible deltas shown here.