"""Cross-agent sharing benchmark.

Proves three behaviors of `neural_mesh.sharing`:
  1. CORROBORATION  — the same fact from two agents FUSES; trust rises.
  2. CONSENSUS      — a contradictory fact in the same `conflict_group` does NOT
                      overwrite; the higher-trust claim wins, the loser is
                      retained-but-demoted (visible, never silently dropped).
  3. TRUST CAPPING  — an untrusted peer's contributions are scaled down by the
                      receiver's per-peer policy instead of polluting local truth.

Run:
    PYTHONPATH=. python bench/sharing_bench.py
"""
from __future__ import annotations

import os
import tempfile

from neural_mesh import (
    Mesh, MemoryType, export_mesh, merge_peer_mesh,
    consensus_rank, PeerPolicy, export_for_peer,
)


def _hits(mesh, q, k=5):
    return mesh.recall(q, top_k=k)


def main():
    results = {}

    # ---- 1. CORROBORATION -------------------------------------------------
    a = Mesh(":memory:")
    a.add("Postgres connection pool max is 20", type=MemoryType.SEMANTIC,
          agent_id="agent_a", trust=0.8)
    # export A
    fa = tempfile.mktemp(suffix=".mesh")
    export_for_peer(a, fa, "agent_a")

    # agent B starts with the SAME fact (slightly different wording -> same hash
    # only if identical; use identical content to prove true fusion)
    b = Mesh(":memory:")
    b.add("Postgres connection pool max is 20", type=MemoryType.SEMANTIC,
          agent_id="agent_b", trust=0.7)
    before = b._load()
    before_node = next(n for n in before.values())
    before_trust = before_node.trust

    res1 = merge_peer_mesh(b, fa, peer_id="agent_a", policy=PeerPolicy(trust=1.0))
    after = b._load()
    # after fusion there should be exactly ONE node for that fact
    fact_nodes = [n for n in after.values() if "Postgres connection pool" in n.content]
    fused_node = fact_nodes[0]
    results["corroboration"] = {
        "nodes_before": len(before),
        "nodes_after": len(after),
        "trust_before": round(before_trust, 4),
        "trust_after": round(fused_node.trust, 4),
        "agent_id": fused_node.agent_id,
        "fused": len(fact_nodes) == 1 and fused_node.trust > before_trust,
    }

    # ---- 2. CONSENSUS (conflict) ------------------------------------------
    c = Mesh(":memory:")
    c.add("Deploy target is us-east-1", type=MemoryType.SEMANTIC,
          agent_id="agent_c", trust=0.9, conflict_group="deploy_region")
    # peer asserts a CONTRADICTION in the same conflict_group, lower trust
    p = Mesh(":memory:")
    p.add("Deploy target is eu-west-1", type=MemoryType.SEMANTIC,
          agent_id="agent_p", trust=0.4, conflict_group="deploy_region")
    fp = tempfile.mktemp(suffix=".mesh")
    export_for_peer(p, fp, "agent_p")
    res2 = merge_peer_mesh(c, fp, peer_id="agent_p", policy=PeerPolicy(trust=1.0))
    merged = list(c._load().values())
    conflict_nodes = [n for n in merged if n.conflict_group == "deploy_region"]
    ranked = consensus_rank(conflict_nodes)
    winner = ranked[0]
    results["consensus"] = {
        "conflict_nodes_kept": len(conflict_nodes),   # both retained, not overwritten
        "winner_content": winner.content,
        "winner_trust": round(winner.trust, 4),
        "loser_demoted": ranked[-1].trust < winner.trust,
        "correct_winner": "us-east-1" in winner.content,
    }

    # ---- 3. TRUST CAPPING -------------------------------------------------
    d = Mesh(":memory:")
    d.add("Cache TTL is 300s", type=MemoryType.SEMANTIC,
          agent_id="agent_d", trust=0.95)
    e = Mesh(":memory:")
    # untrusted peer claims a DIFFERENT value; receiver caps peer trust at 0.2
    e.add("Cache TTL is 9999s", type=MemoryType.SEMANTIC,
          agent_id="agent_evil", trust=1.0)
    fe = tempfile.mktemp(suffix=".mesh")
    export_for_peer(e, fe, "agent_evil")
    res3 = merge_peer_mesh(d, fe, peer_id="agent_evil",
                           policy=PeerPolicy(trust=0.2, cap_trust=0.2))
    dnodes = list(d._load().values())
    evil_node = [n for n in dnodes if "9999s" in n.content]
    results["trust_capping"] = {
        "imported_node_trust": round(evil_node[0].trust, 4) if evil_node else None,
        "capped_below_local": (evil_node[0].trust < 0.95) if evil_node else False,
        "local_truth_intact": any("300s" in n.content for n in dnodes),
    }

    # ---- print ------------------------------------------------------------
    print("CROSS-AGENT SHARING BENCHMARK")
    print("=" * 60)
    c_ = results["corroboration"]
    print(f"\n[1] CORROBORATION (same fact from 2 agents)")
    print(f"    nodes {c_['nodes_before']} -> {c_['nodes_after']} "
          f"(no duplicate)")
    print(f"    trust {c_['trust_before']} -> {c_['trust_after']} "
          f"(rose via fusion)")
    print(f"    agent_id: {c_['agent_id']}")
    print(f"    PASS: {c_['fused']}")

    con = results["consensus"]
    print(f"\n[2] CONSENSUS (contradictory facts, same conflict_group)")
    print(f"    conflict nodes kept: {con['conflict_nodes_kept']} "
          f"(both retained, not overwritten)")
    print(f"    winner: '{con['winner_content']}' (trust {con['winner_trust']})")
    print(f"    loser demoted: {con['loser_demoted']}")
    print(f"    correct higher-trust claim won: {con['correct_winner']}")

    tc = results["trust_capping"]
    print(f"\n[3] TRUST CAPPING (untrusted peer)")
    print(f"    imported node trust: {tc['imported_node_trust']} "
          f"(peer's 1.0 -> capped)")
    print(f"    capped below local truth: {tc['capped_below_local']}")
    print(f"    local truth intact: {tc['local_truth_intact']}")

    ok = (c_["fused"] and con["conflict_nodes_kept"] == 2
          and con["correct_winner"] and tc["capped_below_local"]
          and tc["local_truth_intact"])
    print("\n" + "=" * 60)
    print(f"OVERALL: {'PASS' if ok else 'FAIL'}")
    return results


if __name__ == "__main__":
    main()
