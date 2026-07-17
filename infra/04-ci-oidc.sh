#!/usr/bin/env bash
# Phase 4 — keyless CI auth: GitHub Actions -> Azure via OIDC federation.
# Executed MANUALLY by Koustubh on 2026-07-16 (learning exercise); captured here
# for reproducibility. Idempotent-ish: az ad app create by display name will
# create a duplicate if run twice — check first.
#
# Concept (GCP analogy: Workload Identity Federation):
#   app registration = the app's global definition (the "class")
#   service principal = its instance in this tenant (≈ GCP service account)
#   federated credential = "trust GitHub-signed tokens whose claims match this repo"
set -euo pipefail

REPO=koustubh25/ai-evals-talk
# 2026 GitHub OIDC format embeds immutable account/repo IDs in the subject
# (protects against repo-rename hijack). Classic "repo:owner/name:..." subjects
# NO LONGER MATCH. Get the IDs from: gh api repos/$REPO --jq '.id, .owner.id'
REPO_SUBJECT="repo:koustubh25@5240529/ai-evals-talk@1302769253"
RG=rg-evals-demo
ACCOUNT=evalsdemo-ktb-au
SUB=$(az account show --query id -o tsv)
TENANT=$(az account show --query tenantId -o tsv)

# 1. Identity: app registration + service principal
APPID=$(az ad app list --display-name gh-evals-demo --query "[0].appId" -o tsv)
if [ -z "$APPID" ]; then
  APPID=$(az ad app create --display-name gh-evals-demo --query appId -o tsv)
  az ad sp create --id "$APPID" >/dev/null
fi
echo "clientId: $APPID"

# 2. Trust: GitHub OIDC tokens for this repo only (PRs + pushes to main)
az ad app federated-credential create --id "$APPID" --parameters '{
  "name": "gh-pull-requests",
  "issuer": "https://token.actions.githubusercontent.com",
  "subject": "'"$REPO_SUBJECT"':pull_request",
  "audiences": ["api://AzureADTokenExchange"]}' 2>/dev/null || true
az ad app federated-credential create --id "$APPID" --parameters '{
  "name": "gh-main",
  "issuer": "https://token.actions.githubusercontent.com",
  "subject": "'"$REPO_SUBJECT"':ref:refs/heads/main",
  "audiences": ["api://AzureADTokenExchange"]}' 2>/dev/null || true

# 3. Permissions: data-plane access to the Foundry account only (least privilege)
az role assignment create --assignee "$APPID" --role "Cognitive Services User" \
  --scope "/subscriptions/$SUB/resourceGroups/$RG/providers/Microsoft.CognitiveServices/accounts/$ACCOUNT"

# 4. Workflow inputs (identifiers, not credentials — no key exists anywhere)
gh secret set AZURE_CLIENT_ID --repo "$REPO" --body "$APPID"
gh secret set AZURE_TENANT_ID --repo "$REPO" --body "$TENANT"
gh secret set AZURE_SUBSCRIPTION_ID --repo "$REPO" --body "$SUB"

# Teardown after the talk: az ad app delete --id "$APPID"
