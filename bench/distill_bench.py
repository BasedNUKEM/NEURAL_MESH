"""LoRA-ready distillation benchmark.

Proves the sleep -> distill -> LoRA-dataset pipeline produces valid, weighted
training data:
  1. build a mesh with high/low trust nodes + a procedural + a stale (superseded)
  2. sleep() (prune weak) then distill() with min_trust filter
  3. assert: stale node excluded, low-trust excluded, corroborated gets higher
     weight than single-agent, JSONL parses, HF format valid.

Run:
    PYTHONPATH=. python bench/distill_bench.py
"""
from __future__ import annotations

import json
import tempfile

from neural_mesh import Mesh, MemoryType, write_jsonl, write_hf_jsonl, summarize


def main():
    m = Mesh(":memory:")
    # high-trust corroborated (fused via two adds? simulate by agent_id tag)
    m.add("Deploy with: git push && vercel --prod", MemoryType.PROCEDURAL,
          agent_id="atlas+scout", trust=0.95, resonance=0.6)
    m.add("Postgres pool max is 20", MemoryType.SEMANTIC,
          agent_id="atlas", trust=0.9, resonance=0.5)
    # low-trust noise to be filtered out
    m.add("maybe the cache is 123s, not sure", MemoryType.SEMANTIC,
          agent_id="rogue", trust=0.2, resonance=0.4)
    # stale (superseded) — must never appear in distill
    old = m.add("Old deploy: scp to server", MemoryType.PROCEDURAL,
                agent_id="atlas", trust=0.8, resonance=0.5)
    m.add("New deploy: git push && vercel --prod", MemoryType.PROCEDURAL,
          agent_id="atlas", trust=0.9, resonance=0.6, supersedes=old.id)

    # sleep to refresh resonance + prune
    s = m.sleep()
    # distill (filter trust>=0.6, resonance>=0.1)
    d = m.distill(min_trust=0.6, min_resonance=0.1)

    pairs = d["pairs"]
    contents = [p["response"] for p in pairs]

    # validate
    checks = {}
    checks["stale_excluded"] = all("scp to server" not in c for c in contents)
    checks["lowtrust_excluded"] = all("maybe the cache" not in c for c in contents)
    checks["procedural_present"] = any("vercel --prod" in c for c in contents)
    # corroborated weight > single-agent weight
    corr = next(p for p in pairs if "atlas+scout" in p["meta"]["agent_id"])
    solo = next(p for p in pairs if p["meta"]["agent_id"] == "atlas")
    checks["corroborated_heavier"] = corr["weight"] > solo["weight"]

    # JSONL parses
    parsed = [json.loads(l) for l in d["jsonl"].splitlines() if l]
    checks["jsonl_valid"] = len(parsed) == d["count"] and all(
        "instruction" in p and "response" in p and "weight" in p for p in parsed)

    # HF format valid
    hf = tempfile.mktemp(suffix=".jsonl")
    write_hf_jsonl(m, hf, min_trust=0.6, min_resonance=0.1)
    hf_rows = [json.loads(l) for l in open(hf, encoding="utf-8").read().splitlines() if l]
    checks["hf_valid"] = all(
        set(r.keys()) == {"instruction", "input", "output"} for r in hf_rows)
    checks["hf_count_matches"] = len(hf_rows) == d["count"]

    print("LORA DISTILL BENCHMARK")
    print("=" * 60)
    print(f"sleep(): {s}")
    print(f"distill(): {summarize(m, min_trust=0.6, min_resonance=0.1)}")
    print(f"\nexamples in dataset: {d['count']}")
    for p in pairs:
        print(f"  w={p['weight']:<5} {p['meta']['type']:<10} "
              f"{p['instruction'][:40]}")
    print("\nCHECKS:")
    for k, v in checks.items():
        print(f"  {k:<24} {'PASS' if v else 'FAIL'}")

    ok = all(checks.values())
    print("\n" + "=" * 60)
    print(f"OVERALL: {'PASS' if ok else 'FAIL'}")
    return checks


if __name__ == "__main__":
    main()
