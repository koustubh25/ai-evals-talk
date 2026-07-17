#!/usr/bin/env bash
# STAGE SCRIPT — the production incident, one command.
#   ./runbook/degrade.sh on     ./runbook/degrade.sh off     ./runbook/degrade.sh status
set -euo pipefail
BASE=https://inventory-mock-ktb-au.azurewebsites.net

case "${1:-status}" in
  on)   curl -s -X POST "$BASE/admin/degrade" -H 'Content-Type: application/json' -d '{"enabled":true}' ;;
  off)  curl -s -X POST "$BASE/admin/degrade" -H 'Content-Type: application/json' -d '{"enabled":false}' ;;
  *)    curl -s "$BASE/healthz" ;;
esac | python3 -m json.tool
