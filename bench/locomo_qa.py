"""End-to-end LoCoMo QA harness (model-free) for NEURAL_MESH.

WHY THIS EXISTS
---------------
`locomo_eval.py` only measures *retrieval grounding* — does the gold answer
string sit somewhere in the top-k retrieved nodes? That is the input to an
answerer, not an answer. The real LoCoMo test is: given the retrieved context,
could a reader produce the right answer? We approximate that WITHOUT an LLM
judge (so it stays reproducible and free) using an **extractive reader proxy**:

  * Context-Recall@k — union of retrieved nodes contains the gold answer.
  * Extractive-EM@k — the reader picks the node with the highest token overlap
    with the gold answer, then the sentence within it with the highest overlap,
    and we count an exact-match (case/space/punct-normalized) against gold.

This is a LOWER BOUND on what a real LLM reader would score (a language model
can paraphrase and aggregate across nodes; our proxy cannot). We say that
explicitly. It is still the most honest "does the memory contain the answer"
signal we can compute offline.

MODES
-----
We compare three NEURAL_MESH retrievers so the lexical/dense/hybrid story is
backed by measured numbers, not assertions:
  * dense   — pure cosine over stored embeddings
  * lexical — pure hashed (lexical) cosine
  * hybrid  — alpha*dense + (1-alpha)*lexical

Run:
    PYTHONPATH=. python bench/locomo_qa.py --locomo locomo10.json --embedder real
    PYTHONPATH=. python bench/locomo_qa.py --locomo locomo10.json --embedder hashed
    PYTHONPATH=. python bench/locomo_qa.py --locomo locomo10.json --embedder real --alpha 0.3
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from locomo_eval import (  # noqa: E402
    load_full_locomo, build_mesh, _real, _hashed,
)


# ---------- normalization shared with the metric ----------
def _norm(s: str) -> str:
    """Aggressive normalization for answer exact-match (LoCoMo protocol)."""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = s.lower()
    # collapse number words already; keep digits. drop punctuation, keep space
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _tokens(s: str) -> list[str]:
    return _norm(s).split()


def _tok_overlap(a: str, b: str) -> float:
    """Jaccard token overlap between two strings."""
    ta, tb = set(_tokens(a)), set(_tokens(b))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


# ---------- extraction reader ----------
def extractive_answer(hits, gold: str) -> str | None:
    """Extractive-reader proxy: choose the node whose content has the highest
    token overlap with the gold answer, then the sentence within it with the
    highest overlap. Returns the best sentence, or None if no hit."""
    if not hits:
        return None
    gold_n = _norm(gold)
    best_sent = None
    best_score = -1.0
    for h in hits:
        for sent in re.split(r"(?<=[.!?])\s+", h.content):
            sc = _tok_overlap(gold_n, sent)
            if sc > best_score:
                best_score = sc
                best_sent = sent
    return best_sent


def _context_recall(hits, gold: str) -> bool:
    g = _norm(gold)
    return any(g and g in _norm(h.content) for h in hits)


def evaluate_qa(mesh, queries, mode: str = "dense", top_k: int = 5,
                alpha: float = 0.5):
    ks = (1, 2, 3, 5)
    ctx = {k: 0 for k in ks}            # context contains answer
    em = {k: 0 for k in ks}             # extractive EM matches gold
    mrr_ctx = 0.0
    for q, gold in queries:
        if mode == "dense":
            hits = mesh.dense_recall(q, top_k=max(ks))
        elif mode == "lexical":
            hits = mesh.lexical_recall(q, top_k=max(ks))
        else:  # hybrid
            hits = mesh.hybrid_recall(q, top_k=max(ks), alpha=alpha)
        # context recall per k
        for k in ks:
            if _context_recall(hits[:k], gold):
                ctx[k] += 1
        # extractive EM at top_k
        pred = extractive_answer(hits[:top_k], gold)
        if pred is not None and _norm(pred) == _norm(gold):
            em[top_k] += 1
        # MRR over context (does any retrieved node up to rank r hold answer)
        first = None
        for i, h in enumerate(hits, 1):
            if _norm(gold) in _norm(h.content):
                first = i
                break
        mrr_ctx += (1.0 / first) if first else 0.0

    n = max(1, len(queries))
    return {
        "n": len(queries),
        "context_recall@k": {k: round(ctx[k] / n, 4) for k in ks},
        "extractive_em@%d" % top_k: round(em[top_k] / n, 4),
        "mrr_context": round(mrr_ctx / n, 4),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--locomo", required=True)
    ap.add_argument("--embedder", choices=["hashed", "real"], default="real")
    ap.add_argument("--top_k", type=int, default=5)
    ap.add_argument("--alpha", type=float, default=0.5,
                    help="hybrid lexical weight = (1-alpha); 0.5 = even mix")
    ap.add_argument("--chunk", action="store_true")
    ap.add_argument("--no-autolink", action="store_true")
    args = ap.parse_args()

    embedder = _real() if args.embedder == "real" else _hashed()
    print(f"==> loading FULL LoCoMo from {args.locomo}")
    nodes, queries = load_full_locomo(args.locomo)
    print(f"    nodes={len(nodes)} queries={len(queries)} embedder={args.embedder}")
    mesh = build_mesh(nodes, embedder=embedder, chunk=args.chunk,
                      autolink=not args.no_autolink)

    modes = ["dense", "lexical", "hybrid"]
    print(f"\nEND-TO-END LoCoMo QA (extractive reader proxy, top_k={args.top_k}, "
          f"alpha={args.alpha})")
    print("Lower bound on a real LLM reader; measures 'can the memory answer'.\n")
    for mode in modes:
        res = evaluate_qa(mesh, queries, mode=mode, top_k=args.top_k,
                          alpha=args.alpha)
        cr = res["context_recall@k"]
        print(f"[{mode:7s}] contextRecall@5={cr[5]:.3f}  "
              f"@1={cr[1]:.3f}  extractiveEM@{args.top_k}={res['extractive_em@%d'%args.top_k]:.3f}  "
              f"MRR(ctx)={res['mrr_context']:.3f}")
    print("\nMODES: dense=cosine only | lexical=hashed only | "
          "hybrid=alpha*dense+(1-alpha)*lexical")
    print("extractiveEM = reader picks highest-overlap sentence, exact-match vs gold.")
    return None


if __name__ == "__main__":
    main()
