#!/usr/bin/env python3
"""Probe OpenRouter key + model from the LIVE key location (.env.d0xeddev_populated)."""
import json, os, sys, urllib.request, pathlib

key = ""
model = "deepseek/deepseek-chat"
for src in ["/opt/data/.env.d0xeddev_populated", "/opt/data/D0XEDDEV/.env"]:
    p = pathlib.Path(src)
    if not p.exists():
        continue
    for line in p.read_text().split("\n"):
        line = line.strip()
        if line.startswith("export "):
            line = line[len("export "):]
        if line.startswith("OPENROUTER_API_KEY=") and not key:
            key = line.split("=", 1)[1].strip().strip("\"'")
        if line.startswith("OPENROUTER_MODEL="):
            model = line.split("=", 1)[1].strip().strip("\"'")

if not key:
    print("NO KEY FOUND")
    sys.exit(1)

print(f"model={model} key_len={len(key)} key_head={key[:7]}...")

def probe(model_slug):
    body = json.dumps({
        "model": model_slug,
        "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
        "temperature": 0,
        "max_tokens": 8,
    }).encode()
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://d0xeddev.com",
            "X-Title": "NEURAL_MESH LLM Judge",
        },
    )
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        data = json.loads(resp.read())
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        return f"OK -> {content!r}"
    except urllib.error.HTTPError as e:
        return f"HTTP {e.code}: {e.read().decode()[:200]}"
    except Exception as e:
        return f"ERR {e}"

for slug in [model, "deepseek/deepseek-chat-v3-0324"]:
    print(f"probe {slug}: {probe(slug)}")
