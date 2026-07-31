"""
Tests for cross-agent mesh sharing — merge, trust, consensus, peer policy.
"""
import tempfile
import unittest

from neural_mesh import (
    Mesh, MemoryType, export_mesh,
    merge_peer_mesh, consensus_rank, PeerPolicy, export_for_peer,
)


class TestCrossAgentSharing(unittest.TestCase):
    def setUp(self):
        self.agent_a = Mesh()
        self.agent_b = Mesh()
        self.agent_c = Mesh()  # untrusted agent

        # Agent A knows some facts (with lower trust so fusion shows delta)
        self.agent_a.add("Base L2 is the home of onchain agents",
                         type=MemoryType.SEMANTIC, trust=0.6)
        self.agent_a.add("x402 payments use USDC on Base",
                         type=MemoryType.SEMANTIC, trust=0.5)
        self.agent_a.add("NEURAL_MESH v0.18 ships cross-agent sharing",
                         type=MemoryType.PROCEDURAL, trust=0.5)

        # Agent B knows some overlapping + unique facts (lower trust too)
        self.agent_b.add("Base L2 is the home of onchain agents",
                         type=MemoryType.SEMANTIC, trust=0.6)  # SAME fact — should fuse
        self.agent_b.add("Bankr crossed $5B in onchain volume",
                         type=MemoryType.SEMANTIC)  # B-only fact

        # Agent C (untrusted) contradicts A
        self.agent_c.add("Base L2 is the home of onchain agents",
                         type=MemoryType.SEMANTIC)

    def test_merge_same_fact_fuses_trust(self):
        with tempfile.NamedTemporaryFile(suffix=".mesh", delete=False) as f:
            path_a = f.name
        try:
            export_for_peer(self.agent_a, path_a, "agent-a")
            result = merge_peer_mesh(self.agent_b, path_a,
                                     peer_id="agent-a")
            self.assertEqual(result["fused"], 1)  # 1 overlapping fact (Base L2)
            self.assertGreater(result["added"], 0)  # unique facts from A
            self.assertGreater(result["trust_delta"], 0,
                               "Fused facts should increase trust")
        finally:
            import os
            os.unlink(path_a)

    def test_merge_adds_unique_facts(self):
        with tempfile.NamedTemporaryFile(suffix=".mesh", delete=False) as f:
            path_a = f.name
        try:
            export_for_peer(self.agent_a, path_a, "agent-a")
            result = merge_peer_mesh(self.agent_b, path_a,
                                     peer_id="agent-a")
            self.assertGreater(result["added"], 0)
            self.assertGreater(result["fused"], 0)
        finally:
            import os
            os.unlink(path_a)

    def test_peer_policy_caps_trust(self):
        with tempfile.NamedTemporaryFile(suffix=".mesh", delete=False) as f:
            path_a = f.name
        try:
            export_for_peer(self.agent_a, path_a, "agent-a")
            policy = PeerPolicy(trust=0.3, cap_trust=0.7)
            result = merge_peer_mesh(self.agent_b, path_a,
                                     peer_id="agent-a",
                                     policy=policy)
            nodes = self.agent_b._load()
            # Imported nodes (those with agent-a provenance) should be capped
            found_imported = False
            for n in nodes.values():
                # Nodes that were ADDED (not fused) from the peer
                if n.provenance and "peer:" in n.provenance:
                    found_imported = True
                    self.assertLessEqual(n.trust, 0.7,
                                         f"Imported node '{n.content[:30]}' trust {n.trust} should be capped at 0.7")
            self.assertTrue(found_imported, "Should have imported at least one node from peer")
        finally:
            import os
            os.unlink(path_a)

    def test_peer_policy_disallow_new(self):
        with tempfile.NamedTemporaryFile(suffix=".mesh", delete=False) as f:
            path_a = f.name
        try:
            export_for_peer(self.agent_a, path_a, "agent-a")
            policy = PeerPolicy(allow_new=False)
            result = merge_peer_mesh(self.agent_b, path_a,
                                     peer_id="agent-a",
                                     policy=policy)
            self.assertEqual(result["added"], 0,
                             "No new nodes should be added when allow_new=False")
            self.assertGreater(result["fused"], 0,
                               "Existing overlaps should still fuse")
        finally:
            import os
            os.unlink(path_a)

    def test_consensus_rank_surfaces_highest_trust(self):
        from neural_mesh.node import MemoryNode, MemoryType
        n1 = MemoryNode(id="n1", type=MemoryType.SEMANTIC,
                        content="Base is best L2",
                        trust=0.9, conflict_group="best-l2")
        n2 = MemoryNode(id="n2", type=MemoryType.SEMANTIC,
                        content="Arbitrum is best L2",
                        trust=0.5, conflict_group="best-l2")
        n3 = MemoryNode(id="n3", type=MemoryType.SEMANTIC,
                        content="NEURAL_MESH is awesome",
                        trust=0.8)  # no conflict group
        ranked = consensus_rank([n2, n1, n3])
        self.assertEqual(ranked[0].id, "n1",
                         "Highest trust fact should rank first")
        self.assertEqual(ranked[1].id, "n3",
                         "Non-conflict fact ranks by trust")
        self.assertEqual(ranked[2].id, "n2",
                         "Lower-trust contradictor should be last")
        # Loser should be annotated
        self.assertEqual(ranked[2].meta_conflict_loser, "n1")

    def test_full_cross_agent_workflow(self):
        """End-to-end: A exports -> B imports -> both benefit."""
        with tempfile.NamedTemporaryFile(suffix=".mesh", delete=False) as f:
            path = f.name
        try:
            export_for_peer(self.agent_a, path, "agent-a")
            result = merge_peer_mesh(self.agent_b, path, peer_id="agent-a")
            # B should now have all of A's knowledge
            b_nodes = {n.content for n in self.agent_b._load().values()}
            self.assertIn("x402 payments use USDC on Base", b_nodes)
            self.assertIn("NEURAL_MESH v0.18 ships cross-agent sharing", b_nodes)
            self.assertIn("Bankr crossed $5B in onchain volume", b_nodes)
            # Fused nodes should have agent_id set
            for n in self.agent_b._load().values():
                if n.content == "Base L2 is the home of onchain agents":
                    self.assertIn("agent-a", n.agent_id,
                                  "Fused node should show importing agent")
            self.assertEqual(result["fused"], 1)
            self.assertGreaterEqual(result["added"], 1)
        finally:
            import os
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()