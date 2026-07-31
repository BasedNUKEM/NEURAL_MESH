# Graph Traversal Spike — PyO3 Rust vs Pure Python

**Date**: 2026-07-30
**Project**: NEURAL_MESH / rust_mesh
**File**: `src/lib.rs` — graph section added alongside existing cosine functions

## Goal

Evaluate whether offloading graph traversal (BFS, associative recall, Dijkstra) to Rust via PyO3 yields meaningful speedups for the NEURAL_MESH knowledge graph hot path.

## Implementation

Added to the existing `rust_mesh` crate (pyo3 0.29, edition 2024):

### Data Structure

```rust
#[pyclass]
struct Graph {
    adj: Vec<Vec<(usize, f32)>>,  // adjacency list: node → [(neighbor, weight)]
    num_nodes: usize,
}
```

Memory: O(V + E) with minimal overhead. Each edge stored once (directed). No extra dependencies beyond `std::collections`.

### Operations Exposed to Python

| Method | Description | Complexity |
|--------|-------------|------------|
| `Graph(num_nodes)` | Create empty graph | O(V) |
| `add_edge(u, v, w)` | Add directed weighted edge | O(1) |
| `bfs(start, max_depth)` | BFS with depth limit, returns visited nodes | O(V + E) |
| `associative_recall(query_nodes, max_depth)` | Multi-source BFS with dampened relevance scoring: `w * 0.5^depth`. Returns (node, score) sorted desc | O(Q·(V + E)) |
| `shortest_path(from, to)` | Dijkstra with BinaryHeap. Returns `(path, distance)` or `None` | O((V + E) log V) |
| `graph_from_edges(num_nodes, edges)` | Factory from Python edge list | O(E) |

No external crates added. Uses only `std::collections::{VecDeque, HashMap, BinaryHeap}`.

## Benchmark: 50K nodes, 500K edges

Random directed graph (uniform edge distribution, weights 0.1–10.0). All times in seconds, lower is better.

| Operation | Rust (s) | Python (s) | Speedup |
|-----------|----------|------------|---------|
| Graph build | 0.045 | 0.204 | **4.5×** |
| BFS (depth=10, 50K visited) | 0.009 | 0.141 | **15.0×** |
| Associative recall (4 query nodes, depth=10) | 0.086 | 1.324 | **15.4×** |
| Dijkstra (shortest path, 15 hops) | 0.018 | 0.279 | **15.5×** |

### Key observations

- **BFS is 15× faster** — Rust's zero-overhead iteration over adjacency slices dominates Python's per-edge interpreter dispatch cost.
- **Associative recall is 15.4× faster** — HashMap-based score accumulation + sort in Rust beats Python dicts + `.items()` + sort by a factor consistent with BFS.
- **Dijkstra is 15.5× faster** — BinaryHeap with `f32` ordering beats Python's `heapq` + `float('inf')` sentinel.
- **Graph construction is 4.5× faster** — even though most time is spent pushing tuples onto Vecs, Rust's allocation strategy wins.
- **Memory**: 500K edges ~ 12 MB in the adjacency list (each edge: 8 bytes usize + 4 bytes f32 = 12 bytes payload + Vec overhead).

### Verification

All outputs verified to match between Rust and Python implementations:
- BFS: identical visited sets
- Associative recall: identical result keys and score ordering
- Dijkstra: identical path length and total distance (within f32 precision)

## Python API

```python
import rust_mesh

# Create graph
g = rust_mesh.Graph(1000)

# Add edges
g.add_edge(0, 1, 0.5)
g.add_edge(1, 2, 1.0)

# Or from edge list
g = rust_mesh.graph_from_edges(1000, [(0, 1, 0.5), (1, 2, 1.0)])

# Traversals
visited = g.bfs(start=0, max_depth=5)
scores = g.associative_recall(query_nodes=[0, 42], max_depth=3)
path = g.shortest_path(from_=0, to=999)  # -> ([0, ..., 999], dist) or None
```

### Edge cases handled

- Out-of-range node indices: `bfs` returns `[]`, `shortest_path` returns `None`, `associative_recall` skips invalid query nodes silently.
- Unreachable target: `shortest_path` returns `None`.
- Empty graph / zero edges: all methods return empty/None correctly.
- `max_depth=0`: BFS returns only the start node.

## Recommendation

**Ship it.** The 15× speedup is consistent and impactful. Graph traversal is a NEURAL_MESH hot path — replacing Python BFS/associative recall with the Rust implementation will cut traversal latency from ~1.3s to ~0.09s on a 500K-edge graph. The integration is zero-friction: single `lib.rs` file, no new crates, maturin builds cleanly.

### Next steps

1. Replace Python graph traversal calls in NEURAL_MESH with `rust_mesh.Graph`
2. Add undirected edge support (`add_edge` could push both directions)
3. Consider `Rayon` parallel BFS for multi-query associative recall if query fan-out grows
4. Profile memory impact after integration — current footprint is ~12 MB / 500K edges