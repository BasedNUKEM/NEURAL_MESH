# 🧠 NEURAL_MESH

**A self-organizing, self-forgetting agentic memory mesh — built for the context-overflow era.**

> Your agent's memory is a flat file that grows until it breaks. NEURAL_MESH is a
> neural-mesh brain: typed memory, a self-linking topology, resonance retrieval,
> hot/cold lanes, a sleep cycle that forgets, and pointers that keep big tool
> output out of your context. Light enough for a tiny container, deep enough to
> share across agents.

---

## Why this exists

We kept hitting the same wall in production agents (Hermes, Sibyl, Tony-Simons
setups, Base agent infra):

- **Memory always full** — a flat `MEMORY.md` grows unbounded; context compression
  silently degrades what the agent "remembers."
- **No memory *types*** — an episode (a deploy failed) and a fact (user is in KL)
  get dumped in the same pile and retrieved by the same cosine search.
- **Stale truth** — when a fact updates (Maya's editor was Vim → is now Neovim),
  flat vector search keeps *both* embeddings and returns both. The agent acts on
  the old one.
- **Big output in context** — a 200 KB log dump eats the whole window.

`NousResearch/hermes-agent` opened the door. NEURAL_MESH is the fork-shaped
answer: a memory substrate that organizes itself, forgets on purpose, and serves
only what's *current and relevant*.

---

## The thesis (what makes it different)

```
                 ┌──────────────────────────────────────────┐
   agent  ─────► │   INGEST  (typed write)                  │
                 │   semantic | episodic | procedural |     │
                 │   sensory | prospective                   │
                 └───────────────┬──────────────────────────┘
                                 │ auto-link by meaning
                                 ▼
        ┌────────────────────────────────────────────────────────┐
        │  MESH  (memory nodes self-link into a graph)            │
        │                                                          │
        │   ◉ semantic      ◉ episodic        ◉ procedural        │
        │      │  ╲           │  ╲              │                 │
        │      │   ╲──link─────┘   ╲──link───────┘                 │
        │      ▼                ▼                ▼                 │
        │   ◉ prospective   ◉ sensory        (supersedes ▸)       │
        │                      │                                  │
        │            HOT lane  │  consolidation bus   COLD lane   │
        └──────────────────────┼──────────────────────────────────┘
                               │  SLEEP: replay → strengthen → prune
                               ▼
                 RESONANCE retrieval (query seeds nodes,
                 activation spreads to linked neighbours w/ decay)
                               │
                               ▼
                 only CURRENT + RELEVANT memories → context
```

1. **Five memory types, handled separately.** `semantic`, `episodic`,
   `procedural`, `sensory`, `prospective` (intentions/futures, not just the past).
   Retrieval can filter by type so a deploy log never dilutes a user fact.
2. **Mesh topology, not a list.** Each node auto-links to its nearest neighbours
   (HippoRAG-style hippocampal indexing). Meaning lives in the *edges*.
3. **Resonance retrieval (the differentiator).** A query seeds nodes; activation
   spreads across links with decay and re-ranks by relevance + recency + trust.
   You get the cluster, not a lonely singleton.
4. **Hot / Cold lanes + sleep.** Short-term traces live `hot`; a consolidation
   bus moves durable knowledge `cold`. The **sleep cycle** replays, strengthens,
   and **prunes** weak/aged/low-trust traces — memory that forgets on purpose.
5. **Versioning / no stale truth.** `supersedes` links soft-archive old facts.
   Retrieval skips them. The agent only ever sees *current* truth.
6. **Pointer protocol.** Big tool output is stored externally; context receives
   a `mesh://…` pointer (36 bytes instead of 200 KB).
7. **Cross-agent ready.** Provenance, trust, and a portable `.mesh` interchange
   are on the roadmap so meshes can be shared and merged.

---

## Install

Zero dependencies to run the core + demo:

```bash
git clone https://github.com/D0xedDev/NEURAL_MESH
cd NEURAL_MESH
python -m neural_mesh.demo          # pure stdlib, no pip needed
```

Optional: real embeddings (dense vectors, no torch — uses `fastembed`/ONNX):

```bash
python -m venv .venv && .venv/bin/pip install fastembed
PYTHONPATH=. .venv/bin/python -c "from neural_mesh.core import Mesh, MemoryType
from neural_mesh.embed_real import RealEmbedder
m = Mesh(embedder=RealEmbedder())"
```

---

## Quickstart

```python
from neural_mesh.core import Mesh, MemoryType

m = Mesh()  # sqlite, local, in-memory by default

# 1. write by TYPE
m.add("User Cody is in Kuala Lumpur.", MemoryType.SEMANTIC, provenance="chat")
m.add("Deploy failed: Vercel blocked unknown git author.", MemoryType.EPISODIC, provenance="log")
m.add("Run validate, then gh workflow to ship.", MemoryType.PROCEDURAL, provenance="skill")
m.add("Refactor memory module before launch.", MemoryType.PROSPECTIVE, provenance="user")

# 2. resonance recall — surfaces the cluster, not one match
for n in m.recall("how do I ship the deploy?"):
    print(n.type.value, n.content)

# 3. versioning — update a fact, old one auto-archives
old = m.add("Maya's editor is Vim.", MemoryType.SEMANTIC)
m.add("Maya's editor is Neovim.", MemoryType.SEMANTIC, supersedes=old.id)
# recall("what editor does Maya use?") -> Neovim only. Vim is gone from results.

# 4. sleep — prune + reflect
m.sleep(reflect_fn=lambda nodes: ["insight: deploys need a known git author"])
```

---

## Benchmarks (honest)

We benchmark against **flat cosine vector search** (what Mem0 / vanilla vector
DBs do) on the *same* dense embeddings (`bge-small-en`) — isolating the value of
the mesh + versioning. Run them yourself in `bench/`.

### Versioning / stale-truth — the headline win ✅

Corpus: 12 writes, 6 of them *updates* of a previous fact (Maya's editor, role,
city, cat status, deploy rule, language preference). 6 questions ask for the
**current** value.

```
VERSIONING / CONFLICT  (n=6 update-questions, 12 writes / 6 updates)
  Stale (wrong) hits in top-5:
    FLAT : 17/6 queries returned stale data
    MESH : 0/6   queries returned stale data
  Top-1 points at CURRENT fact:
    FLAT : 1/6  =  16.7%
    MESH : 6/6  = 100.0%
```

**NEURAL_MESH surfaces current truth top-1 100% of the time vs 16.7% for flat —
a 6× precision gap — and leaks zero stale memories (flat leaked 17).**
This is the failure mode that silently breaks production agents. Flat vectors
can't fix it; a `supersedes` link can.

> Reproduce: `PYTHONPATH=. .venv/bin/python bench/versioning_bench.py`

### Recall@k (clean corpus) — honest tie

On a clean 27-fact synthetic set with dense embeddings, flat cosine already
hits ~100% recall@5, and MESH matches it. **We report this as a tie** — dense
embeddings are genuinely good at single-fact recall, and pretending otherwise
would be dishonest. The mesh's edge is *precision under conflict* (above) and
*subgraph completeness* under context budgets (next on the roadmap).

> Reproduce: `PYTHONPATH=. .venv/bin/python bench/locomo_hard.py`

---

## Roadmap

- [x] Five-type memory + mesh auto-linking
- [x] Resonance retrieval (seed + spread + decay)
- [x] Hot/cold lanes + sleep (prune + reflect)
- [x] Pointer protocol (keep big output out of context)
- [x] Versioning / `supersedes` (no stale truth)
- [ ] `.mesh` portable interchange format
- [ ] Cross-agent mesh sharing + consensus
- [ ] Real LoCoMo eval harness (full dataset recall numbers)
- [ ] LoRA-ready sleep output (distill patterns into an adapter)
- [ ] Rust hot path for large meshes
- [ ] Helixa / Agent Aura provenance (Base L2, optional)

---

## Architecture

| File | Role |
|------|------|
| `neural_mesh/node.py` | Memory-node schema: type, lane, provenance, trust, decay, links |
| `neural_mesh/embed.py` | Embedding abstraction + zero-dep hashed fallback |
| `neural_mesh/embed_real.py` | Optional real embedder (`fastembed`, no torch) |
| `neural_mesh/core.py` | `Mesh` orchestrator: store, auto-link, recall, sleep, version |
| `neural_mesh/resonance.py` | Spreading-activation retrieval |
| `neural_mesh/pointer.py` | Big-output → `mesh://` pointer protocol |
| `neural_mesh/demo.py` | End-to-end live demo |
| `bench/` | Reproducible benchmarks (versioning, recall) |

---

## Contributing

This started as a fork-shaped idea off `NousResearch/hermes-agent` and the
Sibyl / Tony-Simons memory practices. PRs welcome — especially on `.mesh`,
cross-agent consensus, and the LoCoMo eval. Keep the core pip-free; real
embedders stay optional.

---

## License

MIT. Build the future of agent memory in the open. 🟦
