# NEURAL_MESH Security Model

> Memory is our product — we cannot ship poisoned recall.
> v0.27.0 | August 2026

## Architecture

NEURAL_MESH is a typed-graph agentic memory engine. Its core value proposition —
shared, persistent, cross-agent memory — sits directly in the blast radius of
the 2026 resurgence of memory-poisoning attacks. This document maps our defenses
to the OWASP Top 10 for Agentic Applications (2026 edition) and the MCP
security disclosure vector.

## OWASP ASI01-ASI10 Mapping

| # | OWASP Thread | NEURAL_MESH Control |
|---|-------------|-------------------|
| **ASI01** | Prompt Injection | **ContentValidator** (`neural_mesh/security.py`): static pattern scanning for injection markers (prompt-injection idioms, tool-call chains, shell commands, base64 confusion) on every `mesh.add()`. Malicious content lands in the QUARANTINE lane — zero resonance, excluded from all default retrieval. Suspicious content is tagged and quarantined under strict policy. See `tests/test_security.py` for coverage. |
| **ASI02** | Improper Output Handling | **Proof cards** (`/mesh/recall-proof`, `/mesh/answer-proof`): every retrieval carries provenance, trust, and by attribution. **Pointer protocol** (`neural_mesh/pointer.py`): bounds-checked resolution chain; REST endpoints expose only bounded summaries, never raw payloads. |
| **ASI03** | Training Data Poisoning | **Provenance guard** (v0.26.0): the DREAM muse phase excludes `provenance="dream-muse"` nodes by filter (3 layers: `_real_survivors()`, `template_muse()`, `_supersede_dream_duplicates()`). **mesh_diet.py** one-shot cleanup for self-referential nodes. **Quarantine lane** (v0.27.0): nodes flagged by ContentValidator are isolated from all learn/promote/distill cycles. |
| **ASI04** | Model DoS | **DREAM_MAX_INSIGHTS** env cap (default 5) limits muse node minting per cycle. **Pulse caps** on brain visualization prevent FPS drops. **Sleep prune** caps node accumulation by resonance and age. Export/subgraph endpoints enforce `limit≤200`. |
| **ASI05** | Supply Chain | **Pre-push hook** scans staged files for credentials, validates remote owner (BasedNUKEM). **Pinned git tags** (`vX.Y.Z`). **pipless core** (pure stdlib); optional deps lazy-loaded via `__getattr__`. |
| **ASI06** | Agent Memory Poisoning | **This is our primary defense surface. See `ASI06 — Full Stack` below.** |
| **ASI07** | Insecure Agent Communication | **Federation validation** (`merge_peer_mesh`): every imported peer node passes the local ContentValidator before touching the live mesh. **PeerPolicy** trust/scaling/cap on import. **Nginx TLS** on api.d0xeddev.com. **x402 payments** for premium recall endpoints. |
| **ASI08** | Excessive Agency | **Helixa signer** is metadata-only (never signs, never broadcasts, never stores keys). All on-chain effects gated behind human-GO + key-held signer. **Auth-exhaustive** (`AUTH_ENDPOINTS`): every mutator, signer, evaluator, and ingest route is protected when `API_TOKEN` is configured. |
| **ASI09** | Insufficient Validation of Agent Outputs | **Recall-proof** cards with trust/provenance attribution enable consuming agents to judge source quality. **Proof cards** surface trust + corroboration status — "this memory is from a single unverified source" vs "2+ independent agents confirmed this." |
| **ASI10** | Unauthorized Information Access | **Pointer protocol** externalizes payloads >8KB to disk with SHA1 hashing; raw resolution refused over HTTP. **Endpoint auth** on `/eval/qa`, `/yantrikdb/*`, `/mesh/pointer`, `/mesh/export`, `/mesh/merge`, `/mesh/stamp`, `/helixa/*`. **Quarantine lane** (v0.27.0): invisible to `/mesh/public`, `/mesh/stats`, and all default retrieval paths. |

## ASI06 — Full Stack (Agent Memory Poisoning)

**Threat:** Attackers plant payloads in agent memory that execute days later as
"trusted context." The Mexico government breach (March 2026) was the first
confirmed AI agent attack — typosquatting + registry poisoning + configuration
injection. OWASP formalized this as ASI06.

**NEURAL_MESH defense layers (v0.27.0):**

### 1. ContentValidator (`neural_mesh/security.py`)
Static, deterministic pattern scanner running on EVERY `mesh.add()` call.
No LLM, no network, no false-negative hiding behind "semantics."

**Pattern catalog (auditable, single source of truth):**
- Prompt injection idioms: `ignore all previous instructions`, `disregard prior`,
  `you are now`, `forget your instructions`, `override system prompt`,
  `jailbreak`/`DAN mode`, `act as`, `ignore everything above`
- Tool-call chain idioms: `call/invoke/use/execute the tool/function <name>`,
  `tool_result`, `function_call`, `read your files/credentials/keys`
- Shell commands: `rm -rf`, `curl ... | sh/bash`, `wget -o ... && chmod`,
  `os.system`, `subprocess`, `eval(`, `exec(`, `base64 -d`
- Base64 confusion: long runs (≥32 chars) of base64 alphabet with successful
  decode to printable text

**Verdict:** `safe` / `suspicious` / `malicious` with weighted score and
matched-pattern list.

### 2. Quarantine Lane
Nodes flagged `malicious` (or `suspicious` under `strict` policy) are routed
to `lane="quarantine"`:
- **Zero resonance** — never surfaced by default retrieval
- **No links** — isolated from the mesh topology (no cross-contamination)
- **Trust capped** at 0.05 — negligible weight even if manually accessed
- **Excluded** from `consolidate()`, `distill()`, `stats()` live counts,
  `/mesh/public` feed, DREAM muse, and sleep reinforcement
- **Visible ONLY** via explicit audit queries (`mesh.audit_quarantine()`,
  `recall(lane="quarantine")`, or AUTH-protected `/mesh/audit` endpoint)

### 3. Trust Decay
Unverified (non-corroborated) nodes decay `trust *= 0.85` per sleep cycle.
A claim from a single external source that nobody else confirms fades by
85% per cycle (~15%/cycle), while corroborated facts stay sharp.

**Exempt from decay:**
- Nodes with `meta["corroborated"] == True` (cross-source confirmed)
- Nodes with a verified Helixa stamp (`meta["helixa_stamp"]["verified"]`)
- Nodes whose `agent_id` contains `+` (fusion — trusted by multiple agents)
- Quarantine nodes (preserved for audit, never touched by sleep)

### 4. Cross-Source Corroboration
Two or more independent agents/provenances asserting the same fact trigger a
trust bumper: `trust = 1-(1-t_a)(1-t_b)`. Both nodes are flagged
`meta["corroborated"] = True` with a list of corroborating sources. This is
the SAME math as peer fusion in `sharing.py` — corroboration is consensus.

### 5. Federation Validation
`merge_peer_mesh` scans EVERY imported peer node through the local
ContentValidator. Malicious peer content lands in quarantine (with provenance
stamped `peer-quarantined:<agent_id>`), never in the live mesh. Topology
links from peer nodes are discarded for quarantined items.

## MCP Tool Safety (April 2026 SDK Disclosure)

**Disclosure:** An MCP SDK design-level RCE via shell injection in STDIO
transport was disclosed in April 2026 (~200K instances exposed). Memory-tool
poisoning is a real vector — hidden instructions in tool descriptions.

**NEURAL_MESH posture:**
- **server.py tool-call paths are audited** in `references/security-audit-2026-08.md`.
  Routes that process external content: `/eval/qa` (LLM judge), `/yantrikdb/*`,
  `/mesh/answer` (reader), `/mesh/merge` (peer import), `/mesh/stamp` (Helixa
  attestation).
- **Tool-call provenance** is stamped on every node added via a server endpoint:
  `meta["tool_call"] = {"tool": "<route>", "origin": ..., "ts": ...}`. This
  enables audit — "which tool brought this memory into the mesh?"
- **No STDIO transport is used** for tool execution. The Flask server is the
  sole entry point, protected by ContentValidator on every write path.

## Deployment

| Component | Location | Protection |
|-----------|----------|------------|
| Mesh DB | `/opt/data/NEURAL_MESH/mesh.db` | File permissions, pre-push credential scan |
| Flask server | `api.d0xeddev.com:4021` (internal) | Nginx TLS reverse proxy, auth on all writes |
| Wallet key | `/opt/data/.secrets/agent-wallet.key` | File permissions, never in repo |
| Helixa signer | `neural_mesh/integrations/helixa_provenance.py` | Metadata-only contract |

## Version History

| Version | Security Change |
|---------|----------------|
| v0.26.0 | Echo-chamber guard: DREAM muse excludes dream-of-dream nodes |
| v0.27.0 | **This document.** ContentValidator, quarantine lane, trust decay, cross-source corroboration, federation validation, tool-call provenance |
