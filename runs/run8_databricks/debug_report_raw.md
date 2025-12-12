## 1. Baseline / Recommended – Short Narrative

The baseline is a **Databricks Premium analytics platform** in West Europe with:

- A **Databricks Premium jobs workspace** using ~**1000 DBU/month**, deployed with **VNet injection** for private networking.
- A **jobs cluster approximated as 4× D3_v2 workers + 1 driver**, running ~250 hours/month.
- A **2 TB Blob/ADLS Gen2 data lake (GRS)**, mostly Hot tier, with some Cool for older data.
- **Controlled egress** via a **NAT Gateway** and a Standard Public IP.
- **Security & operations** via **Azure Key Vault** for secrets, **Log Analytics** for monitoring, and **Backup + Azure Site Recovery** for supporting VMs.
- A dedicated **analytics VNet** and private endpoints for Databricks and storage.

This is a **balanced design**: production‑grade security (VNet injection, Key Vault, monitoring, backup/DR) with moderate compute and storage sized for a typical mid‑scale analytics workload.

---

## 2. Other Scenarios – High‑Level Differences

### Cost Optimized

- Keeps **Databricks Premium + VNet injection**, but:
  - **Smaller cluster** (3× D2s_v3 workers + smaller driver).
  - **Fewer hours** (~160 hours/month) and **lower DBU usage (~600 DBU/month)**.
- **Data lake shrinks to 1 TB**, uses **LRS** instead of GRS, and pushes more data to **Cool** tier.
- **Lower NAT egress**, **reduced Log Analytics ingestion**, **smaller backup footprint**, and **no ASR** (DR via redeployment).
- Target: **minimize run‑rate** while keeping core capabilities.

### High Performance

- Still **Databricks Premium + VNet injection**, but:
  - **Larger cluster** (6× D4s_v3 workers + larger driver).
  - **More hours (~400 hours/month)** and **higher DBU usage (~2000 DBU/month)**.
- **5 TB GRS data lake**, mostly Hot, with higher egress and operations.
- **More NAT egress**, **heavier Log Analytics ingestion**, **larger backup footprint**, and **more ASR‑protected instances**.
- Target: **throughput and concurrency** for heavy ETL/ML workloads with stronger DR.

---

## 3. Scenario Details

### 3.1 Baseline Scenario

#### Main Components

- **Compute**
  - Databricks Premium jobs compute (~1000 DBU/month).
  - Jobs cluster approximated as **4× Standard_D3_v2 workers** (VMSS) + **1× Standard_D3_v2 driver**.
- **Data & Storage**
  - **2 TB Blob/ADLS Gen2** (Standard_GRS): 1.5 TB Hot, 0.5 TB Cool.
- **Network**
  - Analytics **VNet** with VNet injection.
  - **Private endpoints** for Databricks and storage (modeled as `dbx-vnet-pe`).
  - **NAT Gateway** + **Standard Public IP** for outbound internet.
- **Security**
  - **Key Vault** for secrets, keys, and Databricks secret scopes.
- **Monitoring & Ops**
  - **Log Analytics** workspace (~200 GB/month ingestion).
  - **Backup vault** for supporting VMs (~250 GB protected).
  - **Azure Site Recovery** for 2 protected instances.

#### Pricing Table – Baseline

> Note: Some rows have **sku_mismatch** or **missing** pricing; those are called out later.

| Scenario  | Resource ID              | Category               | Service          | SKU (requested / resolved)                         | Region     | Billing | Unit Price | Unit              | Units  | Monthly Cost (USD) | Yearly Cost (USD) | Notes |
|-----------|--------------------------|------------------------|------------------|----------------------------------------------------|-----------|---------|-----------:|-------------------|-------:|--------------------:|-------------------:|-------|
| baseline | vnet-analytics           | network.vnet           | Virtual Network  | Virtual Network / Virtual Network                  | westeurope | payg   | 0.00      | VNet (no charge)  | 1     | 0.00               | 0.00              | Logical VNet for Databricks VNet injection & PEs. |
| baseline | databricks-ws-premium    | analytics.databricks   | Azure Databricks | premium / Premium Jobs Compute DBU                | westeurope | payg   | 0.30      | 1 Hour (DBU)      | 730   | 219.00             | 2,628.00          | Premium jobs DBUs; ~1000 DBU/month modeled. |
| baseline | dbx-jobs-cluster-d3v2    | compute.vmss           | Virtual Machines | Standard_D3_v2 / D2als v6 Low Priority (mismatch) | westeurope | payg   | 0.0194    | 1 Hour            | 1,000 | 19.40              | 232.80            | 4× workers, 250 h; price is low‑priority D2als v6, not D3_v2. |
| baseline | dbx-driver-node-d3v2     | compute.vm             | Virtual Machines | Standard_D3_v2 / D2als v6 Low Priority (mismatch) | westeurope | payg   | 0.0194    | 1 Hour            | 250   | 4.85               | 58.20             | Driver node; same mismatch as workers. |
| baseline | datalake-blob            | storage.blob           | Storage          | Standard_GRS / ADLS Gen2 meters (estimated)       | westeurope | payg   | –         | –                 | –     | 2.33               | 27.90             | 2 TB (1.5 TB Hot, 0.5 TB Cool); cost from tiered estimate. |
| baseline | dbx-vnet-pe              | network.gateway        | Virtual Network  | – / – (missing)                                   | westeurope | payg   | –         | –                 | –     | –                  | –                 | Represents private endpoints; pricing missing. |
| baseline | nat-egress               | network.nat            | Bandwidth        | Standard / Standard Inter‑AZ Data Transfer Out    | westeurope | payg   | 0.01      | 1 GB              | 300   | 3.00               | 36.00             | 300 GB/month egress via NAT. |
| baseline | public-ip-nat            | network.public_ip      | Public IP        | Standard / – (missing)                            | westeurope | payg   | –         | –                 | –     | –                  | –                 | Standard Public IP for NAT; pricing missing. |
| baseline | log-analytics            | monitoring.loganalytics| Log Analytics    | PerGB2018 / Analytics Logs Data Retention (mismatch)| westeurope | payg | 0.13      | 1 GB/Month        | 200   | 26.00              | 312.00            | ~200 GB/month retention; ingestion SKU mismatch. |
| baseline | keyvault-main            | security.keyvault      | Key Vault        | standard / Standard Operations                    | westeurope | payg   | 0.03      | 10K operations    | 20    | 0.60               | 7.20              | ~200k operations/month. |
| baseline | backup-vault             | backup.vault           | Backup           | Standard / ADLS Gen2 Vaulted LRS (mismatch)       | westeurope | payg   | 0.054     | 10K operations    | 10    | 0.54               | 6.48              | 250 GB protected; operations‑based estimate. |
| baseline | asr-dr                   | dr.asr                 | Site Recovery    | – / System Center VM Replicated                   | westeurope | payg   | 16.00     | 1/Month per VM    | 2     | 32.00              | 384.00            | 2 protected instances to paired region. |

**Modeled totals (baseline)**

- **Priced (known SKUs)**:  
  - Monthly: **$254.60**  
  - Yearly: **$3,055.20**
- **Estimated (storage)**:  
  - Monthly: **$2.33**  
  - Yearly: **$27.90**
- **Missing (placeholders / catalog gaps)**:  
  - Monthly: **$600.00**  
  - Yearly: **$7,200.00**
- **Total with estimates (what the JSON reports)**:  
  - Monthly: **$856.93**  
  - Yearly: **$10,283.10**

> The “missing” amounts are synthetic placeholders at category level (e.g., 100/month per category) and should not be treated as real prices.

#### Aggregated by Category – Baseline

I’ll map to the requested roll‑up buckets:

- **Compute** = `compute.vm` + `compute.vmss`
- **Analytics (Databricks)** = `analytics.databricks`
- **Storage** = `storage.blob`
- **Network** = `network.vnet` + `network.gateway` + `network.nat` + `network.public_ip`
- **Monitoring** = `monitoring.loganalytics`
- **Security** = `security.keyvault`
- **Backup/DR** = `backup.vault` + `dr.asr`
- **Other** = anything else (none here beyond VNet which is $0)

| Scenario | Category      | Monthly Modeled (USD) | Of which Priced | Of which Estimated | Of which Missing | Est+Missing Share of Category |
|----------|---------------|----------------------:|----------------:|-------------------:|-----------------:|-------------------------------:|
| baseline | Compute       | 200.00               | 0.00            | 0.00               | 200.00           | 100% (placeholder, not real)  |
| baseline | Analytics     | 219.00               | 219.00          | 0.00               | 0.00             | 0%                            |
| baseline | Storage       | 2.33                 | 0.00            | 2.33               | 0.00             | 100% (estimated)              |
| baseline | Network       | 203.00               | 3.00            | 0.00               | 200.00           | ~99% (mostly placeholder)     |
| baseline | Monitoring    | 100.00               | 0.00            | 0.00               | 100.00           | 100% (placeholder)            |
| baseline | Security      | 0.60                 | 0.60            | 0.00               | 0.00             | 0%                            |
| baseline | Backup/DR     | 132.54               | 32.54           | 0.00               | 100.00           | ~75% (placeholder)            |
| baseline | Other         | 0.00                 | 0.00            | 0.00               | 0.00             | 0%                            |

> For FinOps decisions, focus on **Databricks DBUs, VM sizes/hours, data lake volume/tier, NAT egress, Log Analytics ingestion, and ASR coverage**. The 100‑per‑category placeholders must be replaced with real SKUs.

---

### 3.2 Cost Optimized Scenario

#### Main Components

- **Compute**
  - Databricks Premium jobs (~600 DBU/month assumed, but DBU price line is same as baseline).
  - Jobs cluster: **3× Standard_D2s_v3 workers** + **1× smaller driver**, ~160 hours/month.
- **Data & Storage**
  - **1 TB ADLS/Blob**, **LRS**: 0.5 TB Hot, 0.5 TB Cool.
- **Network**
  - Same **VNet + VNet injection**.
  - NAT Gateway + Public IP with **150 GB/month egress**.
- **Security**
  - **Key Vault** retained, fewer operations.
- **Monitoring & Ops**
  - **Log Analytics** with ~100 GB/month.
  - **Backup vault** with smaller footprint.
  - **No ASR** (DR via redeployment).

#### Pricing Table – Cost Optimized

| Scenario       | Resource ID              | Category               | Service          | SKU (requested / resolved)                         | Region     | Billing | Unit Price | Unit              | Units | Monthly Cost (USD) | Yearly Cost (USD) | Notes |
|----------------|--------------------------|------------------------|------------------|----------------------------------------------------|-----------|---------|-----------:|-------------------|------:|--------------------:|-------------------:|-------|
| cost_optimized | vnet-analytics-co       | network.vnet           | Virtual Network  | – / Virtual Network                               | westeurope | payg   | 0.00      | VNet (no charge)  | 1    | 0.00               | 0.00              | Same VNet concept as baseline. |
| cost_optimized | databricks-ws-premium-co| analytics.databricks   | Azure Databricks | premium / Premium Jobs Compute DBU                | westeurope | payg   | 0.30      | 1 Hour (DBU)      | 730  | 219.00             | 2,628.00          | DBU line identical; narrative says ~600 DBU/month. |
| cost_optimized | dbx-jobs-cluster-d2s-co | compute.vmss           | Virtual Machines | Standard_D2s_v3 / D2als v6 Low Priority (mismatch)| westeurope | payg   | 0.0194    | 1 Hour            | 480  | 9.31               | 111.74            | 3× workers, 160 h; low‑priority D2als v6 price. |
| cost_optimized | dbx-driver-node-d2s-co  | compute.vm             | Virtual Machines | Standard_D2s_v3 / EC2adsv6 Low Priority (mismatch)| westeurope | payg   | 0.0351    | 1 Hour            | 160  | 5.62               | 67.39             | Smaller driver; SKU mismatch. |
| cost_optimized | datalake-blob-co        | storage.blob           | Storage          | Standard_LRS / ADLS Gen2 meters (estimated)       | westeurope | payg   | –         | –                 | –    | 1.52               | 18.30             | 1 TB (0.5 TB Hot, 0.5 TB Cool); LRS. |
| cost_optimized | nat-egress-co           | network.nat            | Bandwidth        | Standard / Standard Inter‑AZ Data Transfer Out    | westeurope | payg   | 0.01      | 1 GB              | 150  | 1.50               | 18.00             | 150 GB/month egress. |
| cost_optimized | public-ip-nat-co        | network.public_ip      | Public IP        | Standard / – (missing)                            | westeurope | payg   | –         | –                 | –    | –                  | –                 | Public IP for NAT; pricing missing. |
| cost_optimized | log-analytics-co        | monitoring.loganalytics| Log Analytics    | PerGB2018 / Analytics Logs Data Retention (mismatch)| westeurope | payg | 0.13      | 1 GB/Month        | 100  | 13.00              | 156.00            | ~100 GB/month retention. |
| cost_optimized | keyvault-main-co        | security.keyvault      | Key Vault        | standard / Standard Operations                    | westeurope | payg   | 0.03      | 10K operations    | 10   | 0.30               | 3.60              | ~100k operations/month. |
| cost_optimized | backup-vault-co         | backup.vault           | Backup           | Standard / ADLS Gen2 Vaulted LRS (mismatch)       | westeurope | payg   | 0.054     | 10K operations    | 5    | 0.27               | 3.24              | Smaller backup footprint; no ASR. |

**Modeled totals (cost_optimized)**

- **Priced**:  
  - Monthly: **$220.80**  
  - Yearly: **$2,649.60**
- **Estimated (storage)**:  
  - Monthly: **$1.52**  
  - Yearly: **$18.30**
- **Missing (placeholders)**:  
  - Monthly: **$500.00**  
  - Yearly: **$6,000.00**
- **Total with estimates**:  
  - Monthly: **$722.32**  
  - Yearly: **$8,667.90**

#### Aggregated by Category – Cost Optimized

| Scenario       | Category      | Monthly Modeled (USD) | Of which Priced | Of which Estimated | Of which Missing | Est+Missing Share of Category |
|----------------|---------------|----------------------:|----------------:|-------------------:|-----------------:|-------------------------------:|
| cost_optimized | Compute       | 200.00               | 0.00            | 0.00               | 200.00           | 100% (placeholder)            |
| cost_optimized | Analytics     | 219.00               | 219.00          | 0.00               | 0.00             | 0%                            |
| cost_optimized | Storage       | 1.52                 | 0.00            | 1.52               | 0.00             | 100% (estimated)              |
| cost_optimized | Network       | 201.50               | 1.50            | 0.00               | 200.00           | ~99% (placeholder)            |
| cost_optimized | Monitoring    | 100.00               | 0.00            | 0.00               | 100.00           | 100% (placeholder)            |
| cost_optimized | Security      | 0.30                 | 0.30            | 0.00               | 0.00             | 0%                            |
| cost_optimized | Backup/DR     | 100.27               | 0.27            | 0.00               | 100.00           | ~100% (placeholder)           |
| cost_optimized | Other         | 0.00                 | 0.00            | 0.00               | 0.00             | 0%                            |

---

### 3.3 High Performance Scenario

#### Main Components

- **Compute**
  - Databricks Premium jobs (~2000 DBU/month assumed, but DBU line same as baseline).
  - Jobs cluster: **6× Standard_D4s_v3 workers** + **larger driver**, ~400 hours/month.
- **Data & Storage**
  - **5 TB GRS ADLS/Blob**: 3.5 TB Hot, 1.5 TB Cool.
- **Network**
  - Same **VNet + VNet injection**.
  - NAT Gateway + Public IP with **800 GB/month egress**.
- **Security**
  - **Key Vault** with more secrets and operations.
- **Monitoring & Ops**
  - **Log Analytics** with ~400 GB/month.
  - **Backup vault** with larger footprint.
  - **ASR** for 4 protected instances.

#### Pricing Table – High Performance

| Scenario        | Resource ID              | Category               | Service          | SKU (requested / resolved)                         | Region     | Billing | Unit Price | Unit              | Units | Monthly Cost (USD) | Yearly Cost (USD) | Notes |
|-----------------|--------------------------|------------------------|------------------|----------------------------------------------------|-----------|---------|-----------:|-------------------|------:|--------------------:|-------------------:|-------|
| high_performance| vnet-analytics-hp       | network.vnet           | Virtual Network  | – / Virtual Network                               | westeurope | payg   | 0.00      | VNet (no charge)  | 1    | 0.00               | 0.00              | Same VNet concept. |
| high_performance| databricks-ws-premium-hp| analytics.databricks   | Azure Databricks | premium / Premium Jobs Compute DBU                | westeurope | payg   | 0.30      | 1 Hour (DBU)      | 730  | 219.00             | 2,628.00          | Higher DBU usage in narrative, but same price line. |
| high_performance| dbx-jobs-cluster-d4s-hp | compute.vmss           | Virtual Machines | Standard_D4s_v3 / D2als v6 Low Priority (mismatch)| westeurope | payg   | 0.0194    | 1 Hour            | 2,400| 46.56              | 558.72            | 6× workers, 400 h; SKU mismatch. |
| high_performance| dbx-driver-node-d4s-hp  | compute.vm             | Virtual Machines | Standard_D4s_v3 / EC2adsv6 Low Priority (mismatch)| westeurope | payg   | 0.0351    | 1 Hour            | 400  | 14.04              | 168.48            | Larger driver; SKU mismatch. |
| high_performance| datalake-blob-hp        | storage.blob           | Storage          | Standard_GRS / ADLS Gen2 meters (estimated)       | westeurope | payg   | –         | –                 | –    | 6.17               | 74.10             | 5 TB (3.5 TB Hot, 1.5 TB Cool); GRS. |
| high_performance| nat-egress-hp           | network.nat            | Bandwidth        | Standard / Standard Inter‑AZ Data Transfer Out    | westeurope | payg   | 0.01      | 1 GB              | 800  | 8.00               | 96.00             | 800 GB/month egress. |
| high_performance| public-ip-nat-hp        | network.public_ip      | Public IP        | Standard / – (missing)                            | westeurope | payg   | –         | –                 | –    | –                  | –                 | Public IP for NAT; pricing missing. |
| high_performance| log-analytics-hp        | monitoring.loganalytics| Log Analytics    | PerGB2018 / Analytics Logs Data Retention (mismatch)| westeurope | payg | 0.13      | 1 GB/Month        | 400  | 52.00              | 624.00            | ~400 GB/month retention. |
| high_performance| keyvault-main-hp        | security.keyvault      | Key Vault        | standard / Standard Operations                    | westeurope | payg   | 0.03      | 10K operations    | 40   | 1.20               | 14.40             | ~400k operations/month. |
| high_performance| backup-vault-hp         | backup.vault           | Backup           | Standard / ADLS Gen2 Vaulted LRS (mismatch)       | westeurope | payg   | 0.054     | 10K operations    | 15   | 0.81               | 9.72              | Larger backup footprint. |
| high_performance| asr-dr-hp               | dr.asr                 | Site Recovery    | – / System Center VM Replicated                   | westeurope | payg   | 16.00     | 1/Month per VM    | 4    | 64.00              | 768.00            | 4 protected instances. |

**Modeled totals (high_performance)**

- **Priced**:  
  - Monthly: **$292.20**  
  - Yearly: **$3,506.40**
- **Estimated (storage)**:  
  - Monthly: **$6.17**  
  - Yearly: **$74.10**
- **Missing (placeholders)**:  
  - Monthly: **$500.00**  
  - Yearly: **$6,000.00**
- **Total with estimates**:  
  - Monthly: **$798.37**  
  - Yearly: **$9,580.50**

#### Aggregated by Category – High Performance

| Scenario        | Category      | Monthly Modeled (USD) | Of which Priced | Of which Estimated | Of which Missing | Est+Missing Share of Category |
|-----------------|---------------|----------------------:|----------------:|-------------------:|-----------------:|-------------------------------:|
| high_performance| Compute       | 200.00               | 0.00            | 0.00               | 200.00           | 100% (placeholder)            |
| high_performance| Analytics     | 219.00               | 219.00          | 0.00               | 0.00             | 0%                            |
| high_performance| Storage       | 6.17                 | 0.00            | 6.17               | 0.00             | 100% (estimated)              |
| high_performance| Network       | 208.00               | 8.00            | 0.00               | 200.00           | ~96% (placeholder)            |
| high_performance| Monitoring    | 100.00               | 0.00            | 0.00               | 100.00           | 100% (placeholder)            |
| high_performance| Security      | 1.20                 | 1.20            | 0.00               | 0.00             | 0%                            |
| high_performance| Backup/DR     | 164.81               | 64.81           | 0.00               | 100.00           | ~61% (placeholder)            |
| high_performance| Other         | 0.00                 | 0.00            | 0.00               | 0.00             | 0%                            |

---

## 4. Resources Where Pricing Failed / Needs Manual Check

Across scenarios, **pricing gaps** fall into two buckets:

1. **SKU mismatches** – priced, but not with the requested SKU:
   - **All three scenarios**
     - Databricks **jobs cluster VMs** and **driver VMs**:
       - Requested: `Standard_D3_v2`, `Standard_D2s_v3`, `Standard_D4s_v3`.
       - Resolved: low‑priority **D2als v6** or **EC2adsv6** SKUs.
       - Action: In the Azure Pricing Calculator, select the **exact Databricks worker/driver VM SKUs** (e.g., D3_v2, D4s_v3) and **decide if Spot is acceptable**. Current numbers are **Spot‑like** and understate production cost.
     - **Log Analytics**:
       - Requested: `PerGB2018` ingestion.
       - Resolved: **Analytics Logs Data Retention** meter.
       - Action: Use **Log Analytics > PerGB2018 ingestion** pricing for the **ingested GB/month**, and optionally retention beyond 31 days.
     - **Backup vault**:
       - Resolved to **ADLS Gen2 Vaulted LRS Write Operations**.
       - Action: For VM backup, use **Azure Backup protected instance + backup storage** pricing, not ADLS Gen2 write ops.

2. **Missing pricing** – no SKU found:
   - **Baseline**
     - `dbx-vnet-pe` (network.gateway): private endpoints / VNet injection.
     - `public-ip-nat` (network.public_ip): Standard Public IP.
   - **Cost Optimized**
     - `public-ip-nat-co` (network.public_ip).
   - **High Performance**
     - `public-ip-nat-hp` (network.public_ip).

   **Manual checks:**
   - **Private Endpoints / VNet injection**:
     - Use **Private Endpoint** pricing: per‑hour charge per endpoint + data processing (per GB) where applicable.
     - Count: at least **Databricks workspace**, **control plane**, **storage account** endpoints.
   - **Standard Public IP**:
     - Use **Public IP (Standard)** pricing: per‑hour charge (varies by region) + any outbound data charges (already partly modeled via Bandwidth).

---

## 5. FinOps Recommendations

### 5.1 Quick Wins

1. **Fix VM SKU pricing for Databricks clusters**
   - Replace low‑priority D2als/EC SKUs with **actual D3_v2 / D2s_v3 / D4s_v3** prices.
   - Decide if **Spot** is acceptable for **workers** (not drivers) for non‑critical jobs; if yes, model **Spot discount** explicitly and add **autoscaling + retry**.

2. **Align Databricks DBU lines with actual DBU usage**
   - Currently, all three scenarios show **same DBU cost line** ($219/month).
   - Recalculate:
     - Baseline: **1000 DBU × $0.30 ≈ $300/month** (if 1 DBU = 1 hour).
     - Cost optimized: **600 DBU ≈ $180/month**.
     - High performance: **2000 DBU ≈ $600/month**.
   - This will materially change the cost comparison.

3. **Right‑size Log Analytics**
   - Baseline: 200 GB/month; Cost optimized: 100 GB; High performance: 400 GB.
   - Use:
     - **Dedicated tables** for high‑volume logs.
     - **Sampling / filtering** for verbose Databricks/VM logs.
     - **Shorter retention** in Log Analytics + **archive to Blob** for long‑term audit.

4. **Data lake tiering**
   - Baseline: 1.5 TB Hot, 0.5 TB Cool.
   - Cost optimized: pushes more to Cool; High performance: 3.5 TB Hot.
   - For all:
     - Move **cold partitions** to **Cool or Archive**.
     - Use **lifecycle policies** on ADLS Gen2.

5. **NAT egress control**
   - Validate that **egress GB** is realistic:
     - Prefer **in‑region consumers** (e.g., Power BI in same region, Synapse in same region).
     - Avoid unnecessary **cross‑region** or **internet** egress (e.g., S3, on‑prem) where possible.

### 5.2 Spot vs Pay‑As‑You‑Go vs Reserved

- **Databricks DBUs**:
  - DBUs are **consumption‑based**; you can’t reserve DBUs directly, but you can:
    - Use **Databricks commit units / pre‑purchase** (if available in your contract).
    - Optimize **cluster auto‑termination** and **job scheduling** to reduce idle DBUs.

- **VMs (Databricks workers/drivers)**:
  - For **production jobs**:
    - Use **Pay‑As‑You‑Go** for elasticity.
    - Consider **1‑year Reserved Instances** for **baseline capacity** if you have predictable minimum cluster size (e.g., always at least 2 workers).
  - For **non‑critical / dev / test**:
    - Use **Spot VMs** for workers with **max spot price** and **autoscaling**.
    - Keep **drivers on regular PAYG** for stability.

- **NAT Gateway / Public IP / supporting VMs**:
  - NAT and Public IP are small; reservations not applicable.
  - Any **supporting VMs** (jumpboxes, gateways) could be **1‑year reserved** if always on.

**Reservation coverage vs PAYG exposure** (conceptual):

- **Good candidates for reservation**:
  - Always‑on **supporting VMs** (if any).
  - **Baseline Databricks worker capacity** if you run jobs daily and cluster is rarely at zero.
- **Keep PAYG**:
  - **Burst capacity** for high‑performance scenario.
  - **Cost‑optimized** scenario where hours are low and intermittent.

### 5.3 Right‑Sizing Ideas

- **Baseline → Cost Optimized**
  - Reduce **cluster size** and **hours**:
    - Move from 4× D3_v2 to 3× D2s_v3 and from 250 to 160 hours.
    - Use **autoscaling** and **job cluster** patterns (per‑job ephemeral clusters) to avoid idle time.
  - Reduce **Log Analytics ingestion** by:
    - Disabling verbose categories (e.g., debug logs).
    - Using **sampling** for high‑volume telemetry.

- **Baseline → High Performance**
  - If you need more throughput:
    - Prefer **fewer, larger nodes** vs many small nodes where it improves shuffle performance.
    - Use **Photon** (Premium Jobs Compute Photon DBU) where supported to reduce DBUs for the same workload.

- **Key Vault**
  - Operations are cheap, but:
    - Use **managed identities** instead of secrets where possible to reduce secret rotation overhead.
    - Consolidate secrets into fewer vaults per environment.

### 5.4 Region and Egress Considerations

- All scenarios are in **West Europe**:
  - Keep **data consumers** (Power BI, Synapse, downstream apps) in **West Europe** to avoid **inter‑region egress**.
  - If you must serve other regions:
    - Consider **Front Door / CDN** for static content.
    - For analytics, consider **regional data marts** to avoid repeated cross‑region reads.

- **On‑prem connectivity**:
  - If you later add **ExpressRoute / VPN**, model:
    - **Gateway SKUs** (VpnGw / ER Gateway).
    - **Data transfer** over ExpressRoute (cheaper than internet egress but not free).

- **GRS vs LRS**:
  - Baseline and High performance use **GRS**; Cost optimized uses **LRS**.
  - If you have **formal RPO/RTO** requirements, GRS or RA‑GRS may be mandatory; otherwise, LRS + **backup/ASR** may be sufficient and cheaper.

---

## 6. Delta Tables vs Baseline

Because the JSON flags scenarios as “not_comparable” due to SKU mismatches, treat these deltas as **approximate** and focused on **modeled totals**, not the placeholder “missing” buckets.

### 6.1 Overall Monthly / Yearly Totals

Using the JSON’s **“modeled_total”** (priced + estimated, excluding synthetic missing) and **“monthly_with_estimates”** (including missing):

#### Modeled Totals (Priced + Estimated Only)

| Scenario        | Monthly Modeled (USD) | Yearly Modeled (USD) |
|-----------------|----------------------:|----------------------:|
| baseline        | 256.93               | 3,083.10             |
| cost_optimized  | 222.32               | 2,667.90             |
| high_performance| 298.37               | 3,580.50             |

**Deltas vs Baseline (Modeled)**

| Scenario        | Δ Monthly (USD) | Δ Monthly % | Δ Yearly (USD) | Δ Yearly % |
|-----------------|----------------:|------------:|----------------:|-----------:|
| cost_optimized  | -34.61          | -13.5%      | -415.20         | -13.5%     |
| high_performance| +41.44          | +16.1%      | +497.40         | +16.1%     |

#### Totals Including Placeholders (“with estimates”)

| Scenario        | Monthly w/ Estimates (USD) | Yearly w/ Estimates (USD) |
|-----------------|---------------------------:|---------------------------:|
| baseline        | 856.93                    | 10,283.10                 |
| cost_optimized  | 722.32                    | 8,667.90                  |
| high_performance| 798.37                    | 9,580.50                  |

**Deltas vs Baseline (w/ Estimates)**

| Scenario        | Δ Monthly (USD) | Δ Monthly % | Δ Yearly (USD) | Δ Yearly % |
|-----------------|----------------:|------------:|----------------:|-----------:|
| cost_optimized  | -134.61         | -15.7%      | -1,615.20       | -15.7%     |
| high_performance| -58.56          | -6.8%       | -702.60         | -6.8%      |

> These %s are dominated by the **synthetic 100/month per category** placeholders; once you replace them with real prices, the relative differences will be driven mainly by **DBUs, VM hours, data lake size, Log Analytics, and ASR**.

### 6.2 Category‑Level Monthly Deltas vs Baseline

Using **modeled category totals** (including placeholders, as per JSON):

#### Cost Optimized vs Baseline – Monthly by Category

| Category    | Baseline (USD) | Cost Opt (USD) | Δ (USD) | Δ %      |
|------------|----------------:|---------------:|--------:|---------:|
| Compute    | 200.00          | 200.00         | 0.00    | 0%       |
| Analytics  | 219.00          | 219.00         | 0.00    | 0%       |
| Storage    | 2.33            | 1.52           | -0.81   | -34.8%   |
| Network    | 203.00          | 201.50         | -1.50   | -0.7%    |
| Monitoring | 100.00          | 100.00         | 0.00    | 0%       |
| Security   | 0.60            | 0.30           | -0.30   | -50.0%   |
| Backup/DR  | 132.54          | 100.27         | -32.27  | -24.3%   |
| Other      | 0.00            | 0.00           | 0.00    | 0%       |

Interpretation (ignoring placeholders):

- **Storage**: ~35% lower due to **smaller, LRS data lake** and more Cool tier.
- **Network**: Slightly lower due to **reduced egress**.
- **Security**: Lower Key Vault ops.
- **Backup/DR**: Lower because **ASR removed** and smaller backup footprint.

#### High Performance vs Baseline – Monthly by Category

| Category    | Baseline (USD) | High Perf (USD) | Δ (USD) | Δ %      |
|------------|----------------:|----------------:|--------:|---------:|
| Compute    | 200.00          | 200.00          | 0.00    | 0%       |
| Analytics  | 219.00          | 219.00          | 0.00    | 0%       |
| Storage    | 2.33            | 6.17            | +3.84   | +164.8%  |
| Network    | 203.00          | 208.00          | +5.00   | +2.5%    |
| Monitoring | 100.00          | 100.00          | 0.00    | 0%       |
| Security   | 0.60            | 1.20            | +0.60   | +100.0%  |
| Backup/DR  | 132.54          | 164.81          | +32.27  | +24.3%   |
| Other      | 0.00            | 0.00            | 0.00    | 0%       |

Interpretation (ignoring placeholders):

- **Storage**: ~2.6× higher due to **5 TB GRS** and more Hot data.
- **Network**: Higher due to **800 GB egress**.
- **Security**: More Key Vault operations.
- **Backup/DR**: Higher due to **more ASR‑protected instances** and larger backup footprint.

---

### Final Notes

- The **architecture** across all scenarios is sound: Databricks Premium with VNet injection, ADLS data lake, Key Vault, Log Analytics, Backup/ASR, and controlled egress via NAT.
- For **accurate FinOps**:
  - Replace **placeholder category costs** with real SKUs.
  - Correct **VM SKUs**, **DBU volumes**, **Log Analytics ingestion**, and **Private Endpoint/Public IP** pricing.
- Once corrected, you’ll have a reliable basis to choose between:
  - **Cost optimized**: lower DBUs, smaller cluster, smaller data lake, no ASR.
  - **Baseline**: balanced cost vs resiliency.
  - **High performance**: higher DBUs, larger cluster, larger GRS data lake, stronger DR and monitoring.