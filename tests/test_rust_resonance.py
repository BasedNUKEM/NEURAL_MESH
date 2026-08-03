"""Parity and fallback tests for the optional Rust resonance hot path."""
from __future__ import annotations

import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from neural_mesh import MemoryType, Mesh  # noqa: E402
from neural_mesh.resonance import retrieve  # noqa: E402


class TestRustSpreadActivation(unittest.TestCase):
    def test_weighted_max_spread_matches_resonance_contract(self):
        import rust_mesh

        # Initial activation exists on every node; only nodes 0 and 3 seed the
        # frontier. Activation propagates only when a path improves a node.
        result = rust_mesh.spread_activation(
            [0.8, 0.1, 0.0, 0.4],
            [(0, 1, 0.9), (1, 2, 0.5), (3, 2, 0.8), (2, 0, 1.0)],
            [0, 3],
            2,
            0.5,
        )

        self.assertEqual(len(result), 4)
        self.assertAlmostEqual(result[0], 0.8, places=6)
        self.assertAlmostEqual(result[1], 0.36, places=6)
        self.assertAlmostEqual(result[2], 0.16, places=6)
        self.assertAlmostEqual(result[3], 0.4, places=6)


class TestRustQueryScoring(unittest.TestCase):
    def test_query_dot_similarity_matches_python_embedding_contract(self):
        import rust_mesh

        result = rust_mesh.query_dot_similarity(
            [2.0, 3.0],
            [4.0, 5.0, 1.0, -1.0, 0.0, 0.0],
            2,
        )

        self.assertEqual(len(result), 3)
        self.assertAlmostEqual(result[0], 23.0, places=6)
        self.assertAlmostEqual(result[1], -1.0, places=6)
        self.assertAlmostEqual(result[2], 0.0, places=6)


class TestResonanceBackendParity(unittest.TestCase):
    def test_rust_and_python_backends_return_the_same_ranked_hits(self):
        mesh = Mesh(":memory:", link_threshold=1.1)
        nodes = [
            mesh.add("deploy seed", MemoryType.SEMANTIC, trust=1.0),
            mesh.add("linked runbook", MemoryType.PROCEDURAL, trust=0.9),
            mesh.add("remote incident", MemoryType.EPISODIC, trust=0.8),
            mesh.add("unrelated weather", MemoryType.SEMANTIC, trust=0.7),
        ]
        nodes[0].links[nodes[1].id] = 0.9
        nodes[1].links[nodes[2].id] = 0.8
        mesh._save(nodes[0])
        mesh._save(nodes[1])
        loaded = mesh._load()
        query_embedding = mesh.embedder("deploy seed")

        python_hits = retrieve(loaded, query_embedding, top_k=4, backend="python")
        rust_hits = retrieve(loaded, query_embedding, top_k=4, backend="rust")

        self.assertEqual([node.id for node in rust_hits],
                         [node.id for node in python_hits])

    def test_mesh_can_pin_resonance_backend(self):
        mesh = Mesh(":memory:", link_threshold=1.1, resonance_backend="python")
        mesh.add("alpha deploy", MemoryType.SEMANTIC)

        with mock.patch(
            "neural_mesh.core._resonance_retrieve",
            wraps=retrieve,
        ) as recalled:
            mesh.recall("deploy")

        self.assertEqual(recalled.call_args.kwargs["backend"], "python")
        self.assertEqual(mesh.stats()["resonance_backend"], "python")

    def test_rust_backend_accelerates_query_scoring(self):
        import rust_mesh

        mesh = Mesh(":memory:", link_threshold=1.1)
        mesh.add("alpha deploy", MemoryType.SEMANTIC)
        mesh.add("beta incident", MemoryType.EPISODIC)
        loaded = mesh._load()

        with mock.patch.object(
            rust_mesh,
            "query_dot_similarity",
            wraps=rust_mesh.query_dot_similarity,
        ) as accelerated:
            retrieve(loaded, mesh.embedder("deploy"), backend="rust")

        accelerated.assert_called_once()


if __name__ == "__main__":
    unittest.main()
