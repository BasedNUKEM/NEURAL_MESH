"""Real LoCoMo evaluation harness for NEURAL_MESH.

WHY THIS EXISTS
---------------
The honest claim we can make is narrow: on *update-heavy* memory, NEURAL_MESH
surfaces current truth where flat vector search leaks stale facts. But "memory
for long conversations" is the real arena — LoCoMo (snap-research) is the
standard benchmark. This harness ingests real LoCoMo conversations and scores
retrieval the way the paper does: does the top-k context contain the gold
answer string?

WHAT IT MEASURES
----------------
* recall@k  — fraction of questions whose gold answer appears in the top-k
  retrieved node contents (substring match, case-insensitive).
* MRR       — mean reciprocal rank of the first node whose content contains the
  gold answer.
This is retrieval-grounding quality (the input to an LLM answerer), not end-to-
end QA accuracy. That distinction is stated in the output, not hidden.

DATA
----
* Default: a SHIPPED mini-fixture (`fixtures/locomo_mini.json`) extracted from
  real LoCoMo conv-50 QA (single/multi-hop questions). Runs offline, verified.
* Full: pass `--locomo path/to/locomo10.json` to score all 10 conversations.
  Download once:
    curl -L https://raw.githubusercontent.com/snap-research/locomo/main/data/locomo10.json -o locomo10.json
  The harness maps each conversation's `qa` list into mesh nodes (one node per
  session summary) and queries with the `question` strings.

Run:
    PYTHONPATH=. python bench/locomo_eval.py            # mini fixture
    PYTHONPATH=. python bench/locomo_eval.py --locomo locomo10.json   # full
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from neural_mesh import Mesh, MemoryType  # noqa: E402


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]", " ", s.lower()).strip()


def build_mesh(nodes_text: list[str], embedder=None, chunk: bool = False,
               autolink: bool = True) -> Mesh:
    mesh = Mesh(db_path=":memory:", embedder=embedder or _hashed())
    mesh.link_threshold = 1.01 if not autolink else mesh.link_threshold
    if chunk:
        pieces = []
        for t in nodes_text:
            pieces += [s.strip() for s in re.split(r"(?<=[.!?])\s+", t)
                       if len(s.strip()) > 3]
    else:
        pieces = nodes_text
    # batched ingest: RealEmbedder.embed_many vs per-call add()
    if hasattr(embedder or _hashed(), "embed_many"):
        mesh.add_many(pieces, type=MemoryType.EPISODIC, provenance="locomo",
                      autolink=autolink)
    else:
        for p in pieces:
            mesh.add(p, type=MemoryType.EPISODIC, provenance="locomo")
    return mesh


def _hashed():
    from neural_mesh.embed import embed
    return embed


def _real():
    try:
        from neural_mesh.embed_real import RealEmbedder
        return RealEmbedder()
    except Exception as e:  # pragma: no cover
        print(f"[warn] real embedder unavailable ({e}); falling back to hashed",
              file=sys.stderr)
        return _hashed()


def recall_at_k(hits, gold: str, ks=(1, 2, 3, 5)):
    g = _norm(gold)
    out = {}
    first_rank = None
    for i, h in enumerate(hits, start=1):
        if g and g in _norm(h.content):
            if first_rank is None:
                first_rank = i
            for k in ks:
                if i <= k:
                    out[k] = out.get(k, 0) + 1
    for k in ks:
        out.setdefault(k, 0)
    return out, (1.0 / first_rank if first_rank else 0.0)


def evaluate(mesh: Mesh, queries: list[tuple[str, str]], top_k: int = 5):
    ks = (1, 2, 3, 5)
    totals = {k: 0 for k in ks}
    mrr_sum = 0.0
    for q, gold in queries:
        hits = mesh.recall(q, top_k=top_k)
        per, mrr = recall_at_k(hits, gold, ks)
        for k in ks:
            totals[k] += per.get(k, 0)
        mrr_sum += mrr
    n = max(1, len(queries))
    return {
        "n": len(queries),
        "recall@k": {k: round(totals[k] / n, 4) for k in ks},
        "mrr": round(mrr_sum / n, 4),
    }


def load_mini_fixture() -> tuple[list[str], list[tuple[str, str]]]:
    path = os.path.join(HERE, "fixtures", "locomo_mini.json")
    with open(path) as fh:
        data = json.load(fh)
    nodes = [s["summary"] for s in data["sessions"]]
    queries = [(q["question"], q["answer"]) for q in data["qa"]]
    return nodes, queries


def load_full_locomo(path: str) -> tuple[list[str], list[tuple[str, str]]]:
    """Map the real snap-research/locomo10.json schema into mesh nodes + Q/A.

    The real file has, per conversation: `session_summary` (dict of
    session_N_summary -> text), `event_summary` (per-session event lists),
    `observation`, `conversation`, and `qa`. We treat each session summary as a
    memory node (these are the curated, de-noised per-session facts the paper
    itself uses as retrieval targets) and every `qa` entry as a query with its
    gold `answer`."""
    with open(path) as fh:
        data = json.load(fh)
    nodes, queries = [], []
    for conv in data:
        # session summaries -> nodes
        for s in (conv.get("session_summary") or {}).values():
            if isinstance(s, str):
                nodes.append(s)
            elif isinstance(s, list):  # some entries are lists of sentences
                nodes.append(" ".join(str(x) for x in s))
        # event summaries also carry facts worth recalling
        for ev in (conv.get("event_summary") or {}).values():
            if isinstance(ev, list):
                nodes.append(" ".join(str(x) for x in ev))
            elif isinstance(ev, str):
                nodes.append(ev)
        for qa in conv.get("qa", []):
            ans = qa.get("answer")
            if ans is None:
                # adversarial/negative qa have no positive answer; skip as a
                # retrieval target (we only score whether gold answers appear)
                continue
            queries.append((qa["question"], str(ans)))
    return nodes, queries


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--locomo", help="path to full locomo10.json")
    ap.add_argument("--embedder", choices=["hashed", "real"], default="hashed")
    ap.add_argument("--top_k", type=int, default=5)
    ap.add_argument("--chunk", action="store_true",
                    help="split session summaries into sentences before indexing")
    ap.add_argument("--no-autolink", action="store_true",
                    help="skip O(n^2) auto-linking for bulk retrieval benchmarks")
    args = ap.parse_args()

    embedder = _real() if args.embedder == "real" else _hashed()
    if args.locomo:
        print(f"==> loading FULL LoCoMo from {args.locomo}")
        nodes, queries = load_full_locomo(args.locomo)
    else:
        print("==> loading shipped mini-fixture (real LoCoMo conv-50 QA)")
        nodes, queries = load_mini_fixture()
    print(f"    nodes={len(nodes)} queries={len(queries)} embedder={args.embedder}")

    mesh = build_mesh(nodes, embedder=embedder, chunk=args.chunk,
                      autolink=not args.no_autolink)
    res = evaluate(mesh, queries, top_k=args.top_k)

    print("\nLOCOMO RETRIEVAL GROUNDING")
    print(f"  queries            : {res['n']}")
    print(f"  recall@1           : {res['recall@k'][1]:.3f}")
    print(f"  recall@3           : {res['recall@k'][3]:.3f}")
    print(f"  recall@5           : {res['recall@k'][5]:.3f}")
    print(f"  MRR                : {res['mrr']:.3f}")
    print("\nNOTE: this measures whether the gold answer is IN the retrieved")
    print("context (retrieval grounding), not end-to-end QA accuracy. To get")
    print("full LoCoMo QA numbers, feed the retrieved context to an LLM.")
    return res


if __name__ == "__main__":
    main()
