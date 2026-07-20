# NEURAL_MESH — launch copy

> Status: DRAFT. Repo not yet created. These are ready-to-post assets for when
> the user gives the GitHub GO.

---

## Repo description (GitHub)
`NEURAL_MESH — a self-organizing, self-forgetting agentic memory mesh. Typed
memory · mesh topology · resonance retrieval · hot/cold lanes · sleep/prune ·
versioned truth. Light enough for a tiny container, deep enough to share.`

## One-liner / tagline
`Stop dumping memory into a flat file that grows until it breaks. NEURAL_MESH is
the neural-mesh brain for agents: it organizes, forgets, and only serves what's
current.`

---

## X / Twitter launch thread (🟦 Devio voice)

**1/**
you know what silently breaks every production agent?
memory.
not "no memory" — *too much memory*. a flat file that grows until context
compression eats the thing you actually needed.
we built the fix. 🧠 @D0xedDev #NEURAL_MESH

**2/**
the problem nobody talks about:
when a fact UPDATES (Maya's editor was Vim → is now Neovim), flat vector search
keeps BOTH embeddings and returns both. your agent acts on the OLD one.
we benchmarked it. flat surfaced stale truth top-1 only 16.7% of the time.

**3/**
NEURAL_MESH uses a `supersedes` link + retrieval-skip.
result on an update-heavy corpus:
• FLAT: 17/6 queries leaked stale data. top-1 current = 16.7%
• MESH: 0/6 leaks. top-1 current = 100%
a 6× precision gap on the exact failure that breaks agents. 📊

**4/**
it's not just versioning. NEURAL_MESH models memory like cognition:
◉ 5 types — semantic / episodic / procedural / sensory / prospective
◉ mesh topology — nodes self-link by meaning
◉ resonance retrieval — a query seeds nodes, activation spreads to the cluster
◉ hot/cold lanes + a SLEEP cycle that prunes weak memory on purpose
◉ pointer protocol — 200KB output → a 36-byte mesh:// pointer

**5/**
zero deps to run the core. pure stdlib. real embeddings optional (no torch).
it's fork-shaped off @NousResearch hermes-agent + the Sibyl / Tony-Simons memory
practices we already run. now it's open, and it's better.
👉 github.com/D0xedDev/NEURAL_MESH

**6/**
roadmap: portable `.mesh` interchange, cross-agent mesh sharing + consensus,
real LoCoMo eval, LoRA-ready sleep output, and Helixa / Agent Aura provenance on
Base L2. built in the open, MIT. come help us make agent memory not suck. 🟦

---

## GitHub Release (v0.1.0) notes
### NEURAL_MESH v0.1.0 — "current truth"
First public cut of the self-organizing agentic memory mesh.

**What's in:**
- Five typed memory lanes (semantic / episodic / procedural / sensory / prospective)
- Mesh auto-linking on ingest (HippoRAG-style)
- Resonance retrieval: seed → spread → decay re-ranking
- Hot/Cold lanes + sleep cycle (replay → strengthen → prune)
- Pointer protocol (big output → `mesh://` reference)
- Versioning via `supersedes` → no stale truth in retrieval

**Benchmarks (reproducible in `bench/`):**
- Versioning: 6× fewer stale-memory errors vs flat cosine (100% vs 16.7% top-1 current)
- Recall@k on clean corpus: tie with flat (dense embeddings are strong; reported honestly)

**Not yet:** `.mesh` interchange, cross-agent networking, full LoCoMo eval, Rust hot path.
Those are the next milestones — PRs welcome.

MIT. 🟦
