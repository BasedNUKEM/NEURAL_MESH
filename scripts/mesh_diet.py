#!/usr/bin/env python3
"""mesh_diet.py — One-shot dream-muse node cleanup (v0.26.0).

Supersedes redundant dream-muse nodes from pre-v0.26.0 DREAM cycles.
Does NOT delete data — marks old summaries as superseded-by the newest
per provenance cluster. The echo-chamber guard (provenance-diversity
filter) then prevents them from re-entering the muse.

Dry-run: python3 scripts/mesh_diet.py --dry-run
Execute: python3 scripts/mesh_diet.py  (backup auto-created)

Goal: bring dream-muse share from ~74% (328/441) down to < 35%.
"""
import argparse
import shutil
import sys
import time
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from neural_mesh import Mesh

DREAM_PROVENANCE = "dream-muse"
DREAM_AUTHOR = "dream"


def diet(db_path: Path, dry_run: bool = True):
    if not db_path.exists():
        print(f"ERROR: mesh db not found at {db_path}", file=sys.stderr)
        return 1

    # Backup
    bak = db_path.with_suffix(f".db.bak-{int(time.time())}")
    shutil.copy2(db_path, bak)
    print(f"Backup: {bak}")

    mesh = Mesh(str(db_path))
    nodes = mesh._load()
    before_total = len(nodes)

    # Group dream-muse nodes by content prefix (same provenance cluster)
    dream_nodes = [n for n in nodes.values()
                   if (n.provenance or "") == DREAM_PROVENANCE
                   and not n.superseded_by]
    before_dream = len(dream_nodes)

    by_cluster: dict[str, list] = defaultdict(list)
    ungrouped_by_prefix: dict[str, list] = defaultdict(list)
    for n in dream_nodes:
        content = n.content or ""
        if "cluster" in content:
            # "[dream summary] <prov> cluster ..."
            tag = content.split(" cluster")[0]
            by_cluster[tag].append(n)
        elif content.startswith("[dream bridge]"):
            by_cluster["[dream bridge]"].append(n)
        elif content.startswith("[dream leaderboard]"):
            by_cluster["[dream leaderboard]"].append(n)
        else:
            # One-off LLM musings — group by content prefix to catch true
            # duplicates, but keep unique insights (don't cull one-offs).
            prefix = content[:80].strip()
            ungrouped_by_prefix[prefix].append(n)

    superseded = 0
    for tag, group in by_cluster.items():
        # Keep the newest (highest created_at), supersede the rest
        group.sort(key=lambda n: n.created_at or 0, reverse=True)
        for old in group[1:]:
            if dry_run:
                print(f"  [DRY-RUN] would supersede: {old.content[:80]}...")
                superseded += 1
                continue
            old.superseded_by = f"mesh_diet-v0.26.0-{tag.split(']')[0].strip('[')}"
            mesh._save(old)
            superseded += 1

    # For ungrouped one-offs: only supersede TRUE duplicates (same prefix)
    for prefix, group in ungrouped_by_prefix.items():
        if len(group) <= 1:
            continue  # unique insight — keep it
        group.sort(key=lambda n: n.created_at or 0, reverse=True)
        for old in group[1:]:
            if dry_run:
                print(f"  [DRY-RUN] would supersede duplicate: {old.content[:80]}...")
                superseded += 1
                continue
            old.superseded_by = "mesh_diet-v0.26.0-llm-dup"
            mesh._save(old)
            superseded += 1

    if dry_run:
        print(f"\nDRY-RUN: would supersede {superseded} of {before_dream} dream-muse nodes")
        print(f"Would reduce dream-muse from {before_dream} → {before_dream - superseded} active")
        kept = before_dream - superseded
        kept_pct = kept / before_total * 100 if before_total else 0
        print(f"Post-diet dream-muse share: ~{kept_pct:.1f}% (target <35%)")
    else:
        # Verify
        mesh2 = Mesh(str(db_path))
        nodes2 = mesh2._load()
        after_dream = sum(1 for n in nodes2.values()
                          if (n.provenance or "") == DREAM_PROVENANCE
                          and not n.superseded_by)
        after_total = len(nodes2)
        pct = after_dream / after_total * 100 if after_total else 0
        print(f"DIET COMPLETE: {after_dream} active dream-muse ({pct:.1f}%) "
              f"← was {before_dream} ({before_dream/before_total*100:.1f}%)")
        print(f"Superseded {superseded} nodes. Backup: {bak}")
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="One-shot dream-muse node cleanup")
    p.add_argument("--dry-run", action="store_true",
                   help="Preview changes without applying")
    p.add_argument("--db", default=None,
                   help="Path to mesh.db (default: ../mesh.db relative to script)")
    args = p.parse_args()

    db_path = Path(args.db) if args.db else HERE.parent / "mesh.db"
    sys.exit(diet(db_path, dry_run=args.dry_run))
