## 1. Baseline scenario – short narrative (recommended)

The baseline is a production-ready web application in West Europe targeting ~50k MAU and 99.9% uptime, built on:

- **2× Linux VMs (D2s v3)** behind a Standard Load Balancer in a production VNet, with Premium SSD OS disks.
- **Azure SQL Database Single DB (GP, Gen5, 2 vCores)** as the primary transactional store.
- **Azure Cache for Redis (Standard C1)** for session/state caching and performance.
- **Blob Storage (hot + cool tiers)** for static assets, served over a Standard Public IP and Load Balancer.
- **Network egress** via Bandwidth plus a **NAT Gateway** for controlled outbound traffic.
- **Security & secrets** via **Azure Key Vault**.
- **Monitoring** via **Log Analytics** for VM, SQL and platform logs.
- **Protection & DR** via **Azure Backup** (backup vault) and **Azure Site Recovery** for VM replication.

This scenario balances cost and reliability: Linux VMs on PAYG, a mid-tier SQL DB, basic Redis, and full operational hygiene (monitoring, backup, DR, Key Vault, NAT, LB). It is the recommended starting point.

---

## 2. Other scenarios – how they differ

### Cost_optimized (1‑year Reserved VMs)

- **Same architecture** as baseline (same Linux VM size, SQL, Redis, storage, network, Key Vault, Log Analytics, Backup, ASR).
- **Intended change**: move the 2× Linux VMs to **1‑year Reserved Instances** to reduce compute cost.
- In the provided pricing data:
  - The VM reservation SKU is present but marked as **sku_mismatch** and the totals treat it as **missing** for required comparisons.
  - SQL DB is also priced via a slightly different meter (FSv2 vCore vs requested Gen5_2).
- Conceptually: this scenario should **lower VM hourly cost** vs baseline, but due to pricing mismatches we cannot compute a reliable delta.

### High_performance

- Same overall topology (VNet, LB, NAT, SQL, Redis, Blob, Key Vault, Log Analytics, Backup, ASR) but:
  - **Compute**: 2× **Windows** VMs, **D4s v3** (double vCores and RAM vs D2s v3) for higher performance.
  - **Disks**: Larger **Premium SSD P10 (128 GB)** OS disks.
  - **Traffic & data**: Higher Redis ops, Blob storage/egress, NAT and Bandwidth egress, Log Analytics ingestion, and Backup storage to reflect higher load.
- VM pricing for D4s v3 Windows is **missing**, and SQL DB is again priced via a different meter, so we can’t fully quantify the uplift vs baseline.

---

## ⚠️ Pricing completeness

Because of missing or mismatched SKUs, **none of the scenarios are fully comparable**. Key blockers:

| Scenario        | Resource ID       | Category     | Reason              | Requested SKU / Meter                         | Notes |
|----------------|-------------------|--------------|---------------------|-----------------------------------------------|-------|
| baseline       | vm-web-1          | compute.vm   | missing_pricing     | Standard_D2s_v3 / (none)                      | Linux PAYG VM price not resolved. |
| baseline       | sql-db-prod       | db.sql       | sku_mismatch        | SQLDB_GP_Compute_Gen5_2 / Zone Redundancy vCore | Resolved to ZR vCore meter; totals treat as missing for “required”. |
| baseline       | blob-static-assets| storage.blob | estimated_required  | (n/a) / Hot LRS Data Stored, Cool LRS Early Delete | Blob costs are estimates, not exact meters. |
| cost_optimized | vm-web-1-reserved | compute.vm   | sku_mismatch        | Standard_D2s_v3 / D2s v3 (Reservation)        | Reservation SKU resolved but flagged mismatch. |
| cost_optimized | sql-db-prod       | db.sql       | sku_mismatch        | SQLDB_GP_Compute_Gen5_2 / vCore (FSv2)        | Different meter vs requested Gen5_2. |
| cost_optimized | blob-static-assets| storage.blob | estimated_required  | (n/a) / Hot LRS Data Stored, Cool Data Retrieval | Blob costs estimated. |
| high_performance | vm-web-hp       | compute.vm   | missing_pricing     | Standard_D4s_v3 / (none)                      | Windows PAYG VM price not resolved. |
| high_performance | sql-db-prod     | db.sql       | sku_mismatch        | SQLDB_GP_Compute_Gen5_2 / vCore (FSv2)        | Different meter vs requested Gen5_2. |
| high_performance | blob-static-assets | storage.blob | estimated_required | (n/a) / Hot LRS Data Stored, Cool Data Retrieval | Blob costs estimated. |

Because `delta_vs_baseline.status = "not_comparable"` for both non‑baseline scenarios, **delta tables are indicative only** and should not be used for commercial commitments.

---

## 3. Scenario details

### 3.1 Baseline / Recommended

#### Main components (baseline)

- **Compute**
  - 2× Linux VMs, Standard_D2s_v3 (PAYG), in an availability set / zones.
  - Premium SSD P6 OS disks (64 GB) per VM.
- **Data / DB**
  - Azure SQL Database Single DB, General Purpose, Gen5, 2 vCores, 128 GB.
- **Caching**
  - Azure Cache for Redis Standard C1.
- **Storage**
  - Blob Storage: 200 GB hot, 50 GB cool, LRS, serving static assets.
- **Network**
  - VNet for web tier and private endpoints.
  - Standard Public IP.
  - Standard Load Balancer.
  - NAT Gateway for outbound.
  - Bandwidth (internet egress ~600 GB/month).
- **Security / Secrets**
  - Azure Key Vault Standard for secrets, keys, certificates.
- **Monitoring / Analytics**
  - Log Analytics workspace (~100 GB/month ingestion).
- **Backup & DR**
  - Azure Backup vault (2 VMs + SQL DB, ~300 GB backup).
  - Azure Site Recovery for 2 Linux VMs to paired region.

#### Pricing table – baseline

_All prices in EUR, West Europe. “null” monthly/yearly means pricing not resolved; some resources are estimated._

| Scenario  | Resource ID        | Category             | Service            | SKU (requested / resolved)                                   | Region     | Billing | Unit Price | Unit          | Units  | Monthly Cost | Yearly Cost | Notes |
|-----------|--------------------|----------------------|--------------------|--------------------------------------------------------------|------------|---------|-----------:|---------------|-------:|-------------:|------------:|-------|
| baseline  | vnet-prod          | network.vnet         | Virtual Network    | Virtual Network / Virtual Network                           | westeurope | payg    | 0.00       | VNet          | 1.0   | 0.00         | 0.00        | No direct VNet charge. |
| baseline  | vm-web-1           | compute.vm           | Virtual Machines   | Standard_D2s_v3 / (missing)                                 | westeurope | payg    | –          | –             | 2.0   | null         | null        | Linux D2s v3; price lookup failed. |
| baseline  | vm-web-osdisk      | storage.disk         | Storage            | P6 / P6 LRS Disk Mount                                       | westeurope | payg    | 0.5284     | 1/Month       | 2.0   | 1.06         | 12.68       | Premium SSD OS disks (64 GB). |
| baseline  | sql-db-prod        | db.sql               | SQL Database       | GP_Gen5_2 / 2 vCore Zone Redundancy (meter: ZR vCore)       | westeurope | payg    | 0.1738     | 1 Hour        | 730.0 | 63.44        | 761.24      | Single DB GP Gen5 2 vCores; treated as mismatch for “required”. |
| baseline  | redis-cache        | cache.redis          | Redis Cache        | Standard C1 / C1 Cache Instance                             | westeurope | payg    | 0.0597     | 1 Hour        | 730.0 | 43.58        | 522.97      | Redis Standard C1. |
| baseline  | blob-static-assets | storage.blob         | Storage            | Hot/Cool / (estimated meters)                               | westeurope | payg    | –          | –             | –     | 3.83         | 45.96       | 200 GB hot, 50 GB cool; cost estimated from tier unit prices. |
| baseline  | public-ip-web      | network.public_ip    | Virtual Network    | Standard / Standard IPv4 Static Public IP                   | westeurope | payg    | 0.0043     | 1 Hour        | 730.0 | 3.14         | 37.67       | 1× Standard Public IP. |
| baseline  | lb-web             | network.lb           | Load Balancer      | Standard / Standard Data Processed                          | westeurope | payg    | 0.0043     | 1 GB          | 300.0 | 1.29         | 15.48       | Data processed aligned with web egress. |
| baseline  | nat-egress         | network.nat          | NAT Gateway        | Standard / Std Inter-AZ Data Transfer Out (proxy meter)     | westeurope | payg    | 0.0086     | 1 GB          | 100.0 | 0.86         | 10.32       | 100 GB outbound via NAT; meter is a bandwidth SKU. |
| baseline  | bandwidth-egress   | network.egress       | Bandwidth          | Standard / Std Inter-AZ Data Transfer Out (proxy meter)     | westeurope | payg    | 0.0086     | 1 GB          | 600.0 | 5.16         | 61.92       | 600 GB/month internet egress (approx). |
| baseline  | keyvault-prod      | security.keyvault    | Key Vault          | Standard / Operations                                       | westeurope | payg    | 0.0259     | 10K ops       | 20.0  | 0.52         | 6.22        | ~200k ops/month. |
| baseline  | loganalytics-prod  | monitoring.loganalytics | Log Analytics   | Per GB / Analytics Logs Data Retention                      | westeurope | payg    | 0.1124     | 1 GB/Month    | 100.0 | 11.24        | 134.88      | 100 GB/month retention (ingestion assumed free in this meter). |
| baseline  | backup-vault-prod  | backup.vault         | Backup             | Azure Backup / Azure Files Protected Instances              | westeurope | payg    | 4.3243     | 1/Month       | 1.0   | 4.32         | 51.89       | Protecting VMs/SQL; 300 GB backup storage. |
| baseline  | asr-dr             | dr.asr               | Azure Site Recovery | Protected Instances / VM Replicated to System Center      | westeurope | payg    | 13.8378    | 1/Month       | 2.0   | 27.68        | 332.11      | ASR for 2 Linux VMs to paired region. |

> **Baseline totals (all services)**  
> - Monthly (priced): **€55.27**  
> - Monthly (estimated): **€3.83**  
> - Monthly (missing): **€107.02** (dominated by VMs + “required” SQL)  
> - Modeled total (priced + estimated): **€59.10**  
> - Reported “with estimates” total: **€166.12** (includes missing treated as modeled in some rollups; use modeled_total for conservative view).

#### Aggregated by category – baseline

Using `totals.by_category` (all services, not just “required”):

| Category            | Monthly Total | Priced | Estimated | Missing | Est. Share of Category | Notes |
|---------------------|-------------:|-------:|----------:|--------:|------------------------:|-------|
| compute.vm          | 0.00         | 0.00   | 0.00      | 0.00    | 0%                      | VM pricing missing; category total shows 0 but missing tracked separately. |
| db.sql              | 63.44        | 0.00   | 0.00      | 63.44   | 0% (all missing)        | SQL DB treated as missing for required; here shown as total. |
| cache.redis         | 43.58        | 0.00   | 0.00      | 43.58   | 0% (all missing)        | Redis C1. |
| storage.disk        | 1.06         | 1.06   | 0.00      | 0.00    | 0%                      | Premium SSD OS disks. |
| storage.blob        | 3.83         | 0.00   | 3.83      | 0.00    | 100%                    | Blob is fully estimated. |
| network.public_ip   | 3.14         | 3.14   | 0.00      | 0.00    | 0%                      | Public IP. |
| network.lb          | 1.29         | 1.29   | 0.00      | 0.00    | 0%                      | Load Balancer. |
| network.nat         | 0.86         | 0.86   | 0.00      | 0.00    | 0%                      | NAT Gateway (via bandwidth meter). |
| network.egress      | 5.16         | 5.16   | 0.00      | 0.00    | 0%                      | Internet egress. |
| security.keyvault   | 0.52         | 0.52   | 0.00      | 0.00    | 0%                      | Key Vault ops. |
| monitoring.loganalytics | 11.24   | 11.24  | 0.00      | 0.00    | 0%                      | Log Analytics retention. |
| backup.vault        | 4.32         | 4.32   | 0.00      | 0.00    | 0%                      | Backup vault. |
| dr.asr              | 27.68        | 27.68  | 0.00      | 0.00    | 0%                      | Site Recovery. |
| **Total (modeled)** | **166.12***  | 55.27  | 3.83      | 107.02  | ~2.3% of modeled is estimated | *Reported total; modeled_total is 59.10 (priced+estimated only). |

> **Where estimates dominate:** Blob storage is 100% estimated.  
> **Where missing dominates:** SQL DB and VM compute dominate the “missing” portion.

---

### 3.2 Cost_optimized (1‑year Reserved VMs)

#### Main components (cost_optimized)

Same as baseline, except:

- **Compute**
  - 2× Linux VMs, Standard_D2s_v3, but **billing_model = reserved** (1‑year RI).
- All other components (SQL DB, Redis, Blob, network, Key Vault, Log Analytics, Backup, ASR) are **identical in architecture and usage** to baseline.

#### Pricing table – cost_optimized

| Scenario      | Resource ID        | Category             | Service            | SKU (requested / resolved)                                   | Region     | Billing   | Unit Price | Unit      | Units  | Monthly Cost | Yearly Cost | Notes |
|---------------|--------------------|----------------------|--------------------|--------------------------------------------------------------|------------|-----------|-----------:|-----------|-------:|-------------:|------------:|-------|
| cost_optimized | vnet-prod         | network.vnet         | Virtual Network    | Virtual Network / Virtual Network                           | westeurope | reserved  | 0.00       | VNet      | 1.0   | 0.00         | 0.00        | No direct VNet charge; “reserved” irrelevant. |
| cost_optimized | vm-web-1-reserved | compute.vm           | Virtual Machines   | Standard_D2s_v3 / D2s v3 (Reservation, 1‑year)              | westeurope | reserved  | 579.4595   | 1 Hour*   | 2.0   | 96.58        | 1158.92     | RI SKU resolved but flagged sku_mismatch; unit price looks like 1‑year prepay, not hourly. |
| cost_optimized | vm-web-osdisk     | storage.disk         | Storage            | P6 / P6 LRS Disk Mount                                       | westeurope | payg      | 0.5284     | 1/Month   | 2.0   | 1.06         | 12.68       | Same as baseline. |
| cost_optimized | sql-db-prod       | db.sql               | SQL Database       | GP_Gen5_2 / 1 vCore (FSv2 vCore meter)                      | westeurope | payg      | 0.1271     | 1 Hour    | 730.0 | 92.78        | 1113.40     | Different meter vs requested Gen5_2; treated as mismatch. |
| cost_optimized | redis-cache       | cache.redis          | Redis Cache        | Standard C1 / C1 Cache Instance                             | westeurope | payg      | 0.0597     | 1 Hour    | 730.0 | 43.58        | 522.97      | Same as baseline. |
| cost_optimized | blob-static-assets| storage.blob         | Storage            | Hot/Cool / (estimated meters)                               | westeurope | payg      | –          | –         | –     | 3.83         | 45.96       | Same usage as baseline; estimated. |
| cost_optimized | public-ip-web     | network.public_ip    | Virtual Network    | Standard / Standard IPv4 Static Public IP                   | westeurope | payg      | 0.0043     | 1 Hour    | 730.0 | 3.14         | 37.67       | Same as baseline. |
| cost_optimized | lb-web            | network.lb           | Load Balancer      | Standard / Standard Data Processed                          | westeurope | payg      | 0.0043     | 1 GB      | 300.0 | 1.29         | 15.48       | Same as baseline. |
| cost_optimized | nat-egress        | network.nat          | NAT Gateway        | Standard / Std Inter-AZ Data Transfer Out                   | westeurope | payg      | 0.0086     | 1 GB      | 100.0 | 0.86         | 10.32       | Same as baseline. |
| cost_optimized | bandwidth-egress  | network.egress       | Bandwidth          | Standard / Std Inter-AZ Data Transfer Out                   | westeurope | payg      | 0.0086     | 1 GB      | 600.0 | 5.16         | 61.92       | Same as baseline. |
| cost_optimized | keyvault-prod     | security.keyvault    | Key Vault          | Standard / Operations                                       | westeurope | payg      | 0.0259     | 10K ops   | 20.0  | 0.52         | 6.22        | Same as baseline. |
| cost_optimized | loganalytics-prod | monitoring.loganalytics | Log Analytics   | Per GB / Analytics Logs Data Retention                      | westeurope | payg      | 0.1124     | 1 GB/Month| 100.0 | 11.24        | 134.88      | Same as baseline. |
| cost_optimized | backup-vault-prod | backup.vault         | Backup             | Azure Backup / Azure Files Protected Instances              | westeurope | payg      | 4.3243     | 1/Month   | 1.0   | 4.32         | 51.89       | Same as baseline. |
| cost_optimized | asr-dr            | dr.asr               | Azure Site Recovery | Protected Instances / VM Replicated to System Center      | westeurope | payg      | 13.8378    | 1/Month   | 2.0   | 27.68        | 332.11      | Same as baseline. |

\* The RI unit price is likely a **1‑year reservation amortized** or prepay value; the metadata labels it as `type: Reservation`. Treat with caution.

> **Cost_optimized totals (all services)**  
> - Monthly (priced): **€55.27**  
> - Monthly (estimated): **€3.83**  
> - Monthly (missing): **€232.94** (VMs + SQL treated as missing for required)  
> - Modeled total (priced + estimated): **€59.10**  
> - Reported “with estimates” total: **€292.04** (includes missing; not reliable).

#### Aggregated by category – cost_optimized

| Category            | Monthly Total | Priced | Estimated | Missing | Est. Share | Notes |
|---------------------|-------------:|-------:|----------:|--------:|-----------:|-------|
| compute.vm          | 96.58        | 0.00   | 0.00      | 96.58   | 0%         | 2× D2s v3 reserved; treated as missing for required. |
| db.sql              | 92.78        | 0.00   | 0.00      | 92.78   | 0%         | SQL DB via FSv2 vCore meter. |
| cache.redis         | 43.58        | 0.00   | 0.00      | 43.58   | 0%         | Redis C1. |
| storage.disk        | 1.06         | 1.06   | 0.00      | 0.00    | 0%         | OS disks. |
| storage.blob        | 3.83         | 0.00   | 3.83      | 0.00    | 100%       | Blob estimated. |
| network.public_ip   | 3.14         | 3.14   | 0.00      | 0.00    | 0%         | Public IP. |
| network.lb          | 1.29         | 1.29   | 0.00      | 0.00    | 0%         | Load Balancer. |
| network.nat         | 0.86         | 0.86   | 0.00      | 0.00    | 0%         | NAT. |
| network.egress      | 5.16         | 5.16   | 0.00      | 0.00    | 0%         | Egress. |
| security.keyvault   | 0.52         | 0.52   | 0.00      | 0.00    | 0%         | Key Vault. |
| monitoring.loganalytics | 11.24   | 11.24  | 0.00      | 0.00    | 0%         | Log Analytics. |
| backup.vault        | 4.32         | 4.32   | 0.00      | 0.00    | 0%         | Backup. |
| dr.asr              | 27.68        | 27.68  | 0.00      | 0.00    | 0%         | ASR. |
| **Total (modeled)** | **292.04***  | 55.27  | 3.83      | 232.94  | ~1.3% est. | *Reported; modeled_total is 59.10 (priced+estimated only). |

---

### 3.3 High_performance

#### Main components (high_performance)

- **Compute**
  - 2× **Windows** VMs, Standard_D4s_v3 (4 vCores, more RAM), PAYG.
  - Premium SSD P10 (128 GB) OS disks per VM.
- **Data / DB**
  - Same Azure SQL DB tier as cost_optimized (FSv2 vCore meter used).
- **Caching**
  - Same Redis C1 tier, with higher ops/throughput.
- **Storage**
  - Blob: 250 GB hot, 50 GB cool, higher egress.
- **Network**
  - Same VNet, Public IP, LB, NAT, but with higher data processed and egress volumes.
- **Security / Secrets**
  - Key Vault with more operations.
- **Monitoring / Analytics**
  - Log Analytics ingestion increased to 130 GB/month.
- **Backup & DR**
  - Backup vault with 400 GB backup storage.
  - ASR for 2 Windows VMs with more replicated storage.

#### Pricing table – high_performance

| Scenario        | Resource ID        | Category             | Service            | SKU (requested / resolved)                                   | Region     | Billing | Unit Price | Unit        | Units  | Monthly Cost | Yearly Cost | Notes |
|----------------|--------------------|----------------------|--------------------|--------------------------------------------------------------|------------|---------|-----------:|-------------|-------:|-------------:|------------:|-------|
| high_performance | vnet-prod        | network.vnet         | Virtual Network    | Virtual Network / Virtual Network                           | westeurope | payg    | 0.00       | VNet        | 1.0   | 0.00         | 0.00        | No direct charge. |
| high_performance | vm-web-hp        | compute.vm           | Virtual Machines   | Standard_D4s_v3 / (missing)                                 | westeurope | payg    | –          | –           | 2.0   | null         | null        | Windows D4s v3; price lookup failed. |
| high_performance | vm-web-hp-osdisk | storage.disk         | Storage            | P10 / P10 LRS Disk Mount                                     | westeurope | payg    | 1.0231     | 1/Month     | 2.0   | 2.05         | 24.55       | Premium SSD 128 GB OS disks. |
| high_performance | sql-db-prod      | db.sql               | SQL Database       | GP_Gen5_2 / 1 vCore (FSv2 vCore meter)                      | westeurope | payg    | 0.1271     | 1 Hour      | 730.0 | 92.78        | 1113.40     | Same meter as cost_optimized; mismatch vs requested Gen5_2. |
| high_performance | redis-cache      | cache.redis          | Redis Cache        | Standard C1 / C1 Cache Instance                             | westeurope | payg    | 0.0597     | 1 Hour      | 730.0 | 43.58        | 522.97      | Same tier as baseline, more ops. |
| high_performance | blob-static-assets | storage.blob       | Storage            | Hot/Cool / (estimated meters)                               | westeurope | payg    | –          | –           | –     | 4.68         | 56.16       | 250 GB hot, 50 GB cool; estimated. |
| high_performance | public-ip-web    | network.public_ip    | Virtual Network    | Standard / Standard IPv4 Static Public IP                   | westeurope | payg    | 0.0043     | 1 Hour      | 730.0 | 3.14         | 37.67       | Same SKU as baseline. |
| high_performance | lb-web           | network.lb           | Load Balancer      | Standard / Standard Data Processed                          | westeurope | payg    | 0.0043     | 1 GB        | 350.0 | 1.50         | 18.06       | Higher processed data (350 GB). |
| high_performance | nat-egress       | network.nat          | NAT Gateway        | Standard / Std Inter-AZ Data Transfer Out                   | westeurope | payg    | 0.0086     | 1 GB        | 120.0 | 1.03         | 12.38       | 120 GB outbound via NAT. |
| high_performance | bandwidth-egress | network.egress       | Bandwidth          | Standard / Std Inter-AZ Data Transfer Out                   | westeurope | payg    | 0.0086     | 1 GB        | 750.0 | 6.45         | 77.40       | 750 GB/month egress. |
| high_performance | keyvault-prod    | security.keyvault    | Key Vault          | Standard / Operations                                       | westeurope | payg    | 0.0259     | 10K ops     | 25.0  | 0.65         | 7.77        | ~250k ops/month. |
| high_performance | loganalytics-prod| monitoring.loganalytics | Log Analytics   | Per GB / Analytics Logs Data Retention                      | westeurope | payg    | 0.1124     | 1 GB/Month  | 130.0 | 14.61        | 175.34      | 130 GB/month retention. |
| high_performance | backup-vault-prod| backup.vault         | Backup             | Azure Backup / Azure Files Protected Instances              | westeurope | payg    | 4.3243     | 1/Month     | 1.0   | 4.32         | 51.89       | 400 GB backup storage. |
| high_performance | asr-dr           | dr.asr               | Azure Site Recovery | Protected Instances / VM Replicated to System Center      | westeurope | payg    | 13.8378    | 1/Month     | 2.0   | 27.68        | 332.11      | ASR for 2 Windows VMs. |

> **High_performance totals (all services)**  
> - Monthly (priced): **€61.43**  
> - Monthly (estimated): **€4.68**  
> - Monthly (missing): **€136.36** (VMs + “required” SQL)  
> - Modeled total (priced + estimated): **€66.11**  
> - Reported “with estimates” total: **€202.47**.

#### Aggregated by category – high_performance

| Category            | Monthly Total | Priced | Estimated | Missing | Est. Share | Notes |
|---------------------|-------------:|-------:|----------:|--------:|-----------:|-------|
| compute.vm          | 0.00         | 0.00   | 0.00      | 0.00    | 0%         | VM pricing missing; category total shows 0 but missing tracked separately. |
| db.sql              | 92.78        | 0.00   | 0.00      | 92.78   | 0%         | SQL DB via FSv2 vCore meter. |
| cache.redis         | 43.58        | 0.00   | 0.00      | 43.58   | 0%         | Redis C1. |
| storage.disk        | 2.05         | 2.05   | 0.00      | 0.00    | 0%         | P10 OS disks. |
| storage.blob        | 4.68         | 0.00   | 4.68      | 0.00    | 100%       | Blob estimated. |
| network.public_ip   | 3.14         | 3.14   | 0.00      | 0.00    | 0%         | Public IP. |
| network.lb          | 1.50         | 1.50   | 0.00      | 0.00    | 0%         | LB with more data. |
| network.nat         | 1.03         | 1.03   | 0.00      | 0.00    | 0%         | NAT. |
| network.egress      | 6.45         | 6.45   | 0.00      | 0.00    | 0%         | Egress. |
| security.keyvault   | 0.65         | 0.65   | 0.00      | 0.00    | 0%         | Key Vault. |
| monitoring.loganalytics | 14.61   | 14.61  | 0.00      | 0.00    | 0%         | Log Analytics. |
| backup.vault        | 4.32         | 4.32   | 0.00      | 0.00    | 0%         | Backup. |
| dr.asr              | 27.68        | 27.68  | 0.00      | 0.00    | 0%         | ASR. |
| **Total (modeled)** | **202.47***  | 61.43  | 4.68      | 136.36  | ~2.3% est. | *Reported; modeled_total is 66.11 (priced+estimated only). |

---

## 4. Resources where pricing failed – what to check manually

### Baseline

1. **vm-web-1 (compute.vm, Standard_D2s_v3, Linux, PAYG)**
   - Error: `Price not found for requested SKU`.
   - Manual check:
     - Use Azure Pricing Calculator for **Linux D2s v3** in **West Europe**, PAYG.
     - Confirm whether you have **Azure Hybrid Benefit** (for Windows, not relevant here) or any dev/test discounts.
     - Ensure correct meter: “Virtual Machines DSv3 Series – D2s v3 – Linux”.

2. **sql-db-prod (db.sql, GP_Gen5_2)**
   - Marked `sku_mismatch` – resolved to **Zone Redundancy vCore** meter.
   - Manual check:
     - Decide if you want **zone redundant** or **non‑ZR** Single DB.
     - For GP Gen5 2 vCores, pick the exact meter:
       - “SQL Database Single – General Purpose – Gen5 – 2 vCore” (ZR or non‑ZR).
     - Re‑price with correct meter and storage (128 GB).

3. **blob-static-assets (storage.blob)**
   - `pricing_status = estimated_required`.
   - Manual check:
     - Confirm **account type** (StorageV2 / BlobStorage), **redundancy** (LRS vs ZRS), and **access tier**.
     - Price:
       - Hot LRS data stored (GB/month).
       - Cool LRS data stored (if used) and early deletion.
       - Read/write/transaction costs if significant.
     - Validate **egress** is not double‑counted with Bandwidth.

### Cost_optimized

1. **vm-web-1-reserved (compute.vm, Standard_D2s_v3, Linux, 1‑year RI)**
   - `sku_mismatch`, and unit_price looks like a **reservation charge**, not an hourly rate.
   - Manual check:
     - In the Azure portal, price a **1‑year Reserved Instance** for **D2s v3 Linux, West Europe**.
     - Decide on **upfront vs monthly** payment and amortize to €/month.
     - Ensure reservation scope (single subscription vs shared).

2. **sql-db-prod (db.sql)**
   - Same as above: FSv2 vCore meter vs requested Gen5_2.
   - Manual check as for baseline.

3. **blob-static-assets (storage.blob)**
   - Same as baseline: estimated.

### High_performance

1. **vm-web-hp (compute.vm, Standard_D4s_v3, Windows, PAYG)**
   - `Price not found for requested SKU`.
   - Manual check:
     - Use Azure Pricing Calculator for **Windows D4s v3** in **West Europe**, PAYG.
     - Check if you have **Hybrid Benefit** for Windows Server licenses; if yes, use the **Linux-equivalent rate** plus Software Assurance cost.

2. **sql-db-prod (db.sql)**
   - Same FSv2 vCore mismatch as cost_optimized.

3. **blob-static-assets (storage.blob)**
   - Estimated; same manual checks as above, but with 250 GB hot and higher egress.

---

## 5. FinOps recommendations

### 5.1 Quick wins

1. **Fix VM and SQL pricing inputs**
   - For all scenarios, correct:
     - VM SKUs: D2s v3 Linux PAYG, D2s v3 Linux 1‑year RI, D4s v3 Windows PAYG.
     - SQL DB: choose **exact** Gen5 2 vCore meter (ZR or non‑ZR).
   - This will turn the “missing” portion into priced values and make scenarios comparable.

2. **Validate Blob Storage configuration**
   - Confirm:
     - Storage account type (StorageV2, LRS).
     - Hot vs Cool vs Archive split.
   - For static assets with CDN or Front Door, you may be able to:
     - Keep origin in **cool** for less frequently accessed content.
     - Use **Azure Front Door** or CDN to reduce origin egress and per‑GB costs (but add FDs own cost).

3. **Right‑size Log Analytics**
   - 100–130 GB/month ingestion is modest but:
     - Use **data caps** and **table‑level retention** to avoid unbounded growth.
     - Turn off noisy diagnostic categories (e.g., verbose logs you don’t query).

4. **Key Vault usage**
   - 200–250k ops/month is low cost, but:
     - Prefer **managed identities** over secrets where possible to reduce secret rotation overhead.
     - Avoid polling Key Vault; cache secrets in app memory with reasonable TTL.

### 5.2 Spot vs PAYG vs Reserved

- **VMs (compute dominates once priced correctly)**:
  - **Baseline**: PAYG Linux D2s v3.
    - For a **steady 24×7 production workload**, 1‑year or 3‑year **Reserved Instances** or **Savings Plans** will typically save **30–60%** vs PAYG.
  - **Cost_optimized**: Intends to use 1‑year RI for the same VMs.
    - Ensure:
      - Reservation term and payment option match your budget.
      - Reservation is scoped to the subscription or shared across subscriptions as needed.
  - **High_performance**: Windows D4s v3 PAYG.
    - For Windows, consider:
      - **Azure Hybrid Benefit** to reuse existing Windows Server licenses.
      - **RI or Savings Plan** if the workload is always‑on.
- **Spot VMs**
  - For this **production** web app with 99.9% uptime, Spot is only suitable for:
    - Non‑critical background jobs.
    - Additional burst capacity behind the main pool, with graceful eviction handling.
  - Do **not** rely solely on Spot for the primary web tier.

### 5.3 Right‑sizing ideas

- **VM size**
  - Start with D2s v3 (baseline) and monitor:
    - CPU, memory, disk, and network utilization.
    - If consistently under 40–50% utilization, consider:
      - Scaling down to **B‑series** (if workload is bursty) or smaller sizes.
      - Or using **App Service** instead of raw VMs if the app is HTTP‑centric and stateless.
  - For high_performance:
    - Only move to D4s v3 Windows if you have clear CPU/RAM bottlenecks or Windows‑specific dependencies.
    - Otherwise, consider **Linux D4s v3** or scale‑out more D2s v3 instances.

- **SQL DB**
  - Monitor DTU/vCore utilization, CPU, IO, and wait stats.
  - If underutilized:
    - Scale down to **1 vCore** or consider **serverless** or **elastic pool** if you have multiple DBs.
  - If overutilized:
    - Consider scaling up DB independently of VMs; don’t over‑provision VMs to compensate for DB bottlenecks.

- **Redis**
  - C1 may be overkill if hit rate and memory usage are low.
  - Monitor:
    - Memory used vs capacity.
    - CPU and connection counts.
  - If low, consider **C0**; if high, consider **C2** or clustering.

- **Log Analytics**
  - Use **sampling** and **log levels** in application logging to avoid unnecessary ingestion.

### 5.4 Region and egress considerations

- **Region**
  - All scenarios are in **West Europe**; good for EU latency and data residency.
  - Moving to a cheaper region (e.g., North Europe) can reduce some unit prices but:
    - Increases **inter‑region latency**.
    - May increase **egress** if users are primarily in West Europe.
  - For production with 50k MAU in EU, West Europe is a sensible default.

- **Egress / NAT / Gateways / Front Door**
  - You currently model:
    - **Bandwidth** (internet egress).
    - **NAT Gateway** data processed.
    - **Load Balancer** data processed.
  - Consider:
    - **Azure Front Door or CDN** in front of the web app:
      - Offloads static content.
      - Reduces origin egress and improves performance.
      - Adds its own per‑GB and per‑rule costs; model this explicitly.
    - Ensure you are **not double‑counting** egress:
      - Bandwidth vs NAT vs LB vs Blob egress; in reality, Azure bills specific meters, not all simultaneously.

- **Costs scaling with volume/throughput**
  - **Blob Storage**: scales with GB stored, operations, and egress.
  - **Bandwidth**: scales linearly with GB out.
  - **Log Analytics**: scales with GB ingested/retained.
  - **Key Vault**: scales with operations.
  - **ASR & Backup**: scale with protected instance count and GB replicated/backed up.

---

## 6. Delta tables vs baseline (indicative only)

Because of `status = "not_comparable"` due to missing pricing, these deltas are **approximate** and based on the reported “with estimates” totals. Use them only for directional insight.

### 6.1 Overall totals – cost_optimized vs baseline

Using `monthly_with_estimates` and `yearly_with_estimates`:

| Scenario        | Metric                    | Baseline | Cost_optimized | Abs Δ   | % Δ vs Baseline |
|----------------|---------------------------|---------:|--------------:|--------:|----------------:|
| All services   | Monthly (priced only)     | 55.27    | 55.27         | 0.00    | 0%              |
| All services   | Monthly (priced+est)      | 59.10    | 59.10         | 0.00    | 0%              |
| All services   | Monthly (with “missing”)  | 166.12   | 292.04        | 125.92  | +75.8%          |
| All services   | Yearly (with “missing”)   | 1993.34  | 3504.42       | 1511.08 | +75.8%          |

Interpretation: the large uplift is an artifact of how missing VM/SQL costs are represented, not a real increase. Once VM and SQL are correctly priced, **cost_optimized should be cheaper than baseline** on compute.

### 6.2 Overall totals – high_performance vs baseline

| Scenario        | Metric                    | Baseline | High_perf | Abs Δ   | % Δ vs Baseline |
|----------------|---------------------------|---------:|----------:|--------:|----------------:|
| All services   | Monthly (priced only)     | 55.27    | 61.43     | 6.16    | +11.1%          |
| All services   | Monthly (priced+est)      | 59.10    | 66.11     | 7.01    | +11.9%          |
| All services   | Monthly (with “missing”)  | 166.12   | 202.47    | 36.35   | +21.9%          |
| All services   | Yearly (with “missing”)   | 1993.34  | 2429.70   | 436.36  | +21.9%          |

Interpretation: priced+estimated components (excluding missing VM/SQL) suggest **~12% higher non‑compute/non‑SQL costs** for high_performance (more storage, egress, logs, backup). The true delta will be higher once D4s v3 Windows VM pricing is added.

### 6.3 Category‑level monthly deltas – cost_optimized vs baseline

Using `totals.by_category.monthly` (all services):

| Category          | Baseline € | Cost_opt € | Abs Δ  | % Δ vs Baseline | Comment |
|-------------------|-----------:|-----------:|-------:|----------------:|---------|
| compute.vm        | 0.00       | 96.58      | 96.58  | n/a             | Baseline VM cost missing; cannot compare. |
| db.sql            | 63.44      | 92.78      | 29.34  | +46.2%          | Different meter; not apples‑to‑apples. |
| cache.redis       | 43.58      | 43.58      | 0.00   | 0%              | Same Redis tier. |
| storage.disk      | 1.06       | 1.06       | 0.00   | 0%              | Same OS disks. |
| storage.blob      | 3.83       | 3.83       | 0.00   | 0%              | Same usage. |
| network.public_ip | 3.14       | 3.14       | 0.00   | 0%              | Same. |
| network.lb        | 1.29       | 1.29       | 0.00   | 0%              | Same. |
| network.nat       | 0.86       | 0.86       | 0.00   | 0%              | Same. |
| network.egress    | 5.16       | 5.16       | 0.00   | 0%              | Same. |
| security.keyvault | 0.52       | 0.52       | 0.00   | 0%              | Same. |
| monitoring.loganalytics | 11.24| 11.24      | 0.00   | 0%              | Same. |
| backup.vault      | 4.32       | 4.32       | 0.00   | 0%              | Same. |
| dr.asr            | 27.68      | 27.68      | 0.00   | 0%              | Same. |

### 6.4 Category‑level monthly deltas – high_performance vs baseline

| Category          | Baseline € | High_perf € | Abs Δ | % Δ vs Baseline | Comment |
|-------------------|-----------:|------------:|------:|----------------:|---------|
| compute.vm        | 0.00       | 0.00        | 0.00 | n/a             | Both missing; cannot compare. |
| db.sql            | 63.44      | 92.78       | 29.34| +46.2%          | Different meter; not apples‑to‑apples. |
| cache.redis       | 43.58      | 43.58       | 0.00 | 0%              | Same tier. |
| storage.disk      | 1.06       | 2.05        | 0.99 | +93.4%          | Larger P10 disks vs P6. |
| storage.blob      | 3.83       | 4.68        | 0.85 | +22.2%          | More hot GB and egress. |
| network.public_ip | 3.14       | 3.14        | 0.00 | 0%              | Same. |
| network.lb        | 1.29       | 1.50        | 0.21 | +16.3%          | More data processed. |
| network.nat       | 0.86       | 1.03        | 0.17 | +19.8%          | More outbound via NAT. |
| network.egress    | 5.16       | 6.45        | 1.29 | +25.0%          | More internet egress. |
| security.keyvault | 0.52       | 0.65        | 0.13 | +25.0%          | More KV ops. |
| monitoring.loganalytics | 11.24| 14.61       | 3.37 | +30.0%          | More log ingestion. |
| backup.vault      | 4.32       | 4.32        | 0.00 | 0%              | Same protected instance meter; more GB not modeled separately. |
| dr.asr            | 27.68      | 27.68       | 0.00 | 0%              | Same meter; more replicated GB not modeled separately. |

---

### Final guidance

- Use the **baseline** as your architectural starting point.
- Decide whether you want:
  - **Cost_optimized**: same performance, lower VM cost via 1‑year RI/Savings Plan.
  - **High_performance**: more powerful Windows VMs and higher throughput, accepting higher compute, storage, and egress costs.
- Before making commercial decisions:
  - Correct the **VM** and **SQL** SKUs in the Azure Pricing Calculator.
  - Replace estimated Blob and bandwidth proxies with exact meters.
  - Re‑run the comparison to get clean, comparable totals and category breakdowns.