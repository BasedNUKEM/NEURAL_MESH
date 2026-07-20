"""NEURAL_MESH core: the Mesh object.

Orchestrates storage (SQLite), embedding, auto-linking, the lane consolidation
bus, resonance retrieval, and the nightly SLEEP cycle. Pure stdlib.
"""
from __future__ import annotations

import os
import sqlite3
import time

from .embed import embed
from .node import MemoryNode, MemoryType
from .resonance import retrieve as _resonance_retrieve


class Mesh:
    def __init__(self, db_path: str = ":memory:", embedder=embed, link_threshold=0.30):
        self.db = sqlite3.connect(db_path)
        self.db.row_factory = sqlite3.Row
        self.embedder = embedder
        self.link_threshold = link_threshold
        self._init_db()

    # ---------- persistence ----------
    def _init_db(self):
        self.db.execute(
            """CREATE TABLE IF NOT EXISTS nodes (
                id TEXT PRIMARY KEY,
                type TEXT,
                content TEXT,
                embedding TEXT,         -- json list
                links TEXT,             -- json dict
                meta TEXT               -- json dict
            )"""
        )
        self.db.commit()

    def _load(self) -> dict:
        out = {}
        for row in self.db.execute("SELECT * FROM nodes"):
            r = (
                row["id"], row["type"], row["content"],
                __import__("json").loads(row["embedding"]),
                __import__("json").loads(row["links"]),
                __import__("json").loads(row["meta"]),
            )
            out[r[0]] = MemoryNode.from_row(r)
        return out

    def _save(self, node: MemoryNode):
        import json
        row = node.to_row()
        self.db.execute(
            "REPLACE INTO nodes VALUES (?,?,?,?,?,?)",
            (row[0], row[1], row[2], json.dumps(list(row[3])),
             json.dumps(row[4]), json.dumps(row[5])),
        )
        self.db.commit()

    # ---------- write ----------
    def add(self, content: str, type: MemoryType = MemoryType.SEMANTIC,
            lane: str = "hot", provenance: str = "", prospective_at: float = 0.0,
            supersedes: str = "", agent_id: str = "", trust: float = 1.0,
            conflict_group: str = "", **meta) -> MemoryNode:
        emb = self.embedder(content)
        node = MemoryNode(id="", type=type, content=content, embedding=emb,
                          lane=lane, provenance=provenance,
                          agent_id=agent_id, trust=trust,
                          conflict_group=conflict_group)
        if prospective_at:
            node.links["__prospective_at__"] = prospective_at
        self._save(node)
        if supersedes:
            self._supersede(supersedes, node)
        self._auto_link(node)
        return node

    def _supersede(self, old_id: str, new_node: MemoryNode):
        """Versioning: old fact is soft-archived, linked to its current successor.
        Retrieval skips superseded nodes, so flat search can't surface stale data."""
        old = self._load().get(old_id)
        if not old:
            return
        old.superseded_by = new_node.id
        old.links["supersedes::" + new_node.id] = 1.0
        new_node.links["superseded::" + old_id] = 1.0
        self._save(old)
        self._save(new_node)

    def _auto_link(self, node: MemoryNode):
        """Self-organizing topology: link the new node to its nearest neighbours."""
        import json
        nodes = self._load()
        for other in nodes.values():
            if other.id == node.id or other.superseded_by:
                continue
            sim = __import__("embed").cosine(node.embedding, other.embedding) \
                if False else _sim(node.embedding, other.embedding)
            if sim >= self.link_threshold:
                w = round(sim, 3)
                node.links[other.id] = w
                other.links[node.id] = w
                self._save(other)
        self._save(node)

    # ---------- consolidation bus (lane promotion/demotion) ----------
    def consolidate(self, hot_ttl: float = 86400.0, cold_threshold: int = 3):
        """Promote hot nodes that prove useful; demote stale ones to cold."""
        now = time.time()
        for node in self._load().values():
            if node.superseded_by:
                continue
            if node.lane == "hot":
                if now - node.created_at > hot_ttl:
                    if node.access_count >= cold_threshold:
                        node.lane = "cold"          # promoted to long-term
                    else:
                        # not worth keeping hot -> mark for sleep pruning
                        node.resonance = min(node.resonance, 0.1)
                self._save(node)

    # ---------- retrieval ----------
    def recall(self, query: str, top_k: int = 5):
        qe = self.embedder(query)
        nodes = self._load()
        hits = _resonance_retrieve(nodes, qe, top_k=top_k)
        for n in hits:
            n.touch()
            self._save(n)
        return hits

    # ---------- SLEEP: replay -> strengthen -> prune ----------
    def sleep(self, prune_below: float = 0.05, max_age_days: float = 30.0,
              reflect_fn=None) -> dict:
        nodes = self._load()
        now = time.time()
        pruned, promoted = 0, 0
        for n in list(nodes.values()):
            if n.superseded_by:
                continue
            age_days = (now - n.last_accessed) / 86400.0
            # resonance decays with age unless reinforced by access
            n.resonance = max(0.0, n.resonance * (0.9 ** age_days))
            # strengthen via sleep replay (re-embed to refresh the trace)
            n.resonance = max(n.resonance, _sim(n.embedding, self.embedder(n.content)))
            self._save(n)
            # prune weak / old / low-trust
            if (n.resonance < prune_below or age_days > max_age_days) and n.trust < 0.5:
                n.superseded_by = "__pruned__"
                self._save(n)
                pruned += 1
        # reflection: synthesize a new semantic insight from surviving nodes
        insights = []
        if reflect_fn:
            insights = reflect_fn([n for n in nodes.values() if not n.superseded_by])
            for ins in insights:
                self.add(ins, type=MemoryType.SEMANTIC, lane="cold",
                         provenance="sleep-reflection")
                promoted += 1
        return {"pruned": pruned, "insights": len(insights)}

    # ---------- DISTILL: LoRA-ready output ----------
    def distill(self, min_trust: float = 0.6, min_resonance: float = 0.1,
                as_pairs: bool = True) -> dict:
        """Produce a LoRA-ready distillation of the surviving mesh.

        The idea: after sleep consolidation, the mesh holds *curated* truth
        (stale pruned, high-trust kept, consensus resolved). That curated set is
        exactly the kind of clean, high-signal (instruction, response) data a
        LoRA adapter wants — instead of finetuning on raw noisy conversation
        logs, you finetune on the agent's *consolidated memory*.

        What counts:
          * high-trust + high-resonance live (non-archived) nodes
          * procedural nodes -> "how do I ...?" -> step text
          * semantic/consensus nodes -> "what is ...?" -> asserted fact
          * corroborated (agent_id has '+') get a bonus weight

        Returns a dict with `pairs` (list of {instruction, response, weight,
        meta}) and a `jsonl` string ready to write to a .jsonl LoRA file.
        """
        nodes = self._load()
        live = [n for n in nodes.values()
                if not n.superseded_by
                and n.trust >= min_trust
                and n.resonance >= min_resonance]
        pairs = []
        for n in live:
            # corroborated knowledge is worth more signal
            weight = round(n.trust * (1.0 + 0.25 * ("+" in n.agent_id)), 3)
            if n.type == MemoryType.PROCEDURAL:
                instruction = f"How do I {n.content.split(':')[0].strip().lower()}?"
                response = n.content
            elif n.type == MemoryType.SEMANTIC:
                instruction = f"What is known about: {n.content[:60]}?"
                response = n.content
            elif n.type == MemoryType.EPISODIC:
                instruction = "Recall the relevant episode."
                response = n.content
            elif n.type == MemoryType.PROSPECTIVE:
                instruction = "What should be done / remembered for later?"
                response = n.content
            else:  # SENSORY / default
                instruction = "Context:"
                response = n.content
            pairs.append({
                "instruction": instruction,
                "response": response,
                "weight": weight,
                "meta": {
                    "type": n.type.value,
                    "trust": n.trust,
                    "resonance": round(n.resonance, 3),
                    "agent_id": n.agent_id,
                    "conflict_group": n.conflict_group,
                },
            })
        # sort by weight desc so a LoRA trainer can truncate by signal
        pairs.sort(key=lambda p: -p["weight"])
        import json as _json
        jsonl = "\n".join(_json.dumps(p, ensure_ascii=False) for p in pairs)
        return {"count": len(pairs), "pairs": pairs, "jsonl": jsonl}

    # ---------- stats ----------
    def stats(self) -> dict:
        nodes = self._load()
        live = [n for n in nodes.values() if not n.superseded_by]
        by_type = {}
        for n in live:
            by_type[n.type.value] = by_type.get(n.type.value, 0) + 1
        hot = sum(1 for n in live if n.lane == "hot")
        return {"total": len(live), "by_type": by_type, "hot": hot, "cold": len(live) - hot}


def _sim(a, b) -> float:
    from .embed import cosine
    return cosine(a, b)
