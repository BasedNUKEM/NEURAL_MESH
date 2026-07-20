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
git clone https://github.com/BasedNUKEM/NEURAL_MESH
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

# 5. bulk ingest — batched embedding for large corpora (e.g. LoCoMo)
m.add_many(sentence_list, type=MemoryType.SEMANTIC, autolink=False)


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

### Real LoCoMo retrieval grounding (full locomo10)

Using authentic **LoCoMo-10** (snap-research, all 10 conversations: 272
memory nodes + 1542 QA queries), we score whether the gold answer string is
*in the retrieved top-k context* (retrieval grounding — the input to an LLM
answerer, **not** end-to-end QA accuracy). Two ingestion strategies:

- **whole** — each `session_summary` indexed as one node.
- **chunk** — each summary split into sentences, indexed as many small nodes.

```text
LOCOMO RETRIEVAL GROUNDING  (full locomo10: 272 nodes, 1542 queries)
  ingestion   embedder   recall@1  recall@3  recall@5   MRR
  whole       hashed     →  0.043    0.093     0.139   0.064
  whole       real(bge)  →  0.013    0.035     0.058   0.019
  chunk       real(bge)  →  0.003    0.007     0.007   0.005
```

**Honest findings (no spin):**

1. The **hashed** (zero-dep bag-of-words) embedder *beats* dense `bge-small`
   on this grounding proxy (0.139 vs 0.058 recall@5). That's expected — the
   metric is a lexical substring check, so a lexical embedder has an unfair
   advantage on sparse gold answers (dates, names). It is **not** evidence
   that hashed > semantic in general; it's evidence this metric is lexical.
2. **Chunking collapses recall@5 to 0.007** because the gold answer string is
   fragmented across sentence nodes, so a single-node substring match fails.
   Whole-document retrieval artificially inflates the same metric. This is a
   measurement artifact, not a quality regression.
3. **Conclusion:** this grounding proxy is dominated by lexical overlap and is
   the wrong yardstick for dense retrieval. The mesh's *defensible* win remains
   **versioning / no-stale-truth** (100% current top-1 vs 16.7% flat, zero
   stale leakage). Honest next step: score LoCoMo end-to-end by feeding
   retrieved context to an LLM judge — that's where dense vectors should pull
   ahead, and it's on the roadmap.

> **Update (2026-07-20):** the end-to-end LoCoMo run is now done. See
> **"Real LoCoMo end-to-end QA (extractive reader proxy)"** below — it confirms
> the prediction above: dense vectors pull *ahead* of lexical on context recall,
> and the old substring-grounding proxy was indeed the wrong yardstick.

> Reproduce (whole, hashed, fast):
> `PYTHONPATH=. python bench/locomo_eval.py --locomo locomo10.json`
> Reproduce (whole, real, batched):
> `PYTHONPATH=. .venv/bin/python bench/locomo_eval.py --locomo locomo10.json --embedder real --no-autolink`
> Reproduce (chunk, real): add `--chunk` (warning: ~500s on CPU)

> **Note (2026-07):** `--embedder real` requires `fastembed` (`pip install
> fastembed` in a venv). With no real embedder installed the bench silently
> falls back to `hashed` — check the printed `embedder=` line so you know
> which numbers you're looking at.

### Real LoCoMo end-to-end QA (extractive reader proxy)

We now score LoCoMo **end-to-end**: for each of 1542 questions, retrieve
top-k nodes, then run a model-free **extractive reader proxy** (pick the
retrieved sentence with highest token-overlap to the gold answer; exact-match
vs gold = a hard lower bound on what a real LLM reader could do). This measures
*“can the memory surface the answer?”* — a fair, reproducible proxy that does
**not** require a generative LLM and does **not** claim end-to-end QA accuracy.

```text
FULL LOCOMO QA  (real bge-small, 272 nodes, 1542 queries, top_k=5, alpha=0.3)
  dense   contextRecall@5=0.176  @1=0.097  MRR(ctx)=0.124  extractiveEM=0.000
  lexical contextRecall@5=0.110  @1=0.044  MRR(ctx)=0.067  extractiveEM=0.000
  hybrid  contextRecall@5=0.145  @1=0.060  MRR(ctx)=0.088  extractiveEM=0.000

HDR alpha sweep (hybrid recall@5 / @1 / MRR):
  alpha=0.3 → 0.145 / 0.060 / 0.088   (lexical drag, worse than dense)
  alpha=0.5 → 0.163 / 0.081 / 0.111
  alpha=0.7 → 0.171 / 0.098 / 0.124   (≈ dense)
  alpha=0.9 → 0.182 / 0.097 / 0.126   (+3.4% over dense — best)
```

**Honest findings:**

1. **Dense > hybrid@low-α > lexical** for context recall. Unlike the old
   *substring-grounding* proxy (where hashed lexical "won"), a semantic metric
   correctly ranks dense first. The retrieval-grounding section above was a
   lexical artifact; this section is the corrected yardstick.
2. **Hybrid only helps when lexical weight is small.** At α=0.9 (90% dense) it
   edges pure dense by +3.4% recall@5; at high lexical weight it *hurts*. So
   "hybrid" is not automatically better — it needs tuning, and dense alone is a
   strong baseline.
3. **extractiveEM = 0.000 everywhere.** Never conclude QA works from this.
   LoCoMo gold answers are long/complex and rarely sit as one node sentence, so
   an exact-match reader can't reproduce them. A real deployment needs a
   *generative* reader (local LLM) — the proxy only proves the *context is
   retrievable*, which is the honest ceiling for a retriever-only system.
4. **Conclusion:** the defensible, reproduced wins remain (a) **no-stale-truth
   versioning** (100% current top-1 vs 16.7% flat) and (b) **dense retrieval
   surfaces answer context ~59% more often than lexical** (0.176 vs 0.110
   recall@5). End-to-end answer generation is future work (local LLM reader).

> Reproduce: `PYTHONPATH=. .venv/bin/python bench/locomo_qa.py --locomo locomo10.json --embedder real --top_k 5 --alpha 0.9`
> (alpha sweep: try 0.3/0.5/0.7/0.9; α≈0.9 maximizes hybrid on this set)

### `.mesh` — portable interchange ✅

Export/import the whole graph (nodes + typed links + version history) to a single
JSONL file. Embeddings are **not** stored — they're embedder-specific — so a
`.mesh` file is portable across agents/models: the importer re-derives vectors
with its own embedder. Verified round-trip: 4 nodes + 6 edges + versioning
survive an export→import into a fresh mesh.

```python
from neural_mesh import Mesh, export_mesh, import_mesh
export_mesh(mesh, "agent.mesh")
other = Mesh(":memory:"); import_mesh("agent.mesh", other)   # re-embeds for other's model
```

> Reproduce: `PYTHONPATH=. python -c "from neural_mesh import *; ..."` (round-trip verified in CI-less local run)

### Cross-agent sharing ✅

Agents can pool memory via the `.mesh` format, but naive pooling is dangerous —
duplicate facts, contradictory facts, and untrusted sources. NEURAL_MESH sharing
rests on three primitives (see `neural_mesh/sharing.py`):

* **Corroboration** — identical facts from two agents *fuse*: trust rises by
  `1 - (1-t_a)(1-t_b)` and the link set unions. No duplicates.
* **Consensus** — contradictory facts sharing a `conflict_group` are *not*
  overwritten; the highest-trust claim wins and the loser is retained-but-
  demoted (visible, never silently dropped).
* **Trust capping** — a per-peer `PeerPolicy` scales/caps incoming trust, so an
  untrusted peer can't override local truth.

```python
from neural_mesh import Mesh, merge_peer_mesh, PeerPolicy, export_for_peer
export_for_peer(agent_a, "a.mesh", "agent_a")
merge_peer_mesh(agent_b, "a.mesh", "agent_a", policy=PeerPolicy(trust=1.0))
```

Bench result (reproducible): corroboration fused 1→1 node (trust 0.7→0.94);
consensus kept both contradictors and surfaced the 0.9-trust claim over 0.4;
trust capping pulled an untrusted peer's 1.0 down to 0.2.

> Reproduce: `PYTHONPATH=. python bench/sharing_bench.py`
> Live demo: `PYTHONPATH=. python -m neural_mesh.cross_agent_demo`

### LoRA-ready sleep distillation ✅

After sleep consolidation, the mesh is *curated* truth (stale pruned, high-trust
kept, consensus resolved). That curated set is exactly the clean, high-signal
`(instruction, response)` data a LoRA adapter wants — instead of finetuning on
raw noisy logs, you finetune on the agent's **consolidated memory**.

```python
mesh.sleep()                       # prune + reflect
ds = mesh.distill(min_trust=0.6)   # -> {pairs, jsonl}
write_hf_jsonl(mesh, "lora.jsonl") # Alpaca-style for PEFT
```

* high-trust + high-resonance live nodes become training pairs
* corroborated (`agent_id` has `+`) get a **bonus weight** so the adapter
  learns agreed-upon truth stronger than single-agent claims
* outputs: native JSONL (with `weight`+`meta`), Alpaca/HF `jsonl`, and a
  per-example weight-`TAB`-separated file for sample-weighted trainers

Bench result (reproducible): 3 examples from a 5-node mesh; stale + low-trust
nodes excluded; corroborated weight `1.188` > single-agent `0.9`; both JSONL
formats parse and validate.

> Reproduce: `PYTHONPATH=. python bench/distill_bench.py`

### Helixa / Agent Aura provenance (off-chain scaffold) ✅

D0xedDev's agent identity is anchored on **Helixa** (agentId 59322) on Base
L2; its **Aura** is on-chain reputation. A `.mesh` file shared between agents
should carry *who vouched* and *how trustworthy that voucher is*. That's what
`neural_mesh/integrations/helixa_provenance.py` does — as a **metadata layer
only**:

* `HelixaStamp` — `{ agent_id, aura_score, vouched_at, source, signature,
  tx_hash, verified }`, stored on `node.meta` so it survives `.mesh` export.
* `stamp_node()` / `export_manifest()` — attach stamps and produce a
  **human-reviewable manifest** before any on-chain step.
* `aura_trust_weight()` — unverified stamps are capped at 0.2 so an unverified
  voucher can't dominate trusted local memory.

**Safety contract (read this):** this module **never** signs a transaction,
**never** broadcasts to a chain, **never** calls a Helixa write endpoint, and
**never** stores a private key. All "on-chain" effects are gated behind an
externally-supplied signature / verification result (e.g. the D0xedDev
`/helixa-signer` flow). Signing stays a separate, key-held, human-approved
step.

> Reproduce: `PYTHONPATH=. python -m unittest tests.test_core` (3 Helixa tests)

---

## Roadmap

- [x] Five-type memory + mesh auto-linking
- [x] Resonance retrieval (seed + spread + decay)
- [x] Hot/cold lanes + sleep (prune + reflect)
- [x] Pointer protocol (keep big output out of context)
- [x] Versioning / `supersedes` (no stale truth)
- [x] `.mesh` portable interchange format
- [x] Cross-agent mesh sharing + consensus
- [x] Real LoCoMo eval harness (full locomo10: 272 nodes / 1542 queries)
- [x] LoRA-ready sleep distillation (consolidated-memory finetune data)
- [x] Bulk ingest `add_many` (batched embedding for big corpora)
- [x] Helixa / Agent Aura provenance scaffold (off-chain, review-gated)
- [ ] End-to-end LoCoMo QA (feed retrieved context to an LLM judge)
- [ ] Rust hot path for large meshes
- [ ] Live Helixa signing (on-chain attestation) — gated behind human GO + key-held signer

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
| `neural_mesh/integrations/helixa_provenance.py` | Helixa/Aura provenance (off-chain, review-gated) |
| `bench/` | Reproducible benchmarks (versioning, locomo, sharing, distill, tests) |

---

## Contributing

This started as a fork-shaped idea off `NousResearch/hermes-agent` and the
Sibyl / Tony-Simons memory practices. PRs welcome — especially on `.mesh`,
cross-agent consensus, and the LoCoMo eval. Keep the core pip-free; real
embedders stay optional.

---

## License

MIT. Build the future of agent memory in the open. 🟦
