#!/usr/bin/env bash
# One-shot OpenRouter credit check (not committed — dev only)
set -uo pipefail
KEY=$(grep -E 'OPENROUTER_API_KEY' /opt/data/.env.d0xeddev_populated | head -1 | sed -E 's/^[^=]*=[[:space:]]*["'"'"']?//; s/["'"'"'][[:space:]]*$//')
if [ -z "${KEY:-}" ]; then
  echo "NO_KEY_FOUND"
  exit 1
fi
echo "key_len=${#KEY}"
curl -s --max-time 20 -H "Authorization: Bearer ${KEY}" https://openrouter.ai/api/v1/credits
echo
