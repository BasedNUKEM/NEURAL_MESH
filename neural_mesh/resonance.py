"""Resonance retrieval — the NEURAL_MESH differentiator.

Instead of flat cosine top-k, a query seeds the most similar nodes, then
activation spreads across the mesh topology to linked neighbours with decay
(HippoRAG-style hippocampal indexing). Final ranking fuses resonance x recency
x trust. This surfaces *related-but-not-obviously-similar* memories that flat
vector search misses.
"""
from __future__ import annotations

import time

from .embed import cosine


def retrieve(mesh_nodes: dict, query_embedding, top_k: int = 5,
             seed_k: int = 6, spread_steps: int = 2, decay: float = 0.5):
    # 1. Seed: nodes most similar to the query.
    seeds = []
    for n in mesh_nodes.values():
        if n.superseded_by:
            continue
        sim = cosine(query_embedding, n.embedding)
        seeds.append((n, sim))
    seeds.sort(key=lambda x: -x[1])

    # 2. Resonance field: seed similarity is the initial activation.
    resonance = {n.id: max(0.0, sim) for n, sim in seeds}

    # 3. Spread: activation flows to linked neighbours, decaying each hop.
    frontier = [n for n, _ in seeds[:max(3, seed_k)]]
    for _ in range(spread_steps):
        nxt = []
        for n in frontier:
            for nbr_id, w in n.links.items():
                nbr = mesh_nodes.get(nbr_id)
                if not nbr or nbr.superseded_by:
                    continue
                gain = resonance[n.id] * decay * w
                if gain > resonance.get(nbr_id, 0.0):
                    resonance[nbr_id] = gain
                    nxt.append(nbr)
        frontier = nxt

    # 4. Rank: resonance x recency x trust.
    now = time.time()
    scored = []
    for nid, r in resonance.items():
        n = mesh_nodes.get(nid)
        if not n:
            continue
        age_days = max(0.0, (now - n.last_accessed) / 86400.0)
        recency = 1.0 / (1.0 + age_days)          # decays over ~a day
        score = r * (0.5 + 0.5 * recency) * n.trust
        scored.append((score, n))
    scored.sort(key=lambda x: -x[0])
    return [n for _, n in scored[:top_k]]
