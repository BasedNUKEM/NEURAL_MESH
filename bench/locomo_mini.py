"""LoCoMo-style mini-benchmark for NEURAL_MESH.

Compares two retrievers on the SAME real embeddings + SAME mesh:
  * FLAT  : cosine top-k (what Mem0 / vanilla vector DB does)
  * MESH  : resonance retrieval (seed -> spread -> decay -> rank)

We measure recall@5 per LoCoMo question category and print a couple of
qualitative traces so the resonance lift is visible, not just a number.

Run:  .venv/bin/python bench/locomo_mini.py
"""
from __future__ import annotations

import os
import tempfile

from neural_mesh.core import Mesh, MemoryType
from neural_mesh.embed import cosine
from neural_mesh.embed_real import RealEmbedder

# --- a compact synthetic "LoCoMo" persona: Maya, a backend engineer ---
FACTS = [
    ("Maya joined the backend team at Acme in March 2024.", MemoryType.EPISODIC),
    ("Maya moved from Berlin to Lisbon in June 2024.", MemoryType.EPISODIC),
    ("Maya's cat Pixel got sick in September 2024.", MemoryType.EPISODIC),
    ("Maya presented at PyCon in April 2025.", MemoryType.EPISODIC),
    ("Maya switched from Vim to Neovim in January 2025.", MemoryType.EPISODIC),
    ("Maya prefers typed languages like Rust and TypeScript.", MemoryType.SEMANTIC),
    ("Maya is allergic to shellfish.", MemoryType.SEMANTIC),
    ("Maya's favorite cuisine is Thai food.", MemoryType.SEMANTIC),
    ("Maya leads the payments squad at Acme.", MemoryType.SEMANTIC),
    ("To run the Acme test suite use: poetry run pytest -n auto.", MemoryType.PROCEDURAL),
    ("Acme production deploys require the release captain's approval.", MemoryType.PROCEDURAL),
    ("Maya has a dentist appointment this Friday.", MemoryType.PROSPECTIVE),
    ("Maya plans to renew her passport before the Lisbon trip.", MemoryType.PROSPECTIVE),
    ("Maya's dog Rex loves the riverside park in Lisbon.", MemoryType.EPISODIC),
]

# question, gold_fact_index (into FACTS), category
QUESTIONS = [
    ("What languages does Maya prefer to code in?", [5], "single-hop"),
    ("When did Maya relocate to Lisbon?", [1], "single-hop"),
    ("What food must we never cook for Maya?", [6], "single-hop"),
    ("Who leads the payments squad and what do they like to build with?", [8, 5], "multi-hop"),
    ("Which city was Maya living in when she presented at PyCon?", [1, 3], "multi-hop+temporal"),
    ("What did Maya do after switching to Neovim?", [4, 3], "temporal"),
    ("Where was Maya based before moving to Lisbon?", [1, 0], "temporal"),
    ("What pet does Maya have in Lisbon?", [13, 2], "multi-hop"),
    ("How do I run the Acme tests before a deploy?", [9, 10], "multi-hop"),
    ("What's Maya's schedule this week?", [11, 12], "open-domain"),
    ("Is Maya a Vim or Neovim user now?", [4], "single-hop"),
    ("What cuisine should I pick for Maya's team dinner?", [7], "open-domain"),
]


def flat_rank(mesh: Mesh, q: str, k: int = 5):
    qe = mesh.embedder(q)
    nodes = mesh._load()
    scored = [(cosine(qe, n.embedding), n) for n in nodes.values() if not n.superseded_by]
    scored.sort(key=lambda x: -x[0])
    return [n for _, n in scored[:k]]


def main():
    tmp = tempfile.mkdtemp()
    mesh = Mesh(db_path=os.path.join(tmp, "bench.db"), embedder=RealEmbedder())

    print("[*] indexing", len(FACTS), "facts with real embeddings (bge-small)...")
    ids = []
    for content, mtype in FACTS:
        ids.append(mesh.add(content, mtype, provenance="locomo").id)

    k = 5
    cats = {}
    flat_hits = mesh_hits = 0
    flat_per_cat = {}
    mesh_per_cat = {}

    for q, gold_idx, cat in QUESTIONS:
        gold = {ids[i] for i in gold_idx}
        fr = flat_rank(mesh, q, k)
        mr = mesh.recall(q, top_k=k)
        fhit = any(n.id in gold for n in fr)
        mhit = any(n.id in gold for n in mr)
        flat_hits += fhit
        mesh_hits += mhit
        cats.setdefault(cat, [0, 0])
        cats[cat][0] += fhit
        cats[cat][1] += mhit

        # qualitative: show a node resonance surfaced that flat missed
        flat_ids = {n.id for n in fr}
        mesh_ids = {n.id for n in mr}
        extra = mesh_ids - flat_ids
        if extra and not mhit == fhit:  # interesting when sets differ in gold coverage
            pass

    n = len(QUESTIONS)
    print("\n" + "=" * 64)
    print(f"LoCoMo-mini  recall@{k}   (n={n})")
    print("=" * 64)
    print(f"  FLAT cosine : {flat_hits}/{n}  = {100*flat_hits/n:5.1f}%")
    print(f"  MESH resonance: {mesh_hits}/{n}  = {100*mesh_hits/n:5.1f}%")
    print("-" * 64)
    print("  by category:")
    for cat, (f, mh) in cats.items():
        tot = sum(1 for _, _, c in QUESTIONS if c == cat)
        print(f"    {cat:22s} flat {f}/{tot}  mesh {mh}/{tot}")
    print("=" * 64)

    # qualitative trace: a multi-hop question
    print("\n  qualitative trace — 'Who leads the payments squad and what do they")
    print("  like to build with?'")
    fr = flat_rank(mesh, QUESTIONS[3][0], k)
    mr = mesh.recall(QUESTIONS[3][0], top_k=k)
    print("    FLAT top-5:")
    for n in fr:
        print(f"      - [{n.type.value}] {n.content[:55]}")
    print("    MESH top-5:")
    for n in mr:
        print(f"      - [{n.type.value}] {n.content[:55]}")


if __name__ == "__main__":
    main()
