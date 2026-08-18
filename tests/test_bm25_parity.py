"""BM25 parity + wiring tests (v0.28.0).

The Rust extension (`rust_mesh.bulk_bm25` / `bm25_score` / `bm25_idf`) must be
formula-identical to the pure-stdlib reference in `neural_mesh.bm25` — same
scores within float tolerance AND identical ranking. The Python-reference and
mesh-wiring tests always run (pure stdlib); the Rust-parity class skips
gracefully when the extension isn't built, so a clean checkout still passes.

Run:  PYTHONPATH=. python3 -m unittest tests.test_bm25_parity -v
"""
from __future__ import annotations

import math
import os
import random
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from neural_mesh import MemoryType, Mesh  # noqa: E402
from neural_mesh.bm25 import (BM25Index, _idf, bm25_score, okapi_bm25,  # noqa: E402
                              rust_bm25_available)


class TestPythonReference(unittest.TestCase):
    """Hand-computed reference values — these pin the formula, not the Rust."""

    def test_idf_hand_value(self):
        # idf(3, 2) = ln(1 + (3-2+0.5)/(2+0.5)) = ln(1.6)
        self.assertAlmostEqual(_idf(3, 2), math.log(1.6), places=12)

    def test_okapi_hand_computed(self):
        corpus = [
            ["alpha", "beta", "gamma"],
            ["alpha", "alpha", "delta"],
            ["beta", "beta", "epsilon"],
        ]
        query = ["alpha", "beta"]
        scores = okapi_bm25(corpus, query)  # k1=1.5, b=0.75, avgdl=3.0
        idf = math.log(1.6)
        # doc0: alpha(1) + beta(1), denom_norm=1.0 -> 2 * idf
        self.assertAlmostEqual(scores[0], 2 * idf, places=6)
        # doc1/doc2: one term with tf=2 -> idf * 2 * 2.5 / (2 + 1.5)
        expected_single = idf * 2 * 2.5 / 3.5
        self.assertAlmostEqual(scores[1], expected_single, places=6)
        self.assertAlmostEqual(scores[2], expected_single, places=6)
        # doc0 (both terms) ranks first
        self.assertEqual(max(range(3), key=lambda i: scores[i]), 0)

    def test_empty_inputs(self):
        self.assertEqual(okapi_bm25([], ["a"]), [])
        self.assertEqual(okapi_bm25([["a", "b"]], []), [0.0])
        self.assertEqual(bm25_score([], ["a"], {}, 1, 1.0), 0.0)
        self.assertEqual(bm25_score(["a"], [], {}, 1, 1.0), 0.0)

    def test_oov_query_term_contributes_zero(self):
        corpus = [["known", "term"], ["other", "words"]]
        # "absent" is in no doc -> df=0, and never in any doc -> all scores 0
        self.assertEqual(okapi_bm25(corpus, ["absent"]), [0.0, 0.0])


@unittest.skipUnless(rust_bm25_available(), "rust_mesh BM25 extension not built")
class TestRustParity(unittest.TestCase):
    """Rust must match the Python reference score-for-score and rank-for-rank."""

    @classmethod
    def setUpClass(cls):
        import rust_mesh
        cls.rust = rust_mesh
        rng = random.Random(7)
        vocab = [f"term_{i}" for i in range(30)]
        cls.corpus = []
        for _ in range(80):
            doc = [rng.choice(vocab) for _ in range(rng.randint(5, 20))]
            cls.corpus.append(doc)
        cls.queries = [
            [rng.choice(vocab) for _ in range(rng.randint(1, 6))]
            for _ in range(10)
        ]

    def test_idf_parity(self):
        for n in (1, 5, 80, 1000):
            for df in range(0, n + 1):
                self.assertAlmostEqual(
                    self.rust.bm25_idf(n, df), _idf(n, df), places=12)

    def test_bulk_bm25_score_parity(self):
        for q in self.queries:
            rust = list(self.rust.bulk_bm25(self.corpus, q, 1.5, 0.75))
            py = okapi_bm25(self.corpus, q, 1.5, 0.75)
            self.assertEqual(len(rust), len(py))
            for r, p in zip(rust, py):
                self.assertAlmostEqual(r, p, places=9)

    def test_bulk_bm25_rank_parity(self):
        for q in self.queries:
            rust = list(self.rust.bulk_bm25(self.corpus, q, 1.5, 0.75))
            py = okapi_bm25(self.corpus, q, 1.5, 0.75)
            rust_rank = sorted(range(len(rust)), key=lambda i: -rust[i])
            py_rank = sorted(range(len(py)), key=lambda i: -py[i])
            self.assertEqual(rust_rank, py_rank)

    def test_single_doc_score_parity(self):
        # Reconstruct df/avgdl exactly as okapi_bm25 does, then compare one doc.
        n = len(self.corpus)
        df = {}
        total_len = 0
        for doc in self.corpus:
            total_len += len(doc)
            for t in set(doc):
                df[t] = df.get(t, 0) + 1
        avgdl = total_len / n
        q = self.queries[0]
        for doc in self.corpus:
            r = self.rust.bm25_score(doc, q, df, n, avgdl, 1.5, 0.75)
            p = bm25_score(doc, q, df, n, avgdl, 1.5, 0.75)
            self.assertAlmostEqual(r, p, places=12)

    def test_persistent_index_parity(self):
        # The optimized `Bm25Index.score` (precomputed per-doc tf) is a
        # separate code path from `bulk_bm25` and must also match Python.
        idx = self.rust.Bm25Index(self.corpus, 1.5, 0.75)
        self.assertEqual(len(idx), len(self.corpus))
        for q in self.queries:
            rust = list(idx.score(q))
            py = okapi_bm25(self.corpus, q, 1.5, 0.75)
            self.assertEqual(len(rust), len(py))
            for r, p in zip(rust, py):
                self.assertAlmostEqual(r, p, places=9)
            rust_rank = sorted(range(len(rust)), key=lambda i: -rust[i])
            py_rank = sorted(range(len(py)), key=lambda i: -py[i])
            self.assertEqual(rust_rank, py_rank)


class TestMeshWiring(unittest.TestCase):
    """The `lexical_backend` selector and `bm25_recall` method are wired in."""

    def _seeded_mesh(self, lexical_backend="bow"):
        m = Mesh(":memory:", lexical_backend=lexical_backend)
        m.add("the quick brown fox", type=MemoryType.SEMANTIC)
        m.add("quantum entanglement decoherence", type=MemoryType.SEMANTIC)
        m.add("the quick brown fox jumps over the lazy dog", type=MemoryType.SEMANTIC)
        return m

    def test_bm25_recall_returns_top_k(self):
        m = self._seeded_mesh()
        hits = m.bm25_recall("decoherence", top_k=2)
        self.assertEqual(len(hits), 2)
        self.assertIn("decoherence", hits[0].content)

    def test_bm25_boosts_rare_discriminating_term(self):
        # "decoherence" appears in exactly one node -> high idf -> ranks first.
        m = self._seeded_mesh()
        hits = m.bm25_recall("decoherence", top_k=1)
        self.assertEqual(len(hits), 1)
        self.assertIn("decoherence", hits[0].content)

    def test_lexical_backend_bm25_routes_to_bm25(self):
        m = self._seeded_mesh(lexical_backend="bm25")
        via_selector = m.lexical_recall("decoherence", top_k=1)
        self.assertTrue(via_selector)
        self.assertIn("decoherence", via_selector[0].content)

    def test_lexical_backend_default_bow_unchanged(self):
        m = self._seeded_mesh()  # default "bow"
        self.assertEqual(m.lexical_backend, "bow")
        # bow still returns hits (content overlap), just not BM25-ranked
        self.assertTrue(m.lexical_recall("quantum", top_k=1))

    def test_invalid_lexical_backend_raises(self):
        with self.assertRaises(ValueError):
            Mesh(":memory:", lexical_backend="wat")

    def test_bm25_index_invalidates_on_add(self):
        m = self._seeded_mesh(lexical_backend="bm25")
        m.lexical_recall("decoherence", top_k=1)  # builds the index (no "bromine")
        m.add("zephyr quixotic bromine", type=MemoryType.SEMANTIC)
        hits = m.bm25_recall("bromine", top_k=1)
        self.assertEqual(len(hits), 1)
        self.assertIn("bromine", hits[0].content)

    def test_bm25_index_dispatch_uses_rust_when_available(self):
        if rust_bm25_available():
            idx = BM25Index(["alpha beta", "gamma delta"])
            import rust_mesh
            self.assertTrue(callable(getattr(rust_mesh, "bulk_bm25", None)))
            # scores() must return one score per doc
            self.assertEqual(len(idx.scores("alpha")), 2)


if __name__ == "__main__":
    unittest.main()
