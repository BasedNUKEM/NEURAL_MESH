"""Benchmark the v0.21 Rust-accelerated resonance retrieval hot path.

Measures complete retrieval (query scoring + seed sort + two-hop spread + rank),
not an isolated Rust kernel. The ranked-hit parity check is mandatory so a speed
claim cannot hide changed retrieval behavior.

Run:
    PYTHONPATH=. python3 bench/rust_resonance_bench.py --nodes 5000
"""
from __future__ import annotations

import argparse
import math
import os
import random
import statistics
import sys
import time
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from neural_mesh.resonance import retrieve, rust_available  # noqa: E402


def _vector(rng: random.Random, dims: int) -> list[float]:
    raw = [rng.random() for _ in range(dims)]
    norm = math.sqrt(sum(value * value for value in raw))
    return [value / norm for value in raw]


def build_mesh(node_count: int, dims: int, edges_per_node: int, seed: int = 42):
    rng = random.Random(seed)
    now = time.time()
    node_ids = [str(i) for i in range(node_count)]
    nodes = {
        node_id: SimpleNamespace(
            id=node_id,
            embedding=_vector(rng, dims),
            links={},
            superseded_by="",
            last_accessed=now,
            trust=0.75 + 0.25 * rng.random(),
        )
        for node_id in node_ids
    }
    for i, node_id in enumerate(node_ids):
        node = nodes[node_id]
        for step in range(1, edges_per_node + 1):
            target = node_ids[(i + step * 7919) % node_count]
            node.links[target] = 0.5 + 0.5 * rng.random()
    return nodes


def _measure(nodes, query, backend: str, repeats: int):
    durations = []
    hits = None
    for _ in range(repeats):
        started = time.perf_counter()
        hits = retrieve(nodes, query, top_k=10, backend=backend)
        durations.append(time.perf_counter() - started)
    return statistics.median(durations), [node.id for node in hits or []]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--nodes", type=int, default=5000)
    parser.add_argument("--dims", type=int, default=256)
    parser.add_argument("--edges-per-node", type=int, default=4)
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args()

    if not rust_available():
        print("rust backend unavailable; build rust_mesh and copy rust_mesh.so to repo root")
        return 2

    nodes = build_mesh(args.nodes, args.dims, args.edges_per_node)
    query = nodes["0"].embedding
    python_s, python_hits = _measure(nodes, query, "python", args.repeats)
    rust_s, rust_hits = _measure(nodes, query, "rust", args.repeats)
    parity = python_hits == rust_hits
    speedup = python_s / rust_s if rust_s else float("inf")

    print(f"nodes={args.nodes:,} dims={args.dims} edges={args.nodes * args.edges_per_node:,}")
    print(f"python_median_ms={python_s * 1000:.3f}")
    print(f"rust_median_ms={rust_s * 1000:.3f}")
    print(f"speedup={speedup:.3f}x")
    print(f"top10_parity={str(parity).lower()}")
    return 0 if parity else 1


if __name__ == "__main__":
    raise SystemExit(main())
