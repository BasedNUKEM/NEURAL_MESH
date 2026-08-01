"""Lane behavior tests for v0.20 retrieval semantics."""
from __future__ import annotations

import unittest

from neural_mesh import MemoryType, Mesh
from neural_mesh.dream import recall_associative


class TestLaneAwareRetrieval(unittest.TestCase):
    def setUp(self):
        self.mesh = Mesh(":memory:", link_threshold=2.0)
        self.hot = self.mesh.add("deployment region hot-primary", lane="hot")
        self.cold = self.mesh.add("deployment region cold-archive", lane="cold")

    def tearDown(self):
        self.mesh.db.close()

    def test_every_retrieval_mode_filters_result_lane(self):
        calls = [
            lambda lane: self.mesh.recall("deployment region", top_k=5, lane=lane),
            lambda lane: self.mesh.dense_recall("deployment region", top_k=5, lane=lane),
            lambda lane: self.mesh.lexical_recall("deployment region", top_k=5, lane=lane),
            lambda lane: self.mesh.hybrid_recall("deployment region", top_k=5, lane=lane),
        ]
        for call in calls:
            with self.subTest(call=call):
                self.assertEqual({n.lane for n in call("hot")}, {"hot"})
                self.assertEqual({n.lane for n in call("cold")}, {"cold"})

    def test_lane_none_preserves_all_lane_behavior(self):
        hits = self.mesh.recall("deployment region", top_k=5)
        self.assertEqual({n.id for n in hits}, {self.hot.id, self.cold.id})

    def test_invalid_lane_rejected(self):
        with self.assertRaises(ValueError):
            self.mesh.recall("deploy", lane="archive")

    def test_associative_recall_filters_lane(self):
        hot = self.mesh.add("hot starting signal", lane="hot", trust=1.0)
        cold = self.mesh.add("cold linked destination", lane="cold", trust=1.0)
        hot.links[cold.id] = 1.0
        cold.links[hot.id] = 1.0
        self.mesh._save(hot)
        self.mesh._save(cold)
        hits = recall_associative(self.mesh, "cold linked destination", top_k=5,
                                  lane="cold")
        self.assertTrue(hits)
        self.assertTrue(all(n.lane == "cold" for n in hits))

    def test_add_many_defaults_to_hot(self):
        nodes = self.mesh.add_many(
            ["bulk alpha", "bulk beta"],
            type=MemoryType.SEMANTIC,
            autolink=False,
        )
        self.assertEqual({n.lane for n in nodes}, {"hot"})


if __name__ == "__main__":
    unittest.main()
