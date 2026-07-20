#!/usr/bin/env bash
set -euo pipefail
# Create D0xedDev/NEURAL_MESH via REST API. Token pulled from git credential
# store; never echoed.
TOKEN=$(printf 'protocol=https\nhost=github.com\n' | git credential fill | awk -F= '/^password=/{print $2}')
if [ -z "$TOKEN" ]; then echo "NO TOKEN FOUND"; exit 1; fi

DESC="A self-organizing, self-forgetting agentic memory mesh. Typed memory · mesh topology · resonance retrieval · hot/cold lanes · sleep/prune · versioned truth."
read -r -d '' BODY <<JSON || true
{
  "name": "NEURAL_MESH",
  "description": "$DESC",
  "private": false,
  "license_template": "mit",
  "auto_init": false,
  "has_issues": true,
  "has_wiki": false
}
JSON

echo "==> creating repo D0xedDev/NEURAL_MESH ..."
RESP=$(curl -s -o /tmp/nm_resp.json -w '%{http_code}' -X POST \
  https://api.github.com/user/repos \
  -H "Authorization: Bearer $TOKEN" \
  -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  -d "$BODY")
echo "HTTP $RESP"
grep -E '"(full_name|html_url|clone_url|message|errors)"' /tmp/nm_resp.json | head -20 || true
