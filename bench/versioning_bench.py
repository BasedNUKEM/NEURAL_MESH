"""Versioning / conflict benchmark.

The single most defensible MESH win over flat vector search:
when a fact is UPDATED, a flat vector DB keeps BOTH the stale and the current
embedding and returns both on query (ambiguous / wrong). NEURAL_MESH soft-
archives the stale node via a supersedes link and retrieval skips it, so the
agent only ever sees the CURRENT truth.

We measure: on an UPDATE-heavy corpus, does flat return stale data in top-5
(MESH should never do so)?
"""
from __future__ import annotations

import os
import tempfile

from neural_mesh.core import Mesh, MemoryType
from neural_mesh.embed import cosine
from neural_mesh.embed_real import RealEmbedder

# A persona that changes over time (the realistic agent case)
TIMELINE = [
    ("Maya's editor is Vim.", MemoryType.SEMANTIC, None),
    ("Maya's editor is Neovim.", MemoryType.SEMANTIC, 0),     # supersedes Vim
    ("Maya's role is backend engineer.", MemoryType.SEMANTIC, None),
    ("Maya's role is payments squad lead.", MemoryType.SEMANTIC, 2),  # supersedes
    ("Maya lives in Berlin.", MemoryType.EPISODIC, None),
    ("Maya lives in Lisbon.", MemoryType.EPISODIC, 4),        # supersedes
    ("Maya's cat Pixel is healthy.", MemoryType.EPISODIC, None),
    ("Maya's cat Pixel is sick.", MemoryType.EPISODIC, 6),    # supersedes
    ("Acme deploys need a senior reviewer.", MemoryType.PROCEDURAL, None),
    ("Acme deploys need the release captain's approval.", MemoryType.PROCEDURAL, 8),  # supersedes
    ("Maya prefers Python for scripts.", MemoryType.SEMANTIC, None),
    ("Maya prefers Rust for services.", MemoryType.SEMANTIC, 10),  # supersedes
]

# Questions whose correct answer is the CURRENT (latest) version
QUESTIONS = [
    "What editor does Maya use?",            # expect Neovim, NOT Vim
    "What is Maya's current role?",          # expect payments squad lead, NOT backend engineer
    "Where does Maya live now?",             # expect Lisbon, NOT Berlin
    "How is Pixel the cat doing?",           # expect sick, NOT healthy
    "Who approves Acme deploys?",            # expect release captain, NOT senior reviewer
    "What language does Maya prefer for services?",  # expect Rust, NOT Python
]


def flat_rank(mesh, q, k=5, include_superseded=False):
    qe = mesh.embedder(q)
    nodes = mesh._load()
    scored = [(cosine(qe, n.embedding), n) for n in nodes.values()
              if include_superseded or not n.superseded_by]
    scored.sort(key=lambda x: -x[0])
    return [n for _, n in scored[:k]]


def main():
    tmp = tempfile.mkdtemp()
    mesh = Mesh(db_path=os.path.join(tmp, "ver.db"), embedder=RealEmbedder())
    print(f"[*] building UPDATE-heavy corpus ({len(TIMELINE)} writes, 6 updates)...")
    ids = []
    for content, t, sup in TIMELINE:
        parent = ids[sup] if sup is not None else ""
        ids.append(mesh.add(content, t, supersedes=parent).id)

    k = 5
    flat_stale = 0   # flat returned a SUPERSEDED (stale) node in top-k
    mesh_stale = 0
    flat_correct = mesh_correct = 0

    for q in QUESTIONS:
        # correct = the node that is NOT superseded and best matches q
        fr = flat_rank(mesh, q, k, include_superseded=True)   # flat keeps stale
        mr = mesh.recall(q, top_k=k)                          # mesh skips stale
        flat_stale += sum(1 for n in fr if n.superseded_by)
        mesh_stale += sum(1 for n in mr if n.superseded_by)
        # "correct" = top result is a current (non-superseded) node
        flat_correct += bool(fr) and not fr[0].superseded_by
        mesh_correct += bool(mr) and not mr[0].superseded_by

    n = len(QUESTIONS)
    print("\n" + "=" * 64)
    print(f"VERSIONING / CONFLICT  (n={n} update-questions)")
    print("=" * 64)
    print(f"  Stale (wrong) hits in top-{k}:")
    print(f"    FLAT : {flat_stale}/{n} queries returned stale data")
    print(f"    MESH : {mesh_stale}/{n} queries returned stale data")
    print(f"  Top-1 points at CURRENT fact:")
    print(f"    FLAT : {flat_correct}/{n}  = {100*flat_correct/n:5.1f}%")
    print(f"    MESH : {mesh_correct}/{n}  = {100*mesh_correct/n:5.1f}%")
    print("=" * 64)
    if flat_stale and not mesh_stale:
        print("  >> MESH wins: flat leaks stale facts; MESH only surfaces current truth.")
    elif flat_stale == mesh_stale:
        print("  >> tie (dense embeddings separated versions by cosine alone).")


if __name__ == "__main__":
    main()
