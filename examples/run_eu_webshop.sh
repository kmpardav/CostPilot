#!/usr/bin/env bash
set -euo pipefail

# Optional: load local overrides (OPENAI_API_KEY, AZURECOST_DEFAULT_REGION/CURRENCY, etc.)
if [ -f "$(dirname "$0")/configs/.env.local" ]; then
  set -a
  source "$(dirname "$0")/configs/.env.local"
  set +a
fi

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
OUTPUT_DIR="$SCRIPT_DIR/out"
mkdir -p "$OUTPUT_DIR"

azure_cost \
  --mode recommend \
  --output-format both \
  --output-prefix "$OUTPUT_DIR/eu_webshop" \
  < "$SCRIPT_DIR/workloads/eu_webshop.txt"
