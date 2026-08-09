#!/usr/bin/env python3
"""Real-world feed ingestor for NEURAL_MESH (v0.26.0+).

Reads x402 economy, paraswarm events, Hermes session digests, and
X post echo from D0XEDDEV data files and ingests them as trusted mesh
nodes. Designed for cron-driven daily runs.

Usage:
  PYTHONPATH=. python3 scripts/ingest_real_feeds.py --mesh mesh.db --all
  PYTHONPATH=. python3 scripts/ingest_real_feeds.py --mesh mesh.db --x402 --dry-run
  PYTHONPATH=. python3 scripts/ingest_real_feeds.py --mesh mesh.db --session-digest --limit 1000

Feeds:
  x402      — economy/payment data from data/x402-economy.json
  paraswarm — compute marketplace events (paraswarm page data)
  session   — Hermes session digests (this agent's work summaries)
  x-echo    — X post performance/echo data (social engine)
  all       — all of the above

Idempotent: content-hash-based dedup prevents duplicate ingest.
Trust: 0.85 (real-world app data, verified by the system's own pipelines).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from neural_mesh.core import Mesh, MemoryType
from neural_mesh.embed import embed

D0XED_DEV = Path("/opt/data/D0XEDDEV")
DEFAULT_MESH = str(ROOT / "mesh.db")
DATA_DIR = D0XED_DEV / "data"


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()[:12]


def _already_ingested(mesh: Mesh, hash_prefix: str) -> bool:
    """Check if a node with this content hash already exists (by meta)."""
    for node in mesh._load().values():
        if (node.meta or {}).get("content_hash") == hash_prefix:
            return True
    return False


def ingest_x402(mesh: Mesh, dry_run: bool = False) -> int:
    """Ingest x402 economy snapshot as a semantic node."""
    path = DATA_DIR / "x402-economy.json"
    if not path.exists():
        print(f"  x402: {path} not found — skip", file=sys.stderr)
        return 0

    with open(path) as f:
        data = json.load(f)

    # Build a compact summary
    payments = data.get("payments", 0)
    total_usdc = data.get("totalUsdc", 0)
    wallet_preview = str(data.get("wallet", ""))[:10]
    content = (
        f"[x402-economy] {payments} payments, {total_usdc} USDC total, "
        f"wallet={wallet_preview}..., "
        f"fetched={data.get('fetchedAt', '?')[:19]}"
    )

    ch = _content_hash(content)
    if _already_ingested(mesh, ch):
        print(f"  x402: already ingested — skip", file=sys.stderr)
        return 0

    if dry_run:
        print(f"  x402: [dry-run] would ingest: {content[:100]}", file=sys.stderr)
        return 0

    mesh.add(
        content,
        type=MemoryType.SEMANTIC,
        lane="cold",
        provenance="x402-economy",
        by="ingest-x402",
        trust=0.85,
        meta={
            "source": "x402-economy.json",
            "content_hash": ch,
            "ingested_at": time.time(),
            "raw_payments": payments,
            "raw_usdc": total_usdc,
        },
    )
    print(f"  x402: ingested 1 node", file=sys.stderr)
    return 1


def ingest_session_digest(mesh: Mesh, content: str, dry_run: bool = False,
                          limit_chars: int = 2000) -> int:
    """Ingest a session digest summary as a hermes-session node."""
    if not content:
        return 0

    # Truncate
    content = content[:limit_chars]
    ch = _content_hash(content)
    if _already_ingested(mesh, ch):
        print(f"  session: already ingested — skip", file=sys.stderr)
        return 0

    if dry_run:
        print(f"  session: [dry-run] would ingest: {content[:80]}...", file=sys.stderr)
        return 0

    mesh.add(
        f"[hermes-session] {content}",
        type=MemoryType.SEMANTIC,
        lane="cold",
        provenance="hermes-session",
        by="hermes-agent",
        trust=0.88,
        meta={
            "source": "hermes-session-digest",
            "content_hash": ch,
            "ingested_at": time.time(),
        },
    )
    print(f"  session: ingested 1 node", file=sys.stderr)
    return 1


def ingest_paraswarm(mesh: Mesh, dry_run: bool = False) -> int:
    """Ingest paraswarm events — currently a stub; paraswarm data is dynamic.
    When a paraswarm events log exists, this reads and ingests it."""
    path = D0XED_DEV / "paraswarm" / "events.json"
    if not path.exists():
        print(f"  paraswarm: events.json not found — skip (no data yet)", file=sys.stderr)
        return 0

    with open(path) as f:
        events = json.load(f)

    ingested = 0
    for ev in events[:20]:  # cap at 20 per run
        content = f"[paraswarm] {json.dumps(ev, sort_keys=True)}"
        ch = _content_hash(content)
        if _already_ingested(mesh, ch):
            continue
        if dry_run:
            continue
        mesh.add(
            content[:800],
            type=MemoryType.SEMANTIC,
            lane="cold",
            provenance="paraswarm",
            by="ingest-paraswarm",
            trust=0.80,
            meta={"source": "paraswarm-events", "content_hash": ch, "ingested_at": time.time()},
        )
        ingested += 1

    print(f"  paraswarm: ingested {ingested} nodes", file=sys.stderr)
    return ingested


def ingest_x_echo(mesh: Mesh, dry_run: bool = False) -> int:
    """Ingest recent X post performance as social-echo nodes."""
    # Check for posted tweets log
    path = DATA_DIR / "posted-tweets.json"
    if not path.exists():
        # Try D0XEDDEV skills data
        path = D0XED_DEV / "skills" / "social-engine" / "data" / "posted-tweets.json"
    if not path.exists():
        print(f"  x-echo: no posted-tweets.json — skip", file=sys.stderr)
        return 0

    with open(path) as f:
        tweets = json.load(f)

    if isinstance(tweets, dict):
        tweets = list(tweets.values())

    ingested = 0
    for t in tweets[-10:]:  # last 10 tweets
        tid = str(t.get("id", ""))[:8]
        txt = str(t.get("text", "") or t.get("content", ""))[:120]
        likes = t.get("likes", 0) or t.get("favorite_count", 0)
        rts = t.get("retweets", 0) or t.get("retweet_count", 0)
        content = f"[x-echo] id={tid} likes={likes} rts={rts} — {txt}"
        ch = _content_hash(content)
        if _already_ingested(mesh, ch):
            continue
        if dry_run:
            continue
        mesh.add(
            content,
            type=MemoryType.SENSORY,
            lane="hot",
            provenance="x-echo",
            by="ingest-x-echo",
            trust=0.75,
            meta={"source": "x-posted-tweets", "content_hash": ch, "ingested_at": time.time()},
        )
        ingested += 1

    print(f"  x-echo: ingested {ingested} nodes", file=sys.stderr)
    return ingested


def main():
    p = argparse.ArgumentParser(description="Real-world feed → NEURAL_MESH")
    p.add_argument("--mesh", default=DEFAULT_MESH, help="Path to mesh.db")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--all", action="store_true", help="Ingest all feeds")
    p.add_argument("--x402", action="store_true")
    p.add_argument("--paraswarm", action="store_true")
    p.add_argument("--session-digest", action="store_true", help="Ingest a session digest")
    p.add_argument("--session-content", help="Session digest content text")
    p.add_argument("--x-echo", action="store_true")
    p.add_argument("--limit", type=int, default=2000, help="Max chars per session digest")
    args = p.parse_args()

    mesh = Mesh(db_path=args.mesh, embedder=embed)
    before = mesh.stats().get("total", 0)
    total = 0

    print(f"🟦 Real-world feed ingest — mesh: {args.mesh} ({before} nodes)", file=sys.stderr)

    if args.dry_run:
        print("  [DRY-RUN MODE — no writes]", file=sys.stderr)

    if args.all or args.x402:
        total += ingest_x402(mesh, dry_run=args.dry_run)

    if args.all or args.paraswarm:
        total += ingest_paraswarm(mesh, dry_run=args.dry_run)

    if args.all or args.session_digest:
        content = args.session_content or f"Session digest {time.strftime('%Y-%m-%dT%H:%M')}"
        total += ingest_session_digest(mesh, content, dry_run=args.dry_run, limit_chars=args.limit)

    if args.all or args.x_echo:
        total += ingest_x_echo(mesh, dry_run=args.dry_run)

    after = mesh.stats().get("total", 0)
    print(f"🟦 Done: {total} nodes ingested (total: {before} → {after})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
