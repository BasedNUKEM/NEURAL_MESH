"""LoCoMo-HARD v2 — measure WHERE MESH actually wins.

Dense embeddings make recall@5 a weak discriminator (flat already ~100%).
The honest differentiators:
  * MRR + recall@k for k in {1,2,3,5}  -> low-k ranking precision
  * SUBGRAPH COVERAGE -> for multi-hop Qs, does the returned set contain the
    WHOLE linked answer cluster (resonance spreads; flat returns singletons)?
"""
from __future__ import annotations

import os
import tempfile

from neural_mesh.core import Mesh, MemoryType
from neural_mesh.embed import cosine
from neural_mesh.embed_real import RealEmbedder

BASE = [
    ("Maya leads the payments squad at Acme.", MemoryType.SEMANTIC),
    ("Maya prefers typed languages like Rust and TypeScript.", MemoryType.SEMANTIC),
    ("Maya moved from Berlin to Lisbon in June 2024.", MemoryType.EPISODIC),
    ("Maya presented at PyCon in April 2025 while living in Lisbon.", MemoryType.EPISODIC),
    ("Maya's cat Pixel got sick in September 2024.", MemoryType.EPISODIC),
    ("Acme production deploys require the release captain's approval.", MemoryType.PROCEDURAL),
    ("To run the Acme test suite use: poetry run pytest -n auto.", MemoryType.PROCEDURAL),
    ("Maya is allergic to shellfish.", MemoryType.SEMANTIC),
]
DISTRACTORS = [
    "Maya attended a meetup about Python web frameworks in 2023.",
    "Maya read a blog post on Rust async runtimes.",
    "Maya's colleague leads the search squad at Acme.",
    "The logistics squad at Acme ships weekly.",
    "A different engineer prefers TypeScript for frontend.",
    "Berlin has many tech meetups every month.",
    "Lisbon hosts a yearly developer conference.",
    "Maya's manager approved the Q3 roadmap.",
    "The payments API had an incident last month.",
    "A Rust service was deployed to production on Friday.",
    "Maya took a course on distributed systems.",
    "The release process at Acme uses a captain rotation.",
    "Maya mentored an intern on the backend team.",
    "TypeScript strict mode caught a bug in the build.",
    "A shellfish allergy is common among developers.",
    "PyCon has talks on testing and deployment.",
]
BRIDGE = [("As payments squad lead, Maya's team standardizes on Rust services.", MemoryType.PROCEDURAL)]
CONFLICT = [
    ("Maya used Vim as her main editor in 2023.", MemoryType.SEMANTIC),
    ("Maya switched to Neovim as her main editor in January 2025.", MemoryType.SEMANTIC),
]
FULL = BASE + [(d, MemoryType.EPISODIC) for d in DISTRACTORS] + BRIDGE + CONFLICT

# q, gold indices, multi_hop (needs whole cluster)?
QUESTIONS = [
    ("What does Maya's team build with on the payments squad?", [len(BASE)+len(DISTRACTORS)], True),
    ("What languages does Maya like to code in?", [1], False),
    ("When did Maya move to Lisbon?", [2], False),
    ("Which editor does Maya use now?", [len(BASE)+len(DISTRACTORS)+2], False),
    ("What must we avoid cooking for Maya?", [7], False),
    ("Who approves Acme production deploys?", [5], False),
    ("Where was Maya living when she presented at PyCon?", [3], False),
    ("How do I run the Acme tests?", [6], False),
    ("What pet did Maya have health trouble with?", [4], False),
    ("What team does Maya run at Acme?", [0], True),   # cluster: leads payments + builds with Rust
    ("What city was Maya in before the Lisbon move?", [2], False),
]


def flat_rank(mesh, q, k=5):
    qe = mesh.embedder(q)
    nodes = mesh._load()
    scored = [(cosine(qe, n.embedding), n) for n in nodes.values() if not n.superseded_by]
    scored.sort(key=lambda x: -x[0])
    return [n for _, n in scored[:k]]


def main():
    tmp = tempfile.mkdtemp()
    mesh = Mesh(db_path=os.path.join(tmp, "hard2.db"), embedder=RealEmbedder())
    print(f"[*] indexing {len(FULL)} facts...")
    ids = [mesh.add(c, t, provenance="hard").id for c, t in FULL]

    ks = [1, 2, 3, 5]
    flat_rec = {k: 0 for k in ks}
    mesh_rec = {k: 0 for k in ks}
    flat_mrr = mesh_mrr = 0.0
    flat_cov = mesh_cov = 0
    mh_questions = [q for q in QUESTIONS if q[2]]

    for q, gold_idx, multi in QUESTIONS:
        gold = {ids[i] for i in gold_idx}
        fr = flat_rank(mesh, q, 5)
        mr = mesh.recall(q, top_k=5)
        for k in ks:
            if any(n.id in gold for n in fr[:k]):
                flat_rec[k] += 1
            if any(n.id in gold for n in mr[:k]):
                mesh_rec[k] += 1
        # MRR (rank of first gold in each list)
        for lst, acc in ((fr, "f"), (mr, "m")):
            for rank, n in enumerate(lst, 1):
                if n.id in gold:
                    if acc == "f":
                        flat_mrr += 1.0 / rank
                    else:
                        mesh_mrr += 1.0 / rank
                    break
        # subgraph coverage for multi-hop: fraction of gold cluster present in top5
        if multi:
            flat_cov += len(gold & {n.id for n in fr[:5]}) / len(gold)
            mesh_cov += len(gold & {n.id for n in mr[:5]}) / len(gold)

    n = len(QUESTIONS)
    print("\n" + "=" * 70)
    print(f"LoCoMo-HARD v2   (n={n}, {len(mh_questions)} multi-hop)")
    print("=" * 70)
    print(f"{'metric':22s}{'FLAT':>14s}{'MESH':>14s}")
    for k in ks:
        print(f"recall@{k:<14d}{100*flat_rec[k]/n:13.1f}%{100*mesh_rec[k]/n:13.1f}%")
    print(f"{'MRR (higher=better)':22s}{flat_mrr/n:14.3f}{mesh_mrr/n:14.3f}")
    if mh_questions:
        print(f"{'multi-hop cluster cov':22s}{100*flat_cov/len(mh_questions):13.1f}%"
              f"{100*mesh_cov/len(mh_questions):13.1f}%")
    print("=" * 70)
    print("Read: MESH should lead on MRR + low-k recall (context-budget precision)")
    print("      and on multi-hop cluster coverage (subgraph completeness).")


if __name__ == "__main__":
    main()
