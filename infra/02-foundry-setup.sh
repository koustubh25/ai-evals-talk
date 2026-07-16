#!/usr/bin/env bash
# Phase 2 — Foundry project, model deployment, tracing backbone.
# Idempotent: safe to re-run. Executed 2026-07-13.
set -euo pipefail

LOCATION=australiaeast
RG=rg-evals-demo
ACCOUNT=evalsdemo-ktb-au          # globally unique; also the custom domain
PROJECT=proj-evals-demo
MODEL=gpt-5-mini                  # only OpenAI chat model with free-tier quota (see 01-*.sh)
MODEL_VERSION=2025-08-07
SUB=$(az account show --query id -o tsv)

# 1. Foundry resource (kind AIServices; new-style: hosts projects directly)
az cognitiveservices account create \
  -n "$ACCOUNT" -g "$RG" -l "$LOCATION" \
  --kind AIServices --sku S0 \
  --custom-domain "$ACCOUNT" --assign-identity --allow-project-management true

# 2. Project (child resource; no first-class CLI yet -> ARM API)
az rest --method put \
  --url "https://management.azure.com/subscriptions/$SUB/resourceGroups/$RG/providers/Microsoft.CognitiveServices/accounts/$ACCOUNT/projects/$PROJECT?api-version=2025-06-01" \
  --body '{"location":"'$LOCATION'","identity":{"type":"SystemAssigned"},"properties":{"displayName":"Evals Demo","description":"Green CI broken production - Experts Live Melbourne 2026"}}'

# 3. Model deployment: 50K TPM slice of the 500K quota; $0 idle, per-token billing
az cognitiveservices account deployment create \
  -g "$RG" -n "$ACCOUNT" \
  --deployment-name "$MODEL" \
  --model-name "$MODEL" --model-version "$MODEL_VERSION" --model-format OpenAI \
  --sku-name GlobalStandard --sku-capacity 50

# 4. Tracing backbone. Public network access must stay Enabled on App Insights:
#    traces-to-dataset (preview) queries it from the Foundry service side.
az monitor log-analytics workspace create -g "$RG" -n law-evals-demo -l "$LOCATION"
WSID=$(az monitor log-analytics workspace show -g "$RG" -n law-evals-demo --query id -o tsv)
# NB: created via generic ARM (the app-insights CLI extension failed to pip-install)
az resource create -g "$RG" -n appi-evals-demo \
  --resource-type "microsoft.insights/components" -l "$LOCATION" \
  --properties "{\"Application_Type\":\"web\",\"WorkspaceResourceId\":\"$WSID\",\"IngestionMode\":\"LogAnalytics\",\"publicNetworkAccessForIngestion\":\"Enabled\",\"publicNetworkAccessForQuery\":\"Enabled\"}"

# 5. Register App Insights as a project connection (powers tracing UI + traces-to-dataset)
APPID=$(az resource show -g "$RG" -n appi-evals-demo --resource-type microsoft.insights/components --query id -o tsv)
CONN=$(az resource show -g "$RG" -n appi-evals-demo --resource-type microsoft.insights/components --query properties.ConnectionString -o tsv)
az rest --method put \
  --url "https://management.azure.com/subscriptions/$SUB/resourceGroups/$RG/providers/Microsoft.CognitiveServices/accounts/$ACCOUNT/projects/$PROJECT/connections/appi-evals-demo?api-version=2025-06-01" \
  --body "{\"properties\":{\"category\":\"AppInsights\",\"target\":\"$APPID\",\"authType\":\"ApiKey\",\"credentials\":{\"key\":\"$CONN\"},\"isSharedToAll\":false,\"metadata\":{\"ApiType\":\"Azure\",\"ResourceId\":\"$APPID\"}}}"

# 6. Smoke test
KEY=$(az cognitiveservices account keys list -g "$RG" -n "$ACCOUNT" --query key1 -o tsv)
curl -s "https://$ACCOUNT.cognitiveservices.azure.com/openai/deployments/$MODEL/chat/completions?api-version=2024-10-21" \
  -H "api-key: $KEY" -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"Reply with exactly: EVALS DEMO ONLINE"}]}'
