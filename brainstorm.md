# NEURAL_MESH — Brainstorm v0.1 (living doc)

> Fork target: https://github.com/NousResearch/hermes-agent (memory module)
> Goal: a memory engine light-years ahead of flat-note + Mem0 + A-MEM, built for
> SMALL and LARGE containers, SHORT and LONG term lanes, single + cross-agent mesh.
> Launch target: 20k+ GitHub stars in the agentic-coding world.

---

## 1. THE PAIN (why now)

- Every agent eventually hits the **context-compression death spiral**: working memory is a
  fixed token budget; conversation history gets re-summarized into mush; the agent re-learns
  what it already knew yesterday.
- We hit this personally: Hermes memory is a flat ~2,200-char note injected EVERY turn. Past
  the cap it's truncated. The only consolidation we have is the nightly "dreaming" cycle
  (propose-only, review-gated). It works but it's *dumb*:
  - no memory topology (flat list, not a graph)
  - no forgetting / pruning (only grows)
  - no separation of memory TYPES
  - no cross-agent sharing
  - no pointer discipline for big tool outputs (214KB logs → context overflow)
- IBM quantified it: a Materials-Science workflow burned **20,822,181 tokens and FAILED**;
  with memory pointers it used **1,234 tokens and succeeded** (16,000× win).

## 2. LANDSCAPE SCAN (what exists + the gap in each)

| System | What it does well | The gap NEURAL_MESH fills |
|---|---|---|
| **Hermes (flat notes)** | Simple, always-injected, durable | No topology, char-capped, no forgetting, no type split → our FORK BASE |
| **Mem0** | Vector+graph, single-pass extraction, multi-signal retrieval (semantic+keyword+entity); LoCoMo 92.5 / LongMemEval 94.4 | API-centralized, no native sleep/forgetting, no cross-agent mesh, heavier |
| **A-MEM (Zettelkasten)** | Memories self-organize + self-link into a graph | No memory LANES (short/long split), no pruning, single-agent only |
| **Sibyl** | Cross-agent COLLECTIVE memory runtime | It's a runtime, not a memory ENGINE; no 5-type separation |
| **SleepGate** | Neuroscience forgetting (replay + prune) | Research-only, not packaged/productized |
| **Tony's dreaming** | Propose-only nightly consolidation we already run | Not a general memory engine; review-gated only |

## 3. THE GAP (nobody has shipped ALL of this together)

1. **Five memory types with DISTINCT retrieval logic** — not collapsed into one vector index.
   (2026 survey: Working / Episodic / Semantic / Sensory / Procedural each need different ranking.
   Most prod systems mix episodic logs into a semantic index and retrieval quality tanks.)
2. **Mesh topology (associative, resonance-spreading)** — Zettelkasten on steroids. Memories are
   NODES that self-link by meaning, not just cosine chunks. Activation spreads like a neural net.
3. **Explicit memory LANES** — short-term HOT ↔ long-term COLD, bridged by a consolidation bus.
4. **Built-in SLEEP / FORGETTING cycle** — auto-prune weak traces. Directly kills "container always full."
5. **Memory POINTER protocol** — big tool outputs stored externally, only a pointer enters context.
6. **Cross-agent MESH** — collective intelligence (Sibyl-style), agents share/verify a mesh.
7. **SIZING TIERS** — tick mode (SQLite + tiny embeddings) for small containers; heavy mode
   (graph DB + reranker) for big agents. One API, two footprints.
8. **POISONING RESISTANCE** — provenance + trust scoring. (Security study: 90% of agents vulnerable,
   100% relapse when "fixed" by correcting in chat.)

## 4. NEURAL_MESH CORE ARCHITECTURE (proposed)

```
                         ┌──────────────────────────────────────┐
   TOOL OUTPUTS ─────────┤  POINTER LAYER  (big data → external)  │──► only ptr in context
                         └──────────────────────────────────────┘
                                        │
   ┌──────────── MESH CORE ────────────────────────────────────────────────┐
   │  LANE A: SHORT-TERM (hot)   LANE B: LONG-TERM (cold)                    │
   │  working+episodic cache      semantic+procedural graph                  │
   │        │                          │                                     │
   │        └──── CONSOLIDATION BUS ───┘  (promote / demote / link)          │
   │                  │                                                     │
   │   MESH TOPOLOGY: nodes self-describe + self-link (resonance retrieval)  │
   │   RETRIEVAL: semantic ⊕ keyword ⊕ entity ⊕ graph-walk (multi-signal)    │
   └───────────────────────────────────────────────────────────────────────┘
                                        │
                         ┌──────────────────────────────────────┐
                         │  SLEEP CYCLE (nightly / threshold)    │
                         │  replay → strengthen → PRUNE weak     │
                         │  provenance + trust re-score          │
                         └──────────────────────────────────────┘
                                        │
                         ┌──────────────────────────────────────┐
                         │  CROSS-AGENT MESH (opt-in, signed)    │
                         │  collective memory, conflict-resolved │
                         └──────────────────────────────────────┘
```

- **Resonance retrieval**: a query seeds N nodes; activation spreads to linked neighbors with
  decay; top-k by resonance + recency + trust. This is the differentiator vs flat vector search.
- **Consolidation bus**: episodic events bubble up into semantic facts; stale semantic facts
  demote; contradictions resolved by recency+trust (not blind overwrite).
- **Sleep**: threshold- or schedule-triggered; prunes low-resonance, low-trust, aged-out nodes.
  This is literally what Tony's dreaming does — we GENERALIZE it into the engine.

## 5. BENCHMARK TARGETS (to beat, publicly)

| Benchmark | Mem0 (2026) | NEURAL_MESH target |
|---|---|---|
| LoCoMo | 92.5 | 94+ |
| LongMemEval | 94.4 | 96+ |
| BEAM (1M) | 64.1 | 67+ |
| BEAM (10M) | 48.6 | 52+ |
| Tokens/query | ~6,900 | <5,000 (pointers + pruning) |

Open problems the benchmarks reward: cross-session identity, temporal abstraction at scale,
memory staleness — NEURAL_MESH lanes + sleep attack all three.

## 6. LAUNCH PLAN (20k stars)

- **Seed**: fork hermes-agent memory module; keep the durable-note UX, replace the engine.
- **Build in the open**: weekly demo reels, public benchmark dashboard (CI runs LoCoMo/LongMemEval).
- **Dogfood first**: wire NEURAL_MESH into our own Hermes + D0xedDev agents (real proof).
- **Base L2 angle**: on-chain memory PROVENANCE / Agent Aura tie-in via Helixa — memory you can
  verify. Nobody else ships verifiable agent memory. This is the CT/memecoin-community hook.
- **Packaging**: `pip install neural-mesh`; one-line init; MIT license for max adoption.
- **Content engine**: contrast posts ("why your RAG memory is a category error"), benchmark
  graphs, the 16,000× token story.

## 7. OPEN QUESTIONS FOR US (decide next)

- [ ] Language: Python core + optional Rust hot path? Or pure Python for contributor reach?
- [ ] Default tick backend: SQLite + sqlite-vec? Heavy: Postgres+pgvector or Neo4j?
- [ ] How deep does the on-chain provenance tie-in go at v1 (Helixa Aura vs simple hash)?
- [ ] Licensing: MIT (adoption) vs something with a commercial clause?
- [ ] First drill target: (a) mesh topology+resonance retrieval, (b) lanes+consolidation bus,
      (c) sleep/pruning, (d) pointer protocol, (e) cross-agent mesh?

---

## 8. ADDENDUM — additional systems scanned (round 2)

| System | Core idea | What it gives NEURAL_MESH |
|---|---|---|
| **MemGPT / Letta** | OS-style hierarchical memory (working/recall/archival) via function-calling | Validates LANES; we do it AUTOMATIC not agent-driven |
| **Zep / Graphiti** | Temporal knowledge graph — facts versioned across time | Temporal fact versioning + conflict resolution |
| **HippoRAG** | Hippocampal indexing theory — 1-hop graph traversal finds related-but-non-obvious memory | **Neuroscience proof for resonance-spreading retrieval** |
| **CoALA** | Foundational taxonomy: working/episodic/semantic/procedural + read/write action space | Grounds our 5-type split in published theory |
| **RAPTOR** | Recursive tree of summaries (multi-scale abstraction) | Abstraction tier in long-term memory |
| **Generative Agents** | Memory stream + salience/recency/importance + reflection (LLM insight synthesis) | Reflection primitive for the sleep cycle |

KEY INSIGHT: NEURAL_MESH's Mesh + resonance is HippoRAG's hippocampal indexing,
productized + generalized across all 5 memory types + lanes + sleep. Defensible + citable.

## 9. THE WHITESPACE (research has touched, NOBODY has shipped as a product)

1. **Prospective memory** — store intentions/futures ("follow up Tuesday", "remind on event"),
   not just the past. Real cognitive type (episodic future thinking); total gap in shipped systems.
2. **Reflection-as-consolidation** — bake LLM insight-synthesis into the SLEEP cycle (Generative
   Agents proved it works; never shipped in a memory engine).
3. **Resonance spreading as PRIMARY retrieval primitive** — graph activation-spread (HippoRAG-
   grounded), not flat cosine. Novel as a shipped primitive.
4. **Self-learning retention** — LRAT/MIA: agents generate training data for their OWN retriever;
   a 7B with good memory beat a 32B. Productize: the mesh learns what to keep.
5. **Verifiable on-chain provenance** (Helixa/Aura) — memory you can PROVE unpoisoned. Unique to us.
6. **Working memory as explicit token-budget optimizer** w/ priority eviction (budget problem,
   not retrieval — Nuanced Perspective). Nobody treats it as a live optimizer.
7. **Portable memory interchange format** (`.mesh` export) — any agent imports another's memory.
   Standards play = stars.
8. **Sleep cycle emits LoRA-ready corpus** — pruning OUTPUT is fine-tuning fuel (Tony's stage-3).
9. **Conflict-resolved cross-agent mesh** — extends Sibyl from shared notes → verified consensus.
10. **Multi-modal sensory nodes** as first-class (images/audio/docs summarized on ingest).
