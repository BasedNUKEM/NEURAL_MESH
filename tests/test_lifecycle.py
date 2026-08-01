"""End-to-end tests for the integrated v0.19 memory lifecycle."""
from __future__ import annotations

import os
import tempfile
import time
import unittest

from neural_mesh import MemoryLifecycle, MemoryType, Mesh


class TestMemoryLifecycle(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.mesh = Mesh(":memory:")
        self.life = MemoryLifecycle(
            self.mesh,
            pointer_root=os.path.join(self.tmp.name, "pointers"),
            pointer_threshold=64,
        )

    def tearDown(self):
        self.mesh.db.close()
        self.tmp.cleanup()

    def test_large_payload_is_externalized_and_indexed_as_pointer_node(self):
        report = self.life.ingest(
            "X" * 256,
            label="deploy-log",
            type=MemoryType.EPISODIC,
            provenance="tool",
        )

        self.assertTrue(report["externalized"])
        self.assertTrue(report["pointer"].startswith("mesh://deploy-log/"))
        self.assertEqual(self.life.pointers.resolve(report["pointer"]), "X" * 256)
        node = self.mesh._load()[report["node_id"]]
        self.assertEqual(node.meta["pointer"], report["pointer"])
        self.assertEqual(node.meta["payload_chars"], 256)
        self.assertNotIn("X" * 64, node.content)

    def test_retrieve_routes_fact_lookup_and_associative_modes(self):
        self.life.ingest("deployment region is eu-west-1", label="fact")
        fact = self.life.retrieve("deployment region", mode="fact", top_k=1)
        associative = self.life.retrieve("deployment region", mode="associative", top_k=1)

        self.assertEqual(fact["mode"], "hybrid")
        self.assertEqual(associative["mode"], "resonance")
        self.assertIn("eu-west-1", fact["hits"][0].content)
        self.assertIn("eu-west-1", associative["hits"][0].content)

    def test_maintain_runs_lane_consolidation_before_sleep(self):
        stale = self.mesh.add("durable runbook", type=MemoryType.PROCEDURAL,
                              lane="hot", trust=0.9)
        stale.created_at = time.time() - 10
        stale.access_count = 3
        self.mesh._save(stale)

        report = self.life.maintain(hot_ttl=1, cold_threshold=2,
                                    prune_below=0.01, max_age_days=30)

        self.assertEqual(self.mesh._load()[stale.id].lane, "cold")
        self.assertEqual(report["lanes"]["promoted"], 1)
        self.assertIn("pruned", report["sleep"])
        self.assertEqual(report["stats"]["cold"], 1)

    def test_maintain_full_mode_runs_dream_after_lane_consolidation(self):
        node = self.mesh.add("durable linked insight", lane="hot", trust=0.9)
        node.created_at = time.time() - 10
        node.access_count = 3
        self.mesh._save(node)

        report = self.life.maintain(
            hot_ttl=1,
            cold_threshold=2,
            mode="dream",
            muse_fn=lambda nodes: ["synthesized memory"],
        )

        self.assertEqual(report["lanes"]["promoted"], 1)
        self.assertIn("drifted", report["dream"])
        self.assertEqual(report["dream"]["insights"], ["synthesized memory"])

    def test_maintain_rejects_unknown_mode(self):
        with self.assertRaises(ValueError):
            self.life.maintain(mode="nap")

    def test_cycle_returns_ingest_retrieval_and_maintenance_report(self):
        report = self.life.cycle(
            "release checklist deploy production",
            query="how do I deploy",
            type=MemoryType.PROCEDURAL,
            hot_ttl=0,
            cold_threshold=0,
        )

        self.assertEqual(report["retrieval"]["mode"], "hybrid")
        self.assertGreaterEqual(len(report["retrieval"]["hits"]), 1)
        self.assertEqual(report["maintenance"]["lanes"]["promoted"], 1)


if __name__ == "__main__":
    unittest.main()
