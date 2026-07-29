#!/usr/bin/env python3
"""Cross-agent mesh sharing demo — two independent agents merge knowledge with Helixa provenance.

Agent A (D0xedDev #5287): focused on Base L2, x402 payments, D0xedDev ecosystem
Agent B (Peer #9912): focused on Solana, DeFi, Utilia integration

The demo:
1. Creates two independent meshes with different knowledge domains
2. Exports Agent B's mesh as .mesh file
3. Agent A imports and merges it
4. Shows the enriched recall after cross-agent knowledge sharing
"""
import sys, os, json, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from neural_mesh.core import Mesh, MemoryType
from neural_mesh.sharing import merge_peer_mesh
from neural_mesh.integrations.helixa_provenance import HelixaStamp, stamp_node, export_manifest

def demo():
    print("=" * 60)
    print("  NEURAL_MESH Cross-Agent Sharing Demo")
    print("=" * 60)

    # ── Agent A: D0xedDev #5287 ──
    print("\n🟦 Agent A: D0xedDev #5287 (Base L2 specialist)")
    agent_a = Mesh(db_path=":memory:")
    agent_a.add("D0XEDDEV x402 routing node on Base Mainnet, port 4020",
                type=MemoryType.SEMANTIC, provenance="d0xeddev", by="agent-5287")
    agent_a.add("DEVIO token live on Base at 0x3d447A385b068B38b2eaF4690B2131e34Ff2eba3",
                type=MemoryType.SEMANTIC, provenance="d0xeddev", by="agent-5287")
    agent_a.add("x402 settlement verifier accepts EIP-3009 signatures on Base",
                type=MemoryType.PROCEDURAL, provenance="d0xeddev", by="agent-5287")
    
    # Stamp Agent A's nodes with Helixa
    for node_id in list(agent_a._load().keys()):
        stamp = HelixaStamp(agent_id="5287", aura_score=0.72, source="d0xeddev",
                           vouched_at=__import__("time").time(), verified="verified")
        stamp_node(agent_a, node_id, stamp)
    
    a_nodes = len(agent_a._load())
    print(f"  Nodes: {a_nodes} (all Helixa-stamped #5287)")

    # ── Agent B: Peer #9912 ──
    print("\n🟪 Agent B: Peer #9912 (Solana/Utilia specialist)")
    agent_b = Mesh(db_path=":memory:")
    agent_b.add("Utilia Solana priority fee API at api.utilia.ink/solana/v1/fees/priority",
                type=MemoryType.SEMANTIC, provenance="peer-9912", by="agent-9912")
    agent_b.add("Base L2 gas averages 0.0001 ETH per transfer as of Q3 2026",
                type=MemoryType.SEMANTIC, provenance="peer-9912", by="agent-9912")
    agent_b.add("Cross-chain x402 settlements need dual RPC confirmation",
                type=MemoryType.PROCEDURAL, provenance="peer-9912", by="agent-9912")
    
    b_nodes = len(agent_b._load())
    print(f"  Nodes: {b_nodes}")

    # ── Export Agent B's mesh ──
    tmp = tempfile.NamedTemporaryFile(suffix=".mesh", delete=False)
    from neural_mesh.meshfile import export_mesh as export_to_file
    export_to_file(agent_b, tmp.name)
    print(f"\n📤 Agent B exported: {tmp.name} ({b_nodes} nodes)")

    # ── Agent A imports Agent B ──
    print(f"\n📥 Agent A imports Agent B's mesh...")
    result = merge_peer_mesh(agent_a, tmp.name, peer_id="agent-9912")
    print(f"  Added: {result.get('added', 0)} | Fused: {result.get('fused', 0)} | Skipped: {result.get('skipped', 0)}")
    print(f"  Trust delta: {result.get('trust_delta', 0):.4f}")

    # ── After merge ──
    merged_nodes = len(agent_a._load())
    print(f"\n🧠 Agent A post-merge: {a_nodes} → {merged_nodes} nodes (+{merged_nodes - a_nodes})")

    # ── Recall: cross-domain query ──
    print(f"\n🔍 Recall test: 'cross-chain x402 Base Solana fee'")
    hits = agent_a.dense_recall("cross-chain x402 Base Solana fee", top_k=3)
    for i, h in enumerate(hits):
        src = f"#{h.agent_id}" if hasattr(h, 'agent_id') and h.agent_id else h.provenance
        print(f"  [{i+1}] trust={h.trust:.2f} [{src}] {h.content[:90]}...")

    # ── Helixa manifest ──
    manifest = export_manifest(agent_a)
    print(f"\n📜 Helixa Manifest: {len(manifest.get('stamps',[]))} stamped nodes")
    for s in manifest.get('stamps', [])[:3]:
        print(f"  #{s['agent_id']} — {s['node_id'][:12]}...")

    # ── Stats ──
    total = len(agent_a._load())
    print(f"\n📊 Final stats: {total} total nodes, 6 merged (+{total-6} from DREAM)")

    os.unlink(tmp.name)
    print("\n✅ Cross-agent sharing demo complete!")
    return True

if __name__ == "__main__":
    sys.exit(0 if demo() else 1)
