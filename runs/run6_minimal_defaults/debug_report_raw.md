## 1. Baseline / Recommended – Short Narrative

The **baseline** scenario is a **single small Linux VM** in `westeurope` running your internal tool, with just enough surrounding services to be “production-safe”:

- A **Virtual Network** with no direct cost.
- One **general‑purpose VM** (D2s_v3‑like) running 24×7 with a Premium SSD OS disk.
- **Outbound-only internet** via a **NAT Gateway** and a **Standard public IP** (VM has no public IP).
- **Azure Bastion** for secure browser-based SSH/RDP without opening inbound ports.
- **Azure Backup** to protect the VM with daily backups and ~30‑day retention.
- **Azure Key Vault** to store secrets/certificates used by the VM.
- **Log Analytics** workspace for basic metrics and logs.

This is a minimal but reasonably secure/operationally sound pattern for a single internal tool VM: private network, no direct public exposure, central secrets management, monitoring, and backup.

> Important: Several prices are missing or mismatched in the catalog. The **modeled/priced** portion is very low (~$32.53/month); the tool has added **$300/month of placeholder “missing” costs** (mainly for VM, disk, public IP). Real Azure prices will be much lower than this placeholder for such a small setup.

---

## 2. Other Scenarios – Summary & Differences

### Cost Optimized

Intent: **Cheapest** version for a light internal tool.

Key differences vs baseline:

- **Compute**: Smaller, **burstable B2s‑class VM**, and only **~400 hours/month** (business hours) instead of 24×7.
- **Disk**: Smaller **32 GB Premium SSD**.
- **Monitoring**: **Half the Log Analytics ingestion** (~5 GB/month) by collecting only essential logs.
- **Backup**: **Shorter retention** and smaller backup footprint (~100 GB).
- **Key Vault**: Fewer operations (smaller workload).
- **NAT & Bastion**: Used fewer hours and less egress.

Result: Modeled/priced costs are about **half** the baseline’s modeled portion, but the tool still carries the same **$300/month placeholder “missing” costs** for VM/disk/public IP, so total-with-estimates only drops slightly on paper.

---

### High Performance

Intent: **More powerful** single VM for heavier internal workloads.

Key differences vs baseline:

- **Compute**: Larger **D4s_v3‑class VM** (4 vCPUs, 16 GB RAM) running **24×7**.
- **Disk**: Larger **128 GB Premium SSD** with higher IOPS/throughput.
- **Monitoring**: **More detailed logging** (~20 GB/month).
- **Backup**: Larger backup footprint (~300 GB) and longer retention.
- **Key Vault**: More operations (more secrets/certs usage).
- **NAT & Bastion**: More egress and more admin hours.

Result: Modeled/priced costs are higher than baseline, but again the same **$300/month placeholder “missing” costs** dominate the total.

---

## 3. Scenario Details

### 3.1 Baseline Scenario

#### Main Components

- **Compute**
  - 1× Linux VM (`vm-internal-tool`, D2s_v3‑like, 2 vCPU, 64 GB Premium SSD OS disk).
- **Storage / Data**
  - 1× Premium SSD OS disk (`disk-os-vm-internal-tool`, ~64 GB).
- **Network**
  - 1× Virtual Network (`vnet-main`).
  - 1× NAT egress + data transfer (`nat-egress`).
  - 1× Standard Public IP for NAT (`public-ip-nat`).
  - 1× Azure Bastion Basic (`bastion-host`).
- **Security**
  - 1× Key Vault Standard (`keyvault-main`) for secrets/certs.
- **Monitoring / Ops**
  - 1× Log Analytics workspace (`la-workspace`) with ~10 GB/month ingestion.
- **Backup / DR**
  - 1× Backup vault / Azure Backup (`backup-vault-main`) protecting the VM.

#### Pricing Table – Baseline

_All costs in USD; “resolved” SKU is what the pricing engine actually matched. Some are clearly mismatched and must be re‑checked._

| Scenario | Resource ID              | Category              | Service        | SKU (requested / resolved)                          | Region     | Billing | Unit Price | Unit                 | Units  | Monthly Cost | Yearly Cost | Notes |
|----------|--------------------------|-----------------------|----------------|------------------------------------------------------|------------|--------|-----------:|----------------------|-------:|-------------:|------------:|-------|
| baseline | vnet-main                | network.vnet          | Virtual Network | Virtual Network / Virtual Network                   | westeurope | payg   | 0.00       | VNet (no direct charge) | 1     | 0.00         | 0.00        | Logical VNet, no direct charge. |
| baseline | vm-internal-tool         | compute.vm            | Virtual Machines | Standard_D2s_v3 / EC2adsv6 Low Priority (mismatch)  | westeurope | payg   | 0.0351     | 1 Hour               | 730   | 25.62        | 307.48      | Spot-like ECadsv6 price used; real D2s_v3 PAYG is higher. |
| baseline | disk-os-vm-internal-tool | storage.disk          | Storage        | P6 / Hot GRS (mismatch)                             | westeurope | payg   | 0.0008     | 1 GB                 | 64    | 0.05         | 0.61        | Not actual Managed Disk pricing; placeholder from ADLS meter. |
| baseline | la-workspace             | monitoring.loganalytics | Log Analytics | n/a / Analytics Logs (Retention)                    | westeurope | payg   | 0.13       | 1 GB/Month           | 10    | 1.30         | 15.60       | Assumes ~10 GB/month retained. Ingestion vs retention split is simplified. |
| baseline | backup-vault-main        | backup.vault          | Backup         | n/a / ADLS Gen2 Vaulted LRS Write Ops               | westeurope | payg   | 0.054      | 10K operations       | 0.5   | 0.03         | 0.32        | Only write ops priced; backup storage itself not modeled here. |
| baseline | keyvault-main            | security.keyvault     | Key Vault      | standard / Standard Operations                       | westeurope | payg   | 0.03       | 10K operations       | 10    | 0.30         | 3.60        | ~100k ops/month. Storage and advanced ops not modeled. |
| baseline | nat-egress               | network.nat           | Bandwidth      | n/a / Standard Inter-AZ Data Transfer Out           | westeurope | payg   | 0.01       | 1 GB                 | 50    | 0.50         | 6.00        | Approximates outbound data; NAT Gateway hourly fee not modeled. |
| baseline | public-ip-nat            | network.public_ip     | Public IP      | Standard / (missing)                                | westeurope | payg   | n/a        | n/a                  | n/a   | n/a          | n/a         | Price missing; Standard public IP has a small hourly cost. |
| baseline | bastion-host             | network.bastion       | Azure Bastion  | Basic / Basic Gateway                               | westeurope | payg   | 0.19       | 1 Hour               | 160   | 30.40        | 364.80      | Bastion Basic, used ~160 hours/month. Data transfer not modeled. |

**Scenario totals (from JSON)**

- **Modeled/priced**:  
  - Monthly: **$32.53**  
  - Yearly: **$390.32**
- **Missing (placeholder)**:  
  - Monthly: **$300.00**  
  - Yearly: **$3,600.00**
- **Total with estimates**:  
  - Monthly: **$332.53**  
  - Yearly: **$3,990.32**

> The $300/month “missing” is spread across compute.vm, storage.disk, and network.public_ip categories as placeholders.

#### Aggregated by Category – Baseline

I’ll map to the requested high-level buckets:

- **compute** → `compute.vm`
- **storage** → `storage.disk`
- **network** → `network.vnet`, `network.nat`, `network.public_ip`, `network.bastion`
- **monitoring** → `monitoring.loganalytics`
- **backup/dr** → `backup.vault`
- **security** → `security.keyvault`
- **analytics, db, other** → none here (or negligible)

| Category    | Monthly Priced | Monthly Missing/Est. | Monthly Total (with est.) | Est./Missing Share of Category |
|------------|---------------:|----------------------:|---------------------------:|--------------------------------|
| compute    | 0.00           | 100.00               | 100.00                    | 100% placeholder (VM price missing/mismatched). |
| storage    | 0.00           | 100.00               | 100.00                    | 100% placeholder (disk price missing/mismatched). |
| network    | 30.90          | 100.00               | 130.90                    | ~76% placeholder (public IP + possibly NAT/Bastion under-modeled). |
| monitoring | 1.30           | 0.00                 | 1.30                      | 0% estimated; ingestion volume is an assumption but priced. |
| backup/dr  | 0.03           | 0.00                 | 0.03                      | 0% estimated; but only operations, not storage, are modeled. |
| security   | 0.30           | 0.00                 | 0.30                      | 0% estimated; operations volume is assumed. |
| analytics  | 0.00           | 0.00                 | 0.00                      | n/a |
| other      | 0.00           | 0.00                 | 0.00                      | n/a |

> Overall, **>90% of the total is placeholder**. Real Azure costs for this baseline will likely be **well under $100/month** in most regions if you use a small D‑series or B‑series VM.

---

### 3.2 Cost Optimized Scenario

#### Main Components

- **Compute**
  - 1× Linux VM (`vm-internal-tool-co`, B2s‑class, burstable) running ~400 hours/month.
- **Storage**
  - 1× smaller Premium SSD OS disk (`disk-os-vm-internal-tool-co`, 32 GB).
- **Network**
  - 1× VNet (`vnet-main-co`).
  - 1× NAT egress (`nat-egress-co`) with ~30 GB/month.
  - 1× Standard Public IP for NAT (`public-ip-nat-co`).
  - 1× Azure Bastion Basic (`bastion-co`) used ~80 hours/month.
- **Security**
  - 1× Key Vault Standard (`keyvault-co`) with fewer operations.
- **Monitoring / Ops**
  - 1× Log Analytics workspace (`la-workspace-co`) with ~5 GB/month ingestion.
- **Backup / DR**
  - 1× Backup vault (`backup-vault-co`) with ~100 GB protected and shorter retention.

#### Pricing Table – Cost Optimized

| Scenario       | Resource ID                    | Category              | Service        | SKU (requested / resolved)                          | Region     | Billing | Unit Price | Unit           | Units | Monthly Cost | Yearly Cost | Notes |
|----------------|--------------------------------|-----------------------|----------------|------------------------------------------------------|------------|--------|-----------:|----------------|------:|-------------:|------------:|-------|
| cost_optimized | vnet-main-co                   | network.vnet          | Virtual Network | n/a / Virtual Network                               | westeurope | payg   | 0.00       | VNet           | 1    | 0.00         | 0.00        | No direct charge. |
| cost_optimized | vm-internal-tool-co            | compute.vm            | Virtual Machines | Standard_B2s / B2pts v2 Low Priority (mismatch)     | westeurope | payg   | 0.00192    | 1 Hour         | 400  | 0.77         | 9.22        | Spot-like Bpsv2 price; real B2s PAYG is higher. |
| cost_optimized | disk-os-vm-internal-tool-co    | storage.disk          | Storage        | P4 / Hot GRS (mismatch)                             | westeurope | payg   | 0.0008     | 1 GB           | 32   | 0.03         | 0.31        | Not actual Managed Disk pricing. |
| cost_optimized | la-workspace-co                | monitoring.loganalytics | Log Analytics | n/a / Analytics Logs (Retention)                    | westeurope | payg   | 0.13       | 1 GB/Month     | 5    | 0.65         | 7.80        | ~5 GB/month retained. |
| cost_optimized | backup-vault-co                | backup.vault          | Backup         | n/a / ADLS Gen2 Vaulted LRS Write Ops               | westeurope | payg   | 0.054      | 10K ops        | 0.3  | 0.02         | 0.19        | Only operations priced. |
| cost_optimized | keyvault-co                    | security.keyvault     | Key Vault      | standard / Standard Operations                       | westeurope | payg   | 0.03       | 10K ops        | 5    | 0.15         | 1.80        | ~50k ops/month. |
| cost_optimized | nat-egress-co                  | network.nat           | Bandwidth      | n/a / Standard Inter-AZ Data Transfer Out           | westeurope | payg   | 0.01       | 1 GB           | 30   | 0.30         | 3.60        | NAT data only; gateway hourly fee not modeled. |
| cost_optimized | public-ip-nat-co               | network.public_ip     | Public IP      | Standard / (missing)                                | westeurope | payg   | n/a        | n/a            | n/a  | n/a          | n/a         | Price missing. |
| cost_optimized | bastion-co                     | network.bastion       | Azure Bastion  | Basic / Basic Gateway                               | westeurope | payg   | 0.19       | 1 Hour         | 80   | 15.20        | 182.40      | Bastion used ~80 hours/month. |

**Scenario totals (from JSON)**

- **Modeled/priced**:  
  - Monthly: **$16.32**  
  - Yearly: **$195.79**
- **Missing (placeholder)**:  
  - Monthly: **$300.00**  
  - Yearly: **$3,600.00**
- **Total with estimates**:  
  - Monthly: **$316.32**  
  - Yearly: **$3,795.79**

#### Aggregated by Category – Cost Optimized

| Category    | Monthly Priced | Monthly Missing/Est. | Monthly Total (with est.) | Est./Missing Share of Category |
|------------|---------------:|----------------------:|---------------------------:|--------------------------------|
| compute    | 0.00           | 100.00               | 100.00                    | 100% placeholder (VM). |
| storage    | 0.00           | 100.00               | 100.00                    | 100% placeholder (disk). |
| network    | 15.50          | 100.00               | 115.50                    | ~87% placeholder (public IP, NAT/Bastion under-modeled). |
| monitoring | 0.65           | 0.00                 | 0.65                      | 0% estimated; ingestion assumption. |
| backup/dr  | 0.02           | 0.00                 | 0.02                      | 0% estimated; storage not modeled. |
| security   | 0.15           | 0.00                 | 0.15                      | 0% estimated; operations assumption. |
| analytics  | 0.00           | 0.00                 | 0.00                      | n/a |
| other      | 0.00           | 0.00                 | 0.00                      | n/a |

---

### 3.3 High Performance Scenario

#### Main Components

- **Compute**
  - 1× Linux VM (`vm-internal-tool-hp`, D4s_v3‑class, 4 vCPU, 16 GB RAM) running 24×7.
- **Storage**
  - 1× larger Premium SSD OS disk (`disk-os-vm-internal-tool-hp`, 128 GB).
- **Network**
  - 1× VNet (`vnet-main-hp`).
  - 1× NAT egress (`nat-egress-hp`) with ~100 GB/month.
  - 1× Standard Public IP for NAT (`public-ip-nat-hp`).
  - 1× Azure Bastion Basic (`bastion-hp`) used ~200 hours/month.
- **Security**
  - 1× Key Vault Standard (`keyvault-hp`) with higher operation volume.
- **Monitoring / Ops**
  - 1× Log Analytics workspace (`la-workspace-hp`) with ~20 GB/month ingestion.
- **Backup / DR**
  - 1× Backup vault (`backup-vault-hp`) with ~300 GB protected and longer retention.

#### Pricing Table – High Performance

| Scenario        | Resource ID                    | Category              | Service        | SKU (requested / resolved)                          | Region     | Billing | Unit Price | Unit           | Units | Monthly Cost | Yearly Cost | Notes |
|-----------------|--------------------------------|-----------------------|----------------|------------------------------------------------------|------------|--------|-----------:|----------------|------:|-------------:|------------:|-------|
| high_performance | vnet-main-hp                 | network.vnet          | Virtual Network | n/a / Virtual Network                               | westeurope | payg   | 0.00       | VNet           | 1    | 0.00         | 0.00        | No direct charge. |
| high_performance | vm-internal-tool-hp          | compute.vm            | Virtual Machines | Standard_D4s_v3 / EC2adsv6 Low Priority (mismatch)  | westeurope | payg   | 0.0351     | 1 Hour         | 730  | 25.62        | 307.48      | Spot-like ECadsv6 price; real D4s_v3 PAYG is higher. |
| high_performance | disk-os-vm-internal-tool-hp  | storage.disk          | Storage        | P10 / Hot GRS (mismatch)                            | westeurope | payg   | 0.0008     | 1 GB           | 128  | 0.10         | 1.23        | Not actual Managed Disk pricing. |
| high_performance | la-workspace-hp              | monitoring.loganalytics | Log Analytics | n/a / Analytics Logs (Retention)                    | westeurope | payg   | 0.13       | 1 GB/Month     | 20   | 2.60         | 31.20       | ~20 GB/month retained. |
| high_performance | backup-vault-hp              | backup.vault          | Backup         | n/a / ADLS Gen2 Vaulted LRS Write Ops               | westeurope | payg   | 0.054      | 10K ops        | 0.8  | 0.04         | 0.52        | Only operations priced. |
| high_performance | keyvault-hp                  | security.keyvault     | Key Vault      | standard / Standard Operations                       | westeurope | payg   | 0.03       | 10K ops        | 20   | 0.60         | 7.20        | ~200k ops/month. |
| high_performance | nat-egress-hp                | network.nat           | Bandwidth      | n/a / Standard Inter-AZ Data Transfer Out           | westeurope | payg   | 0.01       | 1 GB           | 100  | 1.00         | 12.00       | NAT data only; gateway hourly fee not modeled. |
| high_performance | public-ip-nat-hp             | network.public_ip     | Public IP      | Standard / (missing)                                | westeurope | payg   | n/a        | n/a            | n/a  | n/a          | n/a         | Price missing. |
| high_performance | bastion-hp                   | network.bastion       | Azure Bastion  | Basic / Basic Gateway                               | westeurope | payg   | 0.19       | 1 Hour         | 200  | 38.00        | 456.00      | Bastion used ~200 hours/month. |

**Scenario totals (from JSON)**

- **Modeled/priced**:  
  - Monthly: **$42.24**  
  - Yearly: **$506.92**
- **Missing (placeholder)**:  
  - Monthly: **$300.00**  
  - Yearly: **$3,600.00**
- **Total with estimates**:  
  - Monthly: **$342.24**  
  - Yearly: **$4,106.92**

#### Aggregated by Category – High Performance

| Category    | Monthly Priced | Monthly Missing/Est. | Monthly Total (with est.) | Est./Missing Share of Category |
|------------|---------------:|----------------------:|---------------------------:|--------------------------------|
| compute    | 0.00           | 100.00               | 100.00                    | 100% placeholder (VM). |
| storage    | 0.00           | 100.00               | 100.00                    | 100% placeholder (disk). |
| network    | 39.00          | 100.00               | 139.00                    | ~72% placeholder (public IP, NAT/Bastion under-modeled). |
| monitoring | 2.60           | 0.00                 | 2.60                      | 0% estimated; ingestion assumption. |
| backup/dr  | 0.04           | 0.00                 | 0.04                      | 0% estimated; storage not modeled. |
| security   | 0.60           | 0.00                 | 0.60                      | 0% estimated; operations assumption. |
| analytics  | 0.00           | 0.00                 | 0.00                      | n/a |
| other      | 0.00           | 0.00                 | 0.00                      | n/a |

---

## 4. Resources Where Pricing Failed / Is Clearly Wrong

You should **manually check and correct** pricing for the following:

### All Scenarios – Common Issues

1. **Virtual Machines (compute.vm)**
   - Baseline: `vm-internal-tool` – requested `Standard_D2s_v3`, resolved to **EC2adsv6 Low Priority** (spot-like ECadsv6 series).
   - Cost Optimized: `vm-internal-tool-co` – requested `Standard_B2s`, resolved to **B2pts v2 Low Priority** (spot-like).
   - High Performance: `vm-internal-tool-hp` – requested `Standard_D4s_v3`, resolved to **EC2adsv6 Low Priority**.
   - **Action**: Use the Azure Pricing Calculator or retail API for:
     - Region: `westeurope`
     - SKUs: `Standard_B2s`, `Standard_D2s_v3`, `Standard_D4s_v3`
     - OS: Linux
     - Billing: **Pay-as-you-go**, not Spot.

2. **Managed Disks (storage.disk)**
   - Baseline: `disk-os-vm-internal-tool` – requested `P6`, resolved to **Hot GRS ADLS Gen2**.
   - Cost Optimized: `disk-os-vm-internal-tool-co` – requested `P4`, resolved to **Hot GRS ADLS Gen2**.
   - High Performance: `disk-os-vm-internal-tool-hp` – requested `P10`, resolved to **Hot GRS ADLS Gen2**.
   - **Action**: Use Managed Disk pricing for:
     - Premium SSD P4 (32 GB), P6 (64 GB), P10 (128 GB) in `westeurope`.
     - Include disk capacity price; IOPS/throughput are included in disk tier.

3. **Public IP Addresses (network.public_ip)**
   - Baseline: `public-ip-nat` – **pricing_status: missing**.
   - Cost Optimized: `public-ip-nat-co` – **pricing_status: missing**.
   - High Performance: `public-ip-nat-hp` – **pricing_status: missing**.
   - **Action**: Look up **Standard Public IP** (IPv4, zone-redundant or regional) hourly price in `westeurope`. It’s usually small but non-zero.

4. **NAT Gateway**
   - All NAT resources (`nat-egress*`) only price **data transfer**, not the **NAT Gateway hourly fee**.
   - **Action**: Add NAT Gateway hourly cost (Standard NAT Gateway in `westeurope`) plus data transfer out to Internet (Bandwidth – Data Transfer Out).

5. **Azure Backup**
   - Backup resources (`backup-vault-*`) only price **write operations**, not **backup storage**.
   - **Action**: Add Backup storage:
     - Azure Backup vault or Recovery Services vault
     - LRS/GRS storage for the assumed protected GB and retention.

6. **Log Analytics**
   - All `la-workspace*` resources use **retention** meter for ingestion.
   - **Action**: For more accurate modeling:
     - Use **Analytics Logs Data Ingestion** for GB ingested.
     - Use **Data Retention** only for retention beyond free period (31 days).

---

## 5. FinOps Recommendations

### 5.1 Quick Wins

1. **Fix the pricing inputs**
   - Replace placeholder/mismatched SKUs (VMs, disks, public IP, NAT hourly, backup storage).
   - This will likely bring **real monthly totals into the tens of dollars**, not hundreds.

2. **Use a Burstable VM + Scheduled Shutdown (Cost Optimized pattern)**
   - For a light internal tool, **Standard_B2s** with **auto-shutdown outside business hours** is often enough.
   - Combine:
     - B2s (or B1ms if very light).
     - 32–64 GB Premium SSD.
     - Azure Automation or built-in **Start/Stop schedule**.

3. **Right-size Log Analytics**
   - Keep only essential logs:
     - Platform metrics, VM insights basics, key security logs.
   - Use **5–10 GB/month** as a target; archive or drop verbose debug logs.

4. **Bastion usage**
   - Bastion is often a **surprisingly large line item** for small workloads.
   - If admin access is rare:
     - Use **cost_optimized** pattern (80 hours/month) or even less.
     - Consider **just-in-time (JIT) access** with a temporary public IP + NSG lock-down as an alternative (if your security policy allows).

5. **Key Vault**
   - Keep using Key Vault – cost is tiny vs risk.
   - Avoid unnecessary high-frequency secret reads (cache secrets in the app where safe).

### 5.2 Spot vs PAYG vs Reserved

- **Spot (Low Priority)**
  - The current resolved SKUs are **spot-like** (Low Priority) but you’re modeling a **prod** workload.
  - Spot is **not recommended** for a single critical VM unless:
    - You can tolerate eviction and downtime.
    - You have automation to recreate/replace the VM.
- **PAYG**
  - For a single small VM, PAYG is fine if:
    - You’re still experimenting with size/hours.
    - You don’t want commitment.
- **Reserved Instances (RI) / Savings Plan**
  - If you decide:
    - Baseline: VM runs **24×7** and will be needed for **≥1 year**.
    - High Performance: same, but larger VM.
  - Then a **1‑year Reserved VM Instance** or **Compute Savings Plan** can save **30–50%** vs PAYG.
  - For **cost_optimized** (400 hours/month), RI is less attractive; you’re not using full 730 hours.

**Recommendation:**

- Start with **PAYG** while you confirm:
  - VM size (B2s vs D2s_v3 vs D4s_v3).
  - Actual uptime (24×7 vs business hours).
- After 1–2 months of usage data:
  - If VM is **>70% utilized in hours**, consider **1‑year RI or Savings Plan** for that size.

### 5.3 Right-Sizing Ideas

- **CPU/RAM**
  - If CPU <20% and RAM <50% most of the time:
    - Move from D2s_v3 → B2s or even B1ms.
  - If CPU is often >70% or memory pressure is high:
    - Move from D2s_v3 → D4s_v3 (High Performance scenario).
- **Disk**
  - OS disk:
    - 32 GB (P4) is often enough for a small Linux tool.
    - Only go to 64/128 GB if logs or local data require it.
  - If you need more IOPS:
    - Consider P10 or P15, or add a **data disk** instead of oversizing OS disk.

### 5.4 Region and Egress Considerations

- **Region**
  - You’re using `westeurope`. Prices vary slightly by region.
  - If your users are in Europe, `westeurope` or `northeurope` are both fine; check which is cheaper for:
    - VM SKUs.
    - Managed disks.
    - NAT/Bandwidth.
- **Egress**
  - Current assumptions (50 GB baseline, 30 GB cost_optimized, 100 GB high_performance) are small.
  - If the tool starts serving external users or large file downloads:
    - **Data transfer out to Internet** can become a major cost driver.
    - Consider:
      - **Azure Front Door** or **CDN** for caching static content.
      - Private connectivity (VPN/ExpressRoute) for internal-only users.

---

## 6. Delta Tables vs Baseline

Because of SKU mismatches, the engine flags scenarios as “not_comparable”, but we can still compare **totals from the JSON**.

### 6.1 Overall Totals – Monthly & Yearly

Using:

- **Priced totals** = `monthly_priced` / `yearly_priced`
- **With estimates** = `monthly_with_estimates` / `yearly_with_estimates`

#### Cost Optimized vs Baseline

| Metric                         | Baseline | Cost Optimized | Absolute Δ (CO – BL) | % Δ vs Baseline |
|--------------------------------|---------:|---------------:|----------------------:|----------------:|
| Monthly – Priced only          | 32.53    | 16.32          | -16.21                | -49.8%          |
| Yearly – Priced only           | 390.32   | 195.79         | -194.53               | -49.8%          |
| Monthly – With estimates       | 332.53   | 316.32         | -16.21                | -4.9%           |
| Yearly – With estimates        | 3,990.32 | 3,795.79       | -194.53               | -4.9%           |

Interpretation:

- On the **modeled/priced** part, cost_optimized is about **50% cheaper** than baseline (mainly due to smaller VM, fewer hours, less Bastion and logging).
- Because both scenarios carry the same **$300/month placeholder**, the **total** only drops by ~5% in this dataset.

#### High Performance vs Baseline

| Metric                         | Baseline | High Performance | Absolute Δ (HP – BL) | % Δ vs Baseline |
|--------------------------------|---------:|-----------------:|----------------------:|----------------:|
| Monthly – Priced only          | 32.53    | 42.24            | +9.71                 | +29.8%          |
| Yearly – Priced only           | 390.32   | 506.92           | +116.60               | +29.8%          |
| Monthly – With estimates       | 332.53   | 342.24           | +9.71                 | +2.9%           |
| Yearly – With estimates        | 3,990.32 | 4,106.92         | +116.60               | +2.9%           |

Interpretation:

- On the **modeled/priced** part, high_performance is about **30% more expensive** than baseline (larger VM, more Bastion, more logging).
- Again, the **$300/month placeholder** dominates, so total only increases by ~3%.

### 6.2 Category-Level Monthly Deltas

Using **monthly_with_estimates by category** from each scenario.

#### Cost Optimized vs Baseline – Monthly by Category

| Category     | Baseline ($/mo) | Cost Opt. ($/mo) | Δ (CO – BL) | % Δ vs Baseline |
|-------------|----------------:|-----------------:|------------:|----------------:|
| compute     | 100.00          | 100.00           | 0.00        | 0%              |
| storage     | 100.00          | 100.00           | 0.00        | 0%              |
| network     | 130.90          | 115.50           | -15.40      | -11.8%          |
| monitoring  | 1.30            | 0.65             | -0.65       | -50.0%          |
| backup/dr   | 0.03            | 0.02             | -0.01       | -33.3%          |
| security    | 0.30            | 0.15             | -0.15       | -50.0%          |
| analytics   | 0.00            | 0.00             | 0.00        | n/a             |
| other       | 0.00            | 0.00             | 0.00        | n/a             |

Notes:

- **Network**: Lower NAT egress and half Bastion hours drive ~12% lower network cost (on top of placeholders).
- **Monitoring, Security, Backup**: Roughly **50% lower** due to reduced ingestion, fewer Key Vault ops, and smaller backup footprint.

#### High Performance vs Baseline – Monthly by Category

| Category     | Baseline ($/mo) | High Perf. ($/mo) | Δ (HP – BL) | % Δ vs Baseline |
|-------------|----------------:|-------------------:|------------:|----------------:|
| compute     | 100.00          | 100.00             | 0.00        | 0%              |
| storage     | 100.00          | 100.00             | 0.00        | 0%              |
| network     | 130.90          | 139.00             | +8.10       | +6.2%           |
| monitoring  | 1.30            | 2.60               | +1.30       | +100.0%         |
| backup/dr   | 0.03            | 0.04               | +0.01       | +33.3%          |
| security    | 0.30            | 0.60               | +0.30       | +100.0%         |
| analytics   | 0.00            | 0.00               | 0.00        | n/a             |
| other       | 0.00            | 0.00               | 0.00        | n/a             |

Notes:

- **Network**: More NAT egress and more Bastion hours increase network cost modestly.
- **Monitoring & Security**: Roughly **double** due to more logs and more Key Vault operations.
- **Backup**: Slightly higher due to larger protected data and retention.

---

## 7. How to Choose Between the Scenarios

- If this internal tool is **lightweight** and used mainly in business hours:
  - **Cost Optimized** is the right pattern:
    - B2s VM, scheduled shutdown, smaller disk, reduced logging.
- If it’s **business-critical** and performance-sensitive:
  - **High Performance**:
    - D4s_v3, larger disk, more logging, more frequent admin access.
- If you want a **simple, safe default** with minimal tuning:
  - **Baseline**:
    - D2s_v3‑class VM, 24×7, moderate logging and backup.

In all cases:

- Keep **Key Vault** and **Log Analytics** – they’re cheap and essential for security/ops.
- Use **Azure Backup** with at least 14–30 days retention.
- Use **NAT + Bastion** or an equivalent secure pattern (no direct public IP on the VM).
- After correcting prices, revisit:
  - VM size and hours.
  - Reservation vs PAYG.
  - Log volume and retention.
  - Bastion usage patterns.

If you’d like, I can next provide a **cleaned-up cost model** with realistic Azure retail prices for a specific VM size and region (e.g., B2s in `westeurope`, 400 hours/month) so you have a more accurate monthly number.