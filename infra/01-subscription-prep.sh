#!/usr/bin/env bash
# Phase 1 — subscription prep for the Experts Live evals demo.
# Idempotent: safe to re-run. Executed 2026-07-13 against "Azure subscription 1".
set -euo pipefail

LOCATION=australiaeast
RG=rg-evals-demo
ALERT_EMAIL=kosta250@gmail.com

# 1. Resource providers (GCP analogy: gcloud services enable ...)
for p in Microsoft.CognitiveServices Microsoft.Insights Microsoft.OperationalInsights Microsoft.Storage; do
  az provider register -n "$p"
done

# 2. Resource group — single container for ALL demo resources.
# Teardown after the talk: az group delete -n $RG --yes
az group create -n "$RG" -l "$LOCATION" \
  --tags purpose=experts-live-demo owner=koustubh delete-after=2026-08-01

# 3. Budget: $100/month, email alerts at 50% and 90% actual spend.
SUB=$(az account show --query id -o tsv)
az rest --method put \
  --url "https://management.azure.com/subscriptions/$SUB/providers/Microsoft.Consumption/budgets/evals-demo-budget?api-version=2024-08-01" \
  --body "{
    \"properties\": {
      \"category\": \"Cost\", \"amount\": 100, \"timeGrain\": \"Monthly\",
      \"timePeriod\": {\"startDate\": \"2026-07-01T00:00:00Z\", \"endDate\": \"2026-12-31T00:00:00Z\"},
      \"notifications\": {
        \"actual50\": {\"enabled\": true, \"operator\": \"GreaterThan\", \"threshold\": 50, \"thresholdType\": \"Actual\", \"contactEmails\": [\"$ALERT_EMAIL\"]},
        \"actual90\": {\"enabled\": true, \"operator\": \"GreaterThan\", \"threshold\": 90, \"thresholdType\": \"Actual\", \"contactEmails\": [\"$ALERT_EMAIL\"]}
      }
    }
  }"

# 4. Quota check (read-only). Finding on 2026-07-13:
#    OpenAI.GlobalStandard.gpt-5-mini  limit=500 (K TPM) — the ONLY OpenAI chat
#    model with free-tier quota in australiaeast. => Phase 2 deploys gpt-5-mini.
az cognitiveservices usage list -l "$LOCATION" -o table
