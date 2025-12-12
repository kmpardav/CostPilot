## 1. Baseline / Recommended scenario – short narrative

The **baseline** is a production‑grade Azure architecture for an e‑commerce site in West Europe:

- Traffic enters via an **Application Gateway WAF v2** with a **Standard Public IP**, doing SSL termination and path‑based routing to the web tier.
- The web tier runs on a **Premium v3 App Service Plan (Linux) with 2 instances**, hosting the e‑commerce Web App. The plan is integrated with a **VNet** to reach data services privately.
- **Azure SQL Database GP Gen5 2 vCores** is the transactional store (orders, customers, catalog), accessed via a **Private Endpoint**.
- **Azure Cache for Redis Standard C1** accelerates reads and session handling, also via **Private Endpoint**.
- **Blob Storage (GRS)** stores product images, static content, and some logs.
- **Key Vault (Standard)** manages secrets and TLS certificates for App Gateway and App Service.
- **Log Analytics** collects platform and application logs; **Backup (Recovery Services Vault)** and **Azure Site Recovery (ASR placeholder)** cover backup/DR.
- **NAT + general bandwidth** cover outbound traffic and internet egress.

Everything is **pay‑as‑you‑go**, with private endpoints and monitoring in place. Many prices in the JSON are missing or approximated, so the numeric totals should be treated as **order‑of‑magnitude only**, not as a final quote.

---

## 2. Other scenarios – summary and differences

### Cost Optimized

Design intent: **minimize cost** for lower traffic or early‑stage production.

Key differences vs baseline:

- **App Service**:  
  - Baseline: Premium v3 (P1v3), 2 instances.  
  - Cost‑optimized: **Standard S1, 1 instance** → lower SLA, less performance, no Premium features.
- **Redis**:  
  - Baseline: Standard C1 (HA with replica).  
  - Cost‑optimized: **Basic C0 (no replica, no SLA)** → cheaper but cache loss on restart is expected.
- **SQL**: same GP Gen5 2 vCores, but **reduced storage (64 GB vs 128 GB)**.
- **Storage**: **LRS instead of GRS**, smaller capacity.
- **Log Analytics**: lower ingestion (80 GB vs 200 GB).
- **Backup**: smaller backup footprint.
- **Network egress & NAT**: lower volumes (1.5 TB vs 3 TB, 200 GB vs 500 GB).

Indicative totals (with all the caveats about missing prices):

- Baseline: ~**967 €/month** (with estimates).  
- Cost‑optimized: ~**883 €/month** → about **9% cheaper** on the modeled total, but the majority of both totals is still unpriced/estimated.

### High Performance / Scalable

Design intent: **handle significantly higher traffic and load**.

Key differences vs baseline:

- **App Service**:  
  - Baseline: Premium v3 P1v3, 2 instances.  
  - High‑perf: **Premium v3 P2v3, 4 instances** → much more CPU/memory and scale.
- **Redis**:  
  - Baseline: Standard C1.  
  - High‑perf: **Premium P1** with persistence and higher throughput.
- **SQL**: same GP Gen5 2 vCores, but **more storage (256 GB)** and IOPS.
- **Private Endpoints**: **two** for SQL and Redis (vs one) to support more subnets/regions.
- **Storage**: **GZRS** with larger capacity and higher egress.
- **Log Analytics**: higher ingestion (400 GB vs 200 GB).
- **Key Vault**: **Premium** (HSM‑backed keys).
- **Backup**: larger backup footprint.
- **Network egress & NAT**: much higher volumes (7 TB vs 3 TB, 1 TB vs 500 GB).

Indicative totals:

- Baseline: ~**967 €/month** (with estimates).  
- High‑perf: ~**1,113 €/month** → about **15% more** on the modeled total, but again dominated by missing/estimated items.

---

## 3. Scenario details

### 3.1 Baseline / Recommended

#### Main components

- **Compute**
  - `appservice-plan-prod`: App Service Plan, Premium v3 (Linux), 2 instances.
  - `appservice-webapp`: Web App (logical) on that plan.

- **Data / DB / Cache**
  - `sql-db-ecommerce`: Azure SQL Database, GP Gen5, 2 vCores, 128 GB.
  - `redis-cache-prod`: Azure Cache for Redis, Standard C1.

- **Storage**
  - `storage-blob-content`: GPv2 Storage (GRS), 200 GB (150 GB hot, 50 GB cool).

- **Network**
  - `vnet-main`: main VNet with subnets for App GW, App Service integration, private endpoints.
  - `appgw-waf-v2`: Application Gateway WAF v2.
  - `appgw-public-ip`: Standard Public IP for App GW.
  - `sql-db-private-endpoint`: Private Endpoint for SQL.
  - `redis-private-endpoint`: Private Endpoint for Redis.
  - `nat-egress`: NAT outbound for private resources.
  - `network-egress-general`: general internet egress.

- **Security**
  - `keyvault-main`: Key Vault Standard for secrets and certificates.

- **Monitoring / Analytics**
  - `log-analytics-workspace`: Log Analytics workspace for logs and metrics.

- **Backup / DR**
  - `backup-vault-main`: Recovery Services Vault for backups (App Service content, storage, etc.).
  - `asr-dr-config`: Azure Site Recovery placeholder.

- **Other**
  - None beyond logical resources above.

#### Pricing table – Baseline

> Note: Many prices are missing or mismatched; treat this as **illustrative**, not authoritative.

| Scenario | Resource ID              | Category               | Service        | SKU (requested / resolved)                         | Region      | Billing | Unit Price | Unit        | Units  | Monthly Cost | Yearly Cost | Notes |
|---------|--------------------------|------------------------|----------------|----------------------------------------------------|-------------|--------|-----------|------------|--------|-------------|------------|-------|
| baseline | vnet-main               | network.vnet           | Virtual Network | Virtual Network / Virtual Network                  | westeurope  | payg   | 0.00      | VNet       | 1      | 0.00        | 0.00       | No direct charge; required for private endpoints. |
| baseline | appgw-waf-v2            | network.appgw          | Application Gateway | WAF_v2 / Standard Capacity Units (discounted)  | westeurope  | payg   | 0.0069    | 1/Hour     | 730    | 5.04        | 60.44      | Only capacity unit priced; real AppGW WAF v2 cost will be higher (fixed + capacity + L7 traffic). |
| baseline | appgw-public-ip         | network.public_ip      | Public IP      | Standard / (missing)                               | westeurope  | payg   | –         | –          | –      | –           | –          | Standard Public IP – price missing. |
| baseline | appservice-plan-prod    | appservice             | Azure App Service | P1v3 / P0v3 App (Linux)                         | westeurope  | payg   | 0.077     | 1 Hour     | 1460   | 112.42      | 1349.04    | SKU mismatch; actual P1v3 price will be higher than P0v3. |
| baseline | appservice-webapp       | appservice             | Azure App Service | (logical) / included                            | westeurope  | payg   | 0.00      | Included   | 1      | 0.00        | 0.00       | Web App billed via plan. |
| baseline | redis-cache-prod        | cache.redis            | Azure Cache for Redis | Standard_C1 / (missing)                      | westeurope  | payg   | –         | –          | –      | –           | –          | Standard C1 Redis – price missing. |
| baseline | sql-db-ecommerce        | db.sql                 | SQL Database   | GP_Gen5_2 / Gen5 vCore (1–2 vCores)               | westeurope  | payg   | 0.2896*   | 1 Hour     | 730   | 105.70      | 1268.45    | GP Gen5 2 vCores; JSON shows 0.1448 (1 vCore) but cost uses 2 vCores. |
| baseline | sql-db-private-endpoint | network.gateway        | Private Link   | PrivateEndpoint / (missing)                       | westeurope  | payg   | –         | –          | –      | –           | –          | Private Endpoint for SQL – endpoint + data processed not priced. |
| baseline | redis-private-endpoint  | network.gateway        | Private Link   | PrivateEndpoint / (missing)                       | westeurope  | payg   | –         | –          | –      | –           | –          | Private Endpoint for Redis – not priced. |
| baseline | storage-blob-content    | storage.blob           | Storage        | Standard_GRS / ADLS Gen2 (hot+cool)               | westeurope  | payg   | ~0.0007–0.0019 | 1 GB   | 200   | 0.20        | 2.40       | Estimated from hot/cool GB; excludes transactions and egress. |
| baseline | log-analytics-workspace | monitoring.loganalytics| Log Analytics  | PerGB2018 / Analytics Logs                        | westeurope  | payg   | 0.1124    | 1 GB/Month | 200   | 22.48       | 269.76     | Cost shown is for retention; ingestion/analyze charges likely higher. |
| baseline | keyvault-main           | security.keyvault      | Key Vault      | standard / Standard Operations                    | westeurope  | payg   | 0.0259    | 10K ops    | 200   | 5.18        | 62.16      | ~2M operations/month. |
| baseline | backup-vault-main       | backup.vault           | Backup         | Standard / ADLS Gen2 Vaulted LRS Writes           | westeurope  | payg   | 0.0467    | 10K ops    | 10    | 0.47        | 5.60       | Only write ops priced; backup storage itself not modeled. |
| baseline | asr-dr-config           | dr.asr                 | Azure Site Recovery | (placeholder) / System Center VM replicated | westeurope  | payg   | 13.8378   | 1/Month    | 1     | 13.84       | 166.05     | Placeholder; can be removed if DR out of scope. |
| baseline | nat-egress              | network.nat            | Bandwidth      | Standard / Inter‑AZ Data Transfer Out             | westeurope  | payg   | 0.0086    | 1 GB       | 500   | 4.30        | 51.60      | Approximates outbound via NAT; real NAT gateway has per‑hour + data. |
| baseline | network-egress-general  | network.egress         | Bandwidth      | Standard / Inter‑AZ Data Transfer Out             | westeurope  | payg   | 0.0086    | 1 GB       | 3000  | 25.80       | 309.60     | 3 TB/month egress; real internet egress pricing is tiered and different from inter‑AZ. |

\*Effective 2‑vCore price inferred from monthly cost.

#### Aggregated by category (Baseline)

I’ll map Azure categories into higher‑level buckets:

- **Compute**: `appservice`  
- **DB**: `db.sql`, `cache.redis`  
- **Storage**: `storage.blob`  
- **Network**: `network.vnet`, `network.appgw`, `network.public_ip`, `network.gateway`, `network.nat`, `network.egress`  
- **Monitoring/Analytics**: `monitoring.loganalytics`  
- **Security**: `security.keyvault`  
- **Backup/DR**: `backup.vault`, `dr.asr`  
- **Other**: (none)

From `totals.by_category` (monthly, with estimates):

| Bucket            | Included Categories                                      | Monthly (with est.) | Of which priced+est. | Missing part | Est. share of bucket* |
|-------------------|----------------------------------------------------------|----------------------|----------------------|-------------|------------------------|
| Compute           | appservice                                               | 112.42              | 112.42               | 0.00        | ~0% (but SKU mismatch) |
| DB                | db.sql, cache.redis                                      | 205.70              | 105.70               | 100.00      | ~0% (all db.sql priced; Redis fully missing) |
| Storage           | storage.blob                                             | 0.20                | 0.20                 | 0.00        | ~100% (all estimated) |
| Network           | network.\*                                               | 430.10              | 35.14                | 394.96      | ~8% (most network costs missing/approx) |
| Monitoring/Analytics | monitoring.loganalytics                               | 100.00              | 22.48                | 77.52       | ~22% (retention priced; ingestion/analyze missing) |
| Security          | security.keyvault                                        | 5.18                | 5.18                 | 0.00        | ~0% (fully priced) |
| Backup/DR         | backup.vault, dr.asr                                     | 113.84              | 14.31                | 99.53       | ~1–2% (backup storage mostly missing) |
| Other             | –                                                        | 0.00                | 0.00                 | 0.00        | – |

\*“Est. share” here means “how much of this bucket is explicitly marked estimated vs priced”; but note that many “priced” values are still **incomplete** (e.g., AppGW, NAT, Log Analytics ingestion).

---

### 3.2 Cost Optimized scenario

#### Main components

- **Compute**
  - `appservice-plan-co`: App Service Plan Standard S1, 1 instance.
  - `appservice-webapp-co`: Web App on that plan.

- **Data / DB / Cache**
  - `sql-db-ecommerce-co`: Azure SQL Database GP Gen5 2 vCores, 64 GB.
  - `redis-cache-co`: Azure Cache for Redis Basic C0 (no replica).

- **Storage**
  - `storage-blob-content-co`: Storage LRS, 100 GB (60 hot, 40 cool).

- **Network**
  - `vnet-main-co`: main VNet.
  - `appgw-waf-v2-co`: App Gateway WAF v2 (lower traffic).
  - `appgw-public-ip-co`: Standard Public IP.
  - `sql-db-private-endpoint-co`, `redis-private-endpoint-co`: Private Endpoints.
  - `nat-egress-co`: NAT outbound (200 GB).
  - `network-egress-co`: general egress (1.5 TB).

- **Security**
  - `keyvault-co`: Key Vault Standard (fewer operations).

- **Monitoring / Analytics**
  - `log-analytics-co`: Log Analytics with ~80 GB/month ingestion/retention.

- **Backup / DR**
  - `backup-vault-co`: smaller backup footprint.

#### Pricing table – Cost Optimized

| Scenario      | Resource ID               | Category               | Service        | SKU (requested / resolved)                         | Region      | Billing | Unit Price | Unit        | Units | Monthly Cost | Yearly Cost | Notes |
|--------------|---------------------------|------------------------|----------------|----------------------------------------------------|-------------|--------|-----------|------------|-------|-------------|------------|-------|
| cost_optimized | vnet-main-co            | network.vnet           | Virtual Network | Virtual Network / Virtual Network                  | westeurope  | payg   | 0.00      | VNet       | 1     | 0.00        | 0.00       | No direct charge. |
| cost_optimized | appgw-waf-v2-co         | network.appgw          | Application Gateway | WAF_v2 / Standard Capacity Units (discounted)  | westeurope  | payg   | 0.0069    | 1/Hour     | 730   | 5.04        | 60.44      | Same pricing caveats as baseline. |
| cost_optimized | appgw-public-ip-co      | network.public_ip      | Public IP      | Standard / (missing)                               | westeurope  | payg   | –         | –          | –     | –           | –          | Public IP price missing. |
| cost_optimized | appservice-plan-co      | appservice             | Azure App Service | S1 / S1 App (Linux)                             | westeurope  | payg   | 0.0822    | 1 Hour     | 730   | 60.01       | 720.07     | Standard S1, 1 instance. |
| cost_optimized | appservice-webapp-co    | appservice             | Azure App Service | (logical) / included                            | westeurope  | payg   | 0.00      | Included   | 1     | 0.00        | 0.00       | Web App billed via plan. |
| cost_optimized | redis-cache-co          | cache.redis            | Azure Cache for Redis | Basic_C0 / (missing)                         | westeurope  | payg   | –         | –          | –     | –           | –          | Basic C0 Redis – price missing. |
| cost_optimized | sql-db-ecommerce-co     | db.sql                 | SQL Database   | GP_Gen5_2 / Gen5 vCore (1–2 vCores)               | westeurope  | payg   | 0.2896*   | 1 Hour     | 730  | 105.70      | 1268.45    | Same compute as baseline; storage reduced. |
| cost_optimized | sql-db-private-endpoint-co | network.gateway     | Private Link   | PrivateEndpoint / (missing)                       | westeurope  | payg   | –         | –          | –     | –           | –          | Private Endpoint for SQL – not priced. |
| cost_optimized | redis-private-endpoint-co | network.gateway      | Private Link   | PrivateEndpoint / (missing)                       | westeurope  | payg   | –         | –          | –     | –           | –          | Private Endpoint for Redis – not priced. |
| cost_optimized | storage-blob-content-co | storage.blob           | Storage        | Standard_LRS / ADLS Gen2 (hot+cool)               | westeurope  | payg   | ~0.0007–0.0019 | 1 GB   | 100  | 0.12        | 1.42       | Estimated; smaller and LRS vs baseline GRS. |
| cost_optimized | log-analytics-co        | monitoring.loganalytics| Log Analytics  | PerGB2018 / Analytics Logs                        | westeurope  | payg   | 0.1124    | 1 GB/Month | 80   | 8.99        | 107.90     | Retention only; ingestion/analyze not modeled. |
| cost_optimized | keyvault-co             | security.keyvault      | Key Vault      | standard / Standard Operations                    | westeurope  | payg   | 0.0259    | 10K ops    | 100  | 2.59        | 31.08      | ~1M operations/month. |
| cost_optimized | backup-vault-co         | backup.vault           | Backup         | Standard / ADLS Gen2 Vaulted LRS Writes           | westeurope  | payg   | 0.0467    | 10K ops    | 5    | 0.23        | 2.80       | Only write ops priced; storage not modeled. |
| cost_optimized | nat-egress-co           | network.nat            | Bandwidth      | Standard / Inter‑AZ Data Transfer Out             | westeurope  | payg   | 0.0086    | 1 GB       | 200  | 1.72        | 20.64      | Approximated NAT egress. |
| cost_optimized | network-egress-co       | network.egress         | Bandwidth      | Standard / Inter‑AZ Data Transfer Out             | westeurope  | payg   | 0.0086    | 1 GB       | 1500 | 12.90       | 154.80     | 1.5 TB/month egress; real internet egress differs. |

\*Again, inferred.

#### Aggregated by category (Cost Optimized)

From `totals.by_category` (monthly, with estimates):

| Bucket            | Included Categories                                      | Monthly (with est.) | Priced+est. | Missing | Est. share of bucket* |
|-------------------|----------------------------------------------------------|----------------------|------------|---------|------------------------|
| Compute           | appservice                                               | 60.01               | 60.01      | 0.00    | ~0% (fully priced) |
| DB                | db.sql, cache.redis                                      | 205.70              | 105.70     | 100.00  | ~0% (Redis missing) |
| Storage           | storage.blob                                             | 0.12                | 0.12       | 0.00    | ~100% (estimated) |
| Network           | network.\*                                               | 414.62              | 19.66      | 394.96  | ~5% (most network missing/approx) |
| Monitoring/Analytics | monitoring.loganalytics                               | 100.00              | 8.99       | 91.01   | ~9% (retention priced only) |
| Security          | security.keyvault                                        | 2.59                | 2.59       | 0.00    | ~0% |
| Backup/DR         | backup.vault                                             | 100.00              | 0.23       | 99.77   | ~0% (backup storage missing) |
| Other             | –                                                        | 0.00                | 0.00       | 0.00    | – |

---

### 3.3 High Performance / Scalable scenario

#### Main components

- **Compute**
  - `appservice-plan-hp`: App Service Plan Premium v3 P2v3, 4 instances.
  - `appservice-webapp-hp`: Web App on that plan.

- **Data / DB / Cache**
  - `sql-db-ecommerce-hp`: Azure SQL Database GP Gen5 2 vCores, 256 GB.
  - `redis-cache-hp`: Azure Cache for Redis Premium P1.

- **Storage**
  - `storage-blob-content-hp`: Storage GZRS, 500 GB (350 hot, 150 cool).

- **Network**
  - `vnet-main-hp`: main VNet.
  - `appgw-waf-v2-hp`: App Gateway WAF v2 (high traffic).
  - `appgw-public-ip-hp`: Standard Public IP.
  - `sql-db-private-endpoint-hp`, `redis-private-endpoint-hp`: two Private Endpoints each.
  - `nat-egress-hp`: NAT outbound (1 TB).
  - `network-egress-hp`: general egress (7 TB).

- **Security**
  - `keyvault-hp`: Key Vault Premium (HSM‑backed).

- **Monitoring / Analytics**
  - `log-analytics-hp`: Log Analytics with ~400 GB/month ingestion/retention.

- **Backup / DR**
  - `backup-vault-hp`: larger backup footprint.

#### Pricing table – High Performance

| Scenario        | Resource ID                 | Category               | Service        | SKU (requested / resolved)                         | Region      | Billing | Unit Price | Unit        | Units | Monthly Cost | Yearly Cost | Notes |
|----------------|-----------------------------|------------------------|----------------|----------------------------------------------------|-------------|--------|-----------|------------|-------|-------------|------------|-------|
| high_performance | vnet-main-hp              | network.vnet           | Virtual Network | Virtual Network / Virtual Network                  | westeurope  | payg   | 0.00      | VNet       | 1     | 0.00        | 0.00       | No direct charge. |
| high_performance | appgw-waf-v2-hp           | network.appgw          | Application Gateway | WAF_v2 / Standard Capacity Units (discounted)  | westeurope  | payg   | 0.0069    | 1/Hour     | 730   | 5.04        | 60.44      | High traffic; real cost will be higher than shown. |
| high_performance | appgw-public-ip-hp        | network.public_ip      | Public IP      | Standard / (missing)                               | westeurope  | payg   | –         | –          | –     | –           | –          | Public IP price missing. |
| high_performance | appservice-plan-hp        | appservice             | Azure App Service | P2v3 / P0v3 App (Linux)                         | westeurope  | payg   | 0.077     | 1 Hour     | 2920  | 224.84      | 2698.08    | SKU mismatch; real P2v3 price > P0v3. |
| high_performance | appservice-webapp-hp      | appservice             | Azure App Service | (logical) / included                            | westeurope  | payg   | 0.00      | Included   | 1     | 0.00        | 0.00       | Web App billed via plan. |
| high_performance | redis-cache-hp            | cache.redis            | Azure Cache for Redis | Premium_P1 / (missing)                       | westeurope  | payg   | –         | –          | –     | –           | –          | Premium P1 Redis – price missing. |
| high_performance | sql-db-ecommerce-hp       | db.sql                 | SQL Database   | GP_Gen5_2 / Gen5 vCore (1–2 vCores)               | westeurope  | payg   | 0.2896*   | 1 Hour     | 730  | 105.70      | 1268.45    | Same compute as baseline; more storage/IOPS. |
| high_performance | sql-db-private-endpoint-hp | network.gateway       | Private Link   | PrivateEndpoint / (missing)                       | westeurope  | payg   | –         | –          | –     | –           | –          | Two SQL Private Endpoints – not priced. |
| high_performance | redis-private-endpoint-hp | network.gateway        | Private Link   | PrivateEndpoint / (missing)                       | westeurope  | payg   | –         | –          | –     | –           | –          | Two Redis Private Endpoints – not priced. |
| high_performance | storage-blob-content-hp   | storage.blob           | Storage        | Standard_GZRS / ADLS Gen2 (hot+cool)              | westeurope  | payg   | ~0.0007–0.0019 | 1 GB   | 500  | 0.53        | 6.36       | Estimated; GZRS, larger capacity. |
| high_performance | log-analytics-hp          | monitoring.loganalytics| Log Analytics  | PerGB2018 / Analytics Logs                        | westeurope  | payg   | 0.1124    | 1 GB/Month | 400  | 44.96       | 539.52     | Retention only; ingestion/analyze not modeled. |
| high_performance | keyvault-hp               | security.keyvault      | Key Vault      | premium / Premium Operations                      | westeurope  | payg   | 0.0259    | 10K ops    | 500  | 12.95       | 155.40     | ~5M operations/month; Premium HSM features extra. |
| high_performance | backup-vault-hp           | backup.vault           | Backup         | Standard / ADLS Gen2 Vaulted LRS Writes           | westeurope  | payg   | 0.0467    | 10K ops    | 20   | 0.93        | 11.21      | Only write ops priced; storage not modeled. |
| high_performance | nat-egress-hp             | network.nat            | Bandwidth      | Standard / Inter‑AZ Data Transfer Out             | westeurope  | payg   | 0.0086    | 1 GB       | 1000 | 8.60        | 103.20     | Approximated NAT egress. |
| high_performance | network-egress-hp         | network.egress         | Bandwidth      | Standard / Inter‑AZ Data Transfer Out             | westeurope  | payg   | 0.0086    | 1 GB       | 7000 | 60.20       | 722.40     | 7 TB/month egress; real internet egress differs. |

#### Aggregated by category (High Performance)

From `totals.by_category` (monthly, with estimates):

| Bucket            | Included Categories                                      | Monthly (with est.) | Priced+est. | Missing | Est. share of bucket* |
|-------------------|----------------------------------------------------------|----------------------|------------|---------|------------------------|
| Compute           | appservice                                               | 224.84              | 224.84     | 0.00    | ~0% (but SKU mismatch) |
| DB                | db.sql, cache.redis                                      | 205.70              | 105.70     | 100.00  | ~0% (Redis missing) |
| Storage           | storage.blob                                             | 0.53                | 0.53       | 0.00    | ~100% (estimated) |
| Network           | network.\*                                               | 468.80              | 73.84      | 394.96  | ~16% (most network missing/approx) |
| Monitoring/Analytics | monitoring.loganalytics                               | 100.00              | 44.96      | 55.04   | ~45% (retention priced only) |
| Security          | security.keyvault                                        | 12.95               | 12.95      | 0.00    | ~0% |
| Backup/DR         | backup.vault                                             | 100.00              | 0.93       | 99.07   | ~1% (backup storage missing) |
| Other             | –                                                        | 0.00                | 0.00       | 0.00    | – |

---

## 4. Resources where pricing failed – manual checks

Across scenarios, the following resources have **missing pricing** and must be checked manually in the Azure Pricing Calculator or your EA/Marketplace price sheet:

### Common patterns

1. **Application Gateway WAF v2**
   - All scenarios (`appgw-waf-v2`, `appgw-waf-v2-co`, `appgw-waf-v2-hp`) only have **capacity unit** pricing; they **do not include**:
     - Fixed hourly cost for WAF v2.
     - L7 data processed and rules evaluation.
   - Action: Use Azure Pricing Calculator → Application Gateway → WAF v2, input:
     - Average capacity units, L7 data processed (GB), number of rules, and autoscale expectations.

2. **Standard Public IP**
   - `appgw-public-ip`, `appgw-public-ip-co`, `appgw-public-ip-hp` all have `pricing_status: "missing"`.
   - Action: Check “Public IP address – Standard” in the calculator (per hour + data if applicable).

3. **Azure Cache for Redis**
   - Baseline: `redis-cache-prod` (Standard C1) – missing.
   - Cost‑optimized: `redis-cache-co` (Basic C0) – missing.
   - High‑perf: `redis-cache-hp` (Premium P1) – missing.
   - Action: Use “Azure Cache for Redis” pricing:
     - Region: West Europe.
     - SKUs: Basic C0, Standard C1, Premium P1.
     - Include any clustering or persistence options.

4. **Private Endpoints / Private Link**
   - Baseline: `sql-db-private-endpoint`, `redis-private-endpoint`.
   - Cost‑optimized: `sql-db-private-endpoint-co`, `redis-private-endpoint-co`.
   - High‑perf: `sql-db-private-endpoint-hp`, `redis-private-endpoint-hp`.
   - Action: In “Azure Private Link” pricing:
     - Per‑endpoint hourly charge.
     - Data processed (GB) through the endpoint.

5. **Backup storage**
   - `backup-vault-main`, `backup-vault-co`, `backup-vault-hp` only price **write operations**, not the **backup storage GB**.
   - Action: Use “Azure Backup” pricing:
     - Protected instance size (App Service content, file shares, etc.).
     - Backup storage (LRS/GRS) GB and retention policy.

6. **Log Analytics ingestion and queries**
   - All scenarios (`log-analytics-workspace`, `log-analytics-co`, `log-analytics-hp`) show **Analytics Logs Data Retention** pricing, not:
     - Data ingestion (GB/month).
     - Data analyzed (query costs).
   - Action: In “Azure Monitor / Log Analytics” pricing:
     - Set ingestion volume (GB/month).
     - Retention beyond free period.
     - Consider commitment tiers if volumes are stable.

7. **Bandwidth / NAT / Internet egress**
   - `nat-egress*` and `network-egress*` use **Inter‑AZ data transfer** meters as a proxy.
   - Real internet egress pricing is:
     - Tiered by GB/month.
     - Different meter (“Data Transfer Out”).
   - Action: Use “Bandwidth” pricing:
     - Region: West Europe.
     - Internet egress (GB/month) by tier.
     - NAT Gateway: per‑hour + data processed.

8. **SQL Database storage**
   - For all SQL DB resources, only **compute vCores** are clearly modeled; storage GB and backup storage are not explicitly priced.
   - Action: In “Azure SQL Database – Single Database”:
     - GP Gen5 2 vCores.
     - Storage GB (64/128/256).
     - Long‑term retention if required.

---

## 5. FinOps recommendations

### 5.1 Quick wins

1. **Fix SKU mismatches and missing prices**
   - Align App Service SKUs:
     - Baseline: use actual **P1v3 Linux** price.
     - High‑perf: use actual **P2v3 Linux** price.
   - Redis SKUs:
     - Price Standard C1, Basic C0, Premium P1 explicitly.
   - Private Endpoints, Public IPs, and NAT:
     - Add per‑hour and per‑GB charges.
   - This will give you a **much clearer cost picture** before any optimization.

2. **Right‑size Log Analytics**
   - Baseline: 200 GB/month; Cost‑opt: 80 GB; High‑perf: 400 GB.
   - Actions:
     - Turn off noisy diagnostic categories (e.g., verbose AppGW logs) where not needed.
     - Use **sampling** for high‑volume telemetry.
     - Move older data to **archive** and query it sparingly.
   - Consider **Log Analytics commitment tiers** if you stabilize ingestion (often 20–30% cheaper than pure PAYG at scale).

3. **Storage redundancy choices**
   - Baseline uses **GRS**; cost‑optimized uses **LRS**; high‑perf uses **GZRS**.
   - For non‑critical static content (product images that can be regenerated or re‑uploaded), **LRS or ZRS** may be sufficient and cheaper than GRS/GZRS.
   - Keep **GRS/GZRS** only where cross‑region durability is a hard requirement.

4. **Key Vault usage**
   - Baseline and cost‑opt use Standard; high‑perf uses Premium.
   - Only use **Premium** if you truly need HSM‑backed keys or compliance requirements; otherwise Standard is cheaper and usually sufficient.
   - Reduce unnecessary secret polls by using **managed identities** and caching configuration in the app.

5. **Backup scope and retention**
   - SQL already has built‑in PITR and optional long‑term retention.
   - For App Service and storage:
     - Ensure you’re not double‑backing up data that is already versioned or can be recreated.
     - Tune retention to business RPO/RTO, not “keep everything forever”.

### 5.2 Spot vs PAYG vs Reserved

- **Spot**:
  - Not applicable here (no VM Scale Sets or AKS nodes). App Service, SQL DB, Redis, AppGW do **not** support Spot.
- **Reserved Instances / Reservations**:
  - **SQL Database vCores**:
    - If this is a steady 24x7 production workload, consider **1‑year or 3‑year reserved capacity** for SQL DB vCores (often 30–40% savings vs PAYG).
  - **App Service Plans**:
    - App Service has **Reserved Instances** (App Service Environment / Premium) and **Savings Plans for compute** (if using VMs/AKS). For pure App Service, options are more limited; check if **Azure Savings Plan for Compute** applies to your SKU in your contract.
  - **Redis**:
    - Azure Cache for Redis supports **reserved capacity** (1‑year/3‑year) for Standard/Premium SKUs.
  - **Application Gateway**:
    - No classic RI, but if you have predictable usage, you can benefit from **Savings Plan for Compute** only for VM‑based workloads, not AppGW. For AppGW, focus on right‑sizing and rules optimization.
- **PAYG exposure**:
  - All scenarios are currently **100% PAYG**.
  - For a stable production e‑commerce site, you can safely reserve:
    - SQL DB vCores.
    - Redis capacity (Standard/Premium).
    - Possibly App Service if your contract supports it.
  - Keep **burst components** (e.g., extra App Service instances during sales peaks) on PAYG/autoscale.

### 5.3 Right‑sizing ideas

- **App Service**
  - Baseline: P1v3, 2 instances.
    - Validate CPU/memory and response times under load tests.
    - If underutilized, consider:
      - 1 instance + autoscale rules.
      - Or a smaller Premium SKU (P0v3) if features/SLA still acceptable.
  - Cost‑optimized: S1, 1 instance.
    - Watch for CPU saturation and cold starts under peak; you may need a second instance or move to P1v3.
  - High‑perf: P2v3, 4 instances.
    - Ensure you really need 4 instances; autoscale based on CPU/requests and set a **minimum** that matches normal load (e.g., 2) and a **maximum** for peaks.

- **SQL Database**
  - All scenarios use GP Gen5 2 vCores.
  - Monitor:
    - DTU/vCore utilization, CPU, IO waits, and query performance.
  - If CPU is low but IO is high:
    - Increase storage (for more IOPS) rather than vCores.
  - If CPU is high:
    - Consider 4 vCores during peak periods (scale up/down).

- **Redis**
  - Baseline: Standard C1 – good default.
  - Cost‑opt: Basic C0 – **no SLA**, no replica; acceptable only if cache loss is tolerable and you can rebuild quickly.
  - High‑perf: Premium P1 – good for heavy workloads; consider clustering only if you hit throughput/memory limits.

### 5.4 Region and egress considerations

- All scenarios are in **West Europe** (and one VNet in `francecentral` metadata, but resources are `westeurope`).
- **Egress costs**:
  - 1.5–7 TB/month of internet egress is non‑trivial.
  - Consider:
    - **Azure Front Door / CDN** in front of App Gateway and Blob Storage:
      - Offloads TLS and caching static content closer to users.
      - Can reduce origin egress and AppGW load.
    - If you have many EU users, West Europe is fine; if global, consider multi‑region deployment with traffic manager/Front Door to reduce latency and cross‑region egress.
- **Inter‑AZ vs Internet egress**:
  - The JSON uses **Inter‑AZ** meters as a proxy; real internet egress pricing is different and tiered.
  - For accurate FinOps, recalc with the **Bandwidth – Data Transfer Out** meters.

---

## 6. Delta tables vs Baseline

Because of SKU mismatches and missing prices, the tool flags scenarios as **“not_comparable”**. Still, we can compare the **modeled totals** (priced + estimated + placeholder missing values) as given in `totals.total_monthly` and `totals.total_yearly`.

### 6.1 Overall totals – Cost Optimized vs Baseline

Using `total_monthly` / `total_yearly` (with estimates):

- Baseline: 967.44 €/month, 11,609.30 €/year.
- Cost‑optimized: 883.04 €/month, 10,596.46 €/year.

| Scenario        | Metric              | Baseline | Cost Optimized | Δ (Abs) | Δ (%) vs Baseline |
|----------------|---------------------|----------|----------------|---------|--------------------|
| cost_optimized | Monthly – priced only (`monthly_priced`) | 49.12   | 77.22         | +28.10  | +57.2% (but both very incomplete) |
| cost_optimized | Monthly – with estimates (`total_monthly`) | 967.44  | 883.04        | **‑84.40** | **‑8.7%** |
| cost_optimized | Yearly – priced only (`yearly_priced`) | 589.41  | 926.59        | +337.18 | +57.2% |
| cost_optimized | Yearly – with estimates (`total_yearly`) | 11,609.30 | 10,596.46   | **‑1,012.84** | **‑8.7%** |

Interpretation: the **modeled** cost‑optimized scenario is ~9% cheaper overall, but the “priced only” subset is misleading because different components are missing in each scenario.

### 6.2 Overall totals – High Performance vs Baseline

- Baseline: 967.44 €/month, 11,609.30 €/year.
- High‑perf: 1,112.82 €/month, 13,353.89 €/year.

| Scenario         | Metric              | Baseline | High Performance | Δ (Abs) | Δ (%) vs Baseline |
|-----------------|---------------------|----------|------------------|---------|--------------------|
| high_performance | Monthly – priced only | 49.12   | 81.75           | +32.63  | +66.4% (incomplete) |
| high_performance | Monthly – with estimates | 967.44  | 1,112.82        | **+145.38** | **+15.0%** |
| high_performance | Yearly – priced only | 589.41  | 981.00          | +391.59 | +66.4% |
| high_performance | Yearly – with estimates | 11,609.30 | 13,353.89     | **+1,744.59** | **+15.0%** |

Interpretation: the high‑performance scenario is modeled at ~15% higher cost than baseline, but again dominated by missing/placeholder values.

### 6.3 Category‑level monthly deltas – Cost Optimized vs Baseline

Using `totals.by_category[cat].monthly_with_estimates`:

| Bucket            | Baseline (€/mo) | Cost‑opt (€/mo) | Δ (Abs) | Δ (%) vs Baseline |
|-------------------|-----------------|------------------|---------|--------------------|
| Compute (appservice)        | 112.42          | 60.01           | **‑52.41** | **‑46.6%** |
| DB (db.sql + cache.redis)   | 205.70          | 205.70          | 0.00     | 0% |
| Storage (storage.blob)      | 0.20            | 0.12            | ‑0.08   | ‑40.0% |
| Network (all network.\*)    | 430.10          | 414.62          | ‑15.48  | ‑3.6% |
| Monitoring/Analytics        | 100.00          | 100.00          | 0.00    | 0% |
| Security (Key Vault)        | 5.18            | 2.59            | ‑2.59   | ‑50.0% |
| Backup/DR (backup.vault + dr.asr) | 113.84   | 100.00          | ‑13.84  | ‑12.2% |
| Other                       | 0.00            | 0.00            | 0.00    | – |

Key takeaways:

- **Compute** is the main saving: ~47% lower due to S1 vs P1v3 and 1 vs 2 instances.
- **Security** (Key Vault) halves due to fewer operations.
- Network and backup savings are modest in absolute terms.

### 6.4 Category‑level monthly deltas – High Performance vs Baseline

| Bucket            | Baseline (€/mo) | High‑perf (€/mo) | Δ (Abs) | Δ (%) vs Baseline |
|-------------------|-----------------|-------------------|---------|--------------------|
| Compute (appservice)        | 112.42          | 224.84           | **+112.42** | **+100.0%** |
| DB (db.sql + cache.redis)   | 205.70          | 205.70           | 0.00     | 0% |
| Storage (storage.blob)      | 0.20            | 0.53             | +0.33   | +165.0% (small absolute) |
| Network (all network.\*)    | 430.10          | 468.80           | +38.70  | +9.0% |
| Monitoring/Analytics        | 100.00          | 100.00           | 0.00    | 0% |
| Security (Key Vault)        | 5.18            | 12.95            | +7.77   | +150.0% |
| Backup/DR (backup.vault)    | 100.00          | 100.00           | 0.00    | 0% |
| Other                       | 0.00            | 0.00             | 0.00    | – |

Key takeaways:

- **Compute** doubles due to 4× P2v3 vs 2× P1v3.
- **Network** grows ~9% due to higher egress and NAT.
- **Key Vault** cost increases with Premium and more operations, but still small in absolute terms.
- Storage and monitoring increases are small in € terms but reflect higher volumes.

---

## 7. Explicit mentions requested

- **Key Vault / secrets management**:
  - Present in all scenarios (`keyvault-main`, `keyvault-co`, `keyvault-hp`).
  - Baseline & cost‑opt: Standard; high‑perf: Premium (HSM).
  - Costs scale with **number of operations**, key rotations, certificate renewals.
  - Use **managed identities** and configuration caching to reduce calls.

- **Log Analytics / monitoring**:
  - Central to all scenarios; ingestion volumes: 80–400 GB/month.
  - Costs scale with:
    - **Data ingested (GB)**.
    - **Data retained beyond free period**.
    - **Data analyzed** (queries).
  - Tune diagnostic settings and consider **commitment tiers**.

- **Backup vault & Site Recovery**:
  - Backup vault present in all scenarios; ASR placeholder only in baseline.
  - Current modeling only includes **write operations**, not backup storage.
  - Costs scale with:
    - **Protected instance size**.
    - **Backup storage GB** and **retention**.
  - For ASR, costs scale with:
    - Number of protected VMs.
    - Replication storage and churn.

- **Network egress / NAT / Gateways / Front Door**:
  - App Gateway WAF v2 is the main ingress; NAT handles outbound.
  - Egress volumes: 1.5–7 TB/month.
  - Real internet egress pricing is **tiered** and different from inter‑AZ.
  - Consider **Azure Front Door / CDN** to:
    - Reduce origin egress.
    - Improve performance and security (WAF at edge).

- **Where costs may scale with data volume or throughput**:
  - **Log Analytics**: ingestion and queries.
  - **Storage**: GB stored, transactions, and egress.
  - **Bandwidth**: GB egress to internet and between regions.
  - **App Gateway**: L7 data processed, number of requests, WAF rules.
  - **Redis**: operations per second and memory footprint (may require higher SKUs).
  - **SQL**: IO and CPU (may require more vCores or storage/IOPS).

---

If you’d like, I can next:

- Re‑cast this into a **single comparison matrix** for stakeholders, or  
- Work through a **more accurate pricing pass** using current Azure list prices for the missing SKUs (Redis, AppGW WAF v2 full, Private Link, etc.).