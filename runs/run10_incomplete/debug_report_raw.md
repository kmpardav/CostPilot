## 1. Baseline / Recommended – Short Narrative

The baseline design does two things:

1. **Protect 500 legacy/on‑prem/VM servers** using the Azure Backup **MARS agent** into a single Recovery Services vault in West Europe.  
   - Assumes ~400 GB protected per server with ~30‑day retention (~200 TB effective backup).  
   - Uses **LRS backup storage** (no cross‑region DR in this baseline).  
   - Backup operations and reporting are monitored via **Log Analytics**.  
   - **Key Vault** holds backup credentials, certificates, and secrets.

2. **Run a specialized ND96asr_v4 GPU VM** (in East US as a stand‑in for a “rare” supported region) for AI training/inference.  
   - Full‑time usage (730 h/month) assumed.  
   - Attached Premium‑class OS and data disks (modeled but with SKU mismatches in the pricing data).  
   - ~2 TB/month outbound traffic for model/data transfer.  
   - GPU VM and backup workloads are monitored centrally via Log Analytics; secrets are stored in Key Vault.

This gives you a **production‑grade but not extreme** setup: reasonable backup retention, a powerful always‑on GPU, standard monitoring and secrets management, but without cross‑region backup DR or extreme performance tuning.

---

## 2. Other Scenarios – How They Differ

### Cost Optimized

- **Same 500 MARS servers**, but:
  - **Shorter backup retention / less data** (~80 TB vs 200 TB), lowering vault storage and operations.
  - **Smaller Log Analytics footprint** (~200 GB/month vs 500 GB).
  - **Lower Key Vault operation volume**.
- **Same ND96asr_v4 GPU SKU**, but:
  - **Part‑time usage (~160 h/month)** instead of 24x7.
  - **Lower egress (~500 GB/month)**.
  - **Smaller/cheaper disks** (smaller OS disk, Standard SSD data disk).
- Net effect: **lower OpEx** at the cost of **less retention, less observability, and lower IO performance**.

### High Performance / High Resilience

- **Same 500 MARS servers**, but:
  - **Longer retention and more data** (~300 TB vs 200 TB) and **GRS‑like posture** (modeled via higher operations; actual GRS storage pricing not captured in the catalog row).
  - **Larger Log Analytics ingestion** (~800 GB/month) and likely longer retention.
  - **Premium Key Vault** for HSM‑backed keys and higher security.
- **GPU side**:
  - **Two ND96asr_v4 VMs running 24x7** (2× the GPU capacity).
  - **Much larger and more numerous Premium SSD disks**.
  - **Higher egress (~5 TB/month)**.
- Net effect: **maximum performance and resilience**, with **significantly higher cost** and more exposure to GPU and storage spend.

---

## 3. Scenario Details

### 3.1 Baseline Scenario

#### Main Components (Baseline)

- **Compute**
  - 1× ND96asr_v4 GPU VM (East US, Linux, 24x7) – price missing in catalog.
- **Data / Storage**
  - Recovery Services vault (Backup) with ~200 TB effective MARS backup data (LRS).
  - Premium SSD OS and data disks for GPU VM (modeled as Premium_LRS, but priced as ADLS Gen2 “Hot LRS” – SKU mismatch).
- **Network**
  - ~2 TB/month outbound egress from GPU VM.
- **Security**
  - 1× Azure Key Vault (Standard) for backup and GPU secrets.
- **Monitoring / Ops**
  - 1× Log Analytics workspace (~500 GB/month ingestion/retention) for backup and GPU monitoring.
- **Backup / DR**
  - 500 servers protected via MARS agent into a single Recovery Services vault.
  - No explicit Azure Site Recovery or cross‑region backup vault in this baseline.

#### Pricing Table – Baseline

> Note: “Requested / Resolved” shows what you architecturally asked for vs what the local catalog row actually represents. Rows with `pricing_status = missing` need manual pricing.

| Scenario | Resource ID             | Category              | Service        | SKU (requested / resolved)                         | Region       | Billing | Unit Price | Unit    | Units  | Monthly Cost (USD) | Yearly Cost (USD) | Notes |
|----------|-------------------------|-----------------------|---------------|----------------------------------------------------|-------------|--------|-----------|---------|--------|--------------------|-------------------|-------|
| baseline | backup-vault-mars      | backup.vault          | Backup        | (Vaulted LRS backup) / ADLS Gen2 Vaulted LRS Write Ops | westeurope  | PAYG   | 0.054     | per 10K ops | 200    | 10.80              | 129.60            | Models write operations cost only; backup storage GB cost not captured in this row. |
| baseline | mars-protected-servers | other                 | Backup        | MARS protected instances / (missing)              | westeurope  | PAYG   | –         | –       | –      | –                  | –                 | **Missing**: per‑instance MARS pricing tiers not in local catalog. |
| baseline | gpu-vm-nd96asr         | compute.vm            | Virtual Machines | Standard_ND96asr_v4 / (missing)                 | eastus      | PAYG   | –         | –       | –      | –                  | –                 | **Missing**: ND96asr_v4 PAYG rate; check Azure Pricing Calculator. |
| baseline | gpu-vm-osdisk          | storage.disk          | Storage       | Premium_LRS / Hot LRS (ADLS Gen2)                 | eastus      | PAYG   | 0.0007    | per GB  | 512    | 0.36               | 4.30              | **SKU mismatch**: should be Managed Disk Premium SSD, not ADLS Gen2. Treat as placeholder. |
| baseline | gpu-vm-datadisk        | storage.disk          | Storage       | Premium_LRS / Hot LRS (ADLS Gen2)                 | eastus      | PAYG   | 0.0007    | per GB  | 2048   | 1.43               | 17.20             | **SKU mismatch**: should be Managed Disk Premium SSD, not ADLS Gen2. |
| baseline | gpu-vm-egress          | network.egress        | Bandwidth     | Internet egress / Standard Inter‑AZ Data Transfer Out | eastus  | PAYG   | 0.01      | per GB  | 2000   | 20.00              | 240.00            | Approximates 2 TB/month outbound; actual internet egress tiered pricing may differ. |
| baseline | log-analytics-backup   | monitoring.loganalytics | Log Analytics | Analytics Logs / Analytics Logs Data Retention   | westeurope  | PAYG   | 0.13      | per GB‑month | 500 | 65.00              | 780.00            | Models retention cost for ~500 GB; ingestion/analyzed meters not priced here. |
| baseline | keyvault-backup-gpu    | security.keyvault     | Key Vault     | Standard / Standard Operations                    | westeurope  | PAYG   | 0.03      | per 10K ops | 20  | 0.60               | 7.20              | ~200k operations/month; excludes advanced key/HSM charges. |

#### Aggregated by Category – Baseline

> “Estimate ratio” = `missing_total / total_monthly_with_estimates` (how much of the modeled total is unpriced/missing).

| Category            | Monthly (USD) | Yearly (USD) | Priced Monthly | Missing Monthly | Monthly w/ Estimates | Estimate Ratio |
|---------------------|--------------|--------------|----------------|-----------------|----------------------|----------------|
| backup/dr (backup.vault) | 10.8         | 129.6       | 10.8           | 0.0             | 10.8                 | 0%             |
| other (MARS instances)   | 100.0        | 1200.0      | 0.0            | 100.0           | 100.0                | 100%           |
| compute               | 100.0        | 1200.0      | 0.0            | 100.0           | 100.0                | 100%           |
| storage               | 200.0        | 2400.0      | 1.79 (disks)   | 198.21          | 200.0                | ~99%           |
| network               | 20.0         | 240.0       | 20.0           | 0.0             | 20.0                 | 0%             |
| monitoring (Log Analytics) | 65.0     | 780.0       | 65.0           | 0.0             | 65.0                 | 0%             |
| security (Key Vault) | 0.6          | 7.2         | 0.6            | 0.0             | 0.6                  | 0%             |
| **Total**            | **496.4**    | **5956.8**  | **96.4**       | **400.0**       | **496.4**            | **~81% missing** |

> Interpretation: The **majority of the baseline cost is unpriced/missing** (GPU VM, MARS per‑instance, and correct disk SKUs). The priced portion is dominated by **Log Analytics and network egress**.

---

### 3.2 Cost Optimized Scenario

#### Main Components (Cost Optimized)

- **Compute**
  - Same ND96asr_v4 GPU VM, but **~160 h/month** instead of 730 h (price missing).
- **Data / Storage**
  - Recovery Services vault with **shorter retention / less data (~80 TB)**.
  - Smaller OS disk (256 GB Premium) and **1× Standard SSD 1 TB** data disk (modeled with ADLS Gen2 pricing – mismatch).
- **Network**
  - **~500 GB/month egress** from GPU VM.
- **Security**
  - 1× Key Vault (Standard) with **reduced operations** (~100k/month).
- **Monitoring / Ops**
  - Log Analytics workspace with **~200 GB/month** ingestion/retention.
- **Backup / DR**
  - Same 500 MARS servers; cost reduction is via **retention and storage**, not fewer instances.

#### Pricing Table – Cost Optimized

| Scenario       | Resource ID             | Category              | Service        | SKU (requested / resolved)                         | Region       | Billing | Unit Price | Unit    | Units  | Monthly Cost (USD) | Yearly Cost (USD) | Notes |
|----------------|-------------------------|-----------------------|---------------|----------------------------------------------------|-------------|--------|-----------|---------|--------|--------------------|-------------------|-------|
| cost_optimized | backup-vault-mars-co   | backup.vault          | Backup        | (Vaulted LRS backup) / ADLS Gen2 Vaulted LRS Write Ops | westeurope | PAYG   | 0.054     | per 10K ops | 100 | 5.40               | 64.80             | Fewer backup operations due to less data/retention; storage GB cost not captured here. |
| cost_optimized | mars-protected-servers-co | other              | Backup        | MARS protected instances / (missing)              | westeurope  | PAYG   | –         | –       | –      | –                  | –                 | **Missing**: per‑instance MARS pricing. |
| cost_optimized | gpu-vm-nd96asr-co      | compute.vm            | Virtual Machines | Standard_ND96asr_v4 / (missing)                 | eastus      | PAYG   | –         | –       | –      | –                  | –                 | **Missing**: ND96asr_v4 PAYG rate; usage ~160 h/month. |
| cost_optimized | gpu-vm-osdisk-co       | storage.disk          | Storage       | Premium_LRS / Hot LRS (ADLS Gen2)                 | eastus      | PAYG   | 0.0007    | per GB  | 256    | 0.18               | 2.15              | **SKU mismatch**: should be Managed Disk Premium SSD. |
| cost_optimized | gpu-vm-datadisk-co     | storage.disk          | Storage       | StandardSSD_LRS / Hot LRS (ADLS Gen2)             | eastus      | PAYG   | 0.0007    | per GB  | 1024   | 0.72               | 8.60              | **SKU mismatch**: should be Managed Disk Standard SSD. |
| cost_optimized | gpu-vm-egress-co       | network.egress        | Bandwidth     | Internet egress / Standard Inter‑AZ Data Transfer Out | eastus  | PAYG   | 0.01      | per GB  | 500    | 5.00               | 60.00             | ~500 GB/month outbound. |
| cost_optimized | log-analytics-co       | monitoring.loganalytics | Log Analytics | Analytics Logs / Analytics Logs Data Retention   | westeurope  | PAYG   | 0.13      | per GB‑month | 200 | 26.00              | 312.00            | Reduced ingestion/retention vs baseline. |
| cost_optimized | keyvault-co            | security.keyvault     | Key Vault     | Standard / Standard Operations                    | westeurope  | PAYG   | 0.03      | per 10K ops | 10 | 0.30               | 3.60              | ~100k operations/month. |

#### Aggregated by Category – Cost Optimized

| Category            | Monthly (USD) | Yearly (USD) | Priced Monthly | Missing Monthly | Monthly w/ Estimates | Estimate Ratio |
|---------------------|--------------|--------------|----------------|-----------------|----------------------|----------------|
| backup/dr (backup.vault) | 5.4          | 64.8        | 5.4            | 0.0             | 5.4                  | 0%             |
| other (MARS instances)   | 100.0        | 1200.0      | 0.0            | 100.0           | 100.0                | 100%           |
| compute               | 100.0        | 1200.0      | 0.0            | 100.0           | 100.0                | 100%           |
| storage               | 200.0        | 2400.0      | 0.90           | 199.10          | 200.0                | ~99%           |
| network               | 5.0          | 60.0        | 5.0            | 0.0             | 5.0                  | 0%             |
| monitoring (Log Analytics) | 26.0     | 312.0       | 26.0           | 0.0             | 26.0                 | 0%             |
| security (Key Vault) | 0.3          | 3.6         | 0.3            | 0.0             | 0.3                  | 0%             |
| **Total**            | **436.7**    | **5240.4**  | **36.7**       | **400.0**       | **436.7**            | **~92% missing** |

> The **cost‑optimized scenario reduces priced components** (backup vault, egress, Log Analytics, Key Vault) but still has the same large unpriced block (GPU, MARS, disks).

---

### 3.3 High Performance / High Resilience Scenario

#### Main Components (High Performance)

- **Compute**
  - **2× ND96asr_v4 GPU VMs**, 24x7 (price missing).
- **Data / Storage**
  - Recovery Services vault with **higher retention (~300 TB)** and **GRS‑like resilience** (actual GRS storage pricing not reflected in the catalog row).
  - Larger and more numerous **Premium SSD OS and data disks** (modeled with ADLS Gen2 pricing – mismatch).
- **Network**
  - **~5 TB/month egress** from GPU workloads.
- **Security**
  - **Premium Key Vault** with higher operations and HSM‑backed keys.
- **Monitoring / Ops**
  - Log Analytics with **~800 GB/month** ingestion/retention.
- **Backup / DR**
  - Same 500 MARS servers, but with **longer retention and geo‑resilient posture**.

#### Pricing Table – High Performance

| Scenario        | Resource ID             | Category              | Service        | SKU (requested / resolved)                         | Region       | Billing | Unit Price | Unit    | Units  | Monthly Cost (USD) | Yearly Cost (USD) | Notes |
|-----------------|-------------------------|-----------------------|---------------|----------------------------------------------------|-------------|--------|-----------|---------|--------|--------------------|-------------------|-------|
| high_performance | backup-vault-mars-hp  | backup.vault          | Backup        | (Vaulted GRS backup) / ADLS Gen2 Vaulted LRS Write Ops | westeurope | PAYG | 0.054 | per 10K ops | 300 | 16.20 | 194.40 | Models higher write ops; actual GRS backup storage GB pricing not captured. |
| high_performance | mars-protected-servers-hp | other              | Backup        | MARS protected instances / (missing)              | westeurope  | PAYG   | –         | –       | –      | –                  | –                 | **Missing**: per‑instance MARS pricing. |
| high_performance | gpu-vm-nd96asr-hp     | compute.vm            | Virtual Machines | 2× Standard_ND96asr_v4 / (missing)              | eastus      | PAYG   | –         | –       | –      | –                  | –                 | **Missing**: ND96asr_v4 PAYG rate; 2 VMs × 730 h/month. |
| high_performance | gpu-vm-osdisk-hp      | storage.disk          | Storage       | Premium_LRS / Hot LRS (ADLS Gen2)                 | eastus      | PAYG   | 0.0007    | per GB  | 1024   | 0.72               | 8.60              | **SKU mismatch**: should be Managed Disk Premium SSD (2× 1 TB OS). |
| high_performance | gpu-vm-datadisk-hp    | storage.disk          | Storage       | Premium_LRS / Hot LRS (ADLS Gen2)                 | eastus      | PAYG   | 0.0007    | per GB  | 8192   | 5.73               | 68.81             | **SKU mismatch**: should be 4× 2 TB Premium SSD data disks. |
| high_performance | gpu-vm-egress-hp      | network.egress        | Bandwidth     | Internet egress / Standard Inter‑AZ Data Transfer Out | eastus  | PAYG   | 0.01      | per GB  | 5000   | 50.00              | 600.00            | ~5 TB/month outbound. |
| high_performance | log-analytics-hp      | monitoring.loganalytics | Log Analytics | Analytics Logs / Analytics Logs Data Retention   | westeurope  | PAYG   | 0.13      | per GB‑month | 800 | 104.00             | 1248.00           | Higher ingestion/retention for detailed monitoring. |
| high_performance | keyvault-hp           | security.keyvault     | Key Vault     | Premium / Premium Operations                      | westeurope  | PAYG   | 0.03      | per 10K ops | 40 | 1.20               | 14.40             | Premium tier; HSM and advanced operations may add extra meters. |

#### Aggregated by Category – High Performance

| Category            | Monthly (USD) | Yearly (USD) | Priced Monthly | Missing Monthly | Monthly w/ Estimates | Estimate Ratio |
|---------------------|--------------|--------------|----------------|-----------------|----------------------|----------------|
| backup/dr (backup.vault) | 16.2         | 194.4       | 16.2           | 0.0             | 16.2                 | 0%             |
| other (MARS instances)   | 100.0        | 1200.0      | 0.0            | 100.0           | 100.0                | 100%           |
| compute               | 100.0        | 1200.0      | 0.0            | 100.0           | 100.0                | 100%           |
| storage               | 200.0        | 2400.0      | 6.45           | 193.55          | 200.0                | ~97%           |
| network               | 50.0         | 600.0       | 50.0           | 0.0             | 50.0                 | 0%             |
| monitoring (Log Analytics) | 104.0    | 1248.0      | 104.0          | 0.0             | 104.0                | 0%             |
| security (Key Vault) | 1.2          | 14.4        | 1.2            | 0.0             | 1.2                  | 0%             |
| **Total**            | **571.4**    | **6856.8**  | **171.4**      | **400.0**       | **571.4**            | **~70% missing** |

> High‑performance scenario **increases priced components** (backup ops, egress, Log Analytics, Key Vault) and still has the same large unpriced block (GPU, MARS, disks).

---

## 4. Resources Where Pricing Failed – Manual Checks

Across all scenarios, the following need **manual pricing in the Azure Pricing Calculator** or via the official price sheet:

1. **MARS protected instances (all scenarios)**  
   - IDs: `mars-protected-servers`, `mars-protected-servers-co`, `mars-protected-servers-hp`.  
   - What to check:
     - Azure Backup “MARS agent / Azure Backup Agent” pricing.  
     - Tiered per‑instance pricing by protected size (e.g., 0–50 GB, 50–500 GB, >500 GB).  
     - Multiply by 500 servers and your actual average protected size.

2. **ND96asr_v4 GPU VM (all scenarios)**  
   - IDs: `gpu-vm-nd96asr`, `gpu-vm-nd96asr-co`, `gpu-vm-nd96asr-hp`.  
   - What to check:
     - Region‑specific PAYG price for **Standard_ND96asr_v4** in your actual region (East US is a placeholder).  
     - Hours per month:
       - Baseline: ~730 h/month, 1 VM.  
       - Cost optimized: ~160 h/month, 1 VM.  
       - High performance: ~730 h/month, 2 VMs.  
     - Consider **Reserved Instances** or **Savings Plan** if utilization is high.

3. **Managed Disks for GPU VMs (all scenarios)**  
   - IDs with SKU mismatch:  
     - Baseline: `gpu-vm-osdisk`, `gpu-vm-datadisk`.  
     - Cost optimized: `gpu-vm-osdisk-co`, `gpu-vm-datadisk-co`.  
     - High performance: `gpu-vm-osdisk-hp`, `gpu-vm-datadisk-hp`.  
   - What to check:
     - Use **Azure Managed Disks** pricing, not ADLS Gen2.  
     - Map sizes to disk SKUs:
       - 256 GB / 512 GB / 1 TB / 2 TB → appropriate **Premium SSD** or **Standard SSD** disk sizes (P10/P20/P30/P40/P50 etc.).  
     - Include both **capacity** and **transaction** costs if relevant.

4. **Backup storage GB and GRS uplift**  
   - The current rows only price **write operations**, not **backup storage GB**.  
   - What to check:
     - Azure Backup vault storage pricing for **LRS vs GRS**.  
     - Approximate total stored TB per scenario:
       - Cost optimized: ~80 TB.  
       - Baseline: ~200 TB.  
       - High performance: ~300 TB (and likely GRS).  
     - Apply correct per‑GB‑month rates.

5. **Log Analytics ingestion vs retention**  
   - Current rows use **Data Retention** meter at $0.13/GB‑month.  
   - What to check:
     - **Data ingestion** pricing (per GB) and any **commitment tiers** you might use.  
     - Retention beyond the free/default period.

6. **Key Vault Premium HSM costs (high performance)**  
   - ID: `keyvault-hp`.  
   - What to check:
     - Premium Key Vault has **HSM key** and **HSM operation** meters that may not be fully represented by the generic “Operations” meter.

---

## 5. FinOps Recommendations

### 5.1 Quick Wins

1. **Right‑size Log Analytics ingestion and retention**
   - Baseline: 500 GB/month; High performance: 800 GB/month.  
   - Use **data collection rules** to:
     - Filter noisy logs (e.g., verbose diagnostics you never query).  
     - Route some logs to **storage account (cheaper)** instead of Log Analytics if rarely queried.  
   - Consider **commitment tiers** if ingestion is stable and high.

2. **Tune backup retention policies**
   - Cost optimized scenario shows how much you can save by reducing retention from 30+ days to 7–14 days.  
   - For non‑critical workloads, consider:
     - Shorter daily retention.  
     - Fewer long‑term copies (e.g., monthly instead of weekly).  
   - For long‑term compliance, consider **archive tier** or **Azure Backup for Azure Files/Blob** where appropriate.

3. **GPU utilization discipline**
   - For ND96asr_v4:
     - Use **automation** (Runbooks, Functions, DevOps pipelines) to **start/stop** VMs around training windows.  
     - For experimentation, consider **smaller GPU SKUs** or **Azure ML managed compute** with auto‑scale.

4. **Disk right‑sizing**
   - Validate whether you truly need:
     - Multiple Premium SSD data disks (baseline/high‑perf).  
     - 1 TB OS disks (high‑perf).  
   - For workloads that are **compute‑bound**, move to **Standard SSD** or smaller Premium disks.

5. **Network egress hygiene**
   - Egress grows from 0.5–5 TB/month across scenarios.  
   - Where possible:
     - Keep data processing **in‑region**.  
     - Use **ExpressRoute** or **peering** for predictable costs if you have large on‑prem data flows.  
     - Cache models/datasets closer to consumers to avoid repeated large downloads.

### 5.2 Spot vs PAYG vs Reserved

- **ND96asr_v4 GPU VMs**
  - **PAYG** is flexible but expensive; good for:
    - Cost‑optimized scenario (160 h/month) if usage is bursty and unpredictable.  
  - **Reserved Instances / Savings Plan**:
    - Baseline (730 h/month, 1 VM) and high‑performance (730 h/month, 2 VMs) are **excellent candidates** for 1‑ or 3‑year reservations or a **Compute Savings Plan**.  
    - Expect **30–60%+ savings** vs PAYG if utilization is high and stable.
  - **Spot VMs**:
    - ND‑series spot availability is limited and can be evicted.  
    - Only use for **non‑critical, checkpointed training** where interruptions are acceptable.

- **Managed Disks**
  - No reservations, but:
    - Right‑size disk SKUs and avoid over‑provisioning capacity.  
    - Consider **Ultra Disk** only if you truly need extreme IOPS/throughput.

- **Log Analytics**
  - Consider **commitment tiers** if you have predictable ingestion (e.g., 200/500/800 GB per month).  
  - This can reduce per‑GB cost vs pure PAYG.

### 5.3 Right‑Sizing Ideas

- **Backup**
  - Segment workloads by criticality:
    - Tier 1: longer retention, GRS.  
    - Tier 2/3: shorter retention, LRS only.  
  - Don’t apply “high‑performance” retention to all 500 servers by default.

- **GPU**
  - For experimentation:
    - Use **smaller ND or NC SKUs** or **fractional GPU** offerings where available.  
  - For production:
    - Profile actual GPU utilization; if consistently <50%, consider:
      - Smaller SKU.  
      - Time‑slicing workloads on fewer VMs.

- **Disks**
  - Use **disk metrics** (IOPS, throughput, latency) from Log Analytics / Azure Monitor:
    - If actual IOPS << provisioned, downsize disk tier.  
    - If throughput is the bottleneck, consider **striping multiple smaller disks** vs one large.

### 5.4 Region and Egress Considerations

- **Region choice for ND96asr_v4**
  - ND96asr_v4 is only in **specific regions**; East US is a placeholder.  
  - Check:
    - Actual supported region (e.g., East US, West Europe, etc.).  
    - **Price differences by region** – GPU SKUs can vary significantly.

- **Co‑locate data and compute**
  - Place:
    - Backup vault, Log Analytics, and GPU workloads in **the same or paired regions** where possible.  
  - This reduces:
    - **Inter‑region data transfer**.  
    - Latency and egress costs.

- **Network architecture**
  - If you introduce:
    - **VPN gateways, ExpressRoute, Azure Firewall, NAT Gateway, Front Door / Application Gateway**, each adds recurring and per‑GB costs.  
  - For this design:
    - Egress is currently modeled as simple internet egress; if you later add **Front Door** or **private connectivity**, revisit the egress cost model.

---

## 6. Delta Tables vs Baseline

Because of SKU mismatches and missing prices, the tool flags scenarios as “not_comparable”. Still, we can compare **modeled totals** (priced + missing placeholders) to understand directional changes.

### 6.1 Overall Totals – Cost Optimized vs Baseline

| Metric                          | Baseline (USD) | Cost Optimized (USD) | Delta (CO – Base) | % Delta vs Baseline |
|---------------------------------|----------------|----------------------|-------------------|---------------------|
| **Monthly – Priced only**       | 96.4           | 36.7                 | -59.7             | -61.9%              |
| **Monthly – With estimates**    | 496.4          | 436.7                | -59.7             | -12.0%              |
| **Yearly – Priced only**        | 1156.8         | 440.4                | -716.4            | -61.9%              |
| **Yearly – With estimates**     | 5956.8         | 5240.4               | -716.4            | -12.0%              |
| Monthly Missing (unpriced)      | 400.0          | 400.0                | 0.0               | 0%                  |
| Yearly Missing (unpriced)       | 4800.0         | 4800.0               | 0.0               | 0%                  |

> Interpretation: Among the **priced components**, cost‑optimized is ~62% cheaper. Overall modeled monthly cost drops ~12%, but the big unpriced GPU/MARS block is unchanged.

### 6.2 Overall Totals – High Performance vs Baseline

| Metric                          | Baseline (USD) | High Perf (USD) | Delta (HP – Base) | % Delta vs Baseline |
|---------------------------------|----------------|------------------|-------------------|---------------------|
| **Monthly – Priced only**       | 96.4           | 171.4            | +75.0             | +77.8%              |
| **Monthly – With estimates**    | 496.4          | 571.4            | +75.0             | +15.1%              |
| **Yearly – Priced only**        | 1156.8         | 2056.8           | +900.0            | +77.8%              |
| **Yearly – With estimates**     | 5956.8         | 6856.8           | +900.0            | +15.1%              |
| Monthly Missing (unpriced)      | 400.0          | 400.0            | 0.0               | 0%                  |
| Yearly Missing (unpriced)       | 4800.0         | 4800.0           | 0.0               | 0%                  |

> Interpretation: High‑performance **increases priced components by ~78%**, mainly due to more backup ops, egress, Log Analytics, and Premium Key Vault, while the unpriced GPU/MARS block remains constant.

### 6.3 Category‑Level Monthly Deltas – Cost Optimized vs Baseline

| Category        | Baseline Monthly (USD) | Cost Opt Monthly (USD) | Delta (CO – Base) | % Delta vs Baseline |
|-----------------|------------------------|------------------------|-------------------|---------------------|
| backup/dr       | 10.8                   | 5.4                    | -5.4              | -50.0%              |
| other (MARS)    | 100.0                  | 100.0                  | 0.0               | 0%                  |
| compute         | 100.0                  | 100.0                  | 0.0               | 0%                  |
| storage         | 200.0                  | 200.0                  | 0.0               | 0%                  |
| network         | 20.0                   | 5.0                    | -15.0             | -75.0%              |
| monitoring      | 65.0                   | 26.0                   | -39.0             | -60.0%              |
| security        | 0.6                    | 0.3                    | -0.3              | -50.0%              |
| **Total**       | **496.4**              | **436.7**              | **-59.7**         | **-12.0%**          |

> Biggest savings: **Log Analytics**, **network egress**, and **backup ops**.

### 6.4 Category‑Level Monthly Deltas – High Performance vs Baseline

| Category        | Baseline Monthly (USD) | High Perf Monthly (USD) | Delta (HP – Base) | % Delta vs Baseline |
|-----------------|------------------------|--------------------------|-------------------|---------------------|
| backup/dr       | 10.8                   | 16.2                     | +5.4              | +50.0%              |
| other (MARS)    | 100.0                  | 100.0                    | 0.0               | 0%                  |
| compute         | 100.0                  | 100.0                    | 0.0               | 0%                  |
| storage         | 200.0                  | 200.0                    | 0.0               | 0%                  |
| network         | 20.0                   | 50.0                     | +30.0             | +150.0%             |
| monitoring      | 65.0                   | 104.0                    | +39.0             | +60.0%              |
| security        | 0.6                    | 1.2                      | +0.6              | +100.0%             |
| **Total**       | **496.4**              | **571.4**                | **+75.0**         | **+15.1%**          |

> Biggest increases: **network egress**, **Log Analytics**, and **backup ops**, plus a smaller uplift from **Premium Key Vault**.

---

## 7. Explicit Mentions of Key Services and Scaling Risks

- **Key Vault / Secrets Management**
  - Present in all scenarios; operations scale with:
    - Number of secrets/keys/certificates.  
    - Frequency of rotations and application calls.  
  - High‑performance uses **Premium** for HSM; validate if you truly need HSM for all keys.

- **Log Analytics / Monitoring**
  - Major cost driver in all scenarios.  
  - Costs scale with:
    - **Data volume (GB ingested)**.  
    - **Retention duration**.  
  - Use DCRs, sampling, and commitment tiers to control spend.

- **Backup Vault & Site Recovery**
  - Only **Azure Backup** is modeled; **Azure Site Recovery (ASR)** is not included but would add:
    - Per‑protected instance charges.  
    - Additional storage and network costs.  
  - Backup storage GB and GRS uplift are **not fully priced** in the current data; must be added manually.

- **Network Egress / NAT / Gateways / Front Door**
  - Current model only includes **internet egress** from GPU VMs.  
  - If you add:
    - **VPN/ExpressRoute gateways**, **Azure Firewall**, **NAT Gateway**, **Front Door**, or **Application Gateway**, each introduces:
      - Fixed hourly charges.  
      - Per‑GB data processing/transfer charges.  
  - Egress costs scale with **data volume** and **cross‑region / internet traffic patterns**.

- **Data Volume / Throughput Scaling**
  - Backup, Log Analytics, and egress costs all scale roughly linearly with:
    - **Protected data size**.  
    - **Change rate** (for incremental backups).  
    - **Log verbosity** and **sampling**.  
    - **Model/dataset distribution patterns** for GPU workloads.

---

If you’d like, I can next help you plug in **real ND96asr_v4 and MARS pricing** for your target region and produce a fully quantified comparison with reservations and savings plan scenarios.