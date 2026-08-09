"""Echo-chamber guard tests — the muse must NEVER synthesize from dream-muse.

Regression suite for the v0.26.0 provenance-diversity guard: a mesh where
the DREAM cycle keeps summarizing its own summaries (dream-of-dream) drowns
real-world memory in self-referential noise. These tests pin the contract:

  1. A mesh containing ONLY dream-muse nodes must mint ZERO new insights.
  2. Real-world clusters (cron-auto-seed, pcm-intel-fetch, intuition-mainnet,
     d0xeddev, mcp-bootstrap, bankr-cli, hermes-*) must still be synthesized —
     the guard filters, it does not silence.
  3. Insight minting is capped per cycle (DREAM_MAX_INSIGHTS, default 5).
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from neural_mesh import Mesh, MemoryType  # noqa: E402
from neural_mesh.dream import dream as dream_cycle  # noqa: E402
from neural_mesh.muse import template_muse  # noqa: E402

DREAM_PROVENANCE = "dream-muse"


def _mesh_with_only_dream_nodes(n: int = 6) -> Mesh:
    m = Mesh(":memory:")
    for i in range(n):
        m.add(f"[dream summary] dream-muse cluster ({i} memories): key topics — "
              f"dream, memories, trust, cluster, summary #{i}",
              type=MemoryType.SEMANTIC, lane="cold",
              provenance=DREAM_PROVENANCE, by="dream", trust=0.85)
    return m


class TestDreamProvenanceGuard(unittest.TestCase):

    def test_dream_only_mesh_mints_zero_insights(self):
        """A mesh of ONLY dream-muse nodes must NOT mint dream-of-dream nodes."""
        m = _mesh_with_only_dream_nodes(6)
        rep = dream_cycle(m, muse_fn=template_muse)
        self.assertEqual(rep["insights"], [],
                         "dream must not synthesize from dream-muse-only survivors")

        dream_nodes = [n for n in m._load().values() if n.provenance == DREAM_PROVENANCE]
        # no NEW dream-muse nodes beyond the 6 we seeded
        self.assertEqual(len(dream_nodes), 6)

    def test_real_cluster_still_synthesized(self):
        """Real-world clusters survive the guard — the muse still works."""
        m = Mesh(":memory:")
        # real-world cluster (>= 3 members -> passes template_muse min_cluster)
        for i in range(4):
            m.add(f"cron auto-seed heartbeat agent d0xeddev engine {i}",
                  provenance="cron-auto-seed", trust=0.9)
        # noise: a couple of dream-muse nodes must NOT dilute the real cluster
        for i in range(3):
            m.add(f"[dream leaderboard] top resonance: dream memory {i}",
                  provenance=DREAM_PROVENANCE, by="dream", trust=0.85)
        rep = dream_cycle(m, muse_fn=template_muse)
        self.assertTrue(rep["insights"],
                        "real-world cluster should still produce insights")
        joined = " ".join(rep["insights"]).lower()
        self.assertIn("cron-auto-seed", joined)
        self.assertNotIn("dream-muse cluster", joined)

    def test_cap_insights_per_cycle(self):
        """DREAM_MAX_INSIGHTS caps minted insights (default 5)."""
        old = os.environ.get("DREAM_MAX_INSIGHTS")
        os.environ["DREAM_MAX_INSIGHTS"] = "2"
        try:
            m = Mesh(":memory:")
            for prov in ("cron-auto-seed", "pcm-intel-fetch", "intuition-mainnet",
                         "d0xeddev", "mcp-bootstrap", "bankr-cli"):
                for i in range(4):
                    m.add(f"{prov} real memory node {i} trust high",
                          provenance=prov, trust=0.9)
            rep = dream_cycle(m, muse_fn=template_muse)
            self.assertLessEqual(len(rep["insights"]), 2)
        finally:
            if old is None:
                os.environ.pop("DREAM_MAX_INSIGHTS", None)
            else:
                os.environ["DREAM_MAX_INSIGHTS"] = old

    def test_default_cap_is_five(self):
        """Without the env var, the cap defaults to 5."""
        old = os.environ.pop("DREAM_MAX_INSIGHTS", None)
        try:
            m = Mesh(":memory:")
            for prov in ("cron-auto-seed", "pcm-intel-fetch", "intuition-mainnet",
                         "d0xeddev", "mcp-bootstrap", "bankr-cli", "hermes-session"):
                for i in range(4):
                    m.add(f"{prov} real memory node {i} trust high",
                          provenance=prov, trust=0.9)
            rep = dream_cycle(m, muse_fn=template_muse)
            self.assertLessEqual(len(rep["insights"]), 5)
        finally:
            if old is not None:
                os.environ["DREAM_MAX_INSIGHTS"] = old

    def test_dream_preview_respects_guard(self):
        """dream_preview (dry-run) must apply the same provenance filter."""
        from neural_mesh.dream import dream_preview
        m = _mesh_with_only_dream_nodes(5)
        preview = dream_preview(m, muse_fn=template_muse)
        self.assertEqual(preview["insights"], [])

    def test_supersede_second_cycle(self):
        """Second dream cycle on same real cluster supersedes the first."""
        m = Mesh(":memory:")
        for i in range(4):
            m.add(f"cron auto-seed heartbeat d0xeddev engine {i}",
                  provenance="cron-auto-seed", trust=1.0)
        rep1 = dream_cycle(m, muse_fn=template_muse, prune_below=0.05)
        self.assertTrue(rep1["insights"], f"cycle 1 failed: {rep1}")
        rep2 = dream_cycle(m, muse_fn=template_muse, prune_below=0.05)
        self.assertTrue(rep2["insights"], f"cycle 2 failed: {rep2}")
        active_dream = [n for n in m._load().values()
                        if n.provenance == DREAM_PROVENANCE and not n.superseded_by]
        superseded_dream = [n for n in m._load().values()
                            if n.provenance == DREAM_PROVENANCE and n.superseded_by]
        # second cycle's summary is the only active one per facet
        self.assertGreaterEqual(len(active_dream), 1,
                                f"expected active insights, got superseded={len(superseded_dream)}")
        self.assertGreater(len(superseded_dream), 0,
                           "first cycle's summary should be superseded")


if __name__ == "__main__":
    unittest.main()
