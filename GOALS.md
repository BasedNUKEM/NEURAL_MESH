# NEURAL_MESH — Goals & Next Stages

> Owner: **D0xedDev / Cody** (@d0xb00m) · Co-pilot: Hermes (Devio)
> Repo: `BasedNUKEM/NEURAL_MESH` (branch `master`) · Live: `https://api.d0xeddev.com`
> Last updated: 2026-08-14 · Current shipped: **v0.27.0**

This is the **single source of truth for "what's next"**. It is goal-oriented on
purpose: every stage starts from the *outcome* we want to prove, then lists the
deliverables, acceptance criteria, and verification that make that outcome real.
When a stage ships, check its box in the README roadmap and update the
**Baseline** below.

---

## North Star

NEURAL_MESH is the **local-first typed-graph agentic-memory engine** that wins on
the things flat vector stores structurally cannot: no-stale-truth versioning,
cross-agent corroboration, associative (link-driven) recall, and honest,
reproducible benchmarks. Every stage below either (a) proves a capability with
real numbers, or (b) hardens the mesh so it can be trusted in shared, hostile
memory contexts.

---

## Baseline (where we actually are — 2026-08-14)

🟦 **Shipped:** v0.27.0 (memory-poisoning defense, OWASP ASI06), v0.26.0
(echo-chamber guard), v0.25.x (brain visual health), v0.21.0 (Rust resonance,
abi3), v0.20.0 (unified lifecycle), v0.18.0 (cross-agent `.mesh` + package).

🟦 **Live prod:** 580 nodes · `resonance_backend=rust` · Helixa signer
`degraded:false` (address `0x789B…`) · all public endpoints 200.

🟦 **Honest numbers on record:**
- Versioning / no-stale-truth: **100% current top-1 vs 16.7% flat** (zero stale leakage).
- Dense recall surfaces answer context ~59% more often than lexical (0.176 vs 0.110 ctxR@5).
- Resonance is ~5× *worse* than dense on direct QA (0.037 vs 0.176) — expected, it's for associative recall, not fact lookup.
- LongMemEval (hashed, dense, top_k=5): ctxR@1=0.070, ctxR@5=0.066, MRR=0.112 — **artifact numbers** (lexical substring on a bag-of-words embedder).

🟦 **Known gaps this doc closes:**
1. The README's own thesis — *"dense vectors should pull ahead with an LLM judge"* — is still **unproven** (roadmap checkbox unchecked).
2. Subgraph completeness under context budgets is "next on the roadmap" but has no published numbers.
3. The Rust accelerator covers query scoring + spread only; **BM25 / full-text** is the identified next hot path.
4. **LLM funding gate (verified 2026-08-14):** the OpenRouter account has exhausted its grant — `total_usage $10.20` > `total_credits $10.00` (`GET /v1/credits`). Every real answer/judge call 402s (`Payment Required`) even though the key is valid and both `deepseek/deepseek-chat` + `deepseek/deepseek-chat-v3-0324` slugs return 200 on a trivial probe. Goals 1 + 5 (and the VPS `muse=llm`) are **blocked on a ~$10 top-up**, not on code.
5. The **live** `OPENROUTER_API_KEY` is in `/opt/data/.env.d0xeddev_populated` (73 chars, `sk-or-v1-…`). The copies in `D0XEDDEV/.env` + `plugins/D0xeddev/.env` are **stale/truncated** (9–10 chars) and will 401. VPS mirror: `/root/.hermes/docker-data/.env`.

---

## Goal 1 — Prove dense retrieval wins end-to-end (LLM-judged LoCoMo QA)

**Outcome:** publish a defensible, reproduced number showing dense retrieval
beats lexical *when retrieved context is fed to a generative judge* — the exact
claim the README has promised since v0.14.0.

**Why this is the #1 next stage:** it is the only unchecked non-GO-gated roadmap
item, it closes the single biggest "honest-but-unproven" gap, and the entire
stack is already wired (`neural_mesh/eval.py → QAJudge + run_qa_eval`,
`neural_mesh/reader_llm.py → LLMReader`, `bench/locomo_llm_judge.py`). The only
missing piece is *actually running it and publishing numbers*.

### Deliverables
🟦 Step 0 — top up the OpenRouter account (usage already exceeds the $10 grant),
refresh the live key from `.env.d0xeddev_populated`, and pin a **currently-working**
model slug (verify with `scripts/llm_probe.py` before the run — `deepseek/deepseek-chat`
and `deepseek/deepseek-chat-v3-0324` are both valid, but the account is out of credit).
🟦 Run the E2E harness over a real LoCoMo subset (start 100 queries, scale to full 1542).
🟦 Produce a comparison table: dense vs lexical vs hybrid vs resonance, scored by LLM judge.
🟦 Report EM/F1 with the LLM judge AND the extractive baseline so the improvement is visible.
🟦 Commit any fixes surfaced by the run (API drift, empty-content guards).

### Acceptance criteria
🟦 At least 100 queries judged end-to-end with a **generative** judge (not the keyword fallback).
🟦 Published table in README with reproduction command + cost note.
🟦 Honest framing preserved: report ties/wins for dense *and* a dense-wins-or-loses control; never spin a metric-mismatch.

### Verification
```bash
PYTHONPATH=. python3 bench/locomo_llm_judge.py --locomo locomo10.json --limit 100
# then a full run:
PYTHONPATH=. python3 bench/locomo_llm_judge.py --locomo locomo10.json
```

---

## Goal 2 — Subgraph completeness under context budgets

**Status: 🟦 DONE (v0.28.0, 2026-08-18)** — real numbers published below.

**Outcome:** a `topology_score` (or equivalent) that measures, under a bounded
context budget, what fraction of the *linked* memory neighborhood a retrieval
slice can carry — proving the mesh's structural recall survives compression.

**Published numbers (synthetic, 800 nodes × 5 edges, 100 seeds, `bench/subgraph_completeness.py`):**

| budget | subgraph_recall | edge_density | topology_score |
|--------|-----------------|--------------|----------------|
| k=5    | 0.0091          | 0.9990       | 0.0180         |
| k=10   | 0.0204          | 0.9973       | 0.0400         |
| k=20   | 0.0432          | 0.9970       | 0.0826         |
| k=50   | 0.1113          | 0.9346       | 0.1981         |

Honest note: synthetic graphs have uniform link probability; real mesh graphs
show higher variation due to semantic linking.

### Deliverables
- [x] Run the bench against the real mesh and a synthetic baseline.
- [x] Publish `topology_score` numbers at 2–3 context budgets (small / medium / large).
- [x] Document the reproduction command in README.

### Acceptance criteria
- [x] Numbers are real and reproducible from a clean checkout.
- [x] README gains a "subgraph completeness" section with the exact command + table.

---

## Goal 3 — Rust hot-path coverage: BM25 / full-text search

**Status: 🟦 DONE (v0.28.0, 2026-08-18)** — Rust BM25 shipped with parity + numbers.

**Outcome:** move lexical (bag-of-words) retrieval into the Rust accelerator, so
the *other* half of hybrid recall stops paying Python-level costs on large meshes.

**Published numbers (5000 docs, 50 queries, `bench/bm25_bench.py`):**
- WARM (persistent index — the realistic mesh path): **21.4×** (0.670s → 0.031s)
- ONE-SHOT (naive list-passing): 0.9× — honest note, the PyO3 corpus-conversion
  tax dominates; this is why the persistent `rust_mesh.Bm25Index` is the real path.
- Parity: max|py−rust| = 0.00, rank mismatches 0/50.

### Deliverables
- [x] `bm25_score` / `bulk_bm25` in `rust_mesh/` (pure Rust, abi3, no deps).
- [x] Wire into `neural_mesh/resonance.py` (or a lexical backend selector) with exact-parity tests.
- [x] Bench 5K/50K nodes; report the speedup honestly.

### Acceptance criteria
- [x] Parity tests: Rust BM25 produces identical ranked hits to Python lexical.
- [x] `.so` remains abi3-portable (`ldd rust_mesh.so | grep libpython` prints nothing).
- [x] `/health` or `rust-info` reports the new coverage.

---

## Goal 4 — Live Helixa on-chain attestation ⚠️ GO-GATED

**Outcome:** sign and (optionally) broadcast a Helixa attestation for a mesh node.

**Gate:** **this is irreversible (on-chain, costs gas).** Do NOT proceed without
an explicit human GO. The signer is already live (`degraded:false`); this stage
is only the *policy + broadcast* step.

### Deliverables (only after GO)
🟦 Confirm wallet funding + registry address.
🟦 `scripts/erc8004_register.py --execute` for agent registration.
🟦 Attest a real node via `signer.attest_mesh_node(..., dry_run=False)`.

### Acceptance criteria
🟦 On-chain tx hash recorded + verified; node carries `helixa_stamp` with `verified=true`.

---

## Goal 5 — LongMemEval: real embedder + judge (honest re-score)

**Outcome:** replace the artifact numbers (bag-of-words substring check) with a
real `bge-small` embedder + `--judge` run so the LongMemEval row in the README
stops misleading.

**Why:** the current 0.070/0.066/0.112 numbers are *explicitly documented* as
lexical artifacts, not quality. Re-running with real embeds + a judge converts a
known-weak number into a defensible one (or an honest "we're not competitive yet").

### Acceptance criteria
🟦 Real-embedder numbers published alongside the hashed baseline.
🟦 README states plainly which is which.

---

## Cross-cutting contracts (apply to EVERY stage)

### Honest benchmark contract (non-negotiable)
🟦 Report ties as ties, include dense-wins *and* dense-loses controls, state the metric's limitation.
🟦 Resonance's weak direct-QA number is a **metric mismatch**, never a "regression".
🟦 Never report a number you didn't generate.

### Release completion gate (order matters)
1. Final security patches → rerun RED/GREEN tests → focused suites → known-baseline full regression.
2. Clean isolated package install (`uv pip install --no-deps .` from a fresh venv).
3. Benchmark → live authenticated smoke → diff/secret review.
4. Commit as **Devio** → tag `vX.Y.Z` → `git push origin master --tags`.
5. Kill stale process (3-tier pattern) → clear bytecode → restart → verify `/health` version + endpoints.
6. **X announcement is a deliverable**, not a flourish — draft <280 chars, 🟦 bullets, full URL for the OG card, verify with `xurl read`.

### Version bump — FOUR locations (real pitfall)
`neural_mesh/__init__.py` + **three** hardcoded strings in `server.py` (health,
stats, ERC-8004 manifest). After bumping, `grep -rn '"0\.' neural_mesh/__init__.py server.py`
must show exactly 4 matches, all the new version.

### Git conventions
🟦 Repo is `BasedNUKEM` (never the `D0xedDev` org).
🟦 Commit author `Devio <basednukem@users.noreply.github.com>`.
🟦 Tag + push every shipped milestone.

---

## Priority order & dependencies

| # | Goal | Blocked by | Irreversible? | Status |
|---|------|-----------|---------------|--------|
| 1 | E2E LLM-judged LoCoMo QA | none (Nous portal path) | no | 🟦 DONE (v0.27.x, Nous model path) |
| 2 | Subgraph completeness | none | no | 🟦 DONE (v0.28.0) |
| 3 | Rust BM25 | none | no | 🟦 DONE (v0.28.0) |
| 4 | Helixa on-chain attestation | **human GO** | **yes** | ⚠️ GO-GATED |
| 5 | LongMemEval re-score | `fastembed` + key | no | next |

**Recommended execution order:** 1 → 2 → 3 (all non-irreversible, bundle in
parallel), then 5, then pause for GO on 4. Verify every irreversibility
on-chain before broadcasting.

---

## Risk register

🟦 **Model-slug drift:** OpenRouter deprecates free slugs and some hosted slugs
return empty content. Always `scripts/llm_probe.py` before a judge run.
🟦 **Funding / 402 gate:** the OpenRouter account is over its grant (`usage $10.20 >
credits $10.00`). Real answer/judge calls return 402 even with a valid key + slug.
Top up before any LLM-dependent goal; verify with `GET /v1/credits` first.
🟦 **Key rot:** local `D0XEDDEV/.env` + `plugins/D0xeddev/.env` carry truncated
9–10-char keys (401). The live key is `.env.d0xeddev_populated` (73 chars) or the
VPS parent env; never commit it.
🟦 **Restarts lie:** a stale PID serves old bytecode. Always `curl /health` for
the expected version after restart.
🟦 **Disk:** `/opt/data` can hit 100%; `df -h` before write-heavy ops, purge
`*.log.[2-9]` / `git gc` / `pip cache purge` if low.
