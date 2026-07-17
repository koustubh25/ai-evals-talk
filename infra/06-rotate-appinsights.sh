#!/usr/bin/env bash
# Incident response 2026-07-17: .env (with the App Insights connection string)
# was in the initial public push of the demo repo. Connection strings can't be
# rotated in place, so recreate the App Insights resource (new key) and rewire
# the project connection. Trace data is unaffected (it lives in Log Analytics).
set -euo pipefail

RG=rg-evals-demo
LOCATION=australiaeast
ACCOUNT=evalsdemo-ktb-au
PROJECT=proj-evals-demo
APPI=appi-evals-demo
SUB=$(az account show --query id -o tsv)

az resource delete -g "$RG" -n "$APPI" --resource-type microsoft.insights/components

WSID=$(az monitor log-analytics workspace show -g "$RG" -n law-evals-demo --query id -o tsv)
az resource create -g "$RG" -n "$APPI" \
  --resource-type "microsoft.insights/components" -l "$LOCATION" \
  --properties "{\"Application_Type\":\"web\",\"WorkspaceResourceId\":\"$WSID\",\"IngestionMode\":\"LogAnalytics\",\"publicNetworkAccessForIngestion\":\"Enabled\",\"publicNetworkAccessForQuery\":\"Enabled\"}" >/dev/null

APPID=$(az resource show -g "$RG" -n "$APPI" --resource-type microsoft.insights/components --query id -o tsv)
CONN=$(az resource show -g "$RG" -n "$APPI" --resource-type microsoft.insights/components --query properties.ConnectionString -o tsv)
az rest --method put \
  --url "https://management.azure.com/subscriptions/$SUB/resourceGroups/$RG/providers/Microsoft.CognitiveServices/accounts/$ACCOUNT/projects/$PROJECT/connections/$APPI?api-version=2025-06-01" \
  --body "{\"properties\":{\"category\":\"AppInsights\",\"target\":\"$APPID\",\"authType\":\"ApiKey\",\"credentials\":{\"key\":\"$CONN\"},\"isSharedToAll\":false,\"metadata\":{\"ApiType\":\"Azure\",\"ResourceId\":\"$APPID\"}}}" >/dev/null

echo "rotated. New connection string retrieved; update local .env manually:"
echo "  APPLICATIONINSIGHTS_CONNECTION_STRING=<hidden, in az resource show>"
