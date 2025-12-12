## 1. Baseline / Recommended scenario – short narrative

The baseline is a production BI platform built on **Microsoft Fabric F64 capacity** with around **50 TB in OneLake** and **daily refresh** workloads.

- Fabric F64 provides the unified compute for **Power BI, Lakehouse/Warehouse, Data Engineering and Data Science** workloads.
- OneLake is modeled as **50 TB hot ADLS Gen2 (GRS)** to reflect durable, production-grade storage for curated data and semantic models.
- **Azure Data Factory / Fabric Data Pipelines** orchestrate daily ingestion and refresh from an Azure SQL source and other systems.
- A **GP_Gen5_8 Azure SQL Database** represents a key structured source system.
- A **hub VNet + NAT Gateway + Public IP** pattern secures outbound connectivity for self‑hosted integration runtimes or gateways.
- **Azure Key Vault** manages secrets and connection strings.
- **Log Analytics** centralizes monitoring and diagnostics for Fabric, pipelines, and infra.
- **Backup vault** and **Azure Site Recovery** provide backup and DR for supporting components (e.g., self-hosted IR/gateway VMs).

Cost-wise, the model is **incomplete**: Fabric F64 and SQL DB compute are only partially priced (or treated as “missing”), and some network/public IP prices are missing. The modeled total is about **$161.56/month** (only the parts we can price/estimate), while the “with estimates” total is **$683.79/month**, but this latter number is dominated by placeholder/missing values and should not be treated as a precise TCO.

---

## 2. Other scenarios – how they differ from baseline

### Cost Optimized

Intent: **Non‑critical / pilot / dev-test** environment with lower cost.

Key differences vs baseline:

- **Same F64 capacity**, but assumed **not 24x7** (500 hours/month vs 730) – effectively modeling **partial-time usage**.
- OneLake modeled as **LRS with tiering**: 30 TB hot + 21.2 TB cool instead of 50 TB hot GRS – lower durability and cost.
- **Smaller ADF footprint** (160 hours vs 730).
- **Smaller SQL DB** (GP_Gen5_4, 4 vCores, 256 GB) – but pricing resolution still ambiguous in the JSON.
- **Reduced NAT egress** (500 GB vs 1500 GB).
- **Lower Key Vault and Log Analytics volumes**.
- **ASR removed** (only backup vault remains) – weaker DR posture.

Modeled total: **$92.85/month** (priced + estimated) vs **$161.56/month** baseline modeled; “with estimates” total is **$615.08/month** vs **$683.79/month** baseline, but both are heavily influenced by missing/placeholder values.

### High Performance / Enterprise

Intent: **Enterprise-grade, 24x7, high-throughput** BI platform with stronger HA/DR.

Key differences vs baseline:

- **F64 on 1‑year reservation** (modeled as $100/month placeholder) – assumes high utilization and commitment.
- OneLake modeled as **Premium ZRS** (zone-redundant, higher throughput) with all 50 TB hot.
- **Heavier ADF usage** (same 730 hours but more data movement).
- **Larger SQL DB** (GP_Gen5_16, 16 vCores, 1 TB) on **reserved capacity**.
- **More NAT capacity** (2 NAT gateways, 4000 GB egress).
- **Premium Key Vault** (HSM-backed keys).
- **Higher Log Analytics ingestion and retention**.
- **Larger backup footprint** and **more ASR instances (4 VMs)** for stronger DR.

Modeled total: **$219.46/month** (priced + estimated) vs **$161.56/month** baseline modeled; “with estimates” total **$719.46/month** vs **$683.79/month** baseline, again with large missing components.

---

## 3. Scenario details

### 3.1 Baseline scenario

#### Main components (baseline)

- **Compute / Analytics**
  - Microsoft Fabric **F64** capacity (24x7, production).
  - Azure Data Factory / Fabric Data Pipelines for orchestration.
- **Data & Storage**
  - OneLake modeled as **50 TB hot ADLS Gen2, GRS**.
  - Azure SQL Database **GP_Gen5_8** as a key source.
- **Network**
  - Virtual Network for secure topology.
  - NAT Gateway + Standard Public IP for outbound internet.
- **Security**
  - Azure **Key Vault (Standard)** for secrets and keys.
- **Monitoring & Operations**
  - **Log Analytics** workspace for Fabric, ADF, infra logs.
- **Backup & DR**
  - **Backup vault** (Recovery Services) for supporting components.
  - **Azure Site Recovery** for 2 protected instances.

#### Pricing table – baseline

> Note: Many core items (Fabric F64, SQL DB compute, public IP, some monitoring/backup) are **missing or placeholder-priced**. Treat this table as indicative, not authoritative.

| Scenario | Resource ID           | Category                | Service         | SKU (requested / resolved)                          | Region     | Billing | Unit Price | Unit        | Units   | Monthly Cost | Yearly Cost | Notes |
|---------|-----------------------|-------------------------|-----------------|------------------------------------------------------|-----------|--------|-----------|------------|--------:|------------:|-----------:|-------|
| baseline | fabric-capacity-f64  | analytics.fabric        | Microsoft Fabric | F64 / OneLake Storage Mirroring (mismatch)          | westeurope | payg   | 0.024     | 1 GB/Month | 2000.0 | 48.00       | 576.00     | Intended to be Fabric F64 compute; pricing resolved to OneLake storage mirroring – **not correct** for capacity. Treat as missing for Fabric compute. |
| baseline | onelake-storage      | storage.blob            | Storage         | Standard_GRS / Hot Data Returned (ADLS Gen2)        | westeurope | payg   | 0.0008    | 1 GB       | 51200  | 40.96       | 491.52     | 50 TB hot, GRS, modeled via ADLS Gen2 query acceleration. **Estimated**. |
| baseline | datafactory-orchestration | analytics.datafactory | Azure Data Factory | (activity-based) / On Premises Data Movement    | westeurope | payg   | 0.1       | 1 Hour     | 730.0  | 73.00       | 876.00     | ADF or Fabric Data Pipelines, 730 “data movement hours” as proxy. |
| baseline | sql-source-db        | db.sql                  | SQL Database    | GP_Gen5_8 / Gen5 vCore (1 vCore meter)              | westeurope | payg   | 0.167439  | 1 Hour     | 730.0  | 122.23      | 1466.77    | GP_Gen5_8 requested; pricing engine mapped to 1 vCore meter and scaled. **SKU mismatch; treat as approximate**. |
| baseline | vnet-bi-platform     | network.vnet            | Virtual Network | Virtual Network / Virtual Network (logical)         | westeurope | payg   | 0.0       | VNet       | 1.0    | 0.00        | 0.00       | No direct VNet charge; data transfer/peering not modeled. |
| baseline | nat-egress           | network.nat             | Bandwidth       | Standard / Inter-AZ Data Transfer Out               | westeurope | payg   | 0.01      | 1 GB       | 1500.0 | 15.00       | 180.00     | 1.5 TB/month egress via NAT; only inter-AZ component modeled. Internet egress not fully captured. |
| baseline | public-ip-nat        | network.public_ip       | Public IP       | Standard / (missing)                                | westeurope | payg   | –         | –          | –      | –           | –          | **Price not found**; Standard Public IP hourly charge missing. Check Azure calculator. |
| baseline | keyvault-bi          | security.keyvault       | Key Vault       | standard / Standard Operations                       | westeurope | payg   | 0.03      | 10K ops    | 20.0   | 0.60        | 7.20       | ~200k operations/month. Secrets management for pipelines and IRs. |
| baseline | loganalytics-bi      | monitoring.loganalytics | Log Analytics   | PerGB2018 / Analytics Logs Data Retention           | westeurope | payg   | 0.13      | 1 GB/Month | 200.0 | 26.00       | 312.00     | 200 GB/month retention; ingestion/analyzed meters not modeled. **SKU mismatch flag** but pricing is reasonable. |
| baseline | backup-vault-bi      | backup.vault            | Backup          | Standard / ADLS Gen2 Vaulted LRS Write Ops          | westeurope | payg   | 0.054     | 10K ops    | 10.0   | 0.54        | 6.48       | Only write ops modeled; backup storage capacity not modeled. |
| baseline | asr-dr-bi            | dr.asr                  | Azure Site Recovery | (per-VM) / VM Replicated to System Center       | westeurope | payg   | 16.0      | 1/Month    | 2.0    | 32.00       | 384.00     | 2 protected instances; storage and compute in DR region not modeled. |

#### Aggregated by category – baseline

I’ll map to high-level categories: **compute/analytics, db, storage, network, security, monitoring, backup/DR, other**.

> “Modeled” = priced + estimated; “Missing” = flagged missing in totals. Ratios are vs modeled total ($161.56/month).

| Category          | Monthly (modeled) | Of Scenario Modeled Total | Est. Portion | Notes on estimates/missing |
|-------------------|------------------:|--------------------------:|------------:|----------------------------|
| Compute & Analytics (Fabric + ADF) | ≈121.0 (ADF 73.0 + placeholder 48.0 for Fabric) | ~75% | High (Fabric is mispriced) | Fabric F64 compute is **not correctly priced**; the $48 is actually OneLake mirroring. True Fabric cost will dominate. |
| DB (SQL)          | 122.23           | ~76% (overlaps with above; categories in JSON are separate) | Low (but SKU mismatch) | SQL DB compute is priced but via 1‑vCore meter; treat as approximate. |
| Storage (OneLake ADLS) | 40.96       | 25%                       | 100% estimated | Based on ADLS Gen2 query acceleration meter only; no transaction/storage tiering modeled. |
| Network (NAT + Public IP) | 15.00 (NAT only) | 9% | Low | Public IP cost missing; internet egress tiers not fully modeled. |
| Security (Key Vault) | 0.60          | <1%                       | Low | Ops-based; storage and premium features not modeled. |
| Monitoring (Log Analytics) | 26.00   | 16%                       | Medium | Retention only; ingestion/analyzed GB not modeled. |
| Backup (Vault)    | 0.54             | <1%                       | Medium | Only write ops; backup storage capacity not modeled. |
| DR (ASR)          | 32.00            | 20%                       | Low | Per-VM fee only; replicated storage and DR compute not modeled. |
| Other             | 0.00             | 0%                        | – | – |

> Because of SKU mismatches and missing Fabric/public IP pricing, **true monthly cost will be significantly higher** than the modeled $161.56/month.

---

### 3.2 Cost Optimized scenario

#### Main components (cost_optimized)

- **Compute / Analytics**
  - Microsoft Fabric **F64**, but assumed **500 hours/month** (e.g., business hours or partial month).
  - Reduced Azure Data Factory usage (160 hours).
- **Data & Storage**
  - OneLake modeled as **50 TB LRS** with **tiering**: 30 TB hot, 21.2 TB cool.
  - Smaller Azure SQL Database **GP_Gen5_4** (4 vCores, 256 GB).
- **Network**
  - VNet, NAT Gateway with **lower egress (500 GB)**, Standard Public IP.
- **Security**
  - Standard Key Vault with fewer operations.
- **Monitoring & Operations**
  - Log Analytics with **lower ingestion (80 GB)** and retention.
- **Backup & DR**
  - Backup vault with smaller footprint; **ASR omitted** to save cost.

#### Pricing table – cost_optimized

| Scenario       | Resource ID              | Category                | Service         | SKU (requested / resolved)                                  | Region     | Billing | Unit Price | Unit        | Units   | Monthly Cost | Yearly Cost | Notes |
|----------------|--------------------------|-------------------------|-----------------|--------------------------------------------------------------|-----------|--------|-----------|------------|--------:|------------:|-----------:|-------|
| cost_optimized | fabric-capacity-f64-co   | analytics.fabric        | Microsoft Fabric | F64 / OneLake Storage Mirroring (mismatch)                  | westeurope | payg   | 0.024     | 1 GB/Month | 800.0  | 19.20       | 230.40     | Intended Fabric F64 compute; resolved to OneLake mirroring. **Not correct for capacity**; treat as missing for Fabric compute. Lower “units” reflect reduced hours. |
| cost_optimized | onelake-storage-co       | storage.blob            | Storage         | Standard_LRS / Hot & Cool Data Returned (ADLS Gen2)         | westeurope | payg   | 0.0008/0.00225 | 1 GB   | 30000/21200 | 71.70       | 860.40     | 30 TB hot + 21.2 TB cool. **Estimated** from query acceleration meters. |
| cost_optimized | datafactory-orchestration-co | analytics.datafactory | Azure Data Factory | (activity-based) / On Premises Data Movement            | westeurope | payg   | 0.1       | 1 Hour     | 160.0  | 16.00       | 192.00     | Reduced orchestration vs baseline. |
| cost_optimized | sql-source-db-co         | db.sql                  | SQL Database    | GP_Gen5_4 / Gen5 vCore (1 vCore meter)                      | westeurope | payg   | 0.167439  | 1 Hour     | 730.0  | 122.23      | 1466.77    | Smaller DB requested, but pricing still mapped via 1‑vCore meter; **approximate**. |
| cost_optimized | vnet-bi-platform-co      | network.vnet            | Virtual Network | Virtual Network / Virtual Network (logical)                 | westeurope | payg   | 0.0       | VNet       | 1.0    | 0.00        | 0.00       | No direct VNet charge. |
| cost_optimized | nat-egress-co            | network.nat             | Bandwidth       | Standard / Inter-AZ Data Transfer Out                       | westeurope | payg   | 0.01      | 1 GB       | 500.0  | 5.00        | 60.00      | 500 GB/month via NAT. |
| cost_optimized | public-ip-nat-co         | network.public_ip       | Public IP       | Standard / (missing)                                        | westeurope | payg   | –         | –          | –      | –           | –          | **Price not found**; Standard Public IP hourly charge missing. |
| cost_optimized | keyvault-bi-co           | security.keyvault       | Key Vault       | standard / Standard Operations                               | westeurope | payg   | 0.03      | 10K ops    | 5.0    | 0.15        | 1.80       | ~50k operations/month. |
| cost_optimized | loganalytics-bi-co       | monitoring.loganalytics | Log Analytics   | PerGB2018 / Analytics Logs Data Retention                   | westeurope | payg   | 0.13      | 1 GB/Month | 80.0  | 10.40       | 124.80     | 80 GB/month retention; ingestion not modeled. |
| cost_optimized | backup-vault-bi-co       | backup.vault            | Backup          | Standard / ADLS Gen2 Vaulted LRS Write Ops                  | westeurope | payg   | 0.054     | 10K ops    | 5.0    | 0.27        | 3.24       | Smaller backup footprint; storage capacity not modeled. |

#### Aggregated by category – cost_optimized

Modeled total (priced + estimated) is **$92.85/month**.

| Category          | Monthly (modeled) | Of Scenario Modeled Total | Est. Portion | Notes |
|-------------------|------------------:|--------------------------:|------------:|-------|
| Compute & Analytics (Fabric + ADF) | ≈35.2 (ADF 16.0 + placeholder 19.2 for Fabric) | ~38% | High (Fabric mispriced) | Fabric F64 compute still missing; 19.2 is storage mirroring. |
| DB (SQL)          | 122.23           | >100% vs modeled total (due to JSON category accounting) | Low (approx) | SQL DB dominates modeled cost; but scenario totals treat much of this as “missing”. |
| Storage (OneLake ADLS) | 71.70       | 77%                       | 100% estimated | Tiered hot/cool; only query acceleration meters used. |
| Network (NAT + Public IP) | 5.00     | 5%                        | Low | Public IP missing. |
| Security (Key Vault) | 0.15          | <1%                       | Low | – |
| Monitoring (Log Analytics) | 10.40   | 11%                       | Medium | Retention only. |
| Backup (Vault)    | 0.27             | <1%                       | Medium | Only write ops. |
| DR (ASR)          | 0.00             | 0%                        | – | ASR intentionally omitted. |
| Other             | 0.00             | 0%                        | – | – |

> In practice, **Fabric F64 and SQL DB** will still be the main cost drivers; the “savings” here mostly come from **reduced hours, smaller DB, and cheaper storage redundancy/tiering**.

---

### 3.3 High Performance / Enterprise scenario

#### Main components (high_performance)

- **Compute / Analytics**
  - Microsoft Fabric **F64** on **1‑year reservation** (24x7).
  - Heavier ADF orchestration (730 hours, more data movement).
- **Data & Storage**
  - OneLake modeled as **Premium ZRS ADLS Gen2** (50 TB hot).
  - Larger Azure SQL Database **GP_Gen5_16** (16 vCores, 1 TB) on **reserved capacity**.
- **Network**
  - VNet.
  - **Two NAT Gateways** and **two Standard Public IPs** for higher throughput and zonal resilience; 4 TB/month egress.
- **Security**
  - **Premium Key Vault** with HSM-backed keys and higher operation volume.
- **Monitoring & Operations**
  - Log Analytics with **400 GB/month** retention and archive.
- **Backup & DR**
  - Larger backup vault footprint.
  - **ASR for 4 protected instances** for stronger DR.

#### Pricing table – high_performance

| Scenario         | Resource ID              | Category                | Service         | SKU (requested / resolved)                                  | Region     | Billing   | Unit Price | Unit        | Units | Monthly Cost | Yearly Cost | Notes |
|------------------|--------------------------|-------------------------|-----------------|--------------------------------------------------------------|-----------|----------|-----------|------------|------:|------------:|-----------:|-------|
| high_performance | fabric-capacity-f64-hp   | analytics.fabric        | Microsoft Fabric | F64 / Fabric Capacity Reservation (F64 CU)                  | westeurope | reserved | 1146.0    | 1 Hour     | 1.0  | 100.00      | 1200.00    | Reservation meter UOM ambiguous; modeled as $100/month placeholder. Real Fabric F64 reserved cost will be **much higher**. |
| high_performance | onelake-storage-hp       | storage.blob            | Storage         | Premium_ZRS / Hot Data Returned (ADLS Gen2 Flat)            | westeurope | payg     | 0.0008    | 1 GB       | 51200 | 40.96       | 491.52     | 50 TB hot Premium ZRS; **estimated** via query acceleration meter only. |
| high_performance | datafactory-orchestration-hp | analytics.datafactory | Azure Data Factory | (activity-based) / On Premises Data Movement            | westeurope | payg     | 0.1       | 1 Hour     | 730  | 73.00       | 876.00     | Heavier orchestration; same hours as baseline but more data movement (not fully modeled). |
| high_performance | sql-source-db-hp         | db.sql                  | SQL Database    | GP_Gen5_16 / Gen5 vCore Reservation                         | westeurope | reserved | 953.0     | 1 Hour     | 1.0  | 100.00      | 1200.00    | Reservation UOM ambiguous; modeled as $100/month placeholder. Real cost will be higher. |
| high_performance | vnet-bi-platform-hp      | network.vnet            | Virtual Network | Virtual Network / Virtual Network (logical)                 | westeurope | payg     | 0.0       | VNet       | 1.0  | 0.00        | 0.00       | No direct VNet charge. |
| high_performance | nat-egress-hp            | network.nat             | Bandwidth       | Standard / Inter-AZ Data Transfer Out                       | westeurope | payg     | 0.01      | 1 GB       | 4000 | 40.00       | 480.00     | 4 TB/month via NAT; 2 gateways (quantity=2) but cost modeled via egress GB only. |
| high_performance | public-ip-nat-hp         | network.public_ip       | Public IP       | Standard / (missing)                                        | westeurope | payg     | –         | –          | –    | –           | –          | **Price not found**; 2 Standard Public IPs not priced. |
| high_performance | keyvault-bi-hp           | security.keyvault       | Key Vault       | premium / Premium Operations                                | westeurope | payg     | 0.03      | 10K ops    | 50.0 | 1.50        | 18.00      | ~500k operations/month; HSM key costs not modeled. |
| high_performance | loganalytics-bi-hp       | monitoring.loganalytics | Log Analytics   | PerGB2018 / Analytics Logs Data Retention                   | westeurope | payg     | 0.13      | 1 GB/Month | 400  | 52.00       | 624.00     | 400 GB/month retention; ingestion/analyzed GB not modeled. |
| high_performance | backup-vault-bi-hp       | backup.vault            | Backup          | Standard / ADLS Gen2 Vaulted LRS Write Ops                  | westeurope | payg     | 0.054     | 10K ops    | 15.0 | 0.81        | 9.72       | Larger backup footprint; storage capacity not modeled. |
| high_performance | asr-dr-bi-hp             | dr.asr                  | Azure Site Recovery | (per-VM) / VM Replicated to System Center               | westeurope | payg     | 16.0      | 1/Month    | 4.0  | 64.00       | 768.00     | 4 protected instances; DR storage/compute not modeled. |

#### Aggregated by category – high_performance

Modeled total (priced + estimated) is **$219.46/month**.

| Category          | Monthly (modeled) | Of Scenario Modeled Total | Est. Portion | Notes |
|-------------------|------------------:|--------------------------:|------------:|-------|
| Compute & Analytics (Fabric + ADF) | ≈173.0 (Fabric 100.0 + ADF 73.0) | ~79% | High (Fabric reservation placeholder) | Real Fabric reserved cost will be much higher than $100/month. |
| DB (SQL)          | 100.0            | 46%                        | High (placeholder) | SQL reservation also modeled as $100/month placeholder. |
| Storage (OneLake ADLS) | 40.96       | 19%                        | 100% estimated | Premium ZRS; only query acceleration meter used. |
| Network (NAT + Public IP) | 40.0     | 18%                        | Low | 4 TB egress via NAT; public IPs missing. Internet egress tiers not modeled. |
| Security (Key Vault) | 1.50          | <1%                        | Low | Premium HSM key costs not modeled. |
| Monitoring (Log Analytics) | 52.00   | 24%                        | Medium | Retention only. |
| Backup (Vault)    | 0.81             | <1%                        | Medium | Only write ops. |
| DR (ASR)          | 64.00            | 29%                        | Low | Per-VM fee only; DR storage/compute not modeled. |
| Other             | 0.00             | 0%                         | – | – |

---

## 4. Resources where pricing failed or is clearly wrong – manual checks

Across all scenarios, you should **manually validate** the following in the Azure Pricing Calculator / official Fabric pricing:

### Fabric capacity (all scenarios)

- **baseline**: `fabric-capacity-f64` – resolved to OneLake Storage Mirroring at $0.024/GB/month.  
  - **Issue**: This is **not** Fabric F64 compute pricing.  
  - **Action**: Use official **Microsoft Fabric Capacity** pricing for **F64** in `westeurope`, with:
    - Pay‑as‑you‑go for baseline and cost_optimized (if truly payg).
    - 1‑year or 3‑year reservation for high_performance.
  - Consider whether you’re using **Power BI Premium per capacity** vs Fabric capacity; pricing differs.

- **cost_optimized**: `fabric-capacity-f64-co` – same issue as above, with “units” scaled to 800 GB/month (proxy for hours).  
- **high_performance**: `fabric-capacity-f64-hp` – mapped to a **reservation meter** with ambiguous UOM and then forced to $100/month.  
  - **Action**: Replace with real **F64 reserved** monthly price (1‑year or 3‑year) and ensure 730 hours/month coverage.

### SQL Database compute

- **baseline**: `sql-source-db` (GP_Gen5_8) – SKU mismatch; mapped via 1‑vCore meter and scaled.
- **cost_optimized**: `sql-source-db-co` (GP_Gen5_4) – same pattern.
- **high_performance**: `sql-source-db-hp` (GP_Gen5_16) – reservation meter with ambiguous UOM, forced to $100/month.

**Actions:**

- Use Azure SQL Database **vCore pricing** for **General Purpose Gen5** in `westeurope`:
  - Baseline: 8 vCores, pay‑as‑you‑go (or reservation if you plan to commit).
  - Cost optimized: 4 vCores, pay‑as‑you‑go.
  - High performance: 16 vCores, **1‑year or 3‑year reserved**.
- Add **storage GB/month** and **backup storage** costs explicitly.

### Public IP Addresses

- **baseline**: `public-ip-nat` – price missing.
- **cost_optimized**: `public-ip-nat-co` – price missing.
- **high_performance**: `public-ip-nat-hp` – price missing.

**Actions:**

- Use **Standard Public IP** pricing in `westeurope`:
  - Per IP per hour (or per month).
  - For high_performance, remember there are **2 IPs**.

### OneLake / ADLS modeling

- All scenarios model OneLake via **ADLS Gen2 “Data Returned for Query Acceleration”** meters only.
- **Actions:**
  - For a more accurate model, include:
    - **Data stored (GB/month)** per tier (hot/cool/archive).
    - **Transactions** (read/write/list).
    - **Geo-replication** (GRS/RA‑GRS/ZRS) multipliers.
  - Validate whether **OneLake pricing** differs from raw ADLS Gen2 in your region.

### Log Analytics

- All scenarios use **Analytics Logs Data Retention** at $0.13/GB/month.
- **Actions:**
  - Add **Data Ingestion** and **Data Analyzed** meters for realistic costs.
  - Confirm retention period (e.g., 30/90/180 days) and archive pricing.

### Backup & ASR

- Backup vault resources only price **write operations**, not **backup storage**.
- ASR resources only price **per-VM protection**, not **replicated storage** or **DR compute**.
- **Actions:**
  - Add **backup storage GB/month** (LRS/GRS) for each protected workload.
  - For ASR, add:
    - **Replica storage** in DR region.
    - **Test failover** compute if you plan regular DR drills.

---

## 5. FinOps recommendations

### 5.1 Quick wins

1. **Fix Fabric F64 pricing first**
   - Fabric capacity will be the **dominant cost driver**.  
   - Decide:
     - **Baseline**: is this truly 24x7 production? If yes, consider **1‑year or 3‑year reservation** for F64.
     - **Cost optimized**: if this is dev/test or pilot, consider:
       - **Smaller capacity (F32/F16)**, or
       - **Turn off capacity outside business hours** (if supported by your operating model).
   - Recalculate TCO once correct F64 prices are in place.

2. **Right-size SQL Database**
   - Baseline GP_Gen5_8 vs cost_optimized GP_Gen5_4 vs high_performance GP_Gen5_16:
     - For **source systems** primarily used for extraction, you may not need high vCore counts 24x7.
     - Consider:
       - **Auto-pause** (if using Azure SQL Database Serverless).
       - **Elastic pools** if you have multiple small DBs.
       - **Reservations** for always-on prod DBs (baseline & high_performance).

3. **Storage redundancy and tiering**
   - Baseline uses **GRS hot** for all 50 TB; cost_optimized uses **LRS with hot+cool**.
   - For production:
     - Evaluate whether **ZRS** or **LRS + ASR/backup** meets your RPO/RTO.
     - Move **cold/historical data** to **cool or archive** tiers in OneLake/ADLS.
   - For dev/test:
     - **LRS only** is usually sufficient.
     - Aggressive **lifecycle policies** to delete stale data.

4. **Log Analytics volume control**
   - High_performance has 400 GB/month; baseline 200 GB; cost_optimized 80 GB.
   - Implement:
     - **Diagnostic settings filters** (only necessary categories).
     - **Shorter retention** for verbose logs; archive only what’s needed for compliance.
     - Use **sampling** for high-volume telemetry.

5. **Key Vault usage**
   - Costs are low, but:
     - Consolidate secrets into **fewer vaults** per environment.
     - Use **managed identities** wherever possible to reduce secret rotation overhead.

### 5.2 Spot vs payg vs reserved

- **Fabric capacity**
  - There is no “spot” for Fabric; the main levers are:
    - **Pay‑as‑you‑go** vs **1‑year / 3‑year reservation**.
    - **Capacity size (F SKU)**.
    - **Hours active per month**.
  - For **baseline & high_performance** (24x7, prod):
    - Strong case for **reservations** if you’re confident in long-term usage.
  - For **cost_optimized** (dev/test, pilot):
    - Prefer **pay‑as‑you‑go** and **smaller SKUs**; avoid long reservations.

- **Azure SQL Database**
  - For always-on prod DBs (baseline & high_performance):
    - Consider **1‑year or 3‑year reserved vCores**.
  - For dev/test (cost_optimized):
    - Use **pay‑as‑you‑go** with **smaller SKUs** or **serverless**.
    - Turn off or scale down outside working hours.

- **NAT, Public IP, Log Analytics, Key Vault, Backup, ASR**
  - These are mostly **consumption-based**; reservations are not typically available or not impactful.
  - Focus on **usage optimization** (egress volume, log volume, backup retention) rather than reservations.

### 5.3 Right-sizing ideas

- **Fabric capacity**
  - Monitor:
    - **Capacity utilization**, refresh queue times, query wait times.
  - If utilization is consistently low:
    - **Downsize** from F64 to F32/F16.
  - If utilization is high and users see slow performance:
    - Consider **scaling up** or **splitting workloads** across capacities (e.g., separate capacity for heavy data engineering).

- **SQL Database**
  - Use **Query Store** and **performance insights** to:
    - Identify if CPU/IO is underutilized → **scale down vCores**.
    - Identify if you can move to **serverless** with auto-pause for dev/test.

- **ADF / Data Pipelines**
  - Optimize:
    - Use **copy parallelism** and **staged copy** wisely.
    - Avoid unnecessary **data movement between regions**.
    - Consolidate small pipelines into **fewer, more efficient runs**.

- **Network egress**
  - Reduce **cross-region** and **internet egress**:
    - Co-locate data sources and Fabric in the **same region** where possible.
    - Use **ExpressRoute** or **VPN** for large on-prem transfers if cost-effective.
    - Cache or stage data in-region before heavy processing.

### 5.4 Region and egress considerations

- All scenarios use **westeurope** (Fabric, storage, SQL, ADF, network).
- **Egress drivers**:
  - Report consumption from users in other regions.
  - Data ingestion from external SaaS or other Azure regions.
  - DR replication (ASR) to paired regions.

Recommendations:

- Keep **Fabric, OneLake, SQL, and ADF** in the **same region** to minimize intra-Azure egress.
- If most users are in a different geography, consider:
  - **Front Door / CDN** for static assets (Power BI embedding scenarios).
  - Or **regional capacities** if latency and egress justify it.
- For DR:
  - Understand that **ASR replication** and **GRS/ZRS** both add cross-region traffic and storage; choose one consistent strategy.

---

## 6. Delta tables vs baseline

Because the JSON marks scenarios as “not comparable” due to SKU mismatches, the deltas below are based on the **scenario totals as given**, but you should treat them as **directional only**.

### 6.1 Overall monthly/yearly totals

I’ll compare:

- **Priced + estimated modeled total** (i.e., `modeled_total`).
- **Total with estimates** (i.e., `total_monthly` / `total_yearly`).

#### Modeled totals (priced + estimated)

| Scenario         | Modeled Monthly | Modeled Yearly | Δ vs Baseline (Monthly) | Δ vs Baseline (Yearly) | Δ% Monthly | Δ% Yearly |
|------------------|----------------:|---------------:|------------------------:|-----------------------:|-----------:|----------:|
| baseline         | 161.56          | 1938.72        | –                       | –                      | –          | –         |
| cost_optimized   | 92.85           | 1114.20        | -68.71                  | -824.52                | -42.5%     | -42.5%    |
| high_performance | 219.46          | 2633.52        | +57.90                  | +694.80                | +35.8%     | +35.8%    |

> These percentages are **not reliable** for TCO decisions because Fabric and SQL are mispriced or missing; they mainly show that the cost_optimized scenario reduces modeled usage, and high_performance increases it.

#### Totals “with estimates” (including missing placeholders)

| Scenario         | Total Monthly (with estimates) | Total Yearly (with estimates) | Δ vs Baseline (Monthly) | Δ vs Baseline (Yearly) | Δ% Monthly | Δ% Yearly |
|------------------|-------------------------------:|------------------------------:|------------------------:|-----------------------:|-----------:|----------:|
| baseline         | 683.79                         | 8205.49                       | –                       | –                      | –          | –         |
| cost_optimized   | 615.08                         | 7380.97                       | -68.71                  | -824.52                | -10.0%     | -10.0%    |
| high_performance | 719.46                         | 8633.52                       | +35.67                  | +428.03                | +5.2%      | +5.2%     |

> Again, these deltas are dominated by **missing/placeholder values** (e.g., $100/month category placeholders for Fabric, public IP, monitoring, backup). Use only after correcting core SKUs.

### 6.2 Category-level monthly deltas vs baseline

Using the **`by_category.monthly_with_estimates`** values.

#### Cost Optimized vs Baseline – monthly by category

| Category              | Baseline Monthly | Cost Opt Monthly | Δ (Abs) | Δ% vs Baseline |
|-----------------------|----------------:|-----------------:|--------:|---------------:|
| analytics.fabric      | 100.00          | 100.00           | 0.00    | 0%             |
| storage.blob          | 40.96           | 71.70            | +30.74  | +75.1%         |
| analytics.datafactory | 73.00           | 16.00            | -57.00  | -78.1%         |
| db.sql                | 122.23          | 122.23           | 0.00    | 0%             |
| network.vnet          | 0.00            | 0.00             | 0.00    | –              |
| network.nat           | 15.00           | 5.00             | -10.00  | -66.7%         |
| network.public_ip     | 100.00          | 100.00           | 0.00    | 0%             |
| security.keyvault     | 0.60            | 0.15             | -0.45   | -75.0%         |
| monitoring.loganalytics | 100.00        | 100.00           | 0.00    | 0%             |
| backup.vault          | 100.00          | 100.00           | 0.00    | 0%             |
| dr.asr                | 32.00           | 0.00             | -32.00  | -100%          |

Interpretation (directional):

- **ADF**: strong reduction (dev/test usage).
- **NAT egress**: reduced (500 GB vs 1500 GB).
- **ASR**: removed entirely.
- **Storage.blob**: appears higher due to different modeling (tiered LRS vs GRS hot); in reality, cost_optimized should be **cheaper** per GB – this is a modeling artifact.

#### High Performance vs Baseline – monthly by category

| Category              | Baseline Monthly | High Perf Monthly | Δ (Abs) | Δ% vs Baseline |
|-----------------------|----------------:|------------------:|--------:|---------------:|
| analytics.fabric      | 100.00          | 100.00            | 0.00    | 0%             |
| storage.blob          | 40.96           | 40.96             | 0.00    | 0%             |
| analytics.datafactory | 73.00           | 73.00             | 0.00    | 0%             |
| db.sql                | 122.23          | 100.00            | -22.23  | -18.2%         |
| network.vnet          | 0.00            | 0.00              | 0.00    | –              |
| network.nat           | 15.00           | 40.00             | +25.00  | +166.7%        |
| network.public_ip     | 100.00          | 100.00            | 0.00    | 0%             |
| security.keyvault     | 0.60            | 1.50              | +0.90   | +150.0%        |
| monitoring.loganalytics | 100.00        | 100.00            | 0.00    | 0%             |
| backup.vault          | 100.00          | 100.00            | 0.00    | 0%             |
| dr.asr                | 32.00           | 64.00             | +32.00  | +100%          |

Interpretation (directional):

- **Network NAT**: significantly higher due to 4 TB egress and 2 gateways.
- **ASR**: doubled protected instances.
- **Key Vault**: slightly higher due to premium tier and more operations.
- **DB**: appears lower due to placeholder modeling; in reality, GP_Gen5_16 reserved will be **more expensive** than GP_Gen5_8 payg.

---

### Final notes

Before using any of these numbers for budgeting or approvals:

1. **Correct Fabric F64 and SQL DB pricing** (payg vs reserved, correct vCores, correct hours).
2. **Add missing public IP, backup storage, and DR storage/compute**.
3. **Refine OneLake/ADLS and Log Analytics** to include storage + transactions + ingestion/analysis.

Once those are fixed, re-run the comparison; the **relative patterns** (cost_optimized cheaper, high_performance more expensive with stronger HA/DR) will hold, but the **absolute values and percentages** will change materially.