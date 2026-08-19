#!/usr/bin/env python3
"""Build a representative LongMemEval sample via category-stratified seeded
sampling. The naive dataset[:N] slice is biased (it happens to be 100%
temporal-reasoning and the easy cases), which is why the 20-case retrieval
experiment's absolute MRR (0.26) was 2.6x the full-100 MRR (0.16).

This produces a sample whose category mix matches the full dataset, so
absolute metrics are trustworthy. Output is a JSON list of case indices.

Usage:
  .venv-server/bin/python bench/sample_representative.py --n 50 --seed 7 \
      --dataset data/longmemeval_oracle.json --output data/sample_repr_50.json
"""
import argparse
import json
import os
import random
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default=os.path.join(PARENT, "data", "longmemeval_oracle.json"))
    ap.add_argument("--n", type=int, default=50, help="sample size")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--output", default=os.path.join(PARENT, "data", "sample_repr_50.json"))
    args = ap.parse_args()

    with open(args.dataset) as f:
        cases = json.load(f)

    by_type = defaultdict(list)
    for i, c in enumerate(cases):
        by_type[c["question_type"]].append(i)

    rng = random.Random(args.seed)
    total = len(cases)
    chosen = []
    # Proportional allocation, then top up round-robin to hit exactly n.
    counts = Counter(c["question_type"] for c in cases)
    alloc = {t: max(1, round(n := args.n * cnt / total)) for t, cnt in counts.items()}
    for t in counts:
        pool = list(by_type[t])
        rng.shuffle(pool)
        chosen += pool[:alloc[t]]
    # Trim or top up to exactly n
    rng.shuffle(chosen)
    chosen = chosen[:args.n]
    while len(chosen) < args.n:
        # rare: add unused indices
        used = set(chosen)
        spare = [i for i in range(total) if i not in used]
        if not spare:
            break
        rng.shuffle(spare)
        chosen.append(spare.pop())

    mix = Counter(cases[i]["question_type"] for i in chosen)
    print(f"Sample size {len(chosen)} (seed={args.seed})")
    print("Category mix (sample vs full):")
    for t in sorted(counts, key=lambda x: -counts[x]):
        full_pct = 100 * counts[t] / total
        samp_pct = 100 * mix[t] / len(chosen)
        print(f"  {t:24s} sample={mix[t]:3d} ({samp_pct:4.1f}%)  full={counts[t]:3d} ({full_pct:4.1f}%)")

    with open(args.output, "w") as f:
        json.dump(sorted(chosen), f, indent=2)
    print(f"Saved {len(chosen)} indices to {args.output}")


if __name__ == "__main__":
    main()
