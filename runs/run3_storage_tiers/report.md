## 1. Baseline / Recommended – Short Narrative

The baseline design is a centralized log archive built on **Azure Blob Storage (Standard GRS)** in West Europe, fronted by a **private VNet**. Logs are ingested at **20 TB/month** into the **Hot tier**, then automatically moved to **Cool after 30 days** and **Archive after 180 days** using lifecycle policies. At steady state this yields roughly:

- 20 TB Hot (last month),
- 80 TB Cool (previous 4 months),
- 40 TB Archive (previous 2 months),

all with **GRS redundancy** for compliance.

Access is mostly occasional: about **2 TB/month egress** and ~200M storage operations/month. Security and operations are handled via:

- **Azure Key Vault** for secrets and (optionally) CMK for storage,
- **Log Analytics** for monitoring the storage account and ingestion jobs (500 GB/month assumed),
- A small **Backup vault** for configuration/metadata (not for the 20 TB/month data, which relies on GRS + lifecycle).

This scenario balances cost and usability: enough Hot data for recent investigations, Cool/Archive for long‑term retention, and standard monitoring and security controls.

---

## 2. Other Scenarios – How They Differ

### Cost Optimized

- Same 20 TB/month ingest and GRS, but **more aggressive tiering**:
  - ~10 TB Hot, 60 TB Cool, 60 TB Archive.
- **Lower access assumptions**:
  - 1 TB/month egress (vs 2 TB),
  - 150M operations/month (vs 200M).
- **Smaller monitoring footprint**:
  - Log Analytics: 200 GB/month (vs 500 GB).
- **Smaller backup vault**:
  - 150 GB metadata/config vs 200 GB.
- Key Vault usage reduced (100k ops vs 200k).

Net effect: lower storage and egress cost, but slower access to more of the data (more in Cool/Archive) and less monitoring detail.

### High Performance / Heavy Access

- Same 20 TB/month ingest and GRS, but **more data kept Hot**:
  - ~30 TB Hot, 70 TB Cool, 40 TB Archive.
- **Higher access assumptions**:
  - 5 TB/month egress (vs 2 TB),
  - 400M operations/month (vs 200M).
- **Larger monitoring footprint**:
  - Log Analytics: 1 TB/month (vs 500 GB).
- **Larger backup vault**:
  - 300 GB metadata/config vs 200 GB.
- Key Vault usage increased (400k ops vs 200k).

Net effect: better performance and more analytics on recent data, at higher storage, egress, and monitoring cost.

---

## 3. Scenario Details

### 3.1 Baseline Scenario

#### Main Components (by concern)

- **Compute**
  - None explicitly costed (ingestion/ETL assumed external or serverless; not in this model).

- **Data / Storage**
  - `log-blob-grs`: Azure Storage (Blob / ADLS Gen2), Standard_GRS, Hot/Cool/Archive tiers with lifecycle policies.

- **Network**
  - `log-vnet`: Virtual Network (no direct charge).
  - `log-egress`: Bandwidth for 2 TB/month outbound.

- **Security**
  - `log-keyvault`: Azure Key Vault (Standard) for secrets, keys, CMK.

- **Monitoring / Analytics**
  - `log-la`: Log Analytics workspace for monitoring storage and ingestion (500 GB/month).

- **Backup / DR**
  - `log-backup-vault`: Recovery Services vault for configuration/metadata only (not full log backup).

- **Other**
  - None beyond the above.

#### Pricing Table – Baseline

> Currency: GBP

| Scenario | Resource ID       | Category                 | Service        | SKU (requested / resolved)        | Region     | Billing | Unit Price | Unit          | Units   | Monthly Cost | Yearly Cost | Notes |
|----------|-------------------|--------------------------|----------------|-----------------------------------|-----------|---------|-----------:|---------------|--------:|-------------:|------------:|-------|
| baseline | log-vnet          | network.vnet             | Virtual Network| Virtual Network / Virtual Network | westeurope| payg    | 0.00       | VNet          | 1       | 0.00         | 0.00        | Logical VNet, no direct charge. |
| baseline | log-blob-grs      | storage.blob             | Storage        | Standard_GRS / Standard_GRS       | westeurope| payg    | n/a        | n/a           | n/a     | 148.00*      | 1,776.00*   | Estimated: 20 TB Hot, 80 TB Cool, 40 TB Archive; includes tiered storage + ops. |
| baseline | log-egress        | network.egress           | Bandwidth      | n/a / Standard                    | westeurope| payg    | 0.0076     | 1 GB          | 2,000   | 15.20        | 182.40      | 2 TB/month outbound (inter-AZ transfer SKU used as proxy). |
| baseline | log-keyvault      | security.keyvault        | Key Vault      | standard / Standard               | westeurope| payg    | 0.0228     | 10K ops       | 20      | 0.46         | 5.47        | ~200k operations/month. |
| baseline | log-la            | monitoring.loganalytics  | Log Analytics  | PerGB2018 / Analytics Logs        | westeurope| payg    | 0.0987**   | 1 GB/Month    | 500     | 49.35**      | 592.20**    | 500 GB/month retention; SKU mismatch flag – ingestion vs retention meters. |
| baseline | log-backup-vault  | backup.vault             | Backup         | Standard / ADLS Gen2 Vaulted      | westeurope| payg    | 0.041**    | 10K ops       | 10      | 0.41**       | 4.92**      | 200 GB config/metadata; SKU mismatch, storage component not fully modeled. |

\* Marked as **estimated** in the JSON.  
\** Resource has **sku_mismatch**; treat as approximate and verify in the Azure Pricing Calculator / Portal.

#### Aggregated by Category – Baseline

I’ll map Azure categories into higher-level buckets:

- compute → none
- db → none
- storage → `storage.blob`
- network → `network.vnet`, `network.egress`
- analytics → (none distinct; Log Analytics counted under monitoring)
- security → `security.keyvault`
- monitoring → `monitoring.loganalytics`
- backup/dr → `backup.vault`
- other → none

> Currency: GBP

| High-Level Category | Included JSON Categories                          | Monthly (modeled) | Of which Priced | Of which Estimated | Of which Missing | Estimation Ratio* |
|---------------------|---------------------------------------------------|-------------------:|----------------:|-------------------:|-----------------:|-------------------|
| Compute             | –                                                 | 0.00              | 0.00            | 0.00               | 0.00             | 0%                |
| DB                  | –                                                 | 0.00              | 0.00            | 0.00               | 0.00             | 0%                |
| Storage             | storage.blob                                      | 148.00            | 0.00            | 148.00             | 0.00             | 100% (estimated)  |
| Network             | network.vnet, network.egress                      | 15.20             | 15.20           | 0.00               | 0.00             | 0%                |
| Security            | security.keyvault                                 | 0.46              | 0.46            | 0.00               | 0.00             | 0%                |
| Monitoring          | monitoring.loganalytics                           | 100.00**          | 0.00            | 0.00               | 100.00           | 100% missing      |
| Backup / DR         | backup.vault                                      | 100.00**          | 0.00            | 0.00               | 100.00           | 100% missing      |
| Analytics (other)   | –                                                 | 0.00              | 0.00            | 0.00               | 0.00             | 0%                |
| Other               | –                                                 | 0.00              | 0.00            | 0.00               | 0.00             | 0%                |

\* Estimation ratio = (estimated + missing) / total for that category.  
\** For Log Analytics and Backup, the scenario totals show **£100/month each as “missing”** – the per-resource numbers (e.g., £49.35, £0.41) are partial and flagged as sku_mismatch; assume real costs will be closer to the **£100/month** placeholders until re‑modeled.

---

### 3.2 Cost Optimized Scenario

#### Main Components

- **Compute**
  - None explicitly costed.

- **Data / Storage**
  - `log-blob-grs-co`: Azure Storage (Blob / ADLS Gen2), Standard_GRS, more aggressive Cool/Archive usage (10 TB Hot, 60 TB Cool, 60 TB Archive).

- **Network**
  - `log-vnet-co`: Virtual Network (no direct charge).
  - `log-egress-co`: Bandwidth for 1 TB/month outbound.

- **Security**
  - `log-keyvault-co`: Azure Key Vault (Standard), 100k ops/month.

- **Monitoring / Analytics**
  - `log-la-co`: Log Analytics workspace, 200 GB/month (sku_mismatch).

- **Backup / DR**
  - `log-backup-vault-co`: Recovery Services vault, 150 GB metadata/config (sku_mismatch).

#### Pricing Table – Cost Optimized

> Currency: GBP

| Scenario       | Resource ID         | Category                 | Service        | SKU (requested / resolved)        | Region     | Billing | Unit Price | Unit          | Units   | Monthly Cost | Yearly Cost | Notes |
|----------------|---------------------|--------------------------|----------------|-----------------------------------|-----------|---------|-----------:|---------------|--------:|-------------:|------------:|-------|
| cost_optimized | log-vnet-co         | network.vnet             | Virtual Network| Virtual Network / Virtual Network | westeurope| payg    | 0.00       | VNet          | 1       | 0.00         | 0.00        | Logical VNet, no direct charge. |
| cost_optimized | log-blob-grs-co     | storage.blob             | Storage        | Standard_GRS / Standard_GRS       | westeurope| payg    | n/a        | n/a           | n/a     | 108.00*      | 1,296.00*   | Estimated: 10 TB Hot, 60 TB Cool, 60 TB Archive. |
| cost_optimized | log-egress-co       | network.egress           | Bandwidth      | n/a / Standard                    | westeurope| payg    | 0.0076     | 1 GB          | 1,000   | 7.60         | 91.20       | 1 TB/month outbound. |
| cost_optimized | log-keyvault-co     | security.keyvault        | Key Vault      | standard / Standard               | westeurope| payg    | 0.0228     | 10K ops       | 10      | 0.23         | 2.74        | ~100k operations/month. |
| cost_optimized | log-la-co           | monitoring.loganalytics  | Log Analytics  | PerGB2018 / Analytics Logs        | westeurope| payg    | 0.0987**   | 1 GB/Month    | 200     | 19.74**      | 236.88**    | 200 GB/month; sku_mismatch (ingestion vs retention). |
| cost_optimized | log-backup-vault-co | backup.vault             | Backup         | Standard / ADLS Gen2 Vaulted      | westeurope| payg    | 0.041**    | 10K ops       | 5       | 0.21**       | 2.46**      | 150 GB metadata/config; sku_mismatch, storage not fully modeled. |

\* Estimated.  
\** sku_mismatch; treat as approximate.

#### Aggregated by Category – Cost Optimized

> Currency: GBP

| High-Level Category | Included JSON Categories                          | Monthly (modeled) | Of which Priced | Of which Estimated | Of which Missing | Estimation Ratio |
|---------------------|---------------------------------------------------|-------------------:|----------------:|-------------------:|-----------------:|------------------|
| Compute             | –                                                 | 0.00              | 0.00            | 0.00               | 0.00             | 0%               |
| DB                  | –                                                 | 0.00              | 0.00            | 0.00               | 0.00             | 0%               |
| Storage             | storage.blob                                      | 108.00            | 0.00            | 108.00             | 0.00             | 100% estimated   |
| Network             | network.vnet, network.egress                      | 7.60              | 7.60            | 0.00               | 0.00             | 0%               |
| Security            | security.keyvault                                 | 0.23              | 0.23            | 0.00               | 0.00             | 0%               |
| Monitoring          | monitoring.loganalytics                           | 100.00**          | 0.00            | 0.00               | 100.00           | 100% missing     |
| Backup / DR         | backup.vault                                      | 100.00**          | 0.00            | 0.00               | 100.00           | 100% missing     |
| Analytics (other)   | –                                                 | 0.00              | 0.00            | 0.00               | 0.00             | 0%               |
| Other               | –                                                 | 0.00              | 0.00            | 0.00               | 0.00             | 0%               |

Again, Log Analytics and Backup are dominated by **missing placeholders (£100/month each)** rather than the per-resource partials.

---

### 3.3 High Performance / Heavy Access Scenario

#### Main Components

- **Compute**
  - None explicitly costed (analytics engines assumed external or out of scope).

- **Data / Storage**
  - `log-blob-grs-hp`: Azure Storage (Blob / ADLS Gen2), Standard_GRS, more Hot data (30 TB Hot, 70 TB Cool, 40 TB Archive).

- **Network**
  - `log-vnet-hp`: Virtual Network (no direct charge).
  - `log-egress-hp`: Bandwidth for 5 TB/month outbound.

- **Security**
  - `log-keyvault-hp`: Azure Key Vault (Standard), 400k ops/month.

- **Monitoring / Analytics**
  - `log-la-hp`: Log Analytics workspace, 1 TB/month (sku_mismatch).

- **Backup / DR**
  - `log-backup-vault-hp`: Recovery Services vault, 300 GB metadata/config (sku_mismatch).

#### Pricing Table – High Performance

> Currency: GBP

| Scenario         | Resource ID          | Category                 | Service        | SKU (requested / resolved)        | Region     | Billing | Unit Price | Unit          | Units   | Monthly Cost | Yearly Cost | Notes |
|------------------|----------------------|--------------------------|----------------|-----------------------------------|-----------|---------|-----------:|---------------|--------:|-------------:|------------:|-------|
| high_performance | log-vnet-hp          | network.vnet             | Virtual Network| Virtual Network / Virtual Network | westeurope| payg    | 0.00       | VNet          | 1       | 0.00         | 0.00        | Logical VNet, no direct charge. |
| high_performance | log-blob-grs-hp      | storage.blob             | Storage        | Standard_GRS / Standard_GRS       | westeurope| payg    | n/a        | n/a           | n/a     | 137.00*      | 1,644.00*   | Estimated: 30 TB Hot, 70 TB Cool, 40 TB Archive. |
| high_performance | log-egress-hp        | network.egress           | Bandwidth      | n/a / Standard                    | westeurope| payg    | 0.0076     | 1 GB          | 5,000   | 38.00        | 456.00      | 5 TB/month outbound. |
| high_performance | log-keyvault-hp      | security.keyvault        | Key Vault      | standard / Standard               | westeurope| payg    | 0.0228     | 10K ops       | 40      | 0.91         | 10.94       | ~400k operations/month. |
| high_performance | log-la-hp            | monitoring.loganalytics  | Log Analytics  | PerGB2018 / Analytics Logs        | westeurope| payg    | 0.0987**   | 1 GB/Month    | 1,000   | 98.70**      | 1,184.40**  | 1 TB/month; sku_mismatch (ingestion vs retention). |
| high_performance | log-backup-vault-hp  | backup.vault             | Backup         | Standard / ADLS Gen2 Vaulted      | westeurope| payg    | 0.041**    | 10K ops       | 15      | 0.61**       | 7.38**      | 300 GB metadata/config; sku_mismatch, storage not fully modeled. |

\* Estimated.  
\** sku_mismatch.

#### Aggregated by Category – High Performance

> Currency: GBP

| High-Level Category | Included JSON Categories                          | Monthly (modeled) | Of which Priced | Of which Estimated | Of which Missing | Estimation Ratio |
|---------------------|---------------------------------------------------|-------------------:|----------------:|-------------------:|-----------------:|------------------|
| Compute             | –                                                 | 0.00              | 0.00            | 0.00               | 0.00             | 0%               |
| DB                  | –                                                 | 0.00              | 0.00            | 0.00               | 0.00             | 0%               |
| Storage             | storage.blob                                      | 137.00            | 0.00            | 137.00             | 0.00             | 100% estimated   |
| Network             | network.vnet, network.egress                      | 38.00             | 38.00           | 0.00               | 0.00             | 0%               |
| Security            | security.keyvault                                 | 0.91              | 0.91            | 0.00               | 0.00             | 0%               |
| Monitoring          | monitoring.loganalytics                           | 100.00**          | 0.00            | 0.00               | 100.00           | 100% missing     |
| Backup / DR         | backup.vault                                      | 100.00**          | 0.00            | 0.00               | 100.00           | 100% missing     |
| Analytics (other)   | –                                                 | 0.00              | 0.00            | 0.00               | 0.00             | 0%               |
| Other               | –                                                 | 0.00              | 0.00            | 0.00               | 0.00             | 0%               |

---

## 4. Resources with Pricing Issues – What to Check Manually

Across all scenarios, the following need manual verification in the Azure Pricing Calculator / Portal:

1. **Blob Storage (all scenarios)**
   - IDs: `log-blob-grs`, `log-blob-grs-co`, `log-blob-grs-hp`
   - Status: `pricing_status: "estimated"`
   - Risks:
     - Only some meters (e.g., “Data Returned for Query Acceleration”, “Data Scanned”) are used as proxies.
     - Real costs will include:
       - Per‑GB storage for Hot/Cool/Archive (including GRS uplift),
       - Per‑operation costs (read/write/list),
       - Archive rehydration and early deletion charges.
   - Action:
     - Use the **Storage (Blob) calculator** with:
       - Region: West Europe,
       - Redundancy: GRS,
       - Capacity: Hot/Cool/Archive GB as per scenario,
       - Transactions: approximate read/write/list counts,
       - Egress: align with `egress_gb`.

2. **Log Analytics (all scenarios)**
   - IDs: `log-la`, `log-la-co`, `log-la-hp`
   - Status: `pricing_status: "sku_mismatch"`, and scenario totals show **£100/month missing** per scenario.
   - Risks:
     - The resolved meter is **“Analytics Logs Data Retention”** at £0.0987/GB/month; ingestion and query costs are not fully modeled.
     - Real cost is driven by:
       - GB/day ingestion,
       - Retention beyond 31 days,
       - Search/scan volume (Data Analyzed).
   - Action:
     - Use **Azure Monitor / Log Analytics calculator**:
       - Set **GB/day ingestion** (500 GB/month ≈ 16.7 GB/day; 200 GB/month ≈ 6.7 GB/day; 1 TB/month ≈ 33.3 GB/day),
       - Set retention (30 days or more),
       - Include “Data Analyzed” if you expect heavy querying.

3. **Backup Vault (all scenarios)**
   - IDs: `log-backup-vault`, `log-backup-vault-co`, `log-backup-vault-hp`
   - Status: `pricing_status: "sku_mismatch"`, and scenario totals show **£100/month missing** per scenario.
   - Risks:
     - Only **write operations** for ADLS Gen2 Vaulted are modeled; protected instance and storage GB pricing are not.
   - Action:
     - In the **Azure Backup calculator**:
       - Model a small protected instance (e.g., 200–300 GB) per scenario,
       - Choose appropriate redundancy (LRS/GRS) for the vault,
       - Confirm that you are not backing up the full 20 TB/month log data (only metadata/config).

4. **Network Egress SKUs**
   - All egress resources (`log-egress*`) use **“Standard Inter-Availability Zone Data Transfer Out”** as a proxy.
   - Risks:
     - Real pricing depends on:
       - Internet vs inter-region vs inter-AZ,
       - Routing preference (Internet vs Microsoft Global Network).
   - Action:
     - Confirm:
       - Are logs consumed over the public Internet, via ExpressRoute, or cross-region?
       - Adjust to the correct **Bandwidth** meter in the calculator.

---

## 5. FinOps Recommendations

### 5.1 Quick Wins

1. **Tune Lifecycle Policies (Hot vs Cool vs Archive)**
   - Baseline keeps 20 TB Hot; cost_optimized keeps 10 TB; high_performance keeps 30 TB.
   - For most compliance-driven archives, **minimize Hot retention** to what’s operationally needed (e.g., 7–14 days) and push the rest to Cool/Archive.
   - This is the **largest lever** on storage cost.

2. **Control Log Analytics Ingestion**
   - Do not mirror the 20 TB/month archive into Log Analytics.
   - Keep Log Analytics for **operational telemetry only** (as modeled: 200–1,000 GB/month).
   - Use:
     - Sampling,
     - Dedicated tables with shorter retention,
     - Diagnostic settings that send **bulk logs directly to Blob** and only summaries to Log Analytics.

3. **Reduce Egress Where Possible**
   - Prefer **in-region analytics** (e.g., Azure Data Explorer, Synapse, Fabric) reading directly from Blob.
   - For external SIEMs, consider:
     - Batch exports,
     - Compression,
     - Filtering to only security-relevant events.

4. **Optimize Key Vault Usage**
   - Cache secrets in clients to reduce operations (as in cost_optimized).
   - Use **managed identities** instead of secrets where possible to reduce secret rotation overhead.

5. **Avoid Double-Backing Up the Archive**
   - You already have **GRS** for the Blob archive.
   - Keep the Backup vault limited to **config/metadata**, not the full log dataset.

### 5.2 Spot vs PAYG vs Reserved

- **Blob Storage / ADLS Gen2**
  - No “spot” concept; but you can:
    - Use **Cool/Archive** tiers (effectively a price vs access trade-off),
    - Consider **Reserved Capacity for Blob Storage** (1- or 3‑year) if 20 TB/month ingest and multi‑hundred TB at rest is stable.
  - FinOps action:
    - Once volumes stabilize, evaluate **Blob Reserved Capacity** for Hot and Cool tiers.

- **Compute (if/when added)**
  - For ingestion/processing VMs or AKS nodes (not modeled here):
    - Use **spot VMs** for non-critical batch processing,
    - Use **Reserved Instances / Savings Plans** for always-on ingestion services.

- **Log Analytics**
  - Consider **Commitment Tiers** (e.g., 100 GB/day, 200 GB/day) if ingestion is predictable.
  - This can significantly reduce per‑GB cost vs pure PAYG.

- **Current Exposure**
  - All modeled resources are **PAYG**; there is **0% reservation coverage** in the JSON.
  - Once you finalize architecture and volumes, introduce:
    - Blob Reserved Capacity,
    - Log Analytics commitment tiers,
    - Any compute reservations.

### 5.3 Right-Sizing Ideas

1. **Hot Tier Right-Sizing**
   - Baseline: 20 TB Hot; cost_optimized: 10 TB; high_performance: 30 TB.
   - Start with **baseline** and monitor:
     - Query frequency by age of data,
     - Rehydration events from Archive.
   - If most queries are within 7–14 days, reduce Hot retention accordingly.

2. **Log Analytics Right-Sizing**
   - Start with **cost_optimized** ingestion (200 GB/month) and increase only if:
     - You miss alerts,
     - Troubleshooting becomes difficult.
   - Use **table-level retention** and **data caps** to prevent runaway costs.

3. **Backup Vault Right-Sizing**
   - Keep vault size aligned with **actual metadata/config**.
   - Avoid adding large data sources (e.g., full log copies) unless there is a clear RPO/RTO requirement beyond GRS.

4. **Egress Right-Sizing**
   - Track actual egress via **Azure Cost Management + Monitor metrics**.
   - If you see sustained 5 TB/month patterns (high_performance), consider:
     - Moving consumers into the same region,
     - Using **ExpressRoute** for predictable enterprise traffic.

### 5.4 Region and Egress Considerations

- **Region Choice**
  - All scenarios use **West Europe**; your metadata says default region `uksouth`.
  - If compliance allows, compare **West Europe vs UK South** pricing:
    - Storage per‑GB,
    - Egress,
    - Log Analytics.
  - Also consider **data residency** and **latency** to your main consumers.

- **Network Egress / NAT / Gateways / Front Door**
  - Current model only prices raw **Bandwidth**.
  - In a real deployment you may also have:
    - **NAT Gateway** for outbound SNAT (per-hour + per-GB),
    - **VPN Gateway / ExpressRoute Gateway** for hybrid connectivity,
    - **Azure Front Door / CDN** if logs are exposed to external consumers.
  - These can materially add to network cost; include them in a later iteration if applicable.

- **Data Volume / Throughput Scaling**
  - Storage and Log Analytics costs scale **linearly with GB**.
  - Operations (transactions) can become significant at **hundreds of millions per month**:
    - Optimize ingestion patterns (batch writes, larger blobs),
    - Avoid excessive small reads/lists.

---

## 6. Delta Tables vs Baseline

Note: The JSON marks scenarios as “not_comparable” due to sku_mismatch, but we can still compare the **modeled totals** as a directional guide. Treat these deltas as approximate.

### 6.1 Overall Monthly / Yearly Totals

Using `modeled_total` (priced + estimated, excluding the “missing” placeholders) and also the “with estimates” totals (including missing):

> Currency: GBP

#### a) Modeled Totals (priced + estimated only)

| Scenario        | Modeled Monthly | Modeled Yearly | Δ vs Baseline (Monthly) | Δ vs Baseline (Yearly) | % Δ Monthly | % Δ Yearly |
|-----------------|----------------:|---------------:|------------------------:|------------------------:|------------:|-----------:|
| baseline        | 163.66          | 1,963.87*      | –                       | –                       | –           | –          |
| cost_optimized  | 115.83          | 1,389.94*      | -47.83                  | -573.93                 | -29.2%      | -29.2%     |
| high_performance| 175.91          | 2,111.94*      | +12.25                  | +148.07                 | +7.5%       | +7.5%      |

\* Yearly modeled totals are not explicitly given; I’ve approximated by subtracting the yearly “missing” from the scenario’s `yearly_with_estimates`. The exact numbers in JSON are:

- Baseline: `modeled_total` = 163.66/month, 1,963.87/year (4363.87 – 2400).
- Cost optimized: 115.83/month, 1,389.94/year (3789.94 – 2400).
- High performance: 175.91/month, 2,110.94/year (4510.94 – 2400).

(Your JSON shows 2,110.94; I used that.)

#### b) Totals Including Missing (as reported in `total_monthly` / `total_yearly`)

| Scenario        | Monthly (with estimates) | Yearly (with estimates) | Δ vs Baseline (Monthly) | Δ vs Baseline (Yearly) | % Δ Monthly | % Δ Yearly |
|-----------------|-------------------------:|------------------------:|------------------------:|------------------------:|------------:|-----------:|
| baseline        | 363.66                   | 4,363.87                | –                       | –                       | –           | –          |
| cost_optimized  | 315.83                   | 3,789.94                | -47.83                  | -573.93                 | -13.2%      | -13.2%     |
| high_performance| 375.91                   | 4,510.94                | +12.25                  | +147.07                 | +3.4%       | +3.4%      |

Interpretation:

- **Cost Optimized** saves ~£48/month (~13%) vs baseline, even with the same £200/month missing placeholders.
- **High Performance** adds ~£12/month (~3–4%) vs baseline, but with more Hot data and higher egress/monitoring.

### 6.2 Category-Level Monthly Deltas vs Baseline

Using the scenario `by_category.monthly_with_estimates` values.

#### a) Cost Optimized vs Baseline

> Currency: GBP

| High-Level Category | Baseline Monthly | Cost Optimized Monthly | Δ Monthly | % Δ vs Baseline |
|---------------------|-----------------:|-----------------------:|---------:|----------------:|
| Storage (blob)      | 148.00          | 108.00                 | -40.00   | -27.0%          |
| Network             | 15.20           | 7.60                   | -7.60    | -50.0%          |
| Security            | 0.46            | 0.23                   | -0.23    | -50.0%          |
| Monitoring          | 100.00          | 100.00                 | 0.00     | 0.0%            |
| Backup / DR         | 100.00          | 100.00                 | 0.00     | 0.0%            |
| Compute / DB / Other| 0.00            | 0.00                   | 0.00     | 0.0%            |

Key drivers of savings:

- **Storage**: -£40/month from more aggressive Cool/Archive.
- **Network egress**: -£7.60/month from halving outbound traffic.
- **Key Vault**: minor savings.

#### b) High Performance vs Baseline

> Currency: GBP

| High-Level Category | Baseline Monthly | High Perf Monthly | Δ Monthly | % Δ vs Baseline |
|---------------------|-----------------:|------------------:|---------:|----------------:|
| Storage (blob)      | 148.00          | 137.00            | -11.00   | -7.4%           |
| Network             | 15.20           | 38.00             | +22.80   | +150.0%         |
| Security            | 0.46            | 0.91              | +0.45    | +97.8%          |
| Monitoring          | 100.00          | 100.00            | 0.00     | 0.0%            |
| Backup / DR         | 100.00          | 100.00            | 0.00     | 0.0%            |
| Compute / DB / Other| 0.00            | 0.00              | 0.00     | 0.0%            |

Observations:

- Storage is **slightly cheaper** than baseline (more Cool vs Hot), despite more Hot than cost_optimized.
- The main uplift is **network egress** (+£22.80/month, +150%) and **Key Vault** (small absolute increase).

---

### Final Notes

- **Key Vault / Secrets Management**: Present in all scenarios; cost is small but operationally critical. Use managed identities and caching to keep operations low.
- **Log Analytics / Monitoring**: All scenarios assume a separate Log Analytics workspace; costs are currently under-modeled and dominated by missing placeholders. This is a major potential cost center; tune ingestion and retention carefully.
- **Backup Vault & Site Recovery**: Only small Recovery Services vaults are modeled for metadata/config. You are **not** backing up the full log dataset; GRS + lifecycle tiers provide durability. If you introduce Site Recovery or VM backups later, model them separately.
- **Network Egress / NAT / Gateways / Front Door**: Only raw egress is modeled. If you add NAT Gateway, VPN/ER Gateways, or Front Door/CDN, include their per‑hour and per‑GB charges; they can be material at scale.
- **Data Volume / Throughput Scaling**: Storage and monitoring costs scale with GB; operations and egress scale with access patterns. The three scenarios give you a good envelope to reason about **cost vs access** trade‑offs.