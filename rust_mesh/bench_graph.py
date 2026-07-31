"""Benchmark Rust graph traversal against pure Python on 50K nodes, 500K edges."""
import time
import random
import rust_mesh

random.seed(42)

NUM_NODES = 50_000
NUM_EDGES = 500_000

print(f"Generating graph: {NUM_NODES:,} nodes, {NUM_EDGES:,} edges...")

# Generate random edges
edges = []
for _ in range(NUM_EDGES):
    u = random.randrange(NUM_NODES)
    v = random.randrange(NUM_NODES)
    w = random.uniform(0.1, 10.0)
    edges.append((u, v, w))

# --- Rust Graph ---
t0 = time.perf_counter()
g_rust = rust_mesh.graph_from_edges(NUM_NODES, edges)
t_build_rust = time.perf_counter() - t0
print(f"Rust build: {t_build_rust:.4f}s, {g_rust.edge_count():,} edges")

# --- Python adjacency list (for Python BFS) ---
t0 = time.perf_counter()
adj_py = [[] for _ in range(NUM_NODES)]
for u, v, w in edges:
    adj_py[u].append((v, w))
t_build_py = time.perf_counter() - t0
print(f"Python build: {t_build_py:.4f}s")

# Benchmark parameters
START_NODE = 0
MAX_DEPTH = 10
QUERY_NODES = [0, 100, 1000, 5000]
PATH_FROM = 0
PATH_TO = NUM_NODES - 1

# ===================== BFS =====================
print("\n--- BFS ---")

# Rust BFS
t0 = time.perf_counter()
rust_bfs_result = g_rust.bfs(START_NODE, MAX_DEPTH)
t_rust_bfs = time.perf_counter() - t0
print(f"Rust BFS: {t_rust_bfs:.6f}s, visited {len(rust_bfs_result):,} nodes")

# Python BFS
def py_bfs(adj, start, max_depth):
    visited = [False] * len(adj)
    result = []
    from collections import deque
    q = deque()
    visited[start] = True
    q.append((start, 0))
    result.append(start)
    while q:
        u, d = q.popleft()
        if d >= max_depth:
            continue
        for v, _ in adj[u]:
            if not visited[v]:
                visited[v] = True
                result.append(v)
                q.append((v, d + 1))
    return result

# Warmup
_ = py_bfs(adj_py, START_NODE, MAX_DEPTH)
_ = py_bfs(adj_py, START_NODE, MAX_DEPTH)

t0 = time.perf_counter()
py_bfs_result = py_bfs(adj_py, START_NODE, MAX_DEPTH)
t_py_bfs = time.perf_counter() - t0
print(f"Python BFS: {t_py_bfs:.6f}s, visited {len(py_bfs_result):,} nodes")
print(f"Speedup: {t_py_bfs / t_rust_bfs:.1f}x")

# Verify results match
assert len(rust_bfs_result) == len(py_bfs_result), f"BFS mismatch: {len(rust_bfs_result)} vs {len(py_bfs_result)}"
assert set(rust_bfs_result) == set(py_bfs_result), "BFS result mismatch"

# ===================== Associative Recall =====================
print("\n--- Associative Recall ---")

t0 = time.perf_counter()
rust_recall = g_rust.associative_recall(QUERY_NODES, MAX_DEPTH)
t_rust_recall = time.perf_counter() - t0
print(f"Rust recall: {t_rust_recall:.6f}s, {len(rust_recall):,} results")

# Python associative recall
def py_associative_recall(adj, query_nodes, max_depth):
    from collections import deque
    scores = {}
    n = len(adj)
    for start in query_nodes:
        if start >= n:
            continue
        visited = [False] * n
        q = deque()
        visited[start] = True
        q.append((start, 0))
        while q:
            u, d = q.popleft()
            if d >= max_depth:
                continue
            nd = d + 1
            decay = 0.5 ** nd
            for v, w in adj[u]:
                scores[v] = scores.get(v, 0.0) + w * decay
                if not visited[v]:
                    visited[v] = True
                    q.append((v, nd))
    for start in query_nodes:
        if start < n:
            scores.setdefault(start, 0.0)
    return sorted(scores.items(), key=lambda x: (-x[1], x[0]))

# Warmup
_ = py_associative_recall(adj_py, QUERY_NODES, MAX_DEPTH)

t0 = time.perf_counter()
py_recall = py_associative_recall(adj_py, QUERY_NODES, MAX_DEPTH)
t_py_recall = time.perf_counter() - t0
print(f"Python recall: {t_py_recall:.6f}s, {len(py_recall):,} results")
print(f"Speedup: {t_py_recall / t_rust_recall:.1f}x")

# Verify match
assert len(rust_recall) == len(py_recall), f"Recall size mismatch: {len(rust_recall)} vs {len(py_recall)}"

# ===================== Dijkstra =====================
print("\n--- Dijkstra ---")

t0 = time.perf_counter()
rust_path = g_rust.shortest_path(PATH_FROM, PATH_TO)
t_rust_dijk = time.perf_counter() - t0
print(f"Rust Dijkstra: {t_rust_dijk:.6f}s, path_len={len(rust_path[0]) if rust_path else 'None'}, dist={rust_path[1] if rust_path else 'N/A'}")

# Python Dijkstra
import heapq

def py_dijkstra(adj, frm, to):
    n = len(adj)
    dist = [float('inf')] * n
    prev = [None] * n
    dist[frm] = 0.0
    heap = [(0.0, frm)]
    while heap:
        d, u = heapq.heappop(heap)
        if d > dist[u]:
            continue
        if u == to:
            break
        for v, w in adj[u]:
            nd = d + w
            if nd < dist[v]:
                dist[v] = nd
                prev[v] = u
                heapq.heappush(heap, (nd, v))
    if dist[to] == float('inf'):
        return None
    path = []
    cur = to
    while cur != frm:
        path.append(cur)
        cur = prev[cur]
    path.append(frm)
    path.reverse()
    return (path, dist[to])

# Warmup
_ = py_dijkstra(adj_py, PATH_FROM, PATH_TO)

t0 = time.perf_counter()
py_path = py_dijkstra(adj_py, PATH_FROM, PATH_TO)
t_py_dijk = time.perf_counter() - t0
print(f"Python Dijkstra: {t_py_dijk:.6f}s, path_len={len(py_path[0]) if py_path else 'None'}, dist={py_path[1] if py_path else 'N/A'}")
print(f"Speedup: {t_py_dijk / t_rust_dijk:.1f}x")

# Verify
if rust_path and py_path:
    assert len(rust_path[0]) == len(py_path[0]), f"Dijkstra path mismatch: {len(rust_path[0])} vs {len(py_path[0])}"

# ===================== Summary =====================
print("\n" + "=" * 50)
print("SUMMARY")
print("=" * 50)
print(f"{'Operation':<30} {'Rust (s)':<12} {'Python (s)':<12} {'Speedup':<8}")
print("-" * 50)
print(f"{'Graph build':<30} {t_build_rust:<12.4f} {t_build_py:<12.4f} {t_build_py/t_build_rust:<8.1f}x")
print(f"{'BFS (max_depth=10)':<30} {t_rust_bfs:<12.6f} {t_py_bfs:<12.6f} {t_py_bfs/t_rust_bfs:<8.1f}x")
print(f"{'Associative recall':<30} {t_rust_recall:<12.6f} {t_py_recall:<12.6f} {t_py_recall/t_rust_recall:<8.1f}x")
print(f"{'Dijkstra':<30} {t_rust_dijk:<12.6f} {t_py_dijk:<12.6f} {t_py_dijk/t_rust_dijk:<8.1f}x")