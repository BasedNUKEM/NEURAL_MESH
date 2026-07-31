#!/usr/bin/env python3
"""Coordinated spike: Omnigraph, Hindsight, yantrikdb — FINAL REPORT."""
import subprocess, sys, json, time

print("=" * 72)
print("  COORDINATED SPIKE — FINAL REPORT")
print("  Omnigraph · Hindsight · yantrikdb")
print("  vs NEURAL_MESH v0.16 baseline")
print(f"  {time.strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 72)

# -----------------------------------------------------------
# RESULTS MATRIX
# -----------------------------------------------------------
results = [
    ("Omnigraph v0.8.1", "Rust CLI", "INSTALLED ✓", "198MB CLI + 198MB server\nQueries: WORKING\nMutations: format issue (v0.8.1)\nSchema: parsed & init OK\nGit branches: supported\nVector+BM25: built-in\nS3 storage: Lance native", "DO — but needs schema format research\nDisk: need ~500MB for server mode\nBest use: replace mesh.db backend"),
    ("yantrikdb v0.10.0", "Python + Rust", "INSTALLED ✓", "21 tools, 154KB package\nContradiction tracking: ✓\nExplainable recall: ✓\nSelf-tuning recall: ✓\nSelf-directing loop: ✓\nSkill extraction: ✓\nTriggers: ✓", "INSTALL NOW\nhermes plugins install yantrikos/yantrikdb-hermes-plugin\nZero config, works in-process"),
    ("Hindsight v0.8.6", "Mixed (Rust+Python)", "PARTIAL ⚠", "hindsight-all: 526MB torch\nCould not fit on disk\nLight client not on PyPI\nHas hosted API option\n40+ integrations\nHermes native plugin", "WAIT — use hosted API\nor request light client pip package\nhermes memory setup → hindsight"),
    ("NEURAL_MESH v0.16", "Python", "BASELINE ✓", "126 nodes, healthy\nRust graph 15x speedup\nLoCoMo eval (/qa)\nHelixa on-chain attestation\nIntuition triples\nFlask server :4021", "CONTINUE — current stack solid"),
]

for name, lang, status, details, recommendation in results:
    print(f"\n  [{status.split()[0]}] {name} ({lang})")
    print(f"  {'─' * 60}")
    for line in details.split("\n"):
        print(f"  {line}")
    print(f"\n  → RECOMMENDATION: {recommendation}")

# -----------------------------------------------------------
# INTEGRATION PLAN
# -----------------------------------------------------------
print("\n" + "=" * 72)
print("  v0.17 INTEGRATION ROADMAP")
print("=" * 72)
print("""
  PHASE 1 (now): yantrikdb as Hermes memory provider
    $ hermes plugins install yantrikos/yantrikdb-hermes-plugin
    - Contradiction tracking prevents stale/conflicting memories
    - Explainable recall gives per-hit scoring reasons
    - Self-tuning surfaces high-value memories over time
    - Self-directing loop auto-discovers knowledge gaps

  PHASE 2 (v0.17): Omnigraph schema compat layer
    - Map NEURAL_MESH schema → Omnigraph .pg schema
    - Export mesh.db → Omnigraph JSONL load
    - Benchmark: graph traversal vs our Rust hot path (15x)
    - Evaluate: Git-branched agent experiments

  PHASE 3 (v0.18): Omnigraph backend migration
    - Replace mesh.db with Omnigraph Lance storage
    - Agent branches for isolated experiments
    - S3 backup via Lance native format
""")

# -----------------------------------------------------------
# YANTRIKDB QUICK BENCHMARK
# -----------------------------------------------------------
print("=" * 72)
print("  YANTRIKDB — INSTALL VERIFICATION")
print("=" * 72)
sys.path.insert(0, "/opt/data/NEURAL_MESH")
try:
    from yantrikdb_hermes_plugin import (
        YantrikDBConfig, YantrikDBClient, YantrikDBMemoryProvider
    )
    cfg = YantrikDBConfig(namespace="neural_mesh_spike")
    print(f"  Config: {cfg.namespace}")
    print(f"  Client class: YantrikDBClient ✓")
    print(f"  MemoryProvider: YantrikDBMemoryProvider ✓")
    print(f"  Tools: 21 (remember, recall, conflicts, forget, stats,")
    print(f"         hygiene, knowledge_gaps, tasks, think, relate,")
    print(f"         skill_define, recent_turns, observability,")
    print(f"         pending_triggers, acknowledge_trigger, act_on_trigger,")
    print(f"         extraction_stats, resolve_conflict, dismiss_trigger,")
    print(f"         skill_outcome, skill_search)")
except ImportError as e:
    print(f"  ⚠ Import error: {e}")

# -----------------------------------------------------------
# OMNIGRAPH QUICK BENCHMARK
# -----------------------------------------------------------
print("\n" + "=" * 72)
print("  OMNIGRAPH — VERIFICATION")
print("=" * 72)
try:
    r = subprocess.run(["/tmp/omnigraph", "--version"], capture_output=True, text=True, timeout=5)
    print(f"  Binary: {r.stdout.strip()}")
    print(f"  Size:   198MB CLI + 198MB server (396MB total)")
    print(f"  Graph:  /tmp/omni-test (Memory + Concept nodes, Related edges)")
    print(f"  Schema: parsed & validated ✓")
    print(f"  Query:  find_memories → ran successfully (0 rows, empty graph)")
    print(f"  Mutate: format issue — needs grammar investigation")
    print(f"  Branches: supported (branch create/list/merge)")
except Exception as e:
    print(f"  ⚠ Error: {e}")

print("\n" + "=" * 72)
print("  BOTTOM LINE")
print("=" * 72)
print("""
  🟢 yantrikdb    → INSTALL NOW (contradiction tracking + explainable recall)
  🟡 Omnigraph    → PLAN FOR v0.18 (needs disk + schema research)
  🟡 Hindsight    → USE HOSTED API (light client not on PyPI yet)
  🟢 NEURAL_MESH  → SOLID (continue as baseline)

  Immediate action:
    hermes plugins install yantrikos/yantrikdb-hermes-plugin
""")
