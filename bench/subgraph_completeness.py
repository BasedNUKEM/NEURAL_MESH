#!/usr/bin/env python3
"""Subgraph-completeness benchmark for NEURAL_MESH (v0.26.0).

Measures how well retrieval preserves graph topology under context budgets.
Given a seed node with N linked neighbors (the "ground-truth subgraph"),
how many of those neighbors appear in a recall result set of size k?

This is the metric that matters for agent memory: when you ask a question,
does the mesh surface the *connected* knowledge, not just direct matches?

Usage:
  PYTHONPATH=. python3 bench/subgraph_completeness.py \
      --nodes 500 --edges-per-node 5 --budgets 5,10,20,50

  # With the live VPS mesh:
  PYTHONPATH=. python3 bench/subgraph_completeness.py \
      --db /opt/data/NEURAL_MESH/mesh.db --budgets 5,10,15

Reports:
  - subgraph_recall@k: fraction of ground-truth neighbor set retrieved
  - edge_density@k: edges found / max possible edges in retrieved set
  - topology_score: subgraph_recall × edge_density (0-1 scale)
"""
from __future__ import annotations

import argparse
import random
import sys
import time
from collections import defaultdict

HERE = __import__("pathlib").Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from neural_mesh import Mesh
from neural_mesh.core import MemoryType


def build_random_mesh(nodes: int, edges_per_node: int, seed: int = 42) -> tuple[Mesh, list[str]]:
    """Build an in-memory mesh with clustered content so autolink forms real groups."""
    rng = random.Random(seed)
    mesh = Mesh(db_path=":memory:", link_threshold=0.25)
    ids = []

    # clusters: each node belongs to a topic cluster with shared keywords,
    # so embedding similarity (and thus autolink) forms genuine subgraphs
    clusters = []
    for c in range(max(1, nodes // 50)):
        topic = f"topic_{c}"
        entities = [f"entity_{c}_{e}" for e in range(4)]
        verbs = ["fix", "build", "audit", "ship", "review"]
        clusters.append((topic, entities, verbs))

    for i in range(nodes):
        topic, entities, verbs = clusters[i % len(clusters)]
        content = (
            f"{topic} {entities[i % len(entities)]} "
            f"{verbs[i % len(verbs)]} iteration_{i // len(clusters)} "
            f"weight={rng.random():.3f} desc_{rng.choice(['urgent','normal','low'])}"
        )
        nid = mesh.add(content, type=MemoryType.EPISODIC, provenance="bench-synthetic")
        ids.append(nid.id)

    return mesh, ids


def measure_subgraph_completeness(
    mesh: Mesh,
    node_ids: list[str],
    budgets: list[int],
    limit: int = 100,
    seed: int = 42,
) -> dict:
    """Measure subgraph recall at different context budgets."""
    rng = random.Random(seed)
    sample_ids = rng.sample(node_ids, min(limit, len(node_ids)))

    results: dict = {k: {"subgraph_recall": [], "edge_density": [], "topology_score": []} for k in budgets}
    failures = 0

    for nid in sample_ids:
        node = mesh._load().get(nid)
        if node is None:
            failures += 1
            continue

        # Ground-truth subgraph: all linked neighbors
        linked = set(node.links or {})
        if len(linked) < 2:
            continue  # need at least 2 links for meaningful measurement

        # Retrieve using the node's own content as query
        query = node.content or f"node {nid}"

        for k in budgets:
            recall_results = mesh.recall(query, top_k=k, writeback=False)
            retrieved_ids = {r.id for r in recall_results}

            # subgraph recall: how many linked neighbors are in the result?
            retrieved_linked = retrieved_ids & linked
            subgraph_recall = len(retrieved_linked) / len(linked) if linked else 0.0

            # edge density: how many edges exist among retrieved nodes?
            node_map = mesh._load()
            retrieved_edges = 0
            retrieved_list = list(retrieved_ids)
            max_possible = len(retrieved_list) * (len(retrieved_list) - 1) // 2
            if max_possible > 0:
                for i in range(len(retrieved_list)):
                    rnode = node_map.get(retrieved_list[i])
                    if rnode:
                        rlinks = set(rnode.links or {})
                        for j in range(i + 1, len(retrieved_list)):
                            if retrieved_list[j] in rlinks:
                                retrieved_edges += 1
                edge_density = retrieved_edges / max_possible
            else:
                edge_density = 0.0

            # topology score: combined metric (harmonic mean)
            if subgraph_recall + edge_density > 0:
                topology = 2 * subgraph_recall * edge_density / (subgraph_recall + edge_density)
            else:
                topology = 0.0

            results[k]["subgraph_recall"].append(subgraph_recall)
            results[k]["edge_density"].append(edge_density)
            results[k]["topology_score"].append(topology)

    # Aggregate
    for k in budgets:
        for metric in ("subgraph_recall", "edge_density", "topology_score"):
            vals = results[k][metric]
            results[k][metric] = sum(vals) / len(vals) if vals else 0.0

    results["_meta"] = {
        "sample_size": len(sample_ids),
        "usable_nodes": len(sample_ids) - failures,
    }
    return results


def run_live_mesh_bench(db_path: str, budgets: list[int], limit: int = 50):
    """Bench subgraph completeness on a live mesh DB."""
    mesh = Mesh(db_path=db_path)
    stats = mesh.stats()
    print(f"Live mesh: {stats.get('active_nodes', 0)} active nodes", file=sys.stderr)

    # Get active nodes with links
    all_ids = [
        nid for nid, node in mesh._load().items()
        if not node.superseded_by and (node.links or {})
    ]
    if len(all_ids) > limit * 4:
        all_ids = random.Random(42).sample(all_ids, limit * 4)

    results = measure_subgraph_completeness(mesh, all_ids, budgets, limit=limit)
    return results


def main():
    p = argparse.ArgumentParser(description="Subgraph-completeness benchmark")
    p.add_argument("--db", help="Path to live mesh DB (optional, uses in-memory synthetic otherwise)")
    p.add_argument("--nodes", type=int, default=500)
    p.add_argument("--edges-per-node", type=int, default=5)
    p.add_argument("--budgets", default="5,10,20,50")
    p.add_argument("--limit", type=int, default=100, help="Max nodes to sample")
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()

    budgets = [int(b) for b in args.budgets.split(",")]

    t0 = time.time()

    if args.db:
        results = run_live_mesh_bench(args.db, budgets, limit=args.limit)
    else:
        print(f"Building synthetic mesh: {args.nodes} nodes x {args.edges_per_node} edges...", file=sys.stderr)
        mesh, ids = build_random_mesh(args.nodes, args.edges_per_node, seed=args.seed)
        print(f"Benchmarking {min(args.limit, len(ids))} seed nodes...", file=sys.stderr)
        results = measure_subgraph_completeness(mesh, ids, budgets, limit=args.limit, seed=args.seed)

    elapsed = time.time() - t0

    print("\nSUBRAPH COMPLETENESS BENCHMARK (v0.26.0)")
    print(f"  nodes sampled : {results['_meta']['usable_nodes']}")
    print(f"  context budgets: {budgets}")
    print(f"  elapsed        : {elapsed:.1f}s")
    print()
    print("  budget | subgraph_recall | edge_density | topology_score")
    print("  -------|-----------------|--------------|----------------")
    for k in budgets:
        sr = results[k]["subgraph_recall"]
        ed = results[k]["edge_density"]
        ts = results[k]["topology_score"]
        print(f"  k={k:>4} | {sr:>15.4f} | {ed:>12.4f} | {ts:>14.4f}")

    print("\n  Interpretation:")
    print("  - subgraph_recall@k: fraction of a node's true neighbors")
    print("    surfaced in a top-k retrieval (measures recall)")
    print("  - edge_density@k: edges within the retrieved set / max")
    print("    possible (measures precision / clustering)")
    print("  - topology_score: harmonic mean — the single-number")
    print("    signal for 'does retrieval preserve the graph?'")
    print()
    print("  Honest note: synthetic graphs have uniform link probability;")
    print("  real mesh graphs show higher variation due to semantic linking.")
    return results


if __name__ == "__main__":
    main()
