"""DREAM cycle — the agentic, self-consolidating memory loop.

This is where NEURAL_MESH stops being a passive store and starts behaving
like a *mind*: it revisits what it remembers, strengthens useful associations,
lets attributions (the `by` field + Helixa aura) bias what it trusts, decays
what's stale, and reflects new insight back into itself.

The cycle has 5 phases (mnemonic: DREAM):
  * **D**rift   — decay resonance on old/unaccessed nodes.
  * **R**einforce — Hebbian link strengthening for nodes co-retrieved together.
  * **E**valuate — attribution-weighted scoring; high-aura authors' nodes get a
                    retrieval/trust boost, unverified authors are discounted.
  * **A**rchive  — prune (supersede) low-resonance, low-trust, old nodes.
  * **M**use     — reflect surviving clusters into new synthesized insight nodes.

Critically, DREAM is *agentic*: it returns an actionable report describing what
it did, and `muse` can inject new memory *by* the mesh itself ("by": "dream"),
which then participates in future retrieval. The mesh literally grows new
memories about its own memories.

No network. No signing. Pure local consolidation.
"""
from __future__ import annotations

import time
from collections import defaultdict

from .embed import cosine as _cosine


def _author_weight(mesh, node) -> float:
    """Attribution-aware trust: combine node.trust with the Helixa aura weight
    of the authoring agent (read from node.meta stamp if present)."""
    w = node.trust
    stamp = node.meta.get("helixa_stamp") if node.meta else None
    if stamp and stamp.get("verified") == "verified":
        # verified high-aura author -> boost; low aura -> dampen
        aura = float(stamp.get("aura_score", 0.0))
        w *= (0.5 + 0.5 * aura)  # range 0.5..1.0 of base trust
    elif stamp and stamp.get("verified") != "verified":
        # a claimed-but-unverified stamp cannot be trusted to dominate
        w *= 0.6
    return max(0.0, min(1.0, w))


def dream(mesh, decay: float = 0.9, reinforce_k: int = 3, min_link: float = 0.05,
          prune_below: float = 0.04, max_age_days: float = 30.0,
          muse_fn=None, reinforce: bool = True) -> dict:
    """Run one full DREAM consolidation pass over the live mesh.

    Returns a report dict with counts and the list of newly-minted insights.
    """
    nodes = mesh._load()
    now = time.time()
    report = {
        "drifted": 0, "reinforced": 0, "archived": 0,
        "author_boosted": 0, "insights": [],
    }
    live = [n for n in nodes.values() if not n.superseded_by]

    # D — Drift: age-based resonance decay
    for n in live:
        age_days = max(0.0, (now - n.last_accessed) / 86400.0)
        n.resonance = max(0.0, n.resonance * (decay ** age_days))
        report["drifted"] += 1
        mesh._save(n)

    # E — Evaluate: attribution-weighted trust recompute
    for n in live:
        w = _author_weight(mesh, n)
        # fold author weight into effective trust used downstream
        n.meta = dict(getattr(n, "meta", {}) or {})
        n.meta["author_weight"] = round(w, 3)
        if w > n.trust:
            report["author_boosted"] += 1
        mesh._save(n)

    # R — Reinforce: Hebbian co-retrieval link strengthening
    if reinforce:
        # replay each node as a query, find its top-k nearest; bump their link
        for n in live:
            qe = n.embedding
            scored = sorted(
                ((_cosine(qe, o.embedding), o) for o in live if o.id != n.id),
                key=lambda x: -x[0],
            )[:reinforce_k]
            for sim, o in scored:
                if sim <= 0.0:
                    continue
                key = o.id
                new = min(1.0, n.links.get(key, 0.0) + 0.1 * max(0.0, sim))
                n.links[key] = round(new, 3)
                o.links[n.id] = round(min(1.0, o.links.get(n.id, 0.0) + 0.1 * max(0.0, sim)), 3)
                report["reinforced"] += 1
                mesh._save(o)
            mesh._save(n)

    # A — Archive: prune weak/old/low-trust (and unverified-author) nodes
    for n in live:
        if n.superseded_by:
            continue
        age_days = max(0.0, (now - n.last_accessed) / 86400.0)
        aw = n.meta.get("author_weight", n.trust) if n.meta else n.trust
        if (n.resonance < prune_below or age_days > max_age_days) and aw < 0.5:
            n.superseded_by = "__pruned__"
            mesh._save(n)
            report["archived"] += 1

    # M — Muse: synthesize insights from surviving clusters
    if muse_fn:
        survivors = [n for n in nodes.values()
                     if not n.superseded_by and n.resonance >= prune_below]
        for ins in muse_fn(survivors):
            node = mesh.add(ins, type=__import__("neural_mesh.node", fromlist=["MemoryType"]).MemoryType.SEMANTIC,
                            lane="cold", provenance="dream-muse", by="dream", trust=0.85)
            report["insights"].append(node.content)

    return report


def recall_associative(mesh, query: str, top_k: int = 5, hops: int = 2,
                       seed_k: int = 6, decay: float = 0.5,
                       lane: "str | None" = None) -> list:
    """Multi-hop associative recall.

    Unlike flat dense (which only returns nodes literally similar to the query),
    this seeds from the query, then *walks the link topology* `hops` times.
    This is where resonance/spreading activation earns its keep: a vague or
    partial query that doesn't lexically/semantically match the answer node can
    still *reach* it via a chain of associations.

    Returns ranked nodes (with provenance `by` preserved) — the honest way to
    show associative recall beating dense on path-reliant queries.
    """
    qe = mesh.embedder(query)
    if lane not in (None, "hot", "cold"):
        raise ValueError("lane must be 'hot', 'cold', or None")
    nodes = {n.id: n for n in mesh._load().values()
             if not n.superseded_by and (lane is None or n.lane == lane)}
    # seed
    seeds = sorted(
        ((_cosine(qe, n.embedding), n) for n in nodes.values()),
        key=lambda x: -x[0],
    )
    score = {n.id: max(0.0, s) for s, n in seeds}
    frontier = [n for _, n in seeds[:max(3, seed_k)]]
    for _ in range(max(1, hops)):
        nxt = []
        for n in frontier:
            for nbr_id, w in n.links.items():
                nbr = nodes.get(nbr_id)
                if not nbr or nbr.superseded_by:
                    continue
                gain = score.get(n.id, 0.0) * decay * w
                if gain > score.get(nbr_id, 0.0):
                    score[nbr_id] = gain
                    nxt.append(nbr)
        frontier = nxt
    ranked = sorted(
        (sc for sc in score.items() if sc[1] > 0.0),
        key=lambda x: -x[1],
    )
    return [nodes[i] for i, _ in ranked[:top_k]]


def dream_preview(mesh, decay: float = 0.9, reinforce_k: int = 3,
                  min_link: float = 0.05, prune_below: float = 0.04,
                  max_age_days: float = 30.0, muse_fn=None,
                  reinforce: bool = True) -> dict:
    """Dry-run DREAM consolidation — returns what WOULD happen, no writes.

    Deep-copies the live node dict internally, simulates every phase on the
    copies, and returns a report with affected node IDs + candidate insight
    texts.  The production mesh is never mutated.

    Returns:
      {
        "drifted_ids": [...],      # ids whose resonance would decay
        "reinforced_ids": [...],   # ids that would gain Hebbian link boosts
        "archived_ids": [...],     # ids that WOULD be superseded (pruned)
        "insights": [...]          # insight texts muse_fn would produce
      }
    """
    import copy as _copy

    nodes = mesh._load()
    copies = {k: _copy.deepcopy(v) for k, v in nodes.items()}
    now = time.time()

    drifted_ids, reinforced_ids, archived_ids = [], [], []
    insights = []
    live = [n for n in copies.values() if not n.superseded_by]

    # D — Drift (simulate on copies)
    for n in live:
        age_days = max(0.0, (now - n.last_accessed) / 86400.0)
        new_r = max(0.0, n.resonance * (decay ** age_days))
        if new_r < n.resonance - 0.001:
            drifted_ids.append(n.id)
        n.resonance = new_r

    # E — Evaluate (attribution weighting — reads stamps, no mutation)
    for n in live:
        w = _author_weight(mesh, n)
        n.meta = dict(getattr(n, "meta", {}) or {})
        n.meta["author_weight"] = round(w, 3)

    # R — Reinforce candidates (count per-node boost events)
    link_boost = defaultdict(int)
    if reinforce:
        from .embed import cosine as _cos
        for n in live:
            qe = getattr(n, "embedding", None)
            if qe is None:
                continue
            scored = sorted(
                ((_cos(qe, o.embedding), o) for o in live if o.id != n.id),
                key=lambda x: -x[0],
            )[:reinforce_k]
            for sim, o in scored:
                if sim <= 0.0:
                    continue
                link_boost[o.id] += 1

    reinforced_ids = sorted(
        {i for i, c in link_boost.items() if c >= 2}
        or list(link_boost.keys())[:10]
    )

    # A — Archive candidates
    for n in live:
        if n.superseded_by:
            continue
        age_days = max(0.0, (now - n.last_accessed) / 86400.0)
        aw = n.meta.get("author_weight", n.trust) if n.meta else n.trust
        if (n.resonance < prune_below or age_days > max_age_days) and aw < 0.5:
            archived_ids.append(n.id)

    # M — Muse insights (run on copies — muse_fn only reads, returns strings)
    if muse_fn:
        survivors = [n for n in copies.values()
                     if not n.superseded_by and n.resonance >= prune_below]
        insights = muse_fn(survivors)

    return {
        "drifted_ids": drifted_ids,
        "reinforced_ids": reinforced_ids,
        "archived_ids": archived_ids,
        "insights": insights,
    }
