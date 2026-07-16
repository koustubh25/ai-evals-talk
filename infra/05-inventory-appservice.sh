#!/usr/bin/env bash
# Phase 4 — deploy the mock inventory service publicly so Foundry's cloud can
# call it as an OpenAPI tool (server-side tool execution; localhost is
# unreachable from Foundry). App Service F1 = free tier; `az webapp up` is core
# CLI (Container Apps needs the az extension that's broken on this machine).
# GCP analogy: App Engine standard, free quota.
set -euo pipefail

# Machine-specific workaround: Homebrew python@3.14's pyexpat resolves against
# the stale system /usr/lib/libexpat.1.dylib and crashes az's XML paths.
# Point the loader at Homebrew's expat instead. Root fix (someday):
#   brew update && brew upgrade expat python@3.14 azure-cli
export DYLD_LIBRARY_PATH=/opt/homebrew/opt/expat/lib${DYLD_LIBRARY_PATH:+:$DYLD_LIBRARY_PATH}

RG=rg-evals-demo
LOCATION=australiaeast
APP=inventory-mock-ktb-au           # globally unique -> https://$APP.azurewebsites.net
SRC="$(cd "$(dirname "$0")/../inventory-service" && pwd)"

az provider register -n Microsoft.Web --wait

# Build+deploy from source (Oryx). F1: free, sleeps when idle, 60 CPU-min/day cap
# — fine for CI + rehearsals; cold start ~30s after idle.
(cd "$SRC" && az webapp up \
  --name "$APP" --resource-group "$RG" --location "$LOCATION" \
  --runtime PYTHON:3.11 --sku F1 --os-type Linux)

# FastAPI needs an explicit startup command (default assumes Django/Flask).
az webapp config set -g "$RG" -n "$APP" \
  --startup-file "python -m uvicorn app:app --host 0.0.0.0 --port 8000"

# The app embeds this URL in its OpenAPI spec (servers:) for the Foundry tool.
az webapp config appsettings set -g "$RG" -n "$APP" \
  --settings PUBLIC_BASE_URL="https://$APP.azurewebsites.net" >/dev/null

echo "public URL: https://$APP.azurewebsites.net"
