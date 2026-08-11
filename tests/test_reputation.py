"""Tests for neural_mesh.reputation — ERC-8004 feedback signals + validation."""

import json
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from neural_mesh.reputation import (
    mesh_signal, feedback_signal, validation_summary,
    AGENT_REGISTRY_CAIP, IDENTITY_REGISTRY,
)


# ─── Mesh mock ─────────────────────────────────────────────────────────────

def _mock_mesh(nodes: list[dict]) -> MagicMock:
    """Build a mock Mesh whose _load() returns a dict of mock MemoryNodes."""
    m = MagicMock()
    node_dict = {}
    for i, nd in enumerate(nodes):
        n = MagicMock()
        n.id = nd.get("id", f"n{i}")
        n.content = nd.get("content", "")
        n.trust = nd.get("trust", 0.5)
        n.lane = nd.get("lane", "default")
        n.meta = nd.get("meta", {})
        n.by = nd.get("by", "agent-1")
        n.agent_id = nd.get("agent_id", "")
        n.created_at = nd.get("created_at", "2026-01-01T00:00:00Z")
        n.provenance = nd.get("provenance", "test")
        n.resonance = nd.get("resonance", 0.0)
        node_dict[n.id] = n
    m._load.return_value = node_dict
    m.stats.return_value = {"total_nodes": len(nodes), "active_nodes": len(nodes)}
    return m


# ─── Tests ─────────────────────────────────────────────────────────────────

class TestMeshSignal(unittest.TestCase):

    def test_empty_mesh(self):
        m = _mock_mesh([])
        sig = mesh_signal(m)
        self.assertEqual(sig["node_count"], 0)
        self.assertIn("no nodes", sig.get("warning", ""))

    def test_single_node(self):
        m = _mock_mesh([{"trust": 0.8, "lane": "default"}])
        sig = mesh_signal(m)
        self.assertEqual(sig["node_count"], 1)
        self.assertAlmostEqual(sig["mean_trust"], 0.8, places=4)
        self.assertEqual(sig["signals"]["reachable"], 1)

    def test_all_signals_present(self):
        m = _mock_mesh([
            {"trust": 0.9, "meta": {"corroborated": True}, "by": "agent-1"},
            {"trust": 0.7, "meta": {}, "by": "agent-2"},
        ])
        sig = mesh_signal(m)
        signals = sig["signals"]
        for k in ("starred", "reachable", "uptime", "corroborated",
                  "helixa_verified", "poisoned_rate"):
            self.assertIn(k, signals, f"missing signal {k}")
        # 50% corroborated
        self.assertEqual(signals["corroborated"], 50.0)

    def test_corroboration_boosts_starred(self):
        m = _mock_mesh([
            {"trust": 0.5, "meta": {"corroborated": True}, "by": "a"},
            {"trust": 0.5, "meta": {"corroborated": True}, "by": "b"},
            {"trust": 0.5, "meta": {}, "by": "c"},
        ])
        sig = mesh_signal(m)
        self.assertGreater(sig["signals"]["starred"], 50.0)

    def test_quarantine_flagged(self):
        m = _mock_mesh([
            {"trust": 0.8, "lane": "default", "by": "a"},
            {"trust": 0.0, "lane": "quarantine", "by": "b"},
        ])
        sig = mesh_signal(m)
        self.assertEqual(sig["quarantined"], 1)
        self.assertEqual(sig["signals"]["poisoned_rate"], 50.0)

    def test_helixa_verified_recognized(self):
        m = _mock_mesh([
            {"trust": 0.9, "meta": {"helixa_stamp": {"verified": "verified"}}, "by": "a"},
            {"trust": 0.5, "meta": {}, "by": "b"},
        ])
        sig = mesh_signal(m)
        self.assertEqual(sig["signals"]["helixa_verified"], 50.0)

    def test_agent_id_filter(self):
        m = _mock_mesh([
            {"trust": 0.8, "by": "keeper", "agent_id": "keeper"},
            {"trust": 0.3, "by": "rogue", "agent_id": "rogue"},
        ])
        sig = mesh_signal(m, agent_id="keeper")
        self.assertEqual(sig["node_count"], 1)
        self.assertAlmostEqual(sig["mean_trust"], 0.8, places=4)

    def test_agent_breakdown(self):
        m = _mock_mesh([
            {"trust": 0.8, "by": "a"},
            {"trust": 0.6, "by": "a"},
            {"trust": 0.4, "by": "b"},
        ])
        sig = mesh_signal(m)
        self.assertIn("a", sig["agents"])
        self.assertIn("b", sig["agents"])
        self.assertEqual(sig["agents"]["a"]["nodes"], 2)


class TestFeedbackSignal(unittest.TestCase):

    def test_basic_feedback(self):
        m = _mock_mesh([{"trust": 0.8, "meta": {}, "by": "agent-1"}])
        fb = feedback_signal(m, tag1="starred")
        self.assertIn("agentRegistry", fb)
        self.assertEqual(fb["agentRegistry"], AGENT_REGISTRY_CAIP)
        self.assertIn("clientAddress", fb)
        self.assertIn("offchain", fb)

    def test_uptime_decimals(self):
        m = _mock_mesh([{"trust": 1.0, "meta": {}, "by": "a"}])
        fb = feedback_signal(m, tag1="uptime")
        # uptime: 100 → 10000 with 2 decimals
        self.assertEqual(fb["valueDecimals"], 2)
        self.assertEqual(fb["value"], 10000)

    def test_invalid_tag1(self):
        m = _mock_mesh([{"trust": 0.5, "by": "a"}])
        # feedback_signal handles any tag1 from the signals, but unknown ones
        # just get 0 value. Test: an unexpected tag still returns valid structure.
        fb = feedback_signal(m, tag1="nonexistent")
        # falls back to starred
        self.assertEqual(fb["tag1"], "starred")

    def test_feedback_hash_is_hex(self):
        m = _mock_mesh([{"trust": 0.5, "by": "a"}])
        fb = feedback_signal(m)
        self.assertTrue(isinstance(fb["feedbackHash"], str))
        self.assertEqual(len(fb["feedbackHash"]), 64)  # sha256 hex

    def test_offchain_json_valid(self):
        m = _mock_mesh([{"trust": 0.85, "by": "agent-1",
                         "meta": {"corroborated": True}}])
        fb = feedback_signal(m)
        offchain = fb["offchain"]
        self.assertIn("type", offchain)
        self.assertIn("agentRegistry", offchain)
        self.assertIn("value", offchain)
        self.assertIn("createdAt", offchain)
        self.assertIn("mesh", offchain)


class TestValidationSummary(unittest.TestCase):

    def test_empty_mesh(self):
        m = _mock_mesh([])
        summary = validation_summary(m)
        self.assertEqual(summary["count"], 0)
        self.assertAlmostEqual(summary["averageResponse"], 0.0)

    def test_all_trusted(self):
        m = _mock_mesh([
            {"trust": 0.9, "by": "a", "content": "good"},
            {"trust": 0.8, "by": "a", "content": "also good"},
        ])
        summary = validation_summary(m, agent_id="a")
        self.assertEqual(summary["count"], 2)
        self.assertAlmostEqual(summary["averageResponse"], 0.85, places=4)
        self.assertEqual(len(summary["requestHashes"]), 2)

    def test_quarantine_zero(self):
        m = _mock_mesh([
            {"trust": 0.8, "lane": "default", "by": "a", "content": "ok"},
            {"trust": 0.0, "lane": "quarantine", "by": "a", "content": "bad"},
        ])
        summary = validation_summary(m, agent_id="a")
        self.assertEqual(summary["count"], 2)
        self.assertAlmostEqual(summary["averageResponse"], 0.4, places=4)

    def test_request_hashes_stable(self):
        m = _mock_mesh([
            {"trust": 0.5, "by": "a", "content": "hello world"},
        ])
        s1 = validation_summary(m, agent_id="a")
        s2 = validation_summary(m, agent_id="a")
        self.assertEqual(s1["requestHashes"], s2["requestHashes"])

    def test_max_50_hashes(self):
        nodes = [{"trust": 0.5, "by": "a", "content": f"msg-{i}"}
                 for i in range(100)]
        m = _mock_mesh(nodes)
        summary = validation_summary(m, agent_id="a")
        self.assertLessEqual(len(summary["requestHashes"]), 50)


if __name__ == "__main__":
    unittest.main()
