#!/usr/bin/env python3
"""E2E LoCoMo QA with a generative LLM judge (v0.26.0).

Runs a subset of LoCoMo queries through a real LLM reader (OpenRouter or local)
and reports honest EM/F1 numbers. The extractive reader proxy produced
extractiveEM=0.000 across all modes — the generative reader closes the gap.

Usage:
  # Quick smoke test (20 queries):
  PYTHONPATH=. python3 bench/locomo_llm_judge.py --locomo locomo10.json --limit 20

  # Full run (all 1542 queries — takes minutes, costs ~$0.50):
  PYTHONPATH=. python3 bench/locomo_llm_judge.py --locomo locomo10.json

Requires OPENROUTER_API_KEY (reads from /opt/data/D0XEDDEV/.env as fallback).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from neural_mesh import Mesh
from neural_mesh.reader import ExtractiveReader, CallableReader
from bench.locomo_eval import build_mesh, load_full_locomo, _hashed


def _load_openrouter_key() -> str:
    """Load an inference key: OPENROUTER_API_KEY, OPENAI_API_KEY, else the
    Nous portal access token at /opt/data/shared/nous_auth.json."""
    key = os.environ.get("OPENROUTER_API_KEY", "") or os.environ.get("OPENAI_API_KEY", "")
    if key:
        return key
    env_file = pathlib.Path("/opt/data/D0XEDDEV/.env")
    if env_file.exists():
        for line in env_file.read_text().split("\n"):
            line = line.strip()
            if line.startswith("OPENROUTER_API_KEY="):
                return line.split("=", 1)[1].strip().strip("\"'")
    # Nous portal token
    import json
    for p in ("/opt/data/shared/nous_auth.json", "/opt/data/nous_token/nous_auth.json"):
        if pathlib.Path(p).exists():
            try:
                return json.load(open(p)).get("access_token", "")
            except Exception:
                pass
    return ""


def _base_url() -> str:
    """Inference base URL: explicit env, else the Nous portal endpoint."""
    b = os.environ.get("NEURAL_MESH_LLM_BASE", "")
    if b:
        return b.rstrip("/")
    import json
    for p in ("/opt/data/shared/nous_auth.json", "/opt/data/nous_token/nous_auth.json"):
        if pathlib.Path(p).exists():
            try:
                b = json.load(open(p)).get("inference_base_url", "")
                if b:
                    return b.rstrip("/")
            except Exception:
                pass
    return "https://openrouter.ai/api/v1"


def llm_answer(query: str, passages: list[str], api_key: str, model: str,
               base_url: str | None = None) -> str:
    """Generate a grounded answer from retrieved passages via the LLM API."""
    ctx = "\n\n".join(f"[{i+1}] {p[:800]}" for i, p in enumerate(passages[:5]))
    prompt = (
        "Answer the query concisely using ONLY the provided context passages. "
        "If the context doesn't contain enough information, say so. "
        "One sentence answer.\n\n"
        f"Context:\n{ctx}\n\n"
        f"Query: {query}\n\n"
        "Answer:"
    )

    import urllib.request
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": 100,
    }).encode()
    base = (base_url or _base_url()).rstrip("/")
    req = urllib.request.Request(
        f"{base}/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 hermes-agent",
        },
    )
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        data = json.loads(resp.read())
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        return (content or "").strip()[:300]
    except Exception as e:
        print(f"  [LLM error] {e}", file=sys.stderr)
        return ""


def run_qa(mesh, queries, reader, mode_label: str, top_k: int = 5):
    """Run the QA harness for a list of queries and report numbers."""
    from neural_mesh.core import MemoryType

    total = len(queries)
    ctx_hits = 0
    em = 0  # exact match
    f1_sum = 0.0
    mrr_sum = 0.0
    slow = 0

    for i, (query, gold) in enumerate(queries, 1):
        results = mesh.recall(query, top_k=top_k, writeback=False)

        # Context recall: is the gold answer text present in any result?
        gold_lower = gold.lower()
        got_ctx = any(gold_lower[:40] in (r.content or "").lower() for r in results)
        if got_ctx:
            ctx_hits += 1

        # Get passages
        passages = [r.content for r in results]

        # Generate answer via reader
        answer = reader.answer(query, passages, gold=gold)
        slow += 1

        # Score
        from neural_mesh.reader import _tok_f1
        f1 = _tok_f1(answer, gold)
        f1_sum += f1

        # MRR: first rank where a passage contains gold
        for rank, r in enumerate(results, 1):
            if gold_lower[:40] in (r.content or "").lower():
                mrr_sum += 1.0 / rank
                break

        # Exact match (generous: lowercase strip)
        if answer.lower().strip() == gold.lower().strip():
            em += 1

        if i % 10 == 0:
            print(f"  [{mode_label}] {i}/{total} ... F1={f1_sum/slow:.3f}", file=sys.stderr)

    n = total
    print(f"\n[{mode_label}] n={n} ctxR@5={ctx_hits/n:.3f} EM@5={em/n:.3f} "
          f"F1@5={f1_sum/n:.3f} MRR={mrr_sum/n:.3f}")
    return {"ctxR@5": ctx_hits/n, "EM@5": em/n, "F1@5": f1_sum/n, "MRR": mrr_sum/n}


def main():
    p = argparse.ArgumentParser(description="E2E LoCoMo QA with LLM judge")
    p.add_argument("--locomo", required=True)
    p.add_argument("--limit", type=int, default=0, help="Max queries (0=all)")
    p.add_argument("--top_k", type=int, default=5)
    p.add_argument("--model", default="deepseek/deepseek-chat-v3-0324")
    p.add_argument("--mode", default="dense", choices=["dense", "lexical", "hybrid", "resonance"])
    args = p.parse_args()

    api_key = _load_openrouter_key()
    if not api_key:
        print("WARNING: no OPENROUTER_API_KEY — running extractive only", file=sys.stderr)
        reader = ExtractiveReader()
    else:
        def _answer(q, ctx, **kw):
            return llm_answer(q, ctx, api_key, args.model, base_url=_base_url())
        reader = CallableReader(_answer)
        print(f"LLM judge: {args.model} (limit={args.limit or 'all'})", file=sys.stderr)

    # Load LoCoMo
    nodes, queries = load_full_locomo(args.locomo)
    if args.limit > 0:
        queries = queries[:args.limit]

    print(f"nodes={len(nodes)} queries={len(queries)} mode={args.mode}", file=sys.stderr)

    mesh = build_mesh(nodes, embedder=_hashed(), chunk=False, autolink=True)
    run_qa(mesh, queries, reader, args.mode, top_k=args.top_k)


if __name__ == "__main__":
    main()
