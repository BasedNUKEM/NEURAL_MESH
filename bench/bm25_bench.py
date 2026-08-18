#!/usr/bin/env python3
"""BM25 Rust-vs-Python benchmark (v0.28.0).

Two honest comparisons over the SAME pre-tokenized synthetic corpus:

1. ONE-SHOT (cold): `neural_mesh.bm25.okapi_bm25` (rebuilds df every call) vs
   `rust_mesh.bulk_bm25` (re-converts the corpus over the PyO3 boundary every
   call). This shows the FFI conversion tax dominates — Rust only breaks even.

2. PERSISTENT INDEX (warm): the realistic mesh path — build an index once, then
   score many queries. Python reuses precomputed df/avgdl; Rust keeps the corpus
   in a persistent `rust_mesh.Bm25Index` so per-query scoring pays no conversion.
   This isolates the actual scoring loop.

Usage:
  PYTHONPATH=. python3 bench/bm25_bench.py --nodes 5000 --queries 50
  PYTHONPATH=. python3 bench/bm25_bench.py --nodes 50000 --queries 50
"""
from __future__ import annotations

import argparse
import random
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from neural_mesh.bm25 import (_corpus_stats, bm25_score, okapi_bm25,  # noqa: E402
                              rust_bm25_available)


def build_corpus(n_docs: int, vocab: int, doc_len: int, seed: int) -> list[list[str]]:
    """Zipf-weighted synthetic corpus so df is meaningful (not uniform)."""
    rng = random.Random(seed)
    terms = [f"w{i}" for i in range(vocab)]
    weights = [1.0 / (r + 1) for r in range(vocab)]
    return [rng.choices(terms, weights=weights, k=doc_len) for _ in range(n_docs)]


def make_queries(n: int, vocab: int, seed: int) -> list[list[str]]:
    rng = random.Random(seed)
    return [[f"w{rng.randrange(vocab)}" for _ in range(rng.randint(2, 6))] for _ in range(n)]


def best_of(fn, n=3):
    times = []
    for _ in range(n):
        t0 = time.perf_counter()
        result = fn()
        times.append(time.perf_counter() - t0)
    return min(times), result


def main():
    p = argparse.ArgumentParser(description="BM25 Rust-vs-Python benchmark")
    p.add_argument("--nodes", type=int, default=5000, help="corpus size (docs)")
    p.add_argument("--vocab", type=int, default=10000)
    p.add_argument("--doc-len", type=int, default=20)
    p.add_argument("--queries", type=int, default=50)
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()

    corpus = build_corpus(args.nodes, args.vocab, args.doc_len, args.seed)
    queries = make_queries(args.queries, args.vocab, args.seed + 1)
    avgdl = sum(len(d) for d in corpus) / len(corpus)

    print(f"BM25 BENCHMARK — corpus={len(corpus)} docs, vocab={args.vocab}, "
          f"avg doc_len={avgdl:.1f}, queries={len(queries)}")
    print()

    # ── 1. one-shot (cold) ────────────────────────────────────────────────
    py_cold, py_res = best_of(lambda: [okapi_bm25(corpus, q) for q in queries])
    print(f"  ONE-SHOT   python (stdlib): {py_cold:.3f}s")
    rust_cold = None
    if rust_bm25_available():
        import rust_mesh
        rust_mesh.bulk_bm25(corpus[:10], queries[0], 1.5, 0.75)  # warm up
        rust_cold, rust_res = best_of(
            lambda: [list(rust_mesh.bulk_bm25(corpus, q, 1.5, 0.75)) for q in queries])
        print(f"  ONE-SHOT   rust   (abi3)  : {rust_cold:.3f}s  ({py_cold/rust_cold:.1f}x)")
        _parity(py_res, rust_res, queries)

    # ── 2. persistent index (warm) ───────────────────────────────────────
    t0 = time.perf_counter()
    df, n, avgdl = _corpus_stats(corpus)
    py_build = time.perf_counter() - t0
    py_warm, py_warm_res = best_of(
        lambda: [[bm25_score(d, q, df, n, avgdl) for d in corpus] for q in queries])
    print(f"  WARM       python (stdlib): {py_warm:.3f}s  (df precompute {py_build:.2f}s)")
    if rust_bm25_available():
        import rust_mesh
        t0 = time.perf_counter()
        r_idx = rust_mesh.Bm25Index(corpus, 1.5, 0.75)
        build_t = time.perf_counter() - t0
        rust_warm, rust_warm_res = best_of(lambda: [list(r_idx.score(q)) for q in queries])
        print(f"  WARM       rust   (abi3)  : {rust_warm:.3f}s  ({py_warm/rust_warm:.1f}x) "
              f"(index build {build_t:.2f}s)")
        _parity(py_warm_res, rust_warm_res, queries)

    print()
    print("  Honest note: the warm comparison is the realistic mesh path (index")
    print("  built once, many queries). The one-shot comparison exists to show")
    print("  why a naive list-passing API cannot win — the PyO3 corpus-conversion")
    print("  tax swallows the scoring gain.")


def _parity(py_res, rust_res, queries):
    max_diff = 0.0
    mismatch = 0
    for q, a, b in zip(queries, py_res, rust_res):
        for x, y in zip(a, b):
            max_diff = max(max_diff, abs(x - y))
        if sorted(range(len(a)), key=lambda i: -a[i]) != sorted(range(len(b)), key=lambda i: -b[i]):
            mismatch += 1
    print(f"           parity: max|py-rust|={max_diff:.2e}, rank mismatches={mismatch}/{len(queries)}")


if __name__ == "__main__":
    main()
