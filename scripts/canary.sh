#!/usr/bin/env bash
# Usage: scripts/canary.sh <canary-percent>   e.g. 10 -> 10% canary / 90% stable; 0 = rollback; 100 = promote
set -euo pipefail
pct="${1:?canary percent 0-100}"
[[ "$pct" =~ ^[0-9]+$ ]] && (( pct >= 0 && pct <= 100 )) || { echo "percent must be an integer 0-100"; exit 1; }
if (( pct == 0 )); then export CANARY_RULE=""; else export CANARY_RULE="${pct}.0% canary;"; fi
docker compose up -d --force-recreate nginx
echo "canary=${pct}% stable=$((100 - pct))%"
