```text
$ ./examples/run_eu_webshop.sh
Azure Personal Cost Architect – Local Tool
Designing architecture with LLM (Chat Completions, mode=recommend)…
Ensuring local catalogs in 'catalog' for currency='EUR'...
  - cache.redis @ westeurope (refresh=False)... OK → catalog/cache.redis__westeurope__EUR.jsonl
  - compute.vm @ westeurope (refresh=False)... OK → catalog/compute.vm__westeurope__EUR.jsonl
  - db.sqlmi @ westeurope (refresh=False)... OK → catalog/db.sqlmi__westeurope__EUR.jsonl
  - network.nat @ westeurope (refresh=False)... OK → catalog/network.nat__westeurope__EUR.jsonl
  - storage.blob @ westeurope (refresh=False)... OK → catalog/storage.blob__westeurope__EUR.jsonl
Enriching scenarios with local Azure Retail catalogs…
Generating final architecture + FinOps report (Markdown)…
──────────────────────── Cost Report ────────────────────────
# Azure Cost Architect – EU Webshop (sample)
...
Saved report to /workspace/CostPilot/examples/out/eu_webshop_report.md
```
