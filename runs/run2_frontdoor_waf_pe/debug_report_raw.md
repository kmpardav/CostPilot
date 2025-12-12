## 1. Baseline / Recommended – Architecture Narrative

The baseline scenario is a production-ready, internet-facing web application built on Azure PaaS with secure data access and standard observability:

- **Entry & security:** Users hit the app via **Azure Front Door Premium with WAF**, which provides global anycast entry, TLS termination, WAF protection, and routing to the backend.
- **Web tier:** The application runs on **Azure App Service (Linux, Premium v3)** with **2 instances** for high availability. The web app itself is a logical resource on that plan.
- **Data tier:**  
  - **Azure SQL Database (General Purpose, Gen5, 4 vCores, zone redundant)** as the primary transactional store.  
  - **Azure Cache for Redis (Standard C1)** for session/state caching and performance.
- **Storage:** A **GPv2 Storage Account (GRS)** provides Blob storage across hot/cool/archive tiers for static content and files.
- **Network & security:**  
  - A **VNet** hosts **Private Endpoints** for SQL and Blob, so App Service accesses data over private IPs.  
  - A **NAT Gateway + Standard Public IP** provides controlled outbound internet access.
- **Secrets management:** **Azure Key Vault (Standard)** stores secrets, keys, and certificates for the app and platform components.
- **Monitoring & logging:** **Log Analytics workspace** collects App Service logs, SQL diagnostics, and platform logs with hot + archive retention.
- **Backup & DR:** A **Recovery Services / Backup vault** stores backups (e.g., SQL long-term retention, app content), sized for multiple restore points.

> Note: Many high-cost items (Front Door, Redis, SQL, App Service) have **missing or ambiguous pricing** in the dataset, so the numeric totals are indicative only. Use the Azure Pricing Calculator for final numbers.

---

## 2. Other Scenarios – Summary & Differences

### Cost Optimized Scenario

A lower-cost variant that trades off performance, redundancy, and observability:

- **Front Door:** **Standard** instead of Premium; lower traffic assumptions.
- **App Service:** **Standard S1, single instance** (no zone redundancy, less CPU/RAM).
- **SQL:** **GP Gen5 2 vCores** (smaller compute & storage).
- **Redis:** **Basic C0** (no replica, lower availability and capacity).
- **Storage:** **LRS** instead of GRS, and smaller capacity/egress.
- **Monitoring & backup:** Reduced Log Analytics ingestion/retention and smaller backup footprint.
- **Private Endpoints, NAT, Key Vault:** Still present but sized down.

This is suitable for lower traffic, non-mission-critical workloads or early-stage production with tight budgets.

### High Performance / Scalable Scenario

A higher-performance, more scalable variant for heavy traffic and stricter SLAs:

- **Front Door:** **Premium with WAF**, sized for much higher egress and request volume.
- **App Service:** **Premium v3 P2** with **4 instances**, reserved capacity assumed.
- **SQL:** **Hyperscale-like configuration** (HS_Gen5_8 in description) with more vCores and storage.
- **Redis:** **Premium P2** with more memory, throughput, and enterprise features.
- **Storage:** **GZRS** with significantly more hot/cool capacity and egress.
- **Network:** Multiple **Private Endpoints** for SQL and Blob, higher NAT egress.
- **Key Vault:** **Premium** tier for HSM-backed keys and higher operation volume.
- **Monitoring & backup:** More Log Analytics ingestion and longer retention; larger backup footprint.

This is aimed at high-traffic, business-critical workloads where performance and resilience outweigh cost.

---

## 3. Scenario Details

### 3.1 Baseline Scenario

#### Main Components (Baseline)

- **Compute**
  - Azure App Service Plan – Linux Premium v3 (requested P1v3, resolved P0v3, 2 instances)
  - Web App (logical, billed via plan)
- **Data / DB**
  - Azure SQL Database – General Purpose Gen5, 4 vCores, zone redundant (reserved)
  - Azure Cache for Redis – Standard C1
- **Storage**
  - Storage Account (GPv2) – Blob, Standard GRS (hot/cool/archive)
- **Network**
  - Virtual Network (no direct charge)
  - Azure Front Door Premium with WAF
  - Private Endpoint – SQL
  - Private Endpoint – Blob
  - NAT Gateway + Standard Public IP
- **Security / Secrets**
  - Azure Key Vault – Standard
- **Monitoring / Analytics**
  - Log Analytics workspace – PerGB2018
- **Backup / DR**
  - Backup / Recovery Services vault

#### Pricing Table – Baseline

> Currency: EUR. Many high-value items are **missing or modeled**; treat numbers as indicative.

| Scenario | Resource ID         | Category               | Service            | SKU (requested / resolved)                         | Region     | Billing   | Unit Price | Unit          | Units  | Monthly Cost | Yearly Cost | Notes |
|---------|---------------------|------------------------|--------------------|----------------------------------------------------|-----------|----------|-----------|---------------|--------|--------------|------------|-------|
| baseline | vnet-main          | network.vnet           | Virtual Network    | n/a / Virtual Network                             | westeurope | payg     | 0.00      | VNet          | 1.0    | 0.00         | 0.00       | Logical VNet, no direct charge. |
| baseline | afd-waf            | network.gateway        | Azure Front Door   | Premium_AzureFrontDoor / (missing)                | northeurope | payg    | –         | –             | –      | –            | –          | Front Door Premium with WAF; pricing missing. |
| baseline | appsvc-plan-prod   | appservice             | Azure App Service  | P1v3 / P0v3                                       | westeurope | payg     | 0.077     | 1 Hour        | 1460.0 | 112.42       | 1349.04    | 2 Linux instances; SKU mismatch (P1v3 vs P0v3). |
| baseline | appsvc-webapp      | appservice             | Azure App Service  | (logical) / included                              | westeurope | payg     | 0.00      | Included      | 1.0    | 0.00         | 0.00       | Web App billed via plan. |
| baseline | sql-db-prod        | db.sql                 | SQL Database       | GP_Gen5_4 / vCore ZR Zone Redundancy (reserved)   | westeurope | reserved | 494.7027* | 1 Hour*       | 1.0    | 100.00†      | 1200.00†   | 4 vCores, ZR; reservation UoM ambiguous, cost modeled. |
| baseline | redis-cache-prod   | cache.redis            | Azure Cache Redis  | Standard_C1 / (missing)                           | westeurope | payg     | –         | –             | –      | –            | –          | Standard C1; pricing missing. |
| baseline | blob-storage-prod  | storage.blob           | Storage (Blob)     | Standard_GRS / Standard_GRS (est.)                | westeurope | payg     | –         | GB mix        | –      | 0.73         | 8.76       | 500 GB hot, 200 GB cool, 100 GB archive; estimated. |
| baseline | pe-sql             | network.gateway        | Private Endpoint*  | n/a / (missing)                                   | westeurope | payg     | –         | –             | –      | –            | –          | Private Endpoint for SQL; priced as Private Link (missing). |
| baseline | pe-blob            | network.gateway        | Private Endpoint*  | n/a / (missing)                                   | westeurope | payg     | –         | –             | –      | –            | –          | Private Endpoint for Blob; pricing missing. |
| baseline | nat-egress         | network.nat            | Bandwidth / NAT    | n/a / Standard                                    | westeurope | payg     | 0.0086    | 1 GB          | 500.0  | 4.30         | 51.60      | Modeled as inter-AZ data transfer; egress 500 GB. |
| baseline | public-ip-nat      | network.public_ip      | Public IP          | Standard / (missing)                              | westeurope | payg     | –         | –             | –      | –            | –          | Standard Public IP; pricing missing. |
| baseline | keyvault-prod      | security.keyvault      | Key Vault          | standard / Standard                               | westeurope | payg     | 0.0259    | 10K ops       | 20.0   | 0.52         | 6.22       | ~200k ops/month. |
| baseline | loganalytics-prod  | monitoring.loganalytics| Log Analytics      | PerGB2018 / Analytics Logs (sku mismatch)         | westeurope | payg     | 0.1124    | 1 GB/Month    | 200.0  | 22.48†       | 269.76†    | 200 GB retention; ingestion pricing not modeled. |
| baseline | backup-vault-prod  | backup.vault           | Backup             | n/a / ADLS Gen2 Vaulted                           | westeurope | payg     | 0.0467    | 10K ops       | 10.0   | 0.47         | 5.60       | Backup operations only; storage not modeled. |

\* For SQL DB and reservations, the `unit_price` looks like a **1-year reservation price mis-labeled as hourly**; the tool has normalized to a **modeled 100 EUR/month**.  
† Log Analytics and SQL DB costs are **modeled**, not directly computed from the raw unit price.

##### Baseline – Aggregated by Category

I’ll normalize categories into FinOps-friendly buckets:

- **Compute:** `appservice`
- **DB:** `db.sql`, `cache.redis`
- **Storage:** `storage.blob`
- **Network:** `network.gateway`, `network.nat`, `network.public_ip`, `network.vnet`
- **Security:** `security.keyvault`
- **Monitoring / Analytics:** `monitoring.loganalytics`
- **Backup/DR:** `backup.vault`
- **Other:** (none here)

From `totals.by_category` (monthly):

| Scenario | Category          | Monthly Total | Priced Portion | Estimated Portion | Missing Portion | % Priced | % Estimated | % Missing |
|----------|-------------------|--------------:|---------------:|------------------:|----------------:|---------:|------------:|----------:|
| baseline | Compute (AppSvc)  | 112.42        | 0.00           | 0.00              | 112.42          | 0%       | 0%          | 100%      |
| baseline | DB (SQL)          | 100.00        | 0.00           | 0.00              | 100.00          | 0%       | 0%          | 100%      |
| baseline | DB (Redis)        | 100.00        | 0.00           | 0.00              | 100.00          | 0%       | 0%          | 100%      |
| baseline | Storage (Blob)    | 0.73          | 0.00           | 0.73              | 0.00            | 0%       | 100%        | 0%        |
| baseline | Network (GW)      | 300.00        | 0.00           | 0.00              | 300.00          | 0%       | 0%          | 100%      |
| baseline | Network (NAT)     | 4.30          | 4.30           | 0.00              | 0.00            | 100%     | 0%          | 0%        |
| baseline | Network (Pub IP)  | 100.00        | 0.00           | 0.00              | 100.00          | 0%       | 0%          | 100%      |
| baseline | Network (VNet)    | 0.00          | 0.00           | 0.00              | 0.00            | –        | –           | –         |
| baseline | Security (KV)     | 0.52          | 0.52           | 0.00              | 0.00            | 100%     | 0%          | 0%        |
| baseline | Monitoring (LA)   | 100.00        | 0.00           | 0.00              | 100.00          | 0%       | 0%          | 100%      |
| baseline | Backup/DR         | 0.47          | 0.47           | 0.00              | 0.00            | 100%     | 0%          | 0%        |

**Key observation:** ~99% of the baseline total (812.42 / 818.44 EUR) is **missing/modeled**, dominated by Front Door, App Service, SQL, Redis, Log Analytics, and Public IP. Use this as a **shape of cost**, not a final quote.

---

### 3.2 Cost Optimized Scenario

#### Main Components (Cost Optimized)

- **Compute**
  - Azure App Service Plan – Linux Standard S1, **1 instance**
  - Web App (logical)
- **Data / DB**
  - Azure SQL Database – GP Gen5, 2 vCores (reserved)
  - Azure Cache for Redis – Basic C0
- **Storage**
  - Storage Account – Blob, Standard LRS (hot/cool/archive), smaller capacity
- **Network**
  - Virtual Network
  - Azure Front Door Standard with WAF
  - Private Endpoints – SQL & Blob
  - NAT Gateway + Standard Public IP
- **Security / Secrets**
  - Azure Key Vault – Standard (fewer operations)
- **Monitoring / Analytics**
  - Log Analytics – reduced ingestion/retention
- **Backup / DR**
  - Backup vault – smaller footprint and shorter retention

#### Pricing Table – Cost Optimized

| Scenario       | Resource ID        | Category               | Service            | SKU (requested / resolved)                         | Region     | Billing   | Unit Price | Unit          | Units  | Monthly Cost | Yearly Cost | Notes |
|----------------|--------------------|------------------------|--------------------|----------------------------------------------------|-----------|----------|-----------|---------------|--------|--------------|------------|-------|
| cost_optimized | vnet-main-co      | network.vnet           | Virtual Network    | n/a / Virtual Network                             | westeurope | payg     | 0.00      | VNet          | 1.0    | 0.00         | 0.00       | No direct charge. |
| cost_optimized | afd-standard-co   | network.gateway        | Azure Front Door   | Standard_AzureFrontDoor / (missing)               | northeurope | payg    | –         | –             | –      | –            | –          | Front Door Standard with WAF; pricing missing. |
| cost_optimized | appsvc-plan-co    | appservice             | Azure App Service  | S1 / S1                                           | westeurope | payg     | 0.0822    | 1 Hour        | 730.0  | 60.01        | 720.07     | 1 Linux S1 instance. |
| cost_optimized | appsvc-webapp-co  | appservice             | Azure App Service  | (logical) / included                              | westeurope | payg     | 0.00      | Included      | 1.0    | 0.00         | 0.00       | Web App billed via plan. |
| cost_optimized | sql-db-co         | db.sql                 | SQL Database       | GP_Gen5_2 / vCore (reserved)                      | westeurope | reserved | 824.2162* | 1 Hour*       | 1.0    | 100.00†      | 1200.00†   | 2 vCores; reservation UoM ambiguous, cost modeled. |
| cost_optimized | redis-cache-co    | cache.redis            | Azure Cache Redis  | Basic_C0 / (missing)                              | westeurope | payg     | –         | –             | –      | –            | –          | Basic C0; pricing missing. |
| cost_optimized | blob-storage-co   | storage.blob           | Storage (Blob)     | Standard_LRS / Standard_LRS (est.)                | westeurope | payg     | –         | GB mix        | –      | 0.33         | 3.96       | 200 GB hot, 100 GB cool, 50 GB archive; estimated. |
| cost_optimized | pe-sql-co         | network.gateway        | Private Endpoint*  | n/a / (missing)                                   | westeurope | payg     | –         | –             | –      | –            | –          | Private Endpoint for SQL; pricing missing. |
| cost_optimized | pe-blob-co        | network.gateway        | Private Endpoint*  | n/a / (missing)                                   | westeurope | payg     | –         | –             | –      | –            | –          | Private Endpoint for Blob; pricing missing. |
| cost_optimized | nat-egress-co     | network.nat            | Bandwidth / NAT    | n/a / Standard                                    | westeurope | payg     | 0.0086    | 1 GB          | 200.0  | 1.72         | 20.64      | 200 GB egress. |
| cost_optimized | public-ip-nat-co  | network.public_ip      | Public IP          | Standard / (missing)                              | westeurope | payg     | –         | –             | –      | –            | –          | Standard Public IP; pricing missing. |
| cost_optimized | keyvault-co       | security.keyvault      | Key Vault          | standard / Standard                               | westeurope | payg     | 0.0259    | 10K ops       | 10.0   | 0.26         | 3.11       | ~100k ops/month. |
| cost_optimized | loganalytics-co   | monitoring.loganalytics| Log Analytics      | PerGB2018 / Analytics Logs (sku mismatch)         | westeurope | payg     | 0.1124    | 1 GB/Month    | 100.0  | 11.24†       | 134.88†    | 100 GB retention; ingestion not modeled. |
| cost_optimized | backup-vault-co   | backup.vault           | Backup             | n/a / ADLS Gen2 Vaulted                           | westeurope | payg     | 0.0467    | 10K ops       | 5.0    | 0.23         | 2.80       | Backup operations only. |

##### Cost Optimized – Aggregated by Category

From `totals.by_category` (monthly):

| Scenario       | Category          | Monthly Total | Priced Portion | Estimated Portion | Missing Portion | % Priced | % Estimated | % Missing |
|----------------|-------------------|--------------:|---------------:|------------------:|----------------:|---------:|------------:|----------:|
| cost_optimized | Compute (AppSvc)  | 60.01         | 60.01          | 0.00              | 0.00            | 100%     | 0%          | 0%        |
| cost_optimized | DB (SQL)          | 100.00        | 0.00           | 0.00              | 100.00          | 0%       | 0%          | 100%      |
| cost_optimized | DB (Redis)        | 100.00        | 0.00           | 0.00              | 100.00          | 0%       | 0%          | 100%      |
| cost_optimized | Storage (Blob)    | 0.33          | 0.00           | 0.33              | 0.00            | 0%       | 100%        | 0%        |
| cost_optimized | Network (GW)      | 300.00        | 0.00           | 0.00              | 300.00          | 0%       | 0%          | 100%      |
| cost_optimized | Network (NAT)     | 1.72          | 1.72           | 0.00              | 0.00            | 100%     | 0%          | 0%        |
| cost_optimized | Network (Pub IP)  | 100.00        | 0.00           | 0.00              | 100.00          | 0%       | 0%          | 100%      |
| cost_optimized | Network (VNet)    | 0.00          | 0.00           | 0.00              | 0.00            | –        | –           | –         |
| cost_optimized | Security (KV)     | 0.26          | 0.26           | 0.00              | 0.00            | 100%     | 0%          | 0%        |
| cost_optimized | Monitoring (LA)   | 100.00        | 0.00           | 0.00              | 100.00          | 0%       | 0%          | 100%      |
| cost_optimized | Backup/DR         | 0.23          | 0.23           | 0.00              | 0.00            | 100%     | 0%          | 0%        |

Again, **most of the 762.55 EUR/month is missing/modeled** (700 EUR).

---

### 3.3 High Performance / Scalable Scenario

#### Main Components (High Performance)

- **Compute**
  - Azure App Service Plan – Linux Premium v3 P2, **4 instances**, reserved
  - Web App (logical)
- **Data / DB**
  - Azure SQL Database – Hyperscale / high vCore (HS_Gen5_8 in description; pricing mapped to GP Gen5 vCore)
  - Azure Cache for Redis – Premium P2
- **Storage**
  - Storage Account – Blob, Standard GZRS, large hot/cool/archive capacity
- **Network**
  - Virtual Network
  - Azure Front Door Premium with WAF (higher traffic)
  - Multiple Private Endpoints – SQL (2) & Blob (2)
  - NAT Gateway + 2x Standard Public IPs
- **Security / Secrets**
  - Azure Key Vault – Premium (HSM-backed keys)
- **Monitoring / Analytics**
  - Log Analytics – higher ingestion and longer retention (hot + archive)
- **Backup / DR**
  - Backup vault – larger backup footprint and longer retention

#### Pricing Table – High Performance

| Scenario        | Resource ID        | Category               | Service            | SKU (requested / resolved)                         | Region     | Billing   | Unit Price | Unit          | Units  | Monthly Cost | Yearly Cost | Notes |
|-----------------|--------------------|------------------------|--------------------|----------------------------------------------------|-----------|----------|-----------|---------------|--------|--------------|------------|-------|
| high_performance | vnet-main-hp     | network.vnet           | Virtual Network    | n/a / Virtual Network                             | westeurope | payg     | 0.00      | VNet          | 1.0    | 0.00         | 0.00       | No direct charge. |
| high_performance | afd-premium-hp   | network.gateway        | Azure Front Door   | Premium_AzureFrontDoor / (missing)                | northeurope | payg    | –         | –             | –      | –            | –          | Front Door Premium; pricing missing. |
| high_performance | appsvc-plan-hp   | appservice             | Azure App Service  | P2v3 / P0v3 (reservation, ambiguous)              | westeurope | reserved | 439.3514* | 1 Hour*       | 1.0    | 100.00†      | 1200.00†   | 4 instances; reservation UoM ambiguous, cost modeled. |
| high_performance | appsvc-webapp-hp | appservice             | Azure App Service  | (logical) / included                              | westeurope | payg     | 0.00      | Included      | 1.0    | 0.00         | 0.00       | Web App billed via plan. |
| high_performance | sql-db-hp        | db.sql                 | SQL Database       | HS_Gen5_8 / vCore (reserved, mapped to GP Gen5)   | westeurope | reserved | 824.2162* | 1 Hour*       | 1.0    | 100.00†      | 1200.00†   | Hyperscale-like; reservation UoM ambiguous, cost modeled. |
| high_performance | redis-cache-hp   | cache.redis            | Azure Cache Redis  | Premium_P2 / (missing)                            | westeurope | reserved | –         | –             | –      | –            | –          | Premium P2; pricing missing. |
| high_performance | blob-storage-hp  | storage.blob           | Storage (Blob)     | Standard_GZRS / Standard_GZRS (est.)              | westeurope | payg     | –         | GB mix        | –      | 2.00         | 24.00      | 1500 GB hot, 500 GB cool, 200 GB archive; estimated. |
| high_performance | pe-sql-hp        | network.gateway        | Private Endpoint*  | n/a / (missing)                                   | westeurope | payg     | –         | –             | –      | –            | –          | 2x Private Endpoint for SQL; pricing missing. |
| high_performance | pe-blob-hp       | network.gateway        | Private Endpoint*  | n/a / (missing)                                   | westeurope | payg     | –         | –             | –      | –            | –          | 2x Private Endpoint for Blob; pricing missing. |
| high_performance | nat-egress-hp    | network.nat            | Bandwidth / NAT    | n/a / Standard                                    | westeurope | payg     | 0.0086    | 1 GB          | 1000.0 | 8.60         | 103.20     | 1000 GB egress. |
| high_performance | public-ip-nat-hp | network.public_ip      | Public IP          | Standard / (missing)                              | westeurope | payg     | –         | –             | –      | –            | –          | 2x Standard Public IP; pricing missing. |
| high_performance | keyvault-hp      | security.keyvault      | Key Vault          | premium / Premium                                 | westeurope | payg     | 0.0259    | 10K ops       | 50.0   | 1.29         | 15.54      | ~500k ops/month; Premium tier. |
| high_performance | loganalytics-hp  | monitoring.loganalytics| Log Analytics      | PerGB2018 / Analytics Logs (sku mismatch)         | westeurope | payg     | 0.1124    | 1 GB/Month    | 400.0  | 44.96†       | 539.52†    | 400 GB retention; ingestion not modeled. |
| high_performance | backup-vault-hp  | backup.vault           | Backup             | n/a / ADLS Gen2 Vaulted                           | westeurope | payg     | 0.0467    | 10K ops       | 15.0   | 0.70         | 8.41       | Backup operations only. |

##### High Performance – Aggregated by Category

From `totals.by_category` (monthly):

| Scenario        | Category          | Monthly Total | Priced Portion | Estimated Portion | Missing Portion | % Priced | % Estimated | % Missing |
|-----------------|-------------------|--------------:|---------------:|------------------:|----------------:|---------:|------------:|----------:|
| high_performance | Compute (AppSvc) | 100.00        | 0.00           | 0.00              | 100.00          | 0%       | 0%          | 100%      |
| high_performance | DB (SQL)         | 100.00        | 0.00           | 0.00              | 100.00          | 0%       | 0%          | 100%      |
| high_performance | DB (Redis)       | 100.00        | 0.00           | 0.00              | 100.00          | 0%       | 0%          | 100%      |
| high_performance | Storage (Blob)   | 2.00          | 0.00           | 2.00              | 0.00            | 0%       | 100%        | 0%        |
| high_performance | Network (GW)     | 300.00        | 0.00           | 0.00              | 300.00          | 0%       | 0%          | 100%      |
| high_performance | Network (NAT)    | 8.60          | 8.60           | 0.00              | 0.00            | 100%     | 0%          | 0%        |
| high_performance | Network (Pub IP) | 100.00        | 0.00           | 0.00              | 100.00          | 0%       | 0%          | 100%      |
| high_performance | Network (VNet)   | 0.00          | 0.00           | 0.00              | 0.00            | –        | –           | –         |
| high_performance | Security (KV)    | 1.29          | 1.29           | 0.00              | 0.00            | 100%     | 0%          | 0%        |
| high_performance | Monitoring (LA)  | 100.00        | 0.00           | 0.00              | 100.00          | 0%       | 0%          | 100%      |
| high_performance | Backup/DR        | 0.70          | 0.70           | 0.00              | 0.00            | 100%     | 0%          | 0%        |

Again, **~800 EUR/month is missing/modeled**.

---

## 4. Resources with Failed / Missing Pricing – Manual Checks

Across scenarios, the following resources have **missing pricing** and should be checked manually in the Azure Pricing Calculator or Rate Card API:

### Baseline

- `afd-waf` – Azure Front Door Premium_AzureFrontDoor (with WAF)
- `redis-cache-prod` – Azure Cache for Redis Standard_C1
- `pe-sql` – Private Endpoint for SQL (billed as Private Link endpoint + data processed)
- `pe-blob` – Private Endpoint for Blob
- `public-ip-nat` – Standard Public IP
- Plus: SQL DB, App Service, Log Analytics have **reservation / SKU mismatches**; confirm:
  - SQL DB: GP_Gen5_4, ZR, 4 vCores, 1-year reservation
  - App Service: Premium v3 P1v3 Linux, 2 instances
  - Log Analytics: PerGB2018 ingestion + retention pricing

### Cost Optimized

- `afd-standard-co` – Azure Front Door Standard_AzureFrontDoor
- `redis-cache-co` – Azure Cache for Redis Basic_C0
- `pe-sql-co` – Private Endpoint for SQL
- `pe-blob-co` – Private Endpoint for Blob
- `public-ip-nat-co` – Standard Public IP
- SQL DB (`sql-db-co`) – reservation UoM ambiguous; confirm GP_Gen5_2 1-year reservation.
- Log Analytics (`loganalytics-co`) – ingestion vs retention pricing.

### High Performance

- `afd-premium-hp` – Azure Front Door Premium_AzureFrontDoor
- `redis-cache-hp` – Azure Cache for Redis Premium_P2
- `pe-sql-hp` – 2x Private Endpoints for SQL
- `pe-blob-hp` – 2x Private Endpoints for Blob
- `public-ip-nat-hp` – 2x Standard Public IP
- App Service (`appsvc-plan-hp`) – reservation UoM ambiguous; confirm Premium v3 P2 Linux, 4 instances, 1-year reservation.
- SQL DB (`sql-db-hp`) – Hyperscale vs GP mapping; confirm HS_Gen5_8 pricing.
- Log Analytics (`loganalytics-hp`) – ingestion vs retention pricing.

**What to check manually:**

- Correct **SKU names and tiers** (e.g., P1v3 vs P0v3, HS_Gen5_8 vs GP_Gen5_8).
- **Reservation terms** (1-year vs 3-year) and whether prices are **per vCore-hour** or **per reservation**.
- **Front Door**:  
  - Fixed fee (per deployment)  
  - Data transfer out (per GB, by zone)  
  - Requests (per 10k or million)
- **Private Link**:  
  - Per endpoint-hour  
  - Data processed (per GB)
- **Public IP**:  
  - Standard IP per hour  
  - Data processed (if any)
- **Log Analytics**:  
  - Data ingestion (per GB)  
  - Retention beyond free period (per GB-month)  
  - Potential commitment tiers.

---

## 5. FinOps Recommendations

### 5.1 Quick Wins

1. **Fix SKU mismatches and reservation ambiguity**
   - Align requested vs resolved SKUs (e.g., App Service P1v3 vs P0v3, SQL GP vs HS).
   - Explicitly model **vCore count × price per vCore-hour × 730 hours** for SQL and App Service reservations.
   - This will turn large “missing” buckets into actionable cost numbers.

2. **Right-size Log Analytics**
   - In all scenarios, Log Analytics is modeled as a flat 100 EUR/month.  
   - Tune:
     - Diagnostic settings (only necessary categories).
     - Sampling for high-volume logs.
     - Retention (e.g., 30–60 days hot, archive beyond that).
   - Consider **commitment tiers** if ingestion is steady and >50–100 GB/day.

3. **Validate Redis necessity and tier**
   - For baseline and cost-optimized:
     - If caching is light, consider **smaller Standard** or even **Basic** (with HA trade-offs).
   - For high-performance:
     - Ensure Premium P2 is justified by throughput and features (persistence, clustering).

4. **Storage tiering and redundancy**
   - Baseline uses **GRS**; cost-optimized uses **LRS**; high-performance uses **GZRS**.
   - Confirm RPO/RTO and compliance requirements:
     - If cross-region DR is handled via backup or geo-replication elsewhere, you may not need GRS/GZRS for all data.
   - Aggressively move cold data to **Cool/Archive** to reduce cost.

5. **NAT and egress**
   - NAT egress is relatively small but:
     - Ensure outbound calls are necessary and not chatty (e.g., avoid polling external APIs).
     - Co-locate external dependencies in the same region where possible to reduce inter-region charges.

### 5.2 Spot vs PAYG vs Reserved

- **App Service & SQL DB**:
  - These are **steady-state, 24x7** workloads in all scenarios → strong candidates for **1-year or 3-year reservations**.
  - Baseline and high-performance scenarios already assume reservations, but the pricing is ambiguous; confirm:
    - Number of instances / vCores covered by reservations.
    - Whether any **burst capacity** is left on PAYG (e.g., autoscale to extra instances).
- **Redis**:
  - If usage is steady, consider **Reserved Capacity for Redis** (where available).
  - For dev/test or bursty workloads, keep PAYG and consider **smaller tiers** plus application-level fallbacks.
- **Front Door**:
  - No “spot” equivalent; cost is driven by **traffic and requests**.  
  - For predictable high traffic, consider **Azure Savings Plan for Compute** (does not directly cover Front Door, but can offset other compute).

> **Spot** is not applicable to App Service, SQL DB, or Redis PaaS directly; it’s more relevant to VM-based architectures. Here, focus on **Reservations** and **Savings Plans**.

### 5.3 Right-Sizing Ideas

- **Baseline vs Cost Optimized**
  - App Service: 2× Premium v3 vs 1× Standard S1.  
    - If CPU/memory utilization is low and SLA is flexible, S1 or P0v3 with autoscale might be enough.
  - SQL: 4 vCores vs 2 vCores.  
    - Use **Query Store** and performance insights to see if CPU/IO is underutilized; consider 2 vCores or elastic pool.
  - Redis: Standard C1 vs Basic C0.  
    - If cache hit rate is high and latency is acceptable, C0 may be fine; but note **no replica** (lower availability).

- **High Performance**
  - App Service P2v3 with 4 instances:
    - Start with 2–3 instances and enable autoscale based on CPU/requests; avoid over-provisioning.
  - SQL Hyperscale:
    - Confirm that you truly need Hyperscale (large DB size, high concurrency, fast scale).  
    - If not, GP or Business Critical might be cheaper.
  - Redis Premium P2:
    - Validate memory and throughput requirements; P1 or clustered Standard might suffice.

### 5.4 Region and Egress Considerations

- **Regions used:** `westeurope` for most services, `northeurope` for Front Door.  
  - Front Door is a global service; pricing is by **zone** and **data transfer out** to the internet and between regions.
- **Egress drivers:**
  - Front Door egress to internet clients (2 TB baseline, 1 TB cost-optimized, 5 TB high-performance).
  - Blob storage egress (1 TB baseline, 0.5 TB cost-optimized, 4 TB high-performance).
  - NAT egress (500 GB baseline, 200 GB cost-optimized, 1 TB high-performance).

FinOps actions:

- Use **Front Door caching** and **Blob CDN capabilities** to reduce origin egress.
- Co-locate **App Service, SQL, Redis, Storage** in the same region to avoid inter-region data transfer.
- Monitor **egress per service** in Cost Management + Billing and set budgets/alerts.

---

## 6. Delta Tables vs Baseline

> Note: The tool marks scenarios as “not_comparable” due to SKU mismatches, but we can still compare **modeled totals**. Treat these as **directional**, not precise.

### 6.1 Overall Monthly / Yearly Totals

Using `total_monthly` / `total_yearly` (with estimates):

| Scenario        | Monthly Total (with est.) | Yearly Total (with est.) | Δ Monthly vs Baseline | Δ Monthly % | Δ Yearly vs Baseline | Δ Yearly % |
|-----------------|--------------------------:|--------------------------:|----------------------:|------------:|----------------------:|-----------:|
| baseline        | 818.44                    | 9821.22                   | –                     | –           | –                     | –          |
| cost_optimized  | 762.55                    | 9150.58                   | -55.89                | -6.8%       | -670.64               | -6.8%      |
| high_performance| 812.59                    | 9751.15                   | -5.85                 | -0.7%       | -70.07                | -0.7%      |

**Interpretation:**

- The **cost_optimized** scenario is modeled ~7% cheaper than baseline, mainly via smaller App Service, SQL, Redis, storage, and monitoring.
- The **high_performance** scenario appears only slightly cheaper than baseline in the model, which is **counterintuitive**; this is a strong signal that:
  - High-performance SKUs (P2v3, Hyperscale, Premium Redis, GZRS) are **not correctly priced** and are sitting in the “missing” bucket.

### 6.2 Category-Level Monthly Deltas

Using `totals.by_category.monthly` for each scenario.

#### Cost Optimized vs Baseline – Monthly by Category

| Category          | Baseline Monthly | Cost-Opt Monthly | Δ Monthly | Δ % vs Baseline |
|-------------------|----------------:|-----------------:|---------:|----------------:|
| Compute (AppSvc)  | 112.42          | 60.01            | -52.41   | -46.6%          |
| DB (SQL)          | 100.00          | 100.00           | 0.00     | 0.0%            |
| DB (Redis)        | 100.00          | 100.00           | 0.00     | 0.0%            |
| Storage (Blob)    | 0.73            | 0.33             | -0.40    | -54.8%          |
| Network (Gateway) | 300.00          | 300.00           | 0.00     | 0.0%            |
| Network (NAT)     | 4.30            | 1.72             | -2.58    | -60.0%          |
| Network (Pub IP)  | 100.00          | 100.00           | 0.00     | 0.0%            |
| Security (KV)     | 0.52            | 0.26             | -0.26    | -50.0%          |
| Monitoring (LA)   | 100.00          | 100.00           | 0.00     | 0.0%            |
| Backup/DR         | 0.47            | 0.23             | -0.24    | -51.1%          |

**Key drivers of modeled savings:**

- **Compute**: ~47% lower App Service cost (2× Premium v3 → 1× Standard S1).
- **Storage & NAT**: ~55–60% lower due to reduced capacity and egress.
- **Key Vault & Backup**: ~50% lower due to fewer operations and smaller backup footprint.

#### High Performance vs Baseline – Monthly by Category

| Category          | Baseline Monthly | High-Perf Monthly | Δ Monthly | Δ % vs Baseline |
|-------------------|----------------:|------------------:|---------:|----------------:|
| Compute (AppSvc)  | 112.42          | 100.00            | -12.42   | -11.0%          |
| DB (SQL)          | 100.00          | 100.00            | 0.00     | 0.0%            |
| DB (Redis)        | 100.00          | 100.00            | 0.00     | 0.0%            |
| Storage (Blob)    | 0.73            | 2.00              | +1.27    | +174.0%         |
| Network (Gateway) | 300.00          | 300.00            | 0.00     | 0.0%            |
| Network (NAT)     | 4.30            | 8.60              | +4.30    | +100.0%         |
| Network (Pub IP)  | 100.00          | 100.00            | 0.00     | 0.0%            |
| Security (KV)     | 0.52            | 1.29              | +0.77    | +148.1%         |
| Monitoring (LA)   | 100.00          | 100.00            | 0.00     | 0.0%            |
| Backup/DR         | 0.47            | 0.70              | +0.23    | +48.9%          |

**Interpretation:**

- The model shows **slightly lower compute cost** for high-performance vs baseline, which is clearly wrong given P2v3 with 4 instances vs P1v3 with 2 instances. This is due to:
  - Reservations being normalized to a flat 100 EUR/month.
- It correctly shows:
  - **Higher storage, NAT, Key Vault, and backup costs** due to larger volumes and higher tiers.
- Treat the high-performance scenario as **“same order of magnitude but higher than baseline”** once real prices are applied.

---

## 7. Explicit Notes on Key Services

- **Key Vault / Secrets Management**
  - Present in all scenarios; cost is low but critical for security.
  - Operations scale with:
    - App Service startup and configuration reloads.
    - Certificate renewals and key rotations.
  - For high-performance, Premium Key Vault adds HSM-backed keys and higher operation volume; cost remains small relative to compute/DB.

- **Log Analytics / Monitoring**
  - Present in all scenarios; currently modeled as a flat 100 EUR/month.
  - Real cost scales with:
    - **Data ingestion (GB/day)** from App Service, SQL diagnostics, Front Door, platform logs.
    - **Retention duration** beyond free period.
  - FinOps lever: tune diagnostic settings, use sampling, and consider commitment tiers.

- **Backup Vault & Site Recovery**
  - Backup vault present in all scenarios; Site Recovery is not explicitly modeled.
  - Costs scale with:
    - Protected instance count.
    - Backup frequency and retention (GB-month).
  - For DR, if you add **Azure Site Recovery**, expect additional per-instance and storage costs.

- **Network Egress / NAT / Gateways / Front Door**
  - Front Door and Blob egress dominate internet data transfer costs (not fully priced here).
  - NAT egress is modeled and grows with outbound calls to external services.
  - Private Endpoints introduce **Private Link data processing** charges (missing here).
  - FinOps: optimize caching, co-location, and avoid unnecessary cross-region traffic.

- **Data Volume / Throughput Scaling**
  - **SQL DB**: vCores and storage scale cost; Hyperscale adds more components (compute, log, page servers).
  - **Redis**: memory size and throughput scale cost; Premium adds persistence and clustering.
  - **Blob**: GB stored per tier + operations + egress.
  - **Log Analytics**: GB ingested and retained.

---

If you’d like, I can next:

- Rebuild these three scenarios directly in the **Azure Pricing Calculator** with corrected SKUs, or
- Propose a **target architecture** (e.g., “start with cost_optimized, scale to baseline/high-performance”) with concrete thresholds (CPU, QPS, DB size) for when to move tiers.