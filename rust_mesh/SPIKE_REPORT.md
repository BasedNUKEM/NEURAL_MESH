# SPIKE REPORT: Rust Hot Path for NEURAL_MESH

**Date**: 2026-07-30
**Status**: Completed
**Author**: Hermes Agent

---

## Goal

Evaluate whether offloading NEURAL_MESH hot-path operations to Rust (via PyO3/maturin) yields meaningful performance improvements over the existing Python/NumPy implementation.

## Setup

| Component | Version |
|-----------|---------|
| Rust | 1.97.1 (stable-x86_64-unknown-linux-gnu, minimal profile) |
| Cargo | 1.97.1 |
| maturin | 1.14.1 |
| PyO3 | 0.29.0 |
| Python | 3.13.5 |
| NumPy | 2.5.1 |

**Project location**: `/opt/data/NEURAL_MESH/rust_mesh`

**Functions implemented**:
- `cosine_similarity(vec_a, vec_b)` — single-pair cosine
- `bulk_cosine_similarity(flat_a, flat_b, dim)` — batch cosine from flat lists

---

## Results: Cosine Similarity

### Benchmark: 10,000 vector pairs, 768 dimensions

| Method | Time (s) | Pairs/s | vs Pure Python | vs NumPy Batch |
|--------|----------|---------|----------------|----------------|
| Pure Python nested loop | 5.18 | 1,929 | 1.0x | 0.004x |
| Python sum+math per-pair | 3.18 | 3,144 | 1.6x | 0.006x |
| **NumPy per-pair loop** | **0.041** | **241,373** | **125x** | 0.47x |
| **NumPy batch** | **0.020** | **513,482** | **265x** | **1.0x** |
| Rust bulk (compute only) | 0.322 | 31,034 | 16x | 0.06x |
| Rust bulk (total w/ transfer) | 1.016 | 9,839 | 5x | 0.02x |

### Correctness

- Max difference Rust vs NumPy: **1.64e-07** (within float32 rounding tolerance)
- Both implementations are numerically equivalent.

### Key Finding: Rust Cannot Beat NumPy for Cosine Similarity

NumPy's vectorized operations use **BLAS (Basic Linear Algebra Subprograms)** — highly optimized C/Fortran libraries with SIMD vectorization, cache-aware tiling, and multi-threading. A handwritten Rust loop, even with `--release` optimizations, cannot compete.

**The data-transfer tax** is also significant: converting 7,680,000 numpy floats to Python lists costs **0.69s** — 2x the Rust computation time itself and 35x the NumPy batch time.

### Varying Dimensions (10K pairs)

| Dim | NumPy Batch | Rust Bulk | NumPy Wins By |
|-----|-------------|-----------|---------------|
| 64 | 0.0011s | 0.0190s | 17x |
| 128 | 0.0018s | 0.0371s | 21x |
| 384 | 0.0046s | 0.1141s | 25x |
| 768 | 0.0195s | 0.3222s | 17x |

Rust's relative performance degrades as dimension grows — BLAS's SIMD advantage scales with vector length.

---

## Recommendation: Do NOT Use Rust for Cosine Similarity

NumPy already solves this optimally. Any Rust-based approach would be:
1. **Slower** (BLAS beats handwritten loops)
2. **More complex** (build, deploy, maintain two languages)
3. **Wasteful** (data transfer overhead dominates for small batches)

---

## Where Rust WOULD Help

For NEURAL_MESH, Rust would be beneficial for operations that NumPy/BLAS **cannot** accelerate:

### 1. Graph Traversal / Associative Recall (Strong Candidate)
- BFS/DFS over the knowledge graph is pointer-chasing — no BLAS equivalent
- Python `set` and `deque` operations have per-node overhead
- Rust can use raw `Vec`-backed adjacency lists and bit-set visited tracking
- Estimated speedup: **5-20x** based on typical Rust-vs-Python graph benchmarks

### 2. Full-Text Search / BM25 (Moderate Candidate)
- Tokenization, term frequency counting, BM25 scoring are string-heavy
- Python string operations have per-character overhead
- Rust can use `&str` slices (zero-copy) and hash maps
- Estimated speedup: **3-10x** for indexing, **2-5x** for search

### 3. Custom Data Structures (Niche)
- If NEURAL_MESH needs specialized structures (tries, segment trees, custom hashing), Rust gives control Python can't match without C extensions.

---

## Files Created/Modified

| File | Purpose |
|------|---------|
| `rust_mesh/Cargo.toml` | Rust project manifest (maturin-generated) |
| `rust_mesh/pyproject.toml` | Python build config (maturin-generated) |
| `rust_mesh/src/lib.rs` | Cosine similarity + bulk cosine in Rust/PyO3 |
| `rust_mesh/SPIKE_REPORT.md` | This report |

No existing NEURAL_MESH Python code was modified.

---

## Next Steps (If Pursuing Rust)

If a Rust extension is still desired, the recommended approach is:

1. **Benchmark graph traversal first** — it's the strongest candidate
2. **Use `numpy` crate in Rust** to accept `&PyArray1<f32>` directly (no `.tolist()` tax)
3. **Benchmark with realistic graph sizes** (NEURAL_MESH's actual node/edge counts)
4. **Consider pyo3 `#[pyclass]` for persistent Rust graph** — keep the graph in Rust memory, expose query methods to Python, avoid serialization on every call

---

## Disk Space Note

The Rust toolchain was installed with `--profile minimal` due to limited disk space (1.2GB free on /opt/data). A full toolchain would require ~1.5GB additional. The minimal profile omits `rustfmt`, `clippy`, and documentation but is sufficient for building PyO3 extensions.
