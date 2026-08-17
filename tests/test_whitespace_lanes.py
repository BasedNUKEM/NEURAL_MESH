"""Tests for the two new whitespace lanes: prospective memory + budget.

Run:  PYTHONPATH=. python -m unittest tests.test_whitespace_lanes -v
"""
from __future__ import annotations

import os
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from neural_mesh import Mesh, MemoryType  # noqa: E402
from neural_mesh.prospective import (  # noqa: E402
    upcoming, due_rank, snooze, expired, PROSPECTIVE_LINK,
)
from neural_mesh.budget import (  # noqa: E402
    token_estimate, select_fit, default_value_score, fit_summary,
)


def _mesh():
    return Mesh(":memory:")


class TestProspectiveLane(unittest.TestCase):
    def test_upcoming_surfaces_soon_due_only(self):
        m = _mesh()
        now = time.time()
        m.add("Do X now", type=MemoryType.PROSPECTIVE, prospective_at=now - 60)
        m.add("Do X in an hour", type=MemoryType.PROSPECTIVE,
              prospective_at=now + 3600)
        m.add("Do X in a week", type=MemoryType.PROSPECTIVE,
              prospective_at=now + 7 * 24 * 3600)
        due = upcoming(m, now=now, horizon_sec=24 * 3600)
        contents = [n.content for n in due]
        self.assertIn("Do X now", contents)
        self.assertIn("Do X in an hour", contents)
        self.assertNotIn("Do X in a week", contents)

    def test_due_rank_orders_by_proximity_and_trust(self):
        m = _mesh()
        now = time.time()
        m.add("commitment soon", type=MemoryType.PROSPECTIVE,
              prospective_at=now + 60, trust=0.9)
        m.add("commitment far", type=MemoryType.PROSPECTIVE,
              prospective_at=now + 3600, trust=0.9)
        ranked = due_rank(m, now=now, k=5)
        self.assertEqual(ranked[0].content, "commitment soon")

    def test_snooze_rewrites_due_time(self):
        m = _mesh()
        now = time.time()
        node = m.add("reminder", type=MemoryType.PROSPECTIVE,
                     prospective_at=now + 60)
        self.assertTrue(snooze(m, node.id, now + 24 * 3600))
        reloaded = m._load()[node.id]
        self.assertEqual(reloaded.links[PROSPECTIVE_LINK], now + 24 * 3600)

    def test_snooze_raises_on_non_prospective(self):
        m = _mesh()
        node = m.add("plain fact", type=MemoryType.SEMANTIC)
        with self.assertRaises(KeyError):
            snooze(m, node.id, time.time() + 100)

    def test_expired_tracks_forgotten(self):
        m = _mesh()
        now = time.time()
        m.add("long past", type=MemoryType.PROSPECTIVE,
              prospective_at=now - 10 * 24 * 3600)
        self.assertEqual(len(expired(m, now=now)), 1)


class TestBudgetLane(unittest.TestCase):
    def _nodes(self, n, resonance=0.5, trust=0.8, prefix="m"):
        m = _mesh()
        out = []
        for i in range(n):
            node = m.add(f"{prefix} {i} " + "x" * 100,
                         type=MemoryType.SEMANTIC, trust=trust)
            node.resonance = resonance  # set directly post-add
            out.append(node)
        return out

    def test_select_fit_respects_budget(self):
        nodes = self._nodes(5)
        kept, evicted = select_fit(nodes, budget=150)
        # ~100-char content = ~25 tokens each; 5 nodes fit
        self.assertTrue(kept)
        self.assertEqual(len(kept) + len(evicted), len(nodes))
        total_kept = sum(token_estimate(n.content) for n in kept)
        self.assertLessEqual(total_kept, 150)

    def test_eviction_is_non_destructive(self):
        nodes = self._nodes(4)
        budget = token_estimate(nodes[0].content)  # fits exactly one
        kept, evicted = select_fit(nodes, budget=budget)
        self.assertEqual(len(kept), 1)
        self.assertEqual(len(evicted), 3)
        # evicted nodes still exist in the mesh: their ids remain loadable
        mesh_ids = {n.id for n in nodes}
        self.assertEqual({n.id for n in evicted} | {n.id for n in kept},
                         mesh_ids)

    def test_priority_eviction_keeps_high_value(self):
        m = _mesh()
        low = m.add("low value", type=MemoryType.SEMANTIC, trust=0.8)
        high = m.add("high value", type=MemoryType.SEMANTIC, trust=0.8)
        low.resonance = 0.1
        high.resonance = 0.9
        budget = token_estimate(high.content)
        kept, evicted = select_fit([low, high], budget=budget,
                                   value_score=default_value_score)
        self.assertIn(high, kept)
        self.assertIn(low, evicted)

    def test_fit_summary_reports_counts_and_tokens(self):
        nodes = self._nodes(3)
        kept, evicted = select_fit(nodes, budget=200)
        s = fit_summary(kept, evicted)
        self.assertEqual(s["kept_count"] + s["evicted_count"], 3)
        self.assertTrue(s["evicted_retained_in_mesh"])
        self.assertGreaterEqual(s["kept_tokens"], 0)

    def test_budget_zero_evicts_all(self):
        nodes = self._nodes(2)
        kept, evicted = select_fit(nodes, budget=0)
        self.assertEqual(kept, [])
        self.assertEqual(len(evicted), 2)


if __name__ == "__main__":
    unittest.main()
