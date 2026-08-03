use pyo3::prelude::*;
use std::collections::{BinaryHeap, HashMap, VecDeque};

// ============================================================================
// Cosine similarity (existing, unchanged)
// ============================================================================

/// Compute cosine similarity between two f32 vectors.
///
/// Returns 0.0 if either vector is empty or has zero magnitude.
/// Raises ValueError if vectors have different lengths.
#[pyfunction]
fn cosine_similarity(vec_a: Vec<f32>, vec_b: Vec<f32>) -> PyResult<f32> {
    let n = vec_a.len();
    if n != vec_b.len() {
        return Err(pyo3::exceptions::PyValueError::new_err(format!(
            "vectors must have the same length, got {} vs {}",
            n,
            vec_b.len()
        )));
    }
    if n == 0 {
        return Ok(0.0);
    }

    // Single-pass: compute dot product and squared magnitudes
    let mut dot = 0.0f32;
    let mut mag_a_sq = 0.0f32;
    let mut mag_b_sq = 0.0f32;

    for i in 0..n {
        let a = vec_a[i];
        let b = vec_b[i];
        dot += a * b;
        mag_a_sq += a * a;
        mag_b_sq += b * b;
    }

    let mag_product = (mag_a_sq * mag_b_sq).sqrt();
    if mag_product == 0.0 {
        Ok(0.0)
    } else {
        Ok(dot / mag_product)
    }
}

/// Bulk cosine: takes two flat lists of vectors and a dimension,
/// returns Vec<f32> of cosine similarities.
/// List lengths must both be multiples of dim.
#[pyfunction]
fn bulk_cosine_similarity(flat_a: Vec<f32>, flat_b: Vec<f32>, dim: usize) -> PyResult<Vec<f32>> {
    let total_a = flat_a.len();
    let total_b = flat_b.len();

    if total_a % dim != 0 || total_b % dim != 0 {
        return Err(pyo3::exceptions::PyValueError::new_err(format!(
            "flat_a ({}) or flat_b ({}) not a multiple of dim ({})",
            total_a, total_b, dim
        )));
    }

    let num_pairs_a = total_a / dim;
    let num_pairs_b = total_b / dim;
    if num_pairs_a != num_pairs_b {
        return Err(pyo3::exceptions::PyValueError::new_err(format!(
            "mismatched number of vectors: {} vs {}",
            num_pairs_a, num_pairs_b
        )));
    }

    let num_pairs = num_pairs_a;
    let mut results = Vec::with_capacity(num_pairs);

    for pair_idx in 0..num_pairs {
        let offset = pair_idx * dim;
        let mut dot = 0.0f32;
        let mut mag_a_sq = 0.0f32;
        let mut mag_b_sq = 0.0f32;

        for i in 0..dim {
            let a = flat_a[offset + i];
            let b = flat_b[offset + i];
            dot += a * b;
            mag_a_sq += a * a;
            mag_b_sq += b * b;
        }

        let mag_product = (mag_a_sq * mag_b_sq).sqrt();
        let sim = if mag_product == 0.0 {
            0.0
        } else {
            dot / mag_product
        };
        results.push(sim);
    }

    Ok(results)
}

/// Score one query against a flat matrix using the core embedding contract.
///
/// NEURAL_MESH embedders return normalized vectors and the Python fallback's
/// `cosine()` is intentionally a dot product. Keeping dot semantics here makes
/// the accelerated and stdlib paths exactly interchangeable, including for
/// custom embedders that provide non-normalized vectors.
#[pyfunction]
fn query_dot_similarity(query: Vec<f32>, flat_nodes: Vec<f32>, dim: usize) -> PyResult<Vec<f32>> {
    if dim == 0 || query.len() != dim || flat_nodes.len() % dim != 0 {
        return Err(pyo3::exceptions::PyValueError::new_err(format!(
            "query ({}) and flat_nodes ({}) must align to dim ({})",
            query.len(), flat_nodes.len(), dim
        )));
    }
    let num_nodes = flat_nodes.len() / dim;
    let mut results = Vec::with_capacity(num_nodes);
    for node_idx in 0..num_nodes {
        let offset = node_idx * dim;
        let mut dot = 0.0f32;
        for i in 0..dim {
            dot += query[i] * flat_nodes[offset + i];
        }
        results.push(dot);
    }
    Ok(results)
}

/// Spread weighted activation across a graph using NEURAL_MESH's exact
/// max-propagation contract.
///
/// `initial` contains one activation per node. Only `frontier` nodes propagate
/// during the first step. A neighbor is queued for the next step only when the
/// candidate path improves its current activation:
///
///     gain = activation[source] * decay * edge_weight
///
/// This deliberately mirrors `neural_mesh.resonance` rather than the additive
/// scoring used by `Graph.associative_recall`.
#[pyfunction]
fn spread_activation(
    initial: Vec<f32>,
    edges: Vec<(usize, usize, f32)>,
    frontier: Vec<usize>,
    spread_steps: usize,
    decay: f32,
) -> Vec<f32> {
    let num_nodes = initial.len();
    let mut activation = initial;
    let mut adj = vec![Vec::<(usize, f32)>::new(); num_nodes];
    for (source, target, weight) in edges {
        if source < num_nodes && target < num_nodes {
            adj[source].push((target, weight));
        }
    }

    let mut current: Vec<usize> = frontier
        .into_iter()
        .filter(|&node| node < num_nodes)
        .collect();
    for _ in 0..spread_steps {
        let mut next = Vec::new();
        for source in current {
            let source_activation = activation[source];
            for &(target, weight) in &adj[source] {
                let gain = source_activation * decay * weight;
                if gain > activation[target] {
                    activation[target] = gain;
                    next.push(target);
                }
            }
        }
        current = next;
        if current.is_empty() {
            break;
        }
    }
    activation
}

// ============================================================================
// Graph traversal
// ============================================================================

/// Directional weighted graph backed by an adjacency list.
/// `adj[i]` = list of (neighbor, weight) tuples.
#[pyclass]
struct Graph {
    adj: Vec<Vec<(usize, f32)>>,
    num_nodes: usize,
}

#[pymethods]
impl Graph {
    /// Create a new graph with `num_nodes` vertices (0-indexed).
    #[new]
    fn new(num_nodes: usize) -> Self {
        Graph {
            adj: vec![Vec::new(); num_nodes],
            num_nodes,
        }
    }

    /// Add a directed weighted edge from `u` to `v` with `weight`.
    fn add_edge(&mut self, u: usize, v: usize, weight: f32) {
        if u < self.num_nodes && v < self.num_nodes {
            self.adj[u].push((v, weight));
        }
    }

    fn node_count(&self) -> usize {
        self.num_nodes
    }

    fn edge_count(&self) -> usize {
        self.adj.iter().map(|v| v.len()).sum()
    }

    /// BFS traversal starting from `start`, restricted to `max_depth` hops.
    /// Returns the list of visited node indices in BFS order (start first).
    fn bfs(&self, start: usize, max_depth: usize) -> Vec<usize> {
        if start >= self.num_nodes {
            return Vec::new();
        }
        let mut visited = vec![false; self.num_nodes];
        let mut result = Vec::with_capacity(self.num_nodes);
        let mut queue = VecDeque::new();

        visited[start] = true;
        queue.push_back((start, 0usize));
        result.push(start);

        while let Some((u, depth)) = queue.pop_front() {
            if depth >= max_depth {
                continue;
            }
            for &(v, _) in &self.adj[u] {
                if !visited[v] {
                    visited[v] = true;
                    result.push(v);
                    queue.push_back((v, depth + 1));
                }
            }
        }

        result
    }

    /// Multi-source relevance-scored traversal.
    ///
    /// For each `query_node`, performs BFS limited to `max_depth`.  Each
    /// visited node `v` accumulates a score of
    ///     weight_on_edge * 0.5^depth
    /// summed across all query sources.  Returns (node, score) pairs for
    /// nodes ordered by descending score (ties broken by node id).
    fn associative_recall(
        &self,
        query_nodes: Vec<usize>,
        max_depth: usize,
    ) -> Vec<(usize, f32)> {
        // Collect scores for all nodes across all query sources
        let mut scores: HashMap<usize, f32> = HashMap::new();

        for &start in &query_nodes {
            if start >= self.num_nodes {
                continue;
            }
            let mut visited = vec![false; self.num_nodes];
            let mut queue = VecDeque::new();

            visited[start] = true;
            queue.push_back((start, 0usize));

            while let Some((u, depth)) = queue.pop_front() {
                if depth >= max_depth {
                    continue;
                }
                let next_depth = depth + 1;
                let decay = 0.5f32.powi(next_depth as i32);
                for &(v, w) in &self.adj[u] {
                    let contribution = w * decay;
                    *scores.entry(v).or_insert(0.0) += contribution;
                    if !visited[v] {
                        visited[v] = true;
                        queue.push_back((v, next_depth));
                    }
                }
            }

            // Source nodes contribute with decay at depth 0 as well
            // (optional: we could give them a base score; skip for now per spec)
        }

        // Also include query nodes themselves with a small score so they show up
        for &start in &query_nodes {
            if start < self.num_nodes {
                scores.entry(start).or_insert(0.0);
            }
        }

        let mut result: Vec<(usize, f32)> = scores.into_iter().collect();
        // Sort by descending score, then ascending node id
        result.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal).then(a.0.cmp(&b.0)));
        result
    }

    /// Dijkstra's shortest path from `from` to `to`.
    /// Returns `Some((path, total_weight))` or `None` if unreachable.
    fn shortest_path(&self, from: usize, to: usize) -> Option<(Vec<usize>, f32)> {
        if from >= self.num_nodes || to >= self.num_nodes {
            return None;
        }

        let mut dist: Vec<f32> = vec![f32::INFINITY; self.num_nodes];
        let mut prev: Vec<Option<usize>> = vec![None; self.num_nodes];

        dist[from] = 0.0;

        // BinaryHeap is max-heap; use Reverse for min-heap behaviour.
        let mut heap = BinaryHeap::new();
        heap.push(State {
            cost: 0.0f32,
            node: from,
        });

        while let Some(State { cost, node: u }) = heap.pop() {
            // We may push multiple entries for the same node; skip stale ones.
            if cost > dist[u] {
                continue;
            }
            if u == to {
                break;
            }
            for &(v, w) in &self.adj[u] {
                let next_cost = cost + w;
                if next_cost < dist[v] {
                    dist[v] = next_cost;
                    prev[v] = Some(u);
                    heap.push(State {
                        cost: next_cost,
                        node: v,
                    });
                }
            }
        }

        if dist[to].is_infinite() {
            return None;
        }

        // Reconstruct path
        let mut path = Vec::new();
        let mut cur = to;
        while cur != from {
            path.push(cur);
            cur = prev[cur].unwrap();
        }
        path.push(from);
        path.reverse();

        Some((path, dist[to]))
    }
}

/// Helper for Dijkstra's BinaryHeap (min-heap via Reverse ordering).
#[derive(PartialEq)]
struct State {
    cost: f32,
    node: usize,
}

impl Eq for State {}

// Reverse ordering: smaller cost = greater in the max-heap sense.
use std::cmp::Ordering;
impl Ord for State {
    fn cmp(&self, other: &Self) -> Ordering {
        other
            .cost
            .partial_cmp(&self.cost)
            .unwrap_or(Ordering::Equal)
    }
}
impl PartialOrd for State {
    fn partial_cmp(&self, other: &Self) -> Option<Ordering> {
        Some(self.cmp(other))
    }
}

/// Create a graph from Python edge list (u, v, weight).
#[pyfunction]
fn graph_from_edges(num_nodes: usize, edges: Vec<(usize, usize, f32)>) -> Graph {
    let mut g = Graph::new(num_nodes);
    for (u, v, w) in edges {
        g.add_edge(u, v, w);
    }
    g
}

/// A Python module implemented in Rust.
#[pymodule]
fn rust_mesh(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(cosine_similarity, m)?)?;
    m.add_function(wrap_pyfunction!(bulk_cosine_similarity, m)?)?;
    m.add_function(wrap_pyfunction!(query_dot_similarity, m)?)?;
    m.add_function(wrap_pyfunction!(spread_activation, m)?)?;
    m.add_function(wrap_pyfunction!(graph_from_edges, m)?)?;
    m.add_class::<Graph>()?;
    Ok(())
}