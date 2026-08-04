#!/usr/bin/env python3
"""Intuition Knowledge Graph ↔ NEURAL_MESH bidirectional sync.

PUSH (mesh → Intuition):  export mesh nodes as Intuition atoms + triples
                           ready for on-chain deployment via the Intuition
                           Portal or subgraph.

PULL (Intuition → mesh):  ingest Intuition atom/triple data (from a
                           deployment-receipt file or the Intuition subgraph)
                           as high-trust mesh nodes with provenance=intuition.

Usage::

    python3 scripts/intuition_sync.py push               # mesh → Intuition
    python3 scripts/intuition_sync.py pull <receipt.md>  # Intuition → mesh
    python3 scripts/intuition_sync.py status             # check both directions
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from neural_mesh.core import Mesh, MemoryType
from neural_mesh.embed import embed


DEFAULT_MESH = os.path.join(ROOT, "mesh.db")
INTUITION_RECEIPT = os.path.join(ROOT, "intuition-client",
                                 "INTUITION_DEPLOY_RECEIPTS.md")


# ── Helpers ────────────────────────────────────────────────────────────────

def _load_mesh(path: str) -> Mesh:
    if not os.path.exists(path):
        print(f"mesh not found at {path}", file=sys.stderr)
        sys.exit(1)
    return Mesh(db_path=path, embedder=embed)


def _count_nodes(mesh: Mesh, provenance: str) -> int:
    return sum(1 for n in mesh._load().values()
               if not n.superseded_by and n.provenance == provenance)


def _parse_receipt_md(path: str) -> list[dict]:
    """Very-light Intuition receipt parser.

    Expects a markdown file where atom/triple blocks are separated by
    ``` blocks or --- dividers, and each block contains JSON or key:value
    lines starting with 'term:', 'atom:', 'triple:', etc.
    """
    if not os.path.exists(path):
        print(f"receipt file not found: {path}", file=sys.stderr)
        sys.exit(1)

    with open(path) as f:
        text = f.read()

    entries = []
    for block in text.split("\n---\n"):
        block = block.strip()
        if not block:
            continue

        entry: dict = {}
        for line in block.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("```"):
                continue
            if ":" in line and not line.startswith("http"):
                key, val = line.split(":", 1)
                key = key.strip().lower()
                val = val.strip()
                if val:
                    entry[key] = val

        # Try JSON fallback
        if not entry:
            try:
                entry = json.loads(block)
            except json.JSONDecodeError:
                pass

        if entry:
            entries.append(entry)

    return entries


# ── Commands ───────────────────────────────────────────────────────────────

def cmd_push(mesh_path: str):
    """Export mesh → Intuition atoms + triples."""
    mesh = _load_mesh(mesh_path)
    print(f"🧠 mesh: {mesh_path} ({mesh.stats()['nodes']} nodes)")

    # Build atoms from distinct terms that appear in mesh
    nodes = mesh._load()
    terms: set[str] = set()
    provenance_groups: dict[str, int] = {}
    lane_groups: dict[str, int] = {}
    triples: list[dict] = []

    for n in nodes.values():
        if n.superseded_by:
            continue
        prov = n.provenance or "unknown"
        provenance_groups[prov] = provenance_groups.get(prov, 0) + 1
        lane_groups[n.lane] = lane_groups.get(n.lane, 0) + 1

        # Extract terms from content (simple words >3 chars)
        words = n.content.split()
        for w in words:
            clean = w.strip(".,;:!?\"'()[]{}").lower()
            if len(clean) > 3:
                terms.add(clean)

    # Generate triples from mesh topology
    from collections import Counter
    source_to_target = Counter()
    for n in nodes.values():
        if n.superseded_by:
            continue
        for target_id, weight in n.links.items():
            tgt = nodes.get(target_id)
            if tgt and not tgt.superseded_by:
                source_to_target[(n.provenance or "unknown",
                                  tgt.provenance or "unknown")] += 1

    for (src, tgt), count in source_to_target.most_common(20):
        triples.append({
            "subject": f"mesh:{src}",
            "predicate": "linksTo",
            "object": f"mesh:{tgt}",
            "weight": count,
        })

    output = {
        "source": "NEURAL_MESH v" + (
            __import__("neural_mesh").__version__),
        "generated_at": int(time.time()),
        "atoms": sorted(list(terms))[:100],  # top 100 distinct terms
        "atom_count": len(terms),
        "triples": triples,
        "triple_count": len(triples),
        "stats": {
            "total_nodes": mesh.stats()["nodes"],
            "provenance_groups": provenance_groups,
            "lane_groups": lane_groups,
        },
    }

    print(json.dumps(output, indent=2))
    print(f"\n🟦 {len(terms)} atoms + {len(triples)} triples ready for Intuition deploy")


def cmd_pull(mesh_path: str, receipt_path: str):
    """Ingest Intuition atoms/triples → mesh nodes."""
    mesh = _load_mesh(mesh_path)
    before = _count_nodes(mesh, "intuition")

    entries = _parse_receipt_md(receipt_path)
    ingested = 0
    skipped = 0

    for entry in entries:
        content = entry.get("term") or entry.get("triple") or entry.get("id") or ""
        if not content:
            # build a descriptor from available fields
            parts = []
            for k in ("subject", "predicate", "object", "atom", "term", "triple_name",
                      "atom_numeric_id", "term_display", "tx_hash"):
                if entry.get(k):
                    parts.append(f"{k}={entry[k]}")
            content = " | ".join(parts)
        if not content:
            skipped += 1
            continue

        try:
            node = mesh.add(
                f"[intuition] {content}",
                type=MemoryType.SEMANTIC,
                lane="cold",
                provenance="intuition",
                by="intuition-sync",
                trust=0.82,
                meta={
                    "source": "intuition",
                    "raw_entry": entry,
                    "ingested_at": time.time(),
                },
            )
            ingested += 1
        except Exception as e:
            print(f"  ⚠️ skip: {str(e)[:60]}", file=sys.stderr)
            skipped += 1

    after = _count_nodes(mesh, "intuition")
    print(f"🟦 Intuition → mesh: {ingested} ingested, {skipped} skipped")
    print(f"🟦 intuition nodes: {before} → {after} (+{after - before})")


def cmd_status(mesh_path: str):
    """Show Intuition sync status."""
    mesh = _load_mesh(mesh_path)
    intuition_count = _count_nodes(mesh, "intuition")
    print(f"🟦 Intuition nodes in mesh: {intuition_count}")
    print(f"🟦 Total mesh nodes: {mesh.stats()['nodes']}")
    if intuition_count > 0:
        print(f"🟦 Integration: ACTIVE — {intuition_count / mesh.stats()['nodes'] * 100:.1f}% of mesh")
    else:
        print("🟦 Integration: pending — run `python3 scripts/intuition_sync.py pull <receipt.md>`")


# ── CLI ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Intuition Knowledge Graph ↔ NEURAL_MESH bidirectional sync")
    sub = parser.add_subparsers(dest="command", required=True)

    push_p = sub.add_parser("push", help="Export mesh → Intuition atoms + triples")
    pull_p = sub.add_parser("pull", help="Ingest Intuition atoms/triples → mesh")
    status_p = sub.add_parser("status", help="Show Intuition sync status")

    for p in (push_p, pull_p, status_p):
        p.add_argument("--mesh", default=DEFAULT_MESH, help=f"Path to mesh.db (default: {DEFAULT_MESH})")

    pull_p.add_argument("receipt", nargs="?", default=INTUITION_RECEIPT,
                        help=f"Intuition receipt file (default: {INTUITION_RECEIPT})")

    args = parser.parse_args()

    if args.command == "push":
        cmd_push(args.mesh)
    elif args.command == "pull":
        cmd_pull(args.mesh, args.receipt)
    elif args.command == "status":
        cmd_status(args.mesh)


if __name__ == "__main__":
    main()
