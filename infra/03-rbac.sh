#!/usr/bin/env bash
# Phase 3 — data-plane RBAC: the signed-in user needs data-plane rights on the
# Foundry account to call the project API (agents, connections, telemetry).
# Subscription Owner is control-plane only and does NOT grant these data actions.
# NB: docs say "Azure AI User", but that role doesn't exist in this tenant (16 Jul
# 2026); "Cognitive Services User" carries dataActions Microsoft.CognitiveServices/*.
set -euo pipefail

RG=rg-evals-demo
ACCOUNT=evalsdemo-ktb-au
SUB=$(az account show --query id -o tsv)
ME=$(az ad signed-in-user show --query id -o tsv)
SCOPE="/subscriptions/$SUB/resourceGroups/$RG/providers/Microsoft.CognitiveServices/accounts/$ACCOUNT"

az role assignment create --assignee "$ME" --role "Cognitive Services User" --scope "$SCOPE"
