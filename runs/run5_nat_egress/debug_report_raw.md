## 1. Baseline / Recommended scenario – short narrative

The baseline design is a production AKS deployment in West Europe:

- A single AKS cluster with 10 general‑purpose Linux worker nodes, plus the managed AKS control plane.
- A dedicated Virtual Network hosting the AKS node pool and a managed NAT Gateway.
- Outbound internet access is centralized via the NAT Gateway, with 5 TB/month of egress.
- A static Standard Public IP is used (for NAT and/or ingress).
- Operational hygiene is covered with:
  - Log Analytics for AKS logs/metrics (~200 GB/month ingestion assumed),
  - Azure Key Vault for secrets, keys, and certificates,
  - A Recovery Services/Backup vault for basic backup coverage.

Cost-wise, the **dominant drivers** are internet egress (5 TB/month) and AKS compute. Monitoring and Key Vault are small but important operational costs. Some prices are missing or mismatched (notably the node SKU, public IP, and Log Analytics), so the totals include placeholders and should be validated in the Azure Pricing Calculator.

---

## 2. Other scenarios – how they differ from baseline

### Cost Optimized

Intent: keep the same topology (AKS + NAT + 5 TB egress + static IP) but reduce ongoing spend.

Key differences vs baseline:

- **Compute**:
  - Uses 10 smaller nodes (Standard_D2s_v3) instead of D4s_v3, and assumes **1‑year Reserved Instances** for the node pool.
  - Control plane remains pay‑as‑you‑go.
- **Monitoring**:
  - Log Analytics ingestion reduced from ~200 GB/month to ~80 GB/month (e.g., only warnings/errors, shorter retention).
- **Backup**:
  - Backup footprint reduced (120 GB vs 200 GB).
- **Key Vault**:
  - Fewer operations assumed (50k vs 100k ops/month).

Net effect: Modeled totals are almost identical to baseline in this dataset (because of placeholder/mismatched prices), but **in a real subscription this pattern would reduce compute and Log Analytics costs** if workloads can tolerate smaller nodes and reduced logging.

---

### High Performance

Intent: same topology and 5 TB egress, but more capacity and richer observability.

Key differences vs baseline:

- **Compute**:
  - 10 larger nodes (Standard_D8s_v3) instead of D4s_v3 for more vCPU/RAM per node.
- **Monitoring**:
  - Log Analytics ingestion doubled from 200 GB to 400 GB/month (more detailed diagnostics, container logs).
- **Backup**:
  - Larger backup footprint (300 GB vs 200 GB).
- **Key Vault**:
  - More operations (200k vs 100k ops/month) to support more secrets/keys and rotations.

Net effect: Again, modeled totals are very close to baseline due to placeholder pricing, but **in reality this pattern would significantly increase compute and Log Analytics costs** in exchange for higher performance and richer telemetry.

---

## 3. Scenario details

### 3.1 Baseline – components

**Compute**
- AKS worker nodes: 10 × (intended) `Standard_D4s_v3` Linux nodes (4 vCPU, 16 GB RAM).
- AKS managed control plane (billed per cluster-hour).

**Data / Storage**
- OS disks for nodes (Premium SSD, ~128 GB each) – assumed included in VM pricing.
- Backup vault storage (~200 GB estimated).

**Network**
- Virtual Network (no direct charge).
- Managed NAT Gateway for outbound.
- 5 TB/month internet egress via NAT.
- Static Standard Public IP (for NAT and/or ingress).

**Security**
- Azure Key Vault (Standard) for secrets, keys, certificates.

**Monitoring / Ops**
- Log Analytics workspace for AKS logs/metrics (~200 GB/month ingestion).
- (Implicit) Azure Monitor metrics; only Log Analytics is explicitly costed.

**Backup / DR**
- Recovery Services / Backup vault for AKS-related backups (config/disks).

---

### 3.2 Baseline – pricing table (resource-level)

> Note: “SKU (requested / resolved)” shows what the architecture intends vs what the pricing engine actually matched. Where they differ, treat costs as **approximate** and re‑price manually.

| Scenario | Resource ID         | Category              | Service        | SKU (requested / resolved)                          | Region     | Billing | Unit Price | Unit           | Units  | Monthly Cost | Yearly Cost | Notes |
|----------|---------------------|-----------------------|----------------|------------------------------------------------------|-----------|---------|-----------:|----------------|-------:|-------------:|------------:|-------|
| baseline | vnet-main           | network.vnet          | Virtual Network| Virtual Network / Virtual Network                   | westeurope| payg    | 0.00       | VNet           | 1.0   | 0.00         | 0.00        | No direct VNet charge. |
| baseline | aks-system-nodes    | compute.aks           | Virtual Machines| **Standard_D4s_v3** / B2pts v2 Low Priority (mismatch) | westeurope| payg    | 0.00192    | 1 Hour         | 7300.0| 14.02        | 168.19      | 10 AKS nodes; SKU mismatch – re‑price as D4s_v3. |
| baseline | aks-control-plane   | compute.aks           | Virtual Machines| AKS control plane / B2pts v2 Low Priority           | westeurope| payg    | 0.00192    | 1 Hour         | 730.0 | 1.40         | 16.82       | AKS control plane; actual AKS control-plane pricing differs. |
| baseline | nat-gateway         | network.nat           | Bandwidth      | Standard / Standard Inter-Availability Zone Data Transfer Out | westeurope| payg | 0.01       | 1 GB           | 5120.0| 51.20        | 614.40      | 5 TB/month via NAT; price used is inter‑AZ, not internet egress. |
| baseline | public-ip-static    | network.public_ip     | Public IP      | Standard / **missing**                              | westeurope| payg    | –          | –              | –     | –            | –           | Static Standard Public IP; price missing – check manually. |
| baseline | egress-bandwidth    | network.egress        | Bandwidth      | Internet egress / Standard Inter-Availability Zone Data Transfer Out | westeurope| payg | 0.01 | 1 GB | 5120.0| 51.20 | 614.40 | 5 TB/month internet egress; meter likely wrong – re‑price as “Data Transfer Out”. |
| baseline | log-analytics       | monitoring.loganalytics| Log Analytics | PerGB2018 / Analytics Logs Data Retention (mismatch) | westeurope| payg   | 0.13       | 1 GB/Month     | 200.0 | 26.00        | 312.00      | ~200 GB/month ingestion; ingestion vs retention meters mismatched. |
| baseline | keyvault-main       | security.keyvault     | Key Vault      | Standard / Standard Operations                      | westeurope| payg    | 0.03       | 10K operations | 10.0  | 0.30         | 3.60        | ~100k ops/month. |
| baseline | backup-vault        | backup.vault          | Backup         | – / ADLS Gen2 Vaulted LRS Write Operations          | westeurope| payg    | 0.054      | 10K ops        | 0.0   | 0.00         | 0.00        | 200 GB backup storage assumed; storage not actually priced here. |

---

### 3.3 Baseline – aggregated by category

I’ll map the raw categories into higher-level buckets you requested:

- **compute**: `compute.aks`
- **network**: `network.*`
- **monitoring**: `monitoring.*`
- **security**: `security.*`
- **backup/dr**: `backup.*`
- **other**: `network.vnet` (no cost here)
- (No DB or general storage services in this design.)

“Estimate ratio” = `monthly_missing / monthly_with_estimates` (how much of the category total is missing/placeholder vs modeled).

| Category    | Included raw categories                  | Monthly (with estimates) | Monthly priced | Monthly missing | Estimate ratio | Yearly (with estimates) |
|------------|-------------------------------------------|--------------------------:|---------------:|----------------:|---------------:|-------------------------:|
| compute    | compute.aks                               | 101.40                   | 1.40           | 100.00          | 0.99           | 1,216.82                 |
| network    | network.nat, network.public_ip, network.egress | 202.40              | 102.40         | 100.00          | 0.49           | 2,428.80                 |
| monitoring | monitoring.loganalytics                   | 100.00                   | 0.00           | 100.00          | 1.00           | 1,200.00                 |
| security   | security.keyvault                         | 0.30                     | 0.30           | 0.00            | 0.00           | 3.60                     |
| backup/dr  | backup.vault                              | 0.00                     | 0.00           | 0.00            | –              | 0.00                     |
| other      | network.vnet                              | 0.00                     | 0.00           | 0.00            | –              | 0.00                     |

**Observations**

- Compute and monitoring categories are **almost entirely driven by missing/mismatched pricing** (estimate ratio ~1).
- Network has real modeled egress costs, but the **public IP is missing** and the **meter used for egress is likely wrong** (inter‑AZ vs internet).
- Key Vault is fully modeled and negligible in total cost.
- Backup vault storage is not actually priced; only write operations are modeled (0 units).

---

### 3.4 Cost Optimized – components

**Compute**
- 10 × `Standard_D2s_v3` nodes (2 vCPU, 8 GB RAM) – smaller nodes.
- Node pool assumed on **1‑year Reserved Instances**.
- AKS control plane same as baseline (payg).

**Data / Storage**
- Smaller OS disks implied (640 GB total vs 1280 GB).
- Backup vault footprint reduced to ~120 GB.

**Network**
- Same: VNet, NAT Gateway, 5 TB/month egress, static Standard Public IP.

**Security**
- Key Vault Standard with ~50k operations/month.

**Monitoring / Ops**
- Log Analytics ingestion reduced to ~80 GB/month.

**Backup / DR**
- Recovery Services vault with smaller backup volume.

---

### 3.5 Cost Optimized – pricing table (resource-level)

| Scenario      | Resource ID         | Category              | Service        | SKU (requested / resolved)                          | Region     | Billing   | Unit Price | Unit           | Units | Monthly Cost | Yearly Cost | Notes |
|---------------|---------------------|-----------------------|----------------|------------------------------------------------------|-----------|-----------|-----------:|----------------|------:|-------------:|------------:|-------|
| cost_optimized| vnet-main-co        | network.vnet          | Virtual Network| Virtual Network / Virtual Network                   | westeurope| payg      | 0.00       | VNet           | 1.0  | 0.00         | 0.00        | No direct VNet charge. |
| cost_optimized| aks-nodes-co        | compute.aks           | Virtual Machines| **Standard_D2s_v3** / B2pts v2 (reservation, ambiguous UoM) | westeurope| reserved | 50.00      | 1 Hour         | 1.0  | 100.00       | 1,200.00    | 10 nodes; reservation pricing/UoM clearly wrong – re‑price as D2s_v3 RI. |
| cost_optimized| aks-control-plane-co| compute.aks           | Virtual Machines| AKS control plane / B2pts v2 Low Priority           | westeurope| payg      | 0.00192    | 1 Hour         | 730.0| 1.40         | 16.82       | Same as baseline. |
| cost_optimized| nat-gateway-co      | network.nat           | Bandwidth      | Standard / Standard Inter-Availability Zone Data Transfer Out | westeurope| payg | 0.01 | 1 GB | 5120.0| 51.20 | 614.40 | Same 5 TB/month via NAT; meter likely wrong for internet egress. |
| cost_optimized| public-ip-static-co | network.public_ip     | Public IP      | Standard / **missing**                              | westeurope| payg      | –          | –              | –    | –            | –           | Static Standard Public IP; price missing – check manually. |
| cost_optimized| egress-bandwidth-co | network.egress        | Bandwidth      | Internet egress / Standard Inter-Availability Zone Data Transfer Out | westeurope| payg | 0.01 | 1 GB | 5120.0| 51.20 | 614.40 | Same 5 TB/month; meter likely wrong. |
| cost_optimized| log-analytics-co    | monitoring.loganalytics| Log Analytics | PerGB2018 / Analytics Logs Data Retention (mismatch) | westeurope| payg     | 0.13       | 1 GB/Month     | 80.0 | 10.40        | 124.80      | ~80 GB/month ingestion; ingestion vs retention mismatch. |
| cost_optimized| keyvault-co         | security.keyvault     | Key Vault      | Standard / Standard Operations                      | westeurope| payg      | 0.03       | 10K operations | 5.0  | 0.15         | 1.80        | ~50k ops/month. |
| cost_optimized| backup-vault-co     | backup.vault          | Backup         | – / ADLS Gen2 Vaulted LRS Write Operations          | westeurope| payg      | 0.054      | 10K ops        | 0.0  | 0.00         | 0.00        | 120 GB backup storage assumed; storage not priced. |

---

### 3.6 Cost Optimized – aggregated by category

(Using the scenario’s `by_category` totals.)

| Category    | Included raw categories                  | Monthly (with estimates) | Monthly priced | Monthly missing | Estimate ratio | Yearly (with estimates) |
|------------|-------------------------------------------|--------------------------:|---------------:|----------------:|---------------:|-------------------------:|
| compute    | compute.aks                               | 101.40                   | 1.40           | 100.00          | 0.99           | 1,216.82                 |
| network    | network.nat, network.public_ip, network.egress | 202.40              | 102.40         | 100.00          | 0.49           | 2,428.80                 |
| monitoring | monitoring.loganalytics                   | 100.00                   | 0.00           | 100.00          | 1.00           | 1,200.00                 |
| security   | security.keyvault                         | 0.15                     | 0.15           | 0.00            | 0.00           | 1.80                     |
| backup/dr  | backup.vault                              | 0.00                     | 0.00           | 0.00            | –              | 0.00                     |
| other      | network.vnet                              | 0.00                     | 0.00           | 0.00            | –              | 0.00                     |

**Note:** The category totals are effectively copied from baseline in the JSON, so they don’t reflect the intended savings from smaller nodes and reduced logging. Treat them as placeholders.

---

### 3.7 High Performance – components

**Compute**
- 10 × `Standard_D8s_v3` nodes (8 vCPU, 32 GB RAM) – larger nodes for higher throughput.
- AKS control plane same as baseline (payg).

**Data / Storage**
- Larger OS disks implied (256 GB each).
- Backup vault footprint increased to ~300 GB.

**Network**
- Same: VNet, NAT Gateway, 5 TB/month egress, static Standard Public IP.
- Higher assumed peak throughput (400 Mbps) but same volume.

**Security**
- Key Vault Standard with ~200k operations/month.

**Monitoring / Ops**
- Log Analytics ingestion increased to ~400 GB/month.

**Backup / DR**
- Recovery Services vault with larger backup volume.

---

### 3.8 High Performance – pricing table (resource-level)

| Scenario        | Resource ID         | Category              | Service        | SKU (requested / resolved)                          | Region     | Billing | Unit Price | Unit           | Units  | Monthly Cost | Yearly Cost | Notes |
|-----------------|---------------------|-----------------------|----------------|------------------------------------------------------|-----------|---------|-----------:|----------------|-------:|-------------:|------------:|-------|
| high_performance| vnet-main-hp        | network.vnet          | Virtual Network| Virtual Network / Virtual Network                   | westeurope| payg    | 0.00       | VNet           | 1.0   | 0.00         | 0.00        | No direct VNet charge. |
| high_performance| aks-nodes-hp        | compute.aks           | Virtual Machines| **Standard_D8s_v3** / B2pts v2 Low Priority (mismatch) | westeurope| payg | 0.00192    | 1 Hour         | 7300.0| 14.02        | 168.19      | 10 large nodes; re‑price as D8s_v3. |
| high_performance| aks-control-plane-hp| compute.aks           | Virtual Machines| AKS control plane / B2pts v2 Low Priority           | westeurope| payg    | 0.00192    | 1 Hour         | 730.0 | 1.40         | 16.82       | Same as baseline. |
| high_performance| nat-gateway-hp      | network.nat           | Bandwidth      | Standard / Standard Inter-Availability Zone Data Transfer Out | westeurope| payg | 0.01 | 1 GB | 5120.0| 51.20 | 614.40 | Same 5 TB/month; meter likely wrong for internet egress. |
| high_performance| public-ip-static-hp | network.public_ip     | Public IP      | Standard / **missing**                              | westeurope| payg    | –          | –              | –     | –            | –           | Static Standard Public IP; price missing – check manually. |
| high_performance| egress-bandwidth-hp | network.egress        | Bandwidth      | Internet egress / Standard Inter-Availability Zone Data Transfer Out | westeurope| payg | 0.01 | 1 GB | 5120.0| 51.20 | 614.40 | Same 5 TB/month; meter likely wrong. |
| high_performance| log-analytics-hp    | monitoring.loganalytics| Log Analytics | PerGB2018 / Analytics Logs Data Retention (mismatch) | westeurope| payg   | 0.13       | 1 GB/Month     | 400.0 | 52.00        | 624.00      | ~400 GB/month ingestion; ingestion vs retention mismatch. |
| high_performance| keyvault-hp         | security.keyvault     | Key Vault      | Standard / Standard Operations                      | westeurope| payg    | 0.03       | 10K operations | 20.0  | 0.60         | 7.20        | ~200k ops/month. |
| high_performance| backup-vault-hp     | backup.vault          | Backup         | – / ADLS Gen2 Vaulted LRS Write Operations          | westeurope| payg    | 0.054      | 10K ops        | 0.0   | 0.00         | 0.00        | 300 GB backup storage assumed; storage not priced. |

---

### 3.9 High Performance – aggregated by category

(Again, using the scenario’s `by_category` totals.)

| Category    | Included raw categories                  | Monthly (with estimates) | Monthly priced | Monthly missing | Estimate ratio | Yearly (with estimates) |
|------------|-------------------------------------------|--------------------------:|---------------:|----------------:|---------------:|-------------------------:|
| compute    | compute.aks                               | 101.40                   | 1.40           | 100.00          | 0.99           | 1,216.82                 |
| network    | network.nat, network.public_ip, network.egress | 202.40              | 102.40         | 100.00          | 0.49           | 2,428.80                 |
| monitoring | monitoring.loganalytics                   | 100.00                   | 0.00           | 100.00          | 1.00           | 1,200.00                 |
| security   | security.keyvault                         | 0.60                     | 0.60           | 0.00            | 0.00           | 7.20                     |
| backup/dr  | backup.vault                              | 0.00                     | 0.00           | 0.00            | –              | 0.00                     |
| other      | network.vnet                              | 0.00                     | 0.00           | 0.00            | –              | 0.00                     |

Again, these category totals don’t reflect the intended higher compute and logging costs; they’re placeholders.

---

## 4. Resources where pricing failed or is clearly wrong

You should **manually validate** these in the Azure Pricing Calculator or Portal:

1. **AKS worker nodes – all scenarios**
   - Baseline: `aks-system-nodes` – requested `Standard_D4s_v3`, resolved to `B2pts v2 Low Priority`.
   - Cost Optimized: `aks-nodes-co` – requested `Standard_D2s_v3`, resolved to `B2pts v2` with **$50/hour** reservation (clearly wrong).
   - High Performance: `aks-nodes-hp` – requested `Standard_D8s_v3`, resolved to `B2pts v2 Low Priority`.
   - Action: Re‑price as:
     - West Europe, Linux, D2s_v3 / D4s_v3 / D8s_v3,
     - 730 hours/month,
     - Choose pay‑as‑you‑go or 1/3‑year RI as appropriate.

2. **AKS control plane – all scenarios**
   - `aks-control-plane*` resources priced as a generic VM SKU.
   - Action: Use **AKS pricing** (per cluster-hour, free tier vs standard tier) instead of VM pricing.

3. **Public IP – all scenarios**
   - `public-ip-static`, `public-ip-static-co`, `public-ip-static-hp` – pricing status `missing`.
   - Action: Price a **Standard Public IP (static)** in West Europe (per IP/hour + any data processing if applicable).

4. **Internet egress – all scenarios**
   - `nat-gateway*` and `egress-bandwidth*` use meter `Standard Inter-Availability Zone Data Transfer Out` at $0.01/GB.
   - For 5 TB/month to the internet, you should:
     - Use **“Data Transfer Out” (internet)** pricing for West Europe,
     - Consider tiered pricing (first X GB at one rate, next tier cheaper).
   - Action: Re‑price 5 TB/month as **internet egress**, not inter‑AZ.

5. **Log Analytics – all scenarios**
   - `log-analytics*` use **Data Retention** meter at $0.13/GB/month, but the notes talk about **ingestion**.
   - Real pricing:
     - Ingestion: per GB,
     - Retention beyond 31 days: per GB-month.
   - Action: For each scenario, price:
     - Ingestion GB/month (80 / 200 / 400 GB),
     - Retention period (e.g., 30 vs 90 days) separately.

6. **Backup vault – all scenarios**
   - `backup-vault*` only model **write operations**, with 0 units.
   - Real cost is dominated by **backup storage GB** and **protected instance** tiers.
   - Action: Price:
     - Backup storage (LRS/GRS) for 120 / 200 / 300 GB,
     - Protected instances (e.g., per VM or per disk).

---

## 5. FinOps recommendations

### 5.1 Quick wins

1. **Fix egress pricing and monitor it**
   - 5 TB/month internet egress is a major cost driver.
   - Ensure you’re using the correct **Data Transfer Out (internet)** meter and tiered pricing.
   - Implement:
     - Caching/CDN (Azure Front Door / CDN) if traffic is web‑facing.
     - Compression and protocol optimization.
     - Avoid chatty cross‑region or cross‑cloud calls.

2. **Right‑size Log Analytics**
   - Baseline assumes 200 GB/month; HP assumes 400 GB/month.
   - Quick levers:
     - Reduce noisy logs (debug/trace) and high‑cardinality metrics.
     - Use **table‑level retention** and archive for long‑term logs.
     - Use **Daily Cap** and alerting on ingestion spikes.

3. **Validate node sizing vs workload**
   - If workloads are CPU/memory light, the **Cost Optimized** pattern (D2s_v3) with autoscaling can save money.
   - If workloads are heavy, the **High Performance** pattern (D8s_v3) may be more efficient per unit of work (fewer nodes, less overhead).

4. **Key Vault usage**
   - Costs are small, but:
     - Use **managed identities** and **AKS secrets store CSI driver** to avoid unnecessary secret fetches.
     - Avoid polling patterns that hammer Key Vault.

5. **Backup tuning**
   - Ensure you’re not over‑retaining backups for non‑critical workloads.
   - Use appropriate redundancy (LRS vs GRS) based on RPO/RTO requirements.

---

### 5.2 Spot vs Pay‑as‑you‑go vs Reserved

**Current modeled state**

- Baseline & High Performance:
  - Nodes modeled as payg (but with wrong SKU).
  - Control plane payg.
- Cost Optimized:
  - Nodes modeled as **reserved**, but with clearly incorrect reservation pricing.

**Recommendations**

1. **Baseline scenario**
   - If the cluster is **24×7 production**:
     - Target **60–80% of steady‑state node capacity** with **1‑year or 3‑year Reserved Instances** (or Savings Plan).
     - Leave the remaining 20–40% on payg for autoscaling bursts.
   - Consider **Spot nodes** only for:
     - Non‑critical batch jobs,
     - Stateless workloads that can tolerate eviction.

2. **Cost Optimized scenario**
   - This is the best candidate for **RI/Savings Plan**:
     - Smaller nodes (D2s_v3) with predictable usage.
     - Lock in 1‑year RI for the base 10 nodes if they are always on.
   - Ensure you:
     - Price **Linux D2s_v3 RI** in West Europe correctly,
     - Compare 1‑year vs 3‑year RI vs Savings Plan.

3. **High Performance scenario**
   - Larger nodes (D8s_v3) are more expensive; RI savings are more impactful.
   - If performance demand is steady:
     - Strong case for **3‑year RI** or Savings Plan for the base capacity.
   - For bursty high‑performance workloads:
     - Consider a **mixed pool**: some D8s_v3 on RI, some on payg, and optional Spot for non‑critical jobs.

---

### 5.3 Right‑sizing ideas

1. **Node size and count**
   - Benchmark your workloads:
     - If CPU/memory utilization is consistently <40–50% on D4s_v3, consider D2s_v3 or fewer nodes.
     - If utilization is >70–80% and you see scheduling pressure, D8s_v3 or more nodes may be justified.
   - Use **cluster autoscaler** and **pod requests/limits** to drive efficient bin‑packing.

2. **Pod density and bin‑packing**
   - Ensure pod resource requests are realistic (not over‑provisioned).
   - Use **Vertical Pod Autoscaler** or recommendations to tune requests.

3. **Log Analytics**
   - Right‑size:
     - Ingestion volume (filter noisy sources),
     - Retention per table (short for high‑volume, long for audit/security).

4. **Backup**
   - Right‑size retention and redundancy:
     - Shorter retention for non‑critical namespaces/volumes,
     - LRS instead of GRS where DR requirements allow.

---

### 5.4 Region and egress considerations

1. **Region choice (West Europe)**
   - West Europe is a common production region; pricing is mid‑range.
   - If your users or upstream systems are in another region:
     - Consider **co‑locating** workloads to reduce cross‑region egress.
     - Be aware of **inter‑region data transfer** costs if you replicate data.

2. **Egress via NAT vs Front Door / Gateway**
   - NAT Gateway centralizes outbound IPs; cost is mainly data volume.
   - For **inbound web traffic**, consider:
     - Azure Front Door or Application Gateway + WAF:
       - Additional cost, but can reduce origin egress via caching and improve security.
   - For **API‑only** workloads, API Management may add cost but centralizes control and can reduce chattiness.

3. **Data‑volume scaling**
   - Egress, Log Analytics, and Backup costs all **scale linearly with GB**:
     - If traffic doubles to 10 TB/month, expect egress costs to roughly double.
     - If log volume doubles, Log Analytics costs double unless you cap or filter.
     - If backup retention doubles, backup storage costs double.

---

## 6. Delta tables vs baseline

Because of SKU mismatches and placeholder category totals, these deltas are **very small** and **not representative** of the real architectural differences. Treat them as indicative only of the current JSON, not of real Azure billing.

### 6.1 Overall totals – priced vs with estimates

Using `totals` from each scenario:

| Scenario        | Metric                    | Baseline | Cost Optimized | Δ vs Baseline | Δ % vs Baseline |
|----------------|---------------------------|---------:|---------------:|--------------:|----------------:|
| **Monthly – priced only** |                 | 104.10  | 103.95        | -0.15         | -0.14%          |
| **Monthly – with estimates** |             | 404.10  | 403.95        | -0.15         | -0.04%          |
| **Yearly – priced only**  |                | 1,249.22| 1,247.42      | -1.80         | -0.14%          |
| **Yearly – with estimates** |             | 4,849.22| 4,847.42      | -1.80         | -0.04%          |

| Scenario        | Metric                    | Baseline | High Performance | Δ vs Baseline | Δ % vs Baseline |
|----------------|---------------------------|---------:|-----------------:|--------------:|----------------:|
| **Monthly – priced only** |                 | 104.10  | 104.40          | +0.30         | +0.29%          |
| **Monthly – with estimates** |             | 404.10  | 404.40          | +0.30         | +0.07%          |
| **Yearly – priced only**  |                | 1,249.22| 1,252.82        | +3.60         | +0.29%          |
| **Yearly – with estimates** |             | 4,849.22| 4,852.82        | +3.60         | +0.07%          |

Again, in a real pricing exercise, you should expect **much larger deltas** between D2s_v3 vs D4s_v3 vs D8s_v3 and between 80 vs 200 vs 400 GB/month of Log Analytics ingestion.

---

### 6.2 Category-level monthly deltas vs baseline

Using each scenario’s `by_category.monthly_with_estimates`:

#### Cost Optimized vs Baseline

| Category    | Baseline Monthly | Cost Optimized Monthly | Δ Monthly | Δ % vs Baseline |
|------------|-----------------:|-----------------------:|---------:|----------------:|
| compute    | 101.40           | 101.40                 | 0.00     | 0.0%            |
| network    | 202.40           | 202.40                 | 0.00     | 0.0%            |
| monitoring | 100.00           | 100.00                 | 0.00     | 0.0%            |
| security   | 0.30             | 0.15                   | -0.15    | -50.0%          |
| backup/dr  | 0.00             | 0.00                   | 0.00     | –               |
| other      | 0.00             | 0.00                   | 0.00     | –               |

#### High Performance vs Baseline

| Category    | Baseline Monthly | High Performance Monthly | Δ Monthly | Δ % vs Baseline |
|------------|-----------------:|-------------------------:|---------:|----------------:|
| compute    | 101.40           | 101.40                   | 0.00     | 0.0%            |
| network    | 202.40           | 202.40                   | 0.00     | 0.0%            |
| monitoring | 100.00           | 100.00                   | 0.00     | 0.0%            |
| security   | 0.30             | 0.60                     | +0.30    | +100.0%         |
| backup/dr  | 0.00             | 0.00                     | 0.00     | –               |
| other      | 0.00             | 0.00                     | 0.00     | –               |

**Interpretation**

- The JSON’s category totals don’t change for compute/network/monitoring across scenarios, so the deltas don’t reflect the intended architectural differences.
- Only Key Vault (security) shows small deltas, which are negligible in the overall TCO.

---

## 7. Summary

- Architecturally, all three scenarios share the same **AKS + NAT + 5 TB egress + static IP + Key Vault + Log Analytics + Backup** pattern.
- The **real cost differences** should come from:
  - Node size (D2s_v3 vs D4s_v3 vs D8s_v3),
  - Reservation vs payg,
  - Log Analytics ingestion volume,
  - Backup storage and retention.
- The current pricing data has several **mismatches and missing values**, especially for:
  - VM SKUs,
  - Public IP,
  - Internet egress meters,
  - Log Analytics ingestion vs retention,
  - Backup storage.

For a production‑grade estimate, re‑price those items in the Azure Pricing Calculator, then re‑run the comparison. The FinOps levers to focus on are: **right‑sizing nodes, using RI/Savings Plans for steady capacity, controlling egress, and tuning Log Analytics and backup retention.**