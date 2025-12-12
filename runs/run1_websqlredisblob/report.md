## 1. Baseline / Recommended scenario – short narrative

The **baseline** scenario is a production‑ready web application in `westeurope` built on fully managed PaaS:

- **Compute**: An Azure App Service Basic B2 plan (Windows) hosts the web app 24×7.
- **Data**: A single Azure SQL Database (Standard S1 DTU) stores transactional data.
- **Caching**: Azure Cache for Redis (C1) is used for session state and output caching (price missing in the data).
- **Storage**: A GPv2 Storage Account with Blob storage (Hot + Cool, GRS) stores user uploads.
- **Network & security edge**: An Application Gateway WAF v2 with a Standard Public IP fronts the app; a VNet provides integration and private endpoints; a NAT/Bandwidth line item models outbound traffic.
- **Secrets & keys**: Azure Key Vault (Standard) holds connection strings, secrets, and certificates.
- **Monitoring & logging**: A Log Analytics workspace ingests ~200 GB/month for app, SQL, Redis, and platform logs.
- **Backup & DR**: A Backup vault (Recovery Services) covers SQL backups and configs; Azure Site Recovery is modeled as a placeholder for future IaaS/DR needs.

This is a **balanced, secure, and observable** production design, but the cost model is incomplete: several key items (Redis, AppGW fixed cost, Public IP, some monitoring/backup/DR) are represented as **coarse placeholders** rather than precise prices.

---

## 2. Other scenarios – summary and differences

### Cost Optimized scenario

Intent: **Minimize cost** while keeping the same logical architecture.

Key changes vs baseline:

- **Compute**: App Service downgraded from **B2 → B1** (half the vCores, lower capacity).
- **Database**: Azure SQL moved from **S1 → Basic** (much lower DTUs and storage).
- **Redis**: Smaller **B0** cache (no SLA, no replication) instead of Standard C1.
- **Storage**: Blob redundancy reduced **GRS → LRS**, and capacity/egress reduced.
- **Network edge**: No Application Gateway/WAF; instead, a basic Public IP and generic egress line item (App Service exposed directly).
- **Security/Monitoring/Backup**: Same services but with **lower volumes** (Key Vault ops, Log Analytics ingestion, backup footprint).

Trade‑offs:

- **Lower cost**, but:
  - Reduced performance headroom (App Service, SQL, Redis).
  - Weaker resilience (LRS storage, B0 Redis, no WAF).
  - Reduced observability (less Log Analytics ingestion).
  - Direct exposure of App Service (no AppGW/WAF) – security and routing trade‑off.

### High Performance / Scalable scenario

Intent: **Scale and resilience** for heavier traffic and stricter SLAs.

Key changes vs baseline:

- **Compute**: App Service upgraded from B2 to **Premium (P1v2‑like)** with **2 instances** (modeled as P0v3 Linux in pricing).
- **Database**: Azure SQL upgraded from **S1 → S2** (more DTUs, more storage).
- **Redis**: Upgraded to **Premium P1** (bigger, faster, persistence options).
- **Storage**: Blob redundancy increased **GRS → GZRS**, capacity and egress significantly higher; archive tier introduced.
- **Network edge**: Application Gateway WAF v2 retained but sized for higher throughput; NAT egress increased.
- **Security/Monitoring/Backup/DR**:
  - Key Vault moved to **Premium** with more operations (HSM options).
  - Log Analytics ingestion and retention **doubled+**.
  - Backup storage and ASR protected instances increased.

Trade‑offs:

- **Much higher capacity and resilience**, but:
  - Significantly higher cost (especially App Service, Redis, monitoring, DR).
  - More complex to manage (autoscale, WAF tuning, DR runbooks).
  - Cost becomes more sensitive to **data volume** (Log Analytics, storage, egress).

---

## 3. Scenario details

### 3.1 Baseline scenario

#### Main components (baseline)

- **Compute**
  - Azure App Service Basic B2 (Windows) – primary web app hosting.
- **Database**
  - Azure SQL Database Standard S1 (DTU model, 100 GB assumed).
- **Storage**
  - Storage Account (Blob, Hot + Cool, GRS) for uploads.
- **Network**
  - Virtual Network (integration + private endpoints).
  - Application Gateway WAF v2 (public HTTPS entry point).
  - Standard Public IP for AppGW.
  - NAT/Bandwidth line item for outbound traffic (100 GB/month).
- **Security**
  - Azure Key Vault Standard for secrets and certificates.
- **Monitoring & Analytics**
  - Log Analytics workspace (200 GB/month ingestion modeled via retention meter).
- **Backup & DR**
  - Backup vault (Recovery Services) for SQL and config backups.
  - Azure Site Recovery placeholder for DR of future IaaS/config.
- **Other**
  - Azure Cache for Redis C1 for session state and caching.

#### Pricing table – baseline

> Note: Some “100 EUR” category totals in `totals.by_category` are placeholders; below I stick to the **per‑resource** numbers given.

| Scenario  | Resource ID           | Category              | Service             | SKU (requested / resolved)                         | Region     | Billing | Unit Price | Unit        | Units  | Monthly Cost (EUR) | Yearly Cost (EUR) | Notes |
|-----------|-----------------------|-----------------------|---------------------|----------------------------------------------------|-----------|---------|-----------:|------------|-------:|-------------------:|------------------:|-------|
| baseline  | vnet-main             | network.vnet          | Virtual Network     | n/a / Virtual Network                              | westeurope| PAYG    | 0.00       | VNet       | 1     | 0.00               | 0.00              | No direct VNet charge. |
| baseline  | appsvc-plan-b2-like   | appservice            | Azure App Service   | B2 / B2 (Linux Basic)                              | westeurope| PAYG    | 0.0311     | 1 Hour     | 730   | 22.70              | 272.44            | 1× B2 plan, 24×7. |
| baseline  | sql-db-s1-like        | db.sql                | SQL Database        | S1 / S1 Secondary (Standard DTUs)                  | westeurope| PAYG    | 0.6314     | 1/Day      | 1     | 0.63               | 7.58              | Single S1 DB, 100 GB assumed. (Underpriced vs typical S1 – check.) |
| baseline  | redis-cache-basic-c1  | cache.redis           | Azure Cache Redis   | C1 / (missing)                                     | westeurope| PAYG    | –          | –          | –     | –                  | –                 | **Price missing**; Standard C1 should be ~tens of EUR/month. |
| baseline  | blob-storage-uploads  | storage.blob          | Storage (Blob)      | Standard_GRS / (estimated ADLS Gen2 meters)        | westeurope| PAYG    | 0.0007–0.0019 | 1 GB   | 250  | 0.23               | 2.82              | 200 GB Hot + 50 GB Cool; GRS; ops/egress not fully modeled. |
| baseline  | appgw-waf-public      | network.appgw         | Application Gateway | WAF_v2 / Standard Capacity Units (discounted)      | westeurope| PAYG    | 0.0069     | 1 Hour     | 730   | 5.04               | 60.44             | Only capacity units priced; **fixed cost & per‑GB not modeled**. |
| baseline  | public-ip-appgw       | network.public_ip     | Public IP           | Standard / (missing)                               | westeurope| PAYG    | –          | –          | –     | –                  | –                 | **Price missing**; Standard Public IP is low but non‑zero. |
| baseline  | nat-egress            | network.nat           | Bandwidth           | Standard / Standard Inter‑AZ Data Transfer Out     | westeurope| PAYG    | 0.0086     | 1 GB       | 100   | 0.86               | 10.32             | Models 100 GB outbound via NAT. Internet egress pricing may differ. |
| baseline  | keyvault-main         | security.keyvault     | Key Vault           | standard / Standard Operations                      | westeurope| PAYG    | 0.0259     | 10K ops    | 20    | 0.52               | 6.22              | ~200k ops/month. Premium/HSM not used. |
| baseline  | loganalytics-main     | monitoring.loganalytics| Log Analytics      | PerGB2018 / Analytics Logs Data Retention          | westeurope| PAYG    | 0.1124     | 1 GB/Month | 200   | 22.48              | 269.76            | Using retention meter; ingestion/queries not fully modeled. |
| baseline  | backup-vault-main     | backup.vault          | Backup              | Standard / ADLS Gen2 Vaulted LRS Write Ops         | westeurope| PAYG    | 0.0467     | 10K ops    | 10    | 0.47               | 5.60              | Only write ops priced; backup storage not modeled. |
| baseline  | asr-dr-sql-app        | dr.asr                | Azure Site Recovery | Standard / System Center VM Replicated             | westeurope| PAYG    | 13.8378    | 1/Month    | 1     | 13.84              | 166.05            | Placeholder for 1 protected instance; SQL uses geo‑replication instead. |

**Baseline totals (from JSON)**

- **Modeled (priced + estimated)**:  
  - Monthly modeled (priced + estimated resources): **24.94 EUR**  
  - Yearly modeled: **≈ 299.38 EUR**
- **With placeholders (including “missing_total” 600 EUR/month)**:  
  - Monthly: **624.94 EUR**  
  - Yearly: **7,499.38 EUR**
- **Composition**:
  - Priced: 24.71 EUR/month
  - Estimated: 0.23 EUR/month
  - Missing (placeholder): 600 EUR/month

So **~96% of the baseline total is placeholder/missing**, not from concrete pricing.

#### Aggregated table by category – baseline

I’ll map Azure categories into higher‑level buckets:

- **Compute**: `appservice`
- **DB**: `db.sql`
- **Storage**: `storage.blob`
- **Network**: `network.vnet`, `network.appgw`, `network.public_ip`, `network.nat`
- **Analytics/Monitoring**: `monitoring.loganalytics`
- **Security**: `security.keyvault`
- **Backup/DR**: `backup.vault`, `dr.asr`
- **Other**: `cache.redis` (plus anything uncategorized)

Using `totals.by_category` (monthly_with_estimates) and the scenario’s modeled vs missing:

| Scenario | Bucket        | Monthly (EUR) | Priced+Est (EUR) | Missing (EUR) | % Missing in Bucket | Notes |
|----------|---------------|--------------:|-----------------:|--------------:|--------------------:|-------|
| baseline | Compute       | 22.70         | 22.70            | 0.00          | 0%                  | App Service B2 only. |
| baseline | DB            | 0.63          | 0.63             | 0.00          | 0%                  | SQL S1; likely underpriced vs real S1. |
| baseline | Storage       | 0.23          | 0.23             | 0.00          | 0%                  | Blob storage only; ops/egress simplified. |
| baseline | Network       | 200.86        | 5.90             | 195.0         | ~97%                | AppGW, Public IP, NAT; AppGW/Public IP mostly placeholder. |
| baseline | Analytics/Mon | 100.00        | 22.48            | 77.52         | ~78%                | Log Analytics ingestion/retention largely placeholder. |
| baseline | Security      | 0.52          | 0.52             | 0.00          | 0%                  | Key Vault ops only. |
| baseline | Backup/DR     | 213.84        | 14.31            | 199.53        | ~93%                | Backup vault + ASR; storage & extra instances placeholder. |
| baseline | Other         | 100.00        | 0.00             | 100.00        | 100%                | Redis C1 entirely missing. |

> Takeaway: **Network, monitoring, backup/DR, and Redis are dominated by placeholders**; only App Service, SQL, Key Vault, NAT, and part of Log Analytics are reasonably priced.

---

### 3.2 Cost Optimized scenario

#### Main components (cost_optimized)

- **Compute**
  - Azure App Service Basic B1 (smaller plan, 1 vCore).
- **Database**
  - Azure SQL Database Basic (or small Basic elastic pool meter; 5 DTUs, 50 GB).
- **Storage**
  - Blob storage (Hot + Cool) with **LRS** redundancy, reduced capacity and egress.
- **Network**
  - Same VNet concept (no cost).
  - No Application Gateway/WAF; App Service is effectively internet‑facing.
  - Basic Public IP placeholder.
  - Generic egress Bandwidth line item (150 GB/month).
- **Security**
  - Key Vault Standard retained, with fewer operations.
- **Monitoring & Analytics**
  - Log Analytics workspace with ~100 GB/month ingestion and reduced retention.
- **Backup & DR**
  - Backup vault with smaller backup footprint.
  - No explicit ASR resource in this scenario (only backup).
- **Other**
  - Azure Cache for Redis B0 (no SLA, small).

#### Pricing table – cost_optimized

| Scenario       | Resource ID              | Category              | Service             | SKU (requested / resolved)                         | Region     | Billing | Unit Price | Unit        | Units | Monthly Cost (EUR) | Yearly Cost (EUR) | Notes |
|----------------|--------------------------|-----------------------|---------------------|----------------------------------------------------|-----------|---------|-----------:|------------|------:|-------------------:|------------------:|-------|
| cost_optimized | vnet-main-co             | network.vnet          | Virtual Network     | n/a / Virtual Network                              | westeurope| PAYG    | 0.00       | VNet       | 1    | 0.00               | 0.00              | No direct VNet charge. |
| cost_optimized | appsvc-plan-b1           | appservice            | Azure App Service   | B1 / B1 (Linux Basic)                              | westeurope| PAYG    | 0.0156     | 1 Hour     | 730  | 11.39              | 136.66            | Smaller compute vs baseline. |
| cost_optimized | sql-db-basic             | db.sql                | SQL Database        | Basic / 1 DTU (Elastic Pool Basic)                 | westeurope| PAYG    | 0.0419     | 1/Day      | 1    | 0.04               | 0.50              | Very low DTUs; may not match real Basic single DB pricing. |
| cost_optimized | redis-cache-basic-b0     | cache.redis           | Azure Cache Redis   | B0 / (missing)                                     | westeurope| PAYG    | –          | –          | –    | –                  | –                 | **Price missing**; B0 is cheap but no SLA. |
| cost_optimized | blob-storage-uploads-co  | storage.blob          | Storage (Blob)      | Standard_LRS / (estimated ADLS Gen2 meters)        | westeurope| PAYG    | 0.0007–0.0019 | 1 GB   | 150  | 0.16               | 1.98              | 100 GB Hot + 50 GB Cool; LRS. |
| cost_optimized | public-ip-appsvc-direct  | network.public_ip     | Public IP           | Basic / (missing)                                  | westeurope| PAYG    | –          | –          | –    | –                  | –                 | **Price missing**; small but non‑zero. |
| cost_optimized | egress-general-co        | network.egress        | Bandwidth           | n/a / Standard Inter‑AZ Data Transfer Out          | westeurope| PAYG    | 0.0086     | 1 GB       | 150  | 1.29               | 15.48             | 150 GB outbound; actual internet egress pricing may differ. |
| cost_optimized | keyvault-main-co         | security.keyvault     | Key Vault           | standard / Standard Operations                      | westeurope| PAYG    | 0.0259     | 10K ops    | 10   | 0.26               | 3.11              | ~100k ops/month. |
| cost_optimized | loganalytics-main-co     | monitoring.loganalytics| Log Analytics      | PerGB2018 / Analytics Logs Data Retention          | westeurope| PAYG    | 0.1124     | 1 GB/Month | 100  | 11.24              | 134.88            | Half the baseline volume. |
| cost_optimized | backup-vault-main-co     | backup.vault          | Backup              | Standard / ADLS Gen2 Vaulted LRS Write Ops         | westeurope| PAYG    | 0.0467     | 10K ops    | 5    | 0.23               | 2.80              | Smaller backup footprint; storage not modeled. |

**Cost Optimized totals (from JSON)**

- **Modeled (priced + estimated)**:
  - Monthly modeled: **13.14 EUR**
  - Yearly modeled: **≈ 157.73 EUR**
- **With placeholders (including 400 EUR/month missing)**:
  - Monthly: **413.14 EUR**
  - Yearly: **4,957.73 EUR**
- Composition:
  - Priced: 12.98 EUR/month
  - Estimated: 0.16 EUR/month
  - Missing (placeholder): 400 EUR/month

#### Aggregated table by category – cost_optimized

| Scenario       | Bucket        | Monthly (EUR) | Priced+Est (EUR) | Missing (EUR) | % Missing in Bucket | Notes |
|----------------|---------------|--------------:|-----------------:|--------------:|--------------------:|-------|
| cost_optimized | Compute       | 11.39         | 11.39            | 0.00          | 0%                  | App Service B1. |
| cost_optimized | DB            | 0.04          | 0.04             | 0.00          | 0%                  | SQL Basic. |
| cost_optimized | Storage       | 0.16          | 0.16             | 0.00          | 0%                  | Blob LRS. |
| cost_optimized | Network       | 101.29        | 1.29             | 100.0         | ~99%                | Public IP missing; egress priced. |
| cost_optimized | Analytics/Mon | 100.00        | 11.24            | 88.76         | ~89%                | Log Analytics mostly placeholder. |
| cost_optimized | Security      | 0.26          | 0.26             | 0.00          | 0%                  | Key Vault. |
| cost_optimized | Backup/DR     | 100.23        | 0.23             | 100.0         | ~100%               | Backup storage & instances placeholder. |
| cost_optimized | Other         | 100.00        | 0.00             | 100.0         | 100%                | Redis B0 missing. |

---

### 3.3 High Performance / Scalable scenario

#### Main components (high_performance)

- **Compute**
  - Azure App Service Premium (P1v2‑like) with **2 instances** (modeled as P0v3 Linux).
- **Database**
  - Azure SQL Database Standard S2 (50 DTUs, 250 GB).
- **Storage**
  - Blob storage with **GZRS** redundancy, larger Hot/Cool/Archive footprint and higher egress.
- **Network**
  - VNet with subnets for AppGW, integration, private endpoints.
  - Application Gateway WAF v2 sized for higher throughput.
  - Standard Public IP for AppGW.
  - NAT/Bandwidth line item with 200 GB outbound.
- **Security**
  - Key Vault **Premium** (HSM options, more operations).
- **Monitoring & Analytics**
  - Log Analytics with ~400 GB/month ingestion and extended retention.
- **Backup & DR**
  - Backup vault with ~400 GB backup storage.
  - Azure Site Recovery with **2 protected instances**.
- **Other**
  - Azure Cache for Redis Premium P1 (bigger, faster, persistence).

#### Pricing table – high_performance

| Scenario        | Resource ID              | Category              | Service             | SKU (requested / resolved)                         | Region     | Billing | Unit Price | Unit        | Units | Monthly Cost (EUR) | Yearly Cost (EUR) | Notes |
|-----------------|--------------------------|-----------------------|---------------------|----------------------------------------------------|-----------|---------|-----------:|------------|------:|-------------------:|------------------:|-------|
| high_performance| vnet-main-hp             | network.vnet          | Virtual Network     | n/a / Virtual Network                              | westeurope| PAYG    | 0.00       | VNet       | 1    | 0.00               | 0.00              | No direct VNet charge. |
| high_performance| appsvc-plan-p1v2         | appservice            | Azure App Service   | P1v2 / P0v3 App (Premium v3 Linux)                 | westeurope| PAYG    | 0.077      | 1 Hour     | 1460 | 112.42             | 1349.04           | 2 instances; SKU mismatch vs requested P1v2. |
| high_performance| sql-db-s2                | db.sql                | SQL Database        | S2 / S2 Secondary (Standard DTUs)                  | westeurope| PAYG    | 1.5654     | 1/Day      | 1    | 1.57               | 18.78             | S2 DB, 250 GB assumed. |
| high_performance| redis-cache-premium-p1   | cache.redis           | Azure Cache Redis   | P1 / (missing)                                     | westeurope| PAYG    | –          | –          | –    | –                  | –                 | **Price missing**; Premium P1 is significant (hundreds EUR/month). |
| high_performance| blob-storage-uploads-hp  | storage.blob          | Storage (Blob)      | Standard_GZRS / (estimated ADLS/Blob meters)       | westeurope| PAYG    | 0.0007–0.0019 | 1 GB   | 800  | 0.73               | 8.76              | 500 GB Hot, 200 GB Cool, 100 GB Archive (archive write only). |
| high_performance| appgw-waf-v2-hp          | network.appgw         | Application Gateway | WAF_v2 / Standard Capacity Units (discounted)      | westeurope| PAYG    | 0.0069     | 1 Hour     | 730  | 5.04               | 60.44             | Only capacity units priced; fixed cost & per‑GB missing. |
| high_performance| public-ip-appgw-hp       | network.public_ip     | Public IP           | Standard / (missing)                               | westeurope| PAYG    | –          | –          | –    | –                  | –                 | **Price missing**. |
| high_performance| nat-egress-hp            | network.nat           | Bandwidth           | Standard / Standard Inter‑AZ Data Transfer Out     | westeurope| PAYG    | 0.0086     | 1 GB       | 200  | 1.72               | 20.64             | 200 GB outbound via NAT. |
| high_performance| keyvault-main-hp         | security.keyvault     | Key Vault           | premium / Premium Operations                        | westeurope| PAYG    | 0.0259     | 10K ops    | 50   | 1.29               | 15.54             | 500k ops/month; HSM options not separately priced here. |
| high_performance| loganalytics-main-hp     | monitoring.loganalytics| Log Analytics      | PerGB2018 / Analytics Logs Data Retention          | westeurope| PAYG    | 0.1124     | 1 GB/Month | 400  | 44.96              | 539.52            | 400 GB/month; ingestion/queries not fully modeled. |
| high_performance| backup-vault-main-hp     | backup.vault          | Backup              | Standard / ADLS Gen2 Vaulted LRS Write Ops         | westeurope| PAYG    | 0.0467     | 10K ops    | 20   | 0.93               | 11.21             | Larger backup footprint; storage not modeled. |
| high_performance| asr-dr-hp                | dr.asr                | Azure Site Recovery | Standard / System Center VM Replicated             | westeurope| PAYG    | 13.8378    | 1/Month    | 2    | 27.68              | 332.11            | 2 protected instances; placeholder. |

**High Performance totals (from JSON)**

- **Modeled (priced + estimated)**:
  - Monthly modeled: **5.31 EUR**
  - Yearly modeled: **≈ 63.72 EUR**
- **With placeholders (including 712.42 EUR/month missing)**:
  - Monthly: **717.73 EUR**
  - Yearly: **8,612.76 EUR**
- Composition:
  - Priced: 4.58 EUR/month
  - Estimated: 0.73 EUR/month
  - Missing (placeholder): 712.42 EUR/month

> Note: The “missing_total” is dominated by App Service Premium, Redis Premium, AppGW fixed cost, Public IP, Log Analytics ingestion, backup storage, and ASR.

#### Aggregated table by category – high_performance

| Scenario        | Bucket        | Monthly (EUR) | Priced+Est (EUR) | Missing (EUR) | % Missing in Bucket | Notes |
|-----------------|---------------|--------------:|-----------------:|--------------:|--------------------:|-------|
| high_performance| Compute       | 112.42        | 0.00             | 112.42        | 100%                | App Service Premium cost treated as missing in totals. |
| high_performance| DB            | 1.57          | 1.57             | 0.00          | 0%                  | SQL S2. |
| high_performance| Storage       | 0.73          | 0.73             | 0.00          | 0%                  | Blob GZRS. |
| high_performance| Network       | 207.76        | 6.76             | 201.0         | ~97%                | AppGW, Public IP, NAT; AppGW/Public IP mostly placeholder. |
| high_performance| Analytics/Mon | 100.00        | 44.96            | 55.04         | ~55%                | Log Analytics; ingestion/retention partly placeholder. |
| high_performance| Security      | 1.29          | 1.29             | 0.00          | 0%                  | Key Vault Premium ops. |
| high_performance| Backup/DR     | 127.68        | 28.61            | 99.07         | ~78%                | Backup vault + ASR; storage & extra instances placeholder. |
| high_performance| Other         | 100.00        | 0.00             | 100.0         | 100%                | Redis Premium P1 missing. |

---

## 4. Resources where pricing failed – what to check manually

Across scenarios, these resources need **manual pricing in the Azure Pricing Calculator**:

### Baseline

1. **Azure Cache for Redis – C1**
   - Resource: `redis-cache-basic-c1`
   - Risk: Entire Redis cost missing; for production, C1 Standard is often **tens of EUR/month**.
   - Check:
     - Region: `westeurope`
     - SKU: Standard C1
     - Throughput & memory requirements.
     - If clustering or persistence is needed.

2. **Public IP – Standard**
   - Resource: `public-ip-appgw`
   - Risk: Small but non‑zero; Standard IPs are billed per hour.
   - Check:
     - Region: `westeurope`
     - Standard vs Basic, IPv4 vs IPv6.

3. **Application Gateway WAF v2 – fixed & data processing**
   - Resource: `appgw-waf-public`
   - Current pricing only includes **capacity units** at 0.0069 EUR/hour.
   - Missing:
     - **Fixed hourly cost** (Standard/WAF v2 base).
     - **Per‑GB data processed**.
   - Risk: For real traffic, AppGW can be **one of the larger line items**.

4. **Log Analytics – ingestion & query charges**
   - Resource: `loganalytics-main`
   - Current pricing uses **Data Retention** meter; ingestion is 0 EUR in this model.
   - Check:
     - Ingestion price per GB (PerGB2018).
     - Retention beyond free period.
     - Query/analytics charges if applicable.

5. **Backup – storage and protected instances**
   - Resource: `backup-vault-main`
   - Only write operations priced; missing:
     - Backup storage per GB (LRS/GRS).
     - Protected instance fees (for VMs, SQL in VM, etc.).
   - Risk: For 250 GB+ and long retention, backup storage can be material.

6. **Azure Site Recovery – correct SKU and protected instances**
   - Resource: `asr-dr-sql-app`
   - Using “VM Replicated to System Center” meter; for Azure‑to‑Azure you should use “VM Replicated to Azure”.
   - Check:
     - Number of protected instances.
     - Azure‑to‑Azure vs on‑prem to Azure.
     - Storage and test failover costs.

### Cost Optimized

1. **Azure Cache for Redis – B0**
   - Resource: `redis-cache-basic-b0`
   - Risk: Entire Redis cost missing; B0 is cheap but has **no SLA**.
   - Check:
     - Region: `westeurope`
     - Basic B0 pricing.
     - Whether SLA and replication are required (may need Standard C0/C1).

2. **Public IP – Basic**
   - Resource: `public-ip-appsvc-direct`
   - Risk: Small but missing; Basic IPs may be free or low‑cost depending on allocation and SKU.
   - Check:
     - Allocation method (dynamic vs static).
     - IPv4 vs IPv6.

3. **Log Analytics – ingestion & retention**
   - Resource: `loganalytics-main-co`
   - Same issue as baseline: only retention meter priced.
   - Check ingestion GB/month and retention policy.

4. **Backup – storage and protected instances**
   - Resource: `backup-vault-main-co`
   - Same as baseline; only write ops priced.

### High Performance

1. **Azure App Service Premium – P1v2 (modeled as P0v3)**
   - Resource: `appsvc-plan-p1v2`
   - Risk: The totals treat this as **missing**; real cost is likely **hundreds of EUR/month** for 2 instances.
   - Check:
     - Correct SKU: Premium v2 P1 vs Premium v3 P0/P1.
     - 2 instances × 730 hours.
     - Windows vs Linux pricing.

2. **Azure Cache for Redis – Premium P1**
   - Resource: `redis-cache-premium-p1`
   - Risk: Entire Redis cost missing; Premium P1 is typically **high** (hundreds EUR/month).
   - Check:
     - Region: `westeurope`
     - Persistence, clustering, and network isolation options.

3. **Public IP – Standard**
   - Resource: `public-ip-appgw-hp`
   - Same as baseline; Standard IP hourly cost.

4. **Application Gateway WAF v2 – fixed & data processing**
   - Resource: `appgw-waf-v2-hp`
   - Same as baseline; only capacity units priced.

5. **Log Analytics – ingestion & retention**
   - Resource: `loganalytics-main-hp`
   - Same pattern: retention priced, ingestion not.

6. **Backup – storage and protected instances**
   - Resource: `backup-vault-main-hp`
   - Only write ops priced; storage and instance fees missing.

7. **Azure Site Recovery – correct SKU and count**
   - Resource: `asr-dr-hp`
   - Same SKU issue as baseline; verify Azure‑to‑Azure pricing and 2 protected instances.

---

## 5. FinOps recommendations

### 5.1 Quick wins

1. **Fix missing and placeholder pricing**
   - Before any decision, **rebuild all three scenarios in the Azure Pricing Calculator**:
     - App Service (all SKUs).
     - Redis (C1, B0, P1).
     - Application Gateway WAF v2 (fixed + capacity + data processed).
     - Public IPs.
     - Log Analytics (ingestion + retention).
     - Backup storage and protected instances.
     - ASR (Azure‑to‑Azure).
   - This will likely **change the relative cost ranking** (especially for high_performance).

2. **Right‑size App Service**
   - For baseline:
     - If CPU/memory utilization is low, consider **B1** or **scaling out only at peak**.
   - For high_performance:
     - Validate if **2× Premium** is needed 24×7 or if **autoscale** can keep average instance hours lower.
   - Consider **Reserved Instances (App Service plan reservations)** if you run a fixed number of instances 24×7 for 1–3 years.

3. **Optimize Log Analytics ingestion**
   - All scenarios assume significant GB/month; costs scale **linearly with data volume**.
   - Actions:
     - Enable **sampling** and **filter noisy logs** (e.g., verbose diagnostics).
     - Use **Basic Logs** for low‑value, high‑volume data.
     - Set **per‑table retention** instead of long global retention.

4. **Storage tiering and redundancy**
   - Baseline uses **GRS**; cost_optimized uses **LRS**; high_performance uses **GZRS**.
   - For non‑critical uploads:
     - Consider **LRS** or **ZRS** instead of GRS/GZRS.
     - Move older content to **Cool/Archive** tiers aggressively.
   - Validate **download patterns**; egress from Blob to internet can be material at scale.

5. **Redis right‑sizing**
   - For small workloads, **B0 or C0** may be enough; for production SLAs, prefer **Standard**.
   - Use **cache hit ratio and memory usage** to size:
     - If hit ratio is low, optimize caching strategy before scaling up.
     - If memory is underutilized, consider smaller SKUs.

### 5.2 Spot vs PAYG vs Reserved

- **App Service**
  - No “spot” equivalent; but you can:
    - Use **Dev/Test** pricing for non‑prod.
    - Use **App Service plan reservations** (1‑ or 3‑year) for predictable, always‑on capacity.
  - Recommendation:
    - For baseline and high_performance, if you expect **steady 24×7 usage**, cover **60–80% of baseline instance hours** with reservations, leave the rest on PAYG for burst.

- **SQL Database**
  - DTU model here; for vCore model you can use **Reserved Capacity**.
  - Consider migrating to **vCore** if:
    - You want **Azure Hybrid Benefit** (reuse SQL licenses).
    - You want **1–3 year reserved capacity** discounts.
  - For small Basic/S1/S2, the savings may be modest; evaluate once you have stable utilization.

- **Redis**
  - No spot; PAYG only.
  - For Premium Redis with predictable usage, consider **Enterprise tiers** and reserved capacity if available in your region (check current offers).

- **VM‑based DR (ASR)**
  - ASR itself is PAYG; but if you pre‑provision DR VMs, you can use **Reserved Instances** for those as well.

### 5.3 Right‑sizing ideas

- **Baseline vs Cost Optimized**
  - If your workload is **light to moderate**, the cost_optimized App Service B1 and SQL Basic may be enough.
  - However:
    - SQL Basic (5 DTUs) can be a bottleneck; consider **S0** or **S1** if latency is critical.
    - Redis B0 has **no SLA**; for production, at least **Standard C0/C1** is recommended.

- **Baseline vs High Performance**
  - Only move to high_performance when:
    - You have **measured CPU/memory/DTU saturation** on baseline.
    - You need **higher SLA** (Premium App Service, GZRS storage, Premium Key Vault).
  - Consider intermediate steps:
    - App Service: B2 → S1/S2 before jumping to Premium.
    - SQL: S1 → S2 only when DTUs are consistently high.

- **Monitoring**
  - Start with **baseline ingestion**; only move to high_performance monitoring (400 GB/month) when:
    - You have a clear use case (advanced analytics, security monitoring).
    - You’ve tuned queries and retention to avoid waste.

### 5.4 Region and egress considerations

- All scenarios use `westeurope`. Consider:
  - **Latency to users**: If most users are in another region, moving closer may reduce both latency and some inter‑region traffic.
  - **Egress costs**:
    - Internet egress is charged per GB; NAT and Bandwidth line items here use **Inter‑AZ** meters, which are not the same as internet egress.
    - For accurate FinOps, model:
      - **Blob → Internet** egress.
      - **App Service → Internet** egress.
      - **Inter‑region** traffic (if any).
  - **Multi‑region DR**:
    - If you add a secondary region (Front Door, Traffic Manager, geo‑replication), expect **higher egress and storage** costs.

---

## 6. Delta analysis vs Baseline

Because the JSON flags scenarios as “not_comparable” due to SKU mismatches, I’ll base deltas on the **scenario totals** as provided (including placeholders). Treat these as **directional only**, not precise.

### 6.1 Overall totals – monthly/yearly (priced vs with estimates)

Using:

- Baseline:
  - Modeled (priced+estimated): 24.94 EUR/month
  - With placeholders: 624.94 EUR/month
- Cost Optimized:
  - Modeled: 13.14 EUR/month
  - With placeholders: 413.14 EUR/month
- High Performance:
  - Modeled: 5.31 EUR/month
  - With placeholders: 717.73 EUR/month

#### Cost Optimized vs Baseline

| Metric                         | Baseline | Cost Optimized | Δ (Abs) | Δ (%) vs Baseline |
|--------------------------------|---------:|---------------:|--------:|-------------------:|
| **Modeled monthly** (priced+est) | 24.94   | 13.14          | -11.80 | -47.3%            |
| **Modeled yearly**             | 299.38  | 157.73         | -141.65| -47.3%            |
| **Monthly with placeholders**  | 624.94  | 413.14         | -211.80| -33.9%            |
| **Yearly with placeholders**   | 7,499.38| 4,957.73       | -2,541.65| -33.9%          |

Interpretation:

- On the **modeled portion**, cost_optimized is ~47% cheaper than baseline.
- Including placeholders, cost_optimized is ~34% cheaper, but this is dominated by arbitrary 100‑EUR category placeholders.

#### High Performance vs Baseline

| Metric                         | Baseline | High Perf. | Δ (Abs) | Δ (%) vs Baseline |
|--------------------------------|---------:|-----------:|--------:|-------------------:|
| **Modeled monthly** (priced+est) | 24.94   | 5.31       | -19.63 | -78.7%            |
| **Modeled yearly**             | 299.38  | 63.72      | -235.66| -78.7%            |
| **Monthly with placeholders**  | 624.94  | 717.73     | +92.79 | +14.8%            |
| **Yearly with placeholders**   | 7,499.38| 8,612.76   | +1,113.38| +14.8%          |

Interpretation:

- On the **modeled portion**, high_performance appears cheaper, but that’s an artifact: most of its big‑ticket items (Premium App Service, Redis, ASR) are treated as “missing”.
- Including placeholders, high_performance is ~15% more expensive than baseline.

> Action: Once you have **real prices** for App Service Premium, Redis Premium, AppGW, Log Analytics, and ASR, redo this delta; high_performance will almost certainly be **substantially more expensive** than baseline.

### 6.2 Category‑level monthly deltas vs baseline

Using `monthly_with_estimates` by bucket (see earlier mapping). These are **very approximate** because of placeholders.

#### Cost Optimized vs Baseline – monthly by bucket

| Bucket        | Baseline (EUR) | Cost Opt (EUR) | Δ Monthly (EUR) | Δ (%) vs Baseline | Notes |
|---------------|----------------:|----------------:|----------------:|------------------:|-------|
| Compute       | 22.70           | 11.39           | -11.31          | -49.8%            | B2 → B1. |
| DB            | 0.63            | 0.04            | -0.59           | -93.7%            | S1 → Basic (underpriced in both). |
| Storage       | 0.23            | 0.16            | -0.07           | -30.4%            | GRS → LRS, less capacity. |
| Network       | 200.86          | 101.29          | -99.57          | -49.6%            | Drop AppGW/WAF; simpler egress. |
| Analytics/Mon | 100.00          | 100.00          | 0.00            | 0%                | Both dominated by placeholder 100 EUR. |
| Security      | 0.52            | 0.26            | -0.26           | -50.0%            | Fewer Key Vault ops. |
| Backup/DR     | 213.84          | 100.23          | -113.61         | -53.1%            | Smaller backup + no ASR placeholder. |
| Other         | 100.00          | 100.00          | 0.00            | 0%                | Redis placeholders in both. |

#### High Performance vs Baseline – monthly by bucket

| Bucket        | Baseline (EUR) | High Perf (EUR) | Δ Monthly (EUR) | Δ (%) vs Baseline | Notes |
|---------------|----------------:|----------------:|----------------:|------------------:|-------|
| Compute       | 22.70           | 112.42          | +89.72          | +395.3%           | Premium App Service with 2 instances. |
| DB            | 0.63            | 1.57            | +0.94           | +149.2%           | S1 → S2. |
| Storage       | 0.23            | 0.73            | +0.50           | +217.4%           | More capacity, GZRS. |
| Network       | 200.86          | 207.76          | +6.90           | +3.4%             | More egress; AppGW similar placeholder. |
| Analytics/Mon | 100.00          | 100.00          | 0.00            | 0%                | Both dominated by placeholder 100 EUR. |
| Security      | 0.52            | 1.29            | +0.77           | +148.1%           | Standard → Premium Key Vault. |
| Backup/DR     | 213.84          | 127.68          | -86.16          | -40.3%            | Different placeholder mix; not reliable. |
| Other         | 100.00          | 100.00          | 0.00            | 0%                | Redis placeholders in both. |

> Again, these deltas are **dominated by placeholder 100‑EUR buckets**. Use them only to understand **directional changes** (e.g., compute and DB clearly increase in high_performance, decrease in cost_optimized).

---

## 7. Key service call‑outs

- **Key Vault / secrets management**
  - Present in all scenarios; cost is **small** relative to others.
  - FinOps focus: not cost, but **security posture** (use managed identities, RBAC, private endpoints).

- **Log Analytics / monitoring**
  - Costs scale **linearly with GB ingested and retained**.
  - High_performance scenario doubles ingestion vs baseline; cost_optimized halves it.
  - FinOps levers:
    - Sampling, filtering, Basic Logs, per‑table retention, and query optimization.

- **Backup vault & Site Recovery**
  - Backup storage and ASR protected instances are **under‑modeled**.
  - Costs scale with:
    - **Data volume** (GB backed up).
    - **Retention period**.
    - **Number of protected instances**.
  - FinOps levers:
    - Right‑size retention (e.g., 30/90/365 days by workload).
    - Use **differential backups** and compression.
    - Limit ASR to truly critical workloads.

- **Network egress / NAT / Gateways / Front Door**
  - Current model uses **Inter‑AZ data transfer** meters as a proxy; real internet egress pricing differs.
  - AppGW WAF v2 costs are incomplete (fixed + per‑GB missing).
  - If you add **Front Door** or **CDN**, expect:
    - Additional per‑GB and per‑request charges.
    - Potential **egress savings** from caching and better routing.

- **Data volume / throughput scaling**
  - **Blob storage**: cost scales with GB stored (per tier) + operations + egress.
  - **Log Analytics**: cost scales with GB ingested and retained.
  - **Redis**: cost scales with SKU (memory, throughput), not directly with ops, but you’ll scale up when throughput/memory is insufficient.
  - **SQL**: in DTU model, you scale up tiers as throughput/DTUs are exhausted.

---

### Final recommendation

1. **Rebuild all three scenarios in the Azure Pricing Calculator** with:
   - Correct SKUs (especially SQL S1/S2, App Service Premium, Redis, AppGW WAF v2).
   - Realistic data volumes (ingress/egress, Log Analytics GB, backup GB).
2. **Decide on a target SLA and performance profile**:
   - If this is a **small production** with modest traffic, start from **baseline**, then:
     - Consider **B1 + S1** as a hybrid between baseline and cost_optimized.
   - If you expect **rapid growth or strict SLAs**, start from **baseline**, monitor, and only then move selected components to **high_performance**.
3. **Apply FinOps discipline continuously**:
   - Tag resources by environment and application.
   - Use **Azure Cost Management + budgets**.
   - Review utilization monthly and adjust SKUs, reservations, and retention accordingly.