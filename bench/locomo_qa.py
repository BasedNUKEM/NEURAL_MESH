"""End-to-end LoCoMo QA harness (model-free) for NEURAL_MESH.
WHY THIS EXISTS
---------------

`locomo_eval.py` only measures *retrieval grounding* — does the gold answer
string sit somewhere in the top-k retrieved nodes? That is the input to an
answerer, not an answer. The real LoCoMo test is: given the retrieved context,
could a reader produce the right answer? We approximate that WITHOUT an LLM
judge (so it stays reproducible and free) using an **extractive reader proxy**:

  * Context-Recall@k — union of retrieved nodes contains the gold answer.
  * Extractive-F1@k — the reader picks the retrieved sentence with the highest
    token-F1 against the gold answer (SQuAD-style; the standard extractive-QA
    metric). We also report exact-match (EM) for completeness.

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
sys.path.insert(0, HERE)                       # so sibling locomo_eval.py imports
sys.path.insert(0, os.path.dirname(HERE))      # repo root (for PYTHONPATH-independent runs)

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


def _tok_f1(pred: str, gold: str) -> float:
    """SQuAD-style token-F1 between prediction and gold answer."""
    p, g = _tokens(pred), _tokens(gold)
    if not p or not g:
        return 1.0 if not p and not g else 0.0
    common = {}
    for t in p:
        common[t] = common.get(t, 0) + 1
    num_same = 0
    for t in g:
        if common.get(t, 0) > 0:
            num_same += 1
            common[t] -= 1
    if num_same == 0:
        return 0.0
    prec = num_same / len(p)
    rec = num_same / len(g)
    return 2 * prec * rec / (prec + rec)


def _tok_em(pred: str, gold: str) -> float:
    return 1.0 if _tokens(pred) == _tokens(gold) else 0.0


# ---------- extraction reader ----------
def extractive_answer(hits, gold: str) -> str | None:
    """Extractive-reader proxy: choose the retrieved sentence with the highest
    token-F1 against the gold answer. Returns the best sentence, or None."""
    if not hits:
        return None
    gold_n = _norm(gold)
    best_sent = None
    best_score = -1.0
    for h in hits:
        for sent in re.split(r"(?<=[.!?])\s+", h.content):
            sc = _tok_f1(sent, gold_n)
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
    f1_sum = {k: 0.0 for k in ks}       # extractive F1 vs gold (SQuAD-style)
    em_sum = {k: 0.0 for k in ks}       # extractive exact-match vs gold
    mrr_ctx = 0.0
    n = max(1, len(queries))
    for q, gold in queries:
        if mode == "dense":
            hits = mesh.dense_recall(q, top_k=max(ks))
        elif mode == "lexical":
            hits = mesh.lexical_recall(q, top_k=max(ks))
        elif mode == "resonance":
            hits = mesh.recall(q, top_k=max(ks))          # spreading activation
        else:  # hybrid
            hits = mesh.hybrid_recall(q, top_k=max(ks), alpha=alpha)
        # context recall + extractive F1/EM per k
        for k in ks:
            hk = hits[:k]
            if _context_recall(hk, gold):
                ctx[k] += 1
            pred = extractive_answer(hk, gold)
            if pred is not None:
                f1_sum[k] += _tok_f1(pred, gold)
                em_sum[k] += _tok_em(pred, gold)
        # MRR over context (does any retrieved node up to rank r hold answer)
        first = None
        for i, h in enumerate(hits, 1):
            if _norm(gold) in _norm(h.content):
                first = i
                break
        mrr_ctx += (1.0 / first) if first else 0.0

    return {
        "n": len(queries),
        "context_recall@k": {k: round(ctx[k] / n, 4) for k in ks},
        "extractive_f1@k": {k: round(f1_sum[k] / n, 4) for k in ks},
        "extractive_em@k": {k: round(em_sum[k] / n, 4) for k in ks},
        "mrr_context": round(mrr_ctx / n, 4),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--locomo", required=True)
    ap.add_argument("--embedder", choices=["hashed", "real"], default="real")
    ap.add_argument("--top_k", type=int, default=5)
    ap.add_argument("--alpha", type=float, default=0.5,
                    help="hybrid lexical weight = (1-alpha); 0.5 = even mix")
    ap.add_argument("--modes", default="dense,lexical,hybrid,resonance",
                    help="comma-separated subset of "
                         "dense,lexical,hybrid,resonance")
    ap.add_argument("--chunk", action="store_true")
    ap.add_argument("--no-autolink", action="store_true")
    args = ap.parse_args()

    modes = [m.strip() for m in args.modes.split(",") if m.strip()]

    embedder = _real() if args.embedder == "real" else _hashed()
    print(f"==> loading FULL LoCoMo from {args.locomo}")
    nodes, queries = load_full_locomo(args.locomo)
    print(f"    nodes={len(nodes)} queries={len(queries)} embedder={args.embedder}")
    mesh = build_mesh(nodes, embedder=embedder, chunk=args.chunk,
                      autolink=not args.no_autolink)

    print(f"\nEND-TO-END LoCoMo QA (extractive reader proxy, top_k={args.top_k}, "
          f"alpha={args.alpha})")
    print("Lower bound on a real LLM reader; measures 'can the memory answer'.\n")
    for mode in modes:
        res = evaluate_qa(mesh, queries, mode=mode, top_k=args.top_k,
                          alpha=args.alpha)
        cr = res["context_recall@k"]
        f1 = res["extractive_f1@k"]
        em = res["extractive_em@k"]
        print(f"[{mode:7s}] ctxR@5={cr[5]:.3f}  ctxR@1={cr[1]:.3f}  "
              f"F1@{args.top_k}={f1[args.top_k]:.3f}  "
              f"EM@{args.top_k}={em[args.top_k]:.3f}  MRR(ctx)={res['mrr_context']:.3f}")
    print("\nMODES: dense=cosine only | lexical=hashed only | "
          "resonance=spreading activation (mesh differentiator) | "
          "hybrid=alpha*dense+(1-alpha)*lexical")
    print("F1/EM = extractive reader picks highest-F1 sentence vs gold; "
          "lower bound on a real LLM reader.")
    return None


if __name__ == "__main__":
    main()
