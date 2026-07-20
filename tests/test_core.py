"""Unit tests for NEURAL_MESH core behaviors.

Pure-stdlib: uses unittest + a tiny local SQLite in :memory: so it runs with
`python3 -m unittest` — no pytest needed.

Run:  PYTHONPATH=. python -m unittest tests.test_core -v
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from neural_mesh import Mesh, MemoryType  # noqa: E402
from neural_mesh import export_mesh, import_mesh  # noqa: E402
from neural_mesh import merge_peer_mesh, consensus_rank, PeerPolicy  # noqa: E402


def _export(mesh) -> str:
    path = tempfile.mktemp(suffix=".mesh")
    export_mesh(mesh, path)
    return path


class TestNodeModel(unittest.TestCase):
    def test_auto_id_and_timestamps(self):
        m = Mesh(":memory:")
        n = m.add("hello", MemoryType.SEMANTIC)
        self.assertTrue(n.id)
        self.assertGreater(n.created_at, 0)
        self.assertEqual(n.last_accessed, n.created_at)

    def test_supersede_marks_stale(self):
        m = Mesh(":memory:")
        old = m.add("old fact", MemoryType.SEMANTIC)
        new = m.add("new fact", MemoryType.SEMANTIC, supersedes=old.id)
        self.assertEqual(m._load()[old.id].superseded_by, new.id)


class TestAddAndTypes(unittest.TestCase):
    def test_add_all_six_types(self):
        m = Mesh(":memory:")
        for t in MemoryType:
            n = m.add(f"node-{t.value}", type=t)
            self.assertEqual(n.type, t)
        self.assertEqual(m.stats()["total"], len(list(MemoryType)))

    def test_meta_fields_persist(self):
        m = Mesh(":memory:")
        n = m.add("shared fact", MemoryType.SEMANTIC, agent_id="atlas",
                  trust=0.8, conflict_group="cg1")
        back = m._load()[n.id]
        self.assertEqual(back.agent_id, "atlas")
        self.assertEqual(back.trust, 0.8)
        self.assertEqual(back.conflict_group, "cg1")


class TestAutoLinking(unittest.TestCase):
    def test_add_many_bulk_ingest(self):
        m = Mesh(":memory:")
        nodes = m.add_many(
            ["alpha fact", "beta fact", "gamma fact"],
            type=MemoryType.SEMANTIC, provenance="bulk", autolink=False)
        self.assertEqual(len(nodes), 3)
        for n in nodes:
            self.assertTrue(n.id)
        res = m.recall("alpha", top_k=3)
        self.assertEqual(len(res), 3)
        self.assertEqual(res[0].content, "alpha fact")

    def test_related_nodes_link(self):
        m = Mesh(":memory:")
        a = m.add("the deploy uses vercel prod", MemoryType.PROCEDURAL)
        b = m.add("vercel prod went down last night", MemoryType.EPISODIC)
        self.assertTrue(len(m._load()[a.id].links) >= 1 or
                        len(m._load()[b.id].links) >= 1)

    def test_unrelated_nodes_do_not_link(self):
        m = Mesh(":memory:", link_threshold=0.95)
        x = m.add("banana smoothie recipe omega", MemoryType.SEMANTIC)
        y = m.add("quartz lamp postgresql migration alpha", MemoryType.SEMANTIC)
        self.assertEqual(len(m._load()[x.id].links), 0)
        self.assertEqual(len(m._load()[y.id].links), 0)


class TestResonanceRetrieval(unittest.TestCase):
    def test_retrieves_relevant(self):
        m = Mesh(":memory:")
        m.add("deploy with git push and vercel --prod", MemoryType.PROCEDURAL)
        m.add("the sky is blue", MemoryType.SEMANTIC)
        hits = m.recall("how do I deploy", top_k=3)
        self.assertTrue(any("vercel" in h.content for h in hits))

    def test_recall_touches_access(self):
        m = Mesh(":memory:")
        n = m.add("cache ttl is 300 seconds", MemoryType.SEMANTIC)
        before = m._load()[n.id].access_count
        m.recall("what is the cache ttl")
        after = m._load()[n.id].access_count
        self.assertEqual(after, before + 1)


class TestVersioning(unittest.TestCase):
    def test_superseded_excluded_from_recall(self):
        m = Mesh(":memory:")
        old = m.add("deploy region is us-east-1", MemoryType.SEMANTIC, trust=0.9)
        m.add("deploy region is eu-west-1", MemoryType.SEMANTIC, trust=0.9,
              supersedes=old.id)
        hits = m.recall("deploy region", top_k=5)
        self.assertFalse(any("us-east-1" in h.content for h in hits))
        self.assertTrue(any("eu-west-1" in h.content for h in hits))


class TestMeshFileRoundTrip(unittest.TestCase):
    def test_export_import_preserves(self):
        m = Mesh(":memory:")
        m.add("postgres pool max is 20", MemoryType.SEMANTIC, agent_id="devio",
              trust=0.9, conflict_group="cg")
        old = m.add("old", MemoryType.SEMANTIC)
        m.add("new", MemoryType.SEMANTIC, supersedes=old.id)
        path = _export(m)
        m2 = Mesh(":memory:")
        res = import_mesh(path, m2)
        self.assertEqual(res["loaded"], 3)
        pg = [n for n in m2._load().values()
              if n.content.startswith("postgres")]
        self.assertEqual(len(pg), 1)
        self.assertEqual(pg[0].agent_id, "devio")
        self.assertEqual(pg[0].conflict_group, "cg")


class TestCrossAgentSharing(unittest.TestCase):
    def test_corroboration_fuses_and_raises_trust(self):
        local = Mesh(":memory:")
        local.add("api key stored in vault", MemoryType.SEMANTIC,
                  agent_id="atlas", trust=0.7)
        peer = Mesh(":memory:")
        peer.add("api key stored in vault", MemoryType.SEMANTIC,
                 agent_id="scout", trust=0.8)
        path = _export(peer)
        merged = merge_peer_mesh(local, path, peer_id="scout", policy=PeerPolicy())
        self.assertEqual(merged["fused"], 1)
        fused = [n for n in local._load().values()
                 if "api key stored in vault" in n.content]
        self.assertEqual(len(fused), 1)
        self.assertGreater(fused[0].trust, 0.7)
        self.assertIn("+", fused[0].agent_id)

    def test_untrusted_peer_capped(self):
        local = Mesh(":memory:")
        local.add("the secret is 42", MemoryType.SEMANTIC, trust=0.9)
        peer = Mesh(":memory:")
        peer.add("the secret is 999", MemoryType.SEMANTIC, trust=1.0)
        path = _export(peer)
        pol = PeerPolicy(cap_trust=0.2)
        merge_peer_mesh(local, path, peer_id="rogue", policy=pol)
        rogue = [n for n in local._load().values() if "999" in n.content]
        self.assertTrue(rogue)
        self.assertLessEqual(rogue[0].trust, 0.2)

    def test_consensus_keeps_both_conflicts(self):
        m = Mesh(":memory:")
        a = m.add("region us-east-1", MemoryType.SEMANTIC, trust=0.9,
                  conflict_group="reg")
        b = m.add("region eu-west-1", MemoryType.SEMANTIC, trust=0.4,
                  conflict_group="reg")
        ranked = consensus_rank([m._load()[a.id], m._load()[b.id]])
        self.assertEqual(len(ranked), 2)
        self.assertEqual(ranked[0].content, "region us-east-1")


class TestDistill(unittest.TestCase):
    def test_distill_filters_low_trust_and_stale(self):
        m = Mesh(":memory:")
        m.add("good fact", MemoryType.SEMANTIC, trust=0.9)
        m.add("noise", MemoryType.SEMANTIC, trust=0.2)
        old = m.add("stale", MemoryType.SEMANTIC, trust=0.9)
        m.add("fresh", MemoryType.SEMANTIC, trust=0.9,
              supersedes=old.id)
        d = m.distill(min_trust=0.6, min_resonance=0.1)
        contents = [p["response"] for p in d["pairs"]]
        self.assertIn("good fact", contents)
        self.assertIn("fresh", contents)
        self.assertNotIn("noise", contents)
        self.assertNotIn("stale", contents)


class TestHelixaProvenance(unittest.TestCase):
    def test_stamp_roundtrips_through_node_meta(self):
        from neural_mesh.integrations.helixa_provenance import (
            HelixaStamp, stamp_node, export_manifest, aura_trust_weight,
            make_stamp,
        )
        m = Mesh(":memory:")
        n = m.add("cody prefers concise answers", MemoryType.SEMANTIC, trust=0.9)
        stamp = make_stamp(agent_id="59322", aura_score=0.85)
        ok = stamp_node(m, n.id, stamp)
        self.assertTrue(ok)
        # meta survives reload
        reloaded = m._load()[n.id]
        self.assertEqual(reloaded.meta["helixa_stamp"]["agent_id"], "59322")
        self.assertEqual(reloaded.agent_id, "59322")

    def test_unverified_stamp_is_capped(self):
        from neural_mesh.integrations.helixa_provenance import (
            HelixaStamp, aura_trust_weight, make_stamp,
        )
        unverified = make_stamp(agent_id="59322", aura_score=0.9)
        self.assertLessEqual(aura_trust_weight(unverified), 0.2)
        verified = HelixaStamp(agent_id="59322", aura_score=0.9,
                               verified="verified")
        self.assertGreater(aura_trust_weight(verified), 0.2)

    def test_export_manifest_lists_stamped_nodes(self):
        from neural_mesh.integrations.helixa_provenance import (
            stamp_node, export_manifest, make_stamp,
        )
        m = Mesh(":memory:")
        a = m.add("fact a", MemoryType.SEMANTIC)
        b = m.add("fact b", MemoryType.SEMANTIC)
        stamp_node(m, a.id, make_stamp(agent_id="59322", aura_score=0.7))
        man = export_manifest(m)
        self.assertEqual(man["count"], 1)
        self.assertEqual(man["stamps"][0]["node_id"], a.id)


class TestHybridRetrieval(unittest.TestCase):
    def setUp(self):
        self.m = Mesh(":memory:")
        self.m.add("Maya's editor is Neovim.", MemoryType.SEMANTIC)
        self.m.add("Maya lives in Berlin.", MemoryType.SEMANTIC)
        self.m.add("Ravi prefers Vim.", MemoryType.SEMANTIC)
        # superseded (stale) node that must never surface
        old = self.m.add("Maya lives in Lisbon.", MemoryType.SEMANTIC)
        cur = self.m.add("Maya lives in Amsterdam.", MemoryType.SEMANTIC)
        self.m._supersede(old.id, cur)

    def test_dense_recall_finds_semantic_match(self):
        hits = self.m.dense_recall("Which editor does Maya use?", top_k=1)
        self.assertEqual(len(hits), 1)
        self.assertIn("Neovim", hits[0].content)

    def test_lexical_recall_finds_exact_keyword(self):
        hits = self.m.lexical_recall("Maya Berlin", top_k=1)
        self.assertIn("Berlin", hits[0].content)

    def test_hybrid_recall_skips_superseded(self):
        hits = self.m.hybrid_recall("Where does Maya live now?", top_k=5)
        contents = [h.content for h in hits]
        joined = " ".join(contents)
        self.assertIn("Amsterdam", joined)        # current fact present
        self.assertNotIn("Lisbon", joined)        # stale (superseded) skipped
        # the stale node must never outrank a live one
        self.assertNotIn("Maya lives in Lisbon.", contents[:3])

    def test_alpha_extremes_match_pure_modes(self):
        q = "What does Ravi use?"
        dense_top = self.m.dense_recall(q, top_k=1)[0].content
        hybrid_dense = self.m.hybrid_recall(q, top_k=1, alpha=1.0)[0].content
        self.assertEqual(dense_top, hybrid_dense)


class TestQAReaderMetrics(unittest.TestCase):
    """Model-free extractive-reader proxy metrics (SQuAD-style)."""
    def test_tok_f1_perfect_and_zero(self):
        from bench.locomo_qa import _tok_f1, _tok_em
        self.assertAlmostEqual(_tok_f1("Tom went to the park", "Tom went to the park"), 1.0)
        # disjoint token sets -> F1 = 0
        self.assertAlmostEqual(_tok_f1("zebra quantum", "Tom went to the park"), 0.0, places=4)
        # partial overlap -> nonzero, <1
        f = _tok_f1("Tom went to a park", "Tom went to the park")
        self.assertTrue(0.0 < f < 1.0)

    def test_tok_em_exact_vs_partial(self):
        from bench.locomo_qa import _tok_em
        self.assertEqual(_tok_em("Tom went to the park", "Tom went to the park"), 1.0)
        self.assertEqual(_tok_em("Tom went to a park", "Tom went to the park"), 0.0)

    def test_extractive_answer_picks_best_sentence(self):
        from bench.locomo_qa import extractive_answer
        from neural_mesh.embed import embed
        from neural_mesh.core import MemoryNode

        def _n(c):
            e = embed(c)
            return MemoryNode(id=c[:6], type=MemoryType.SEMANTIC, content=c,
                             embedding=e, lane="hot", trust=1.0)

        hits = [_n("Tom and John went to a park near Tom's house."),
                _n("The weather was sunny that day.")]
        pred = extractive_answer(hits, "Tom went to the park")
        self.assertIsNotNone(pred)
        self.assertIn("park", pred)

