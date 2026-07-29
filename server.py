"""
NEURAL_MESH MCP Server — Flask REST API wrapper.
Drop-in template: copy this file to the NEURAL_MESH repo root and run.

Usage:
  cd /opt/data/NEURAL_MESH
  python3 -m venv .venv-server && .venv-server/bin/pip install flask
  .venv-server/bin/python server.py   # listens on :4021

Health check: curl http://localhost:4021/health
"""

import sys, os, sqlite3
sys.path.insert(0, os.path.dirname(__file__))

from flask import Flask, request, jsonify, send_from_directory
from neural_mesh.core import Mesh, MemoryType

app = Flask(__name__)

# Persist to a file so data survives restarts.
# Set check_same_thread=False because Flask's dev server uses threads.
DB_PATH = os.environ.get("NEURAL_MESH_DB", os.path.join(os.path.dirname(__file__), "mesh.db"))
mesh = Mesh(db_path=DB_PATH)
mesh.db = sqlite3.connect(DB_PATH, check_same_thread=False)  # Overwrite with thread-safe connection
mesh.db.row_factory = sqlite3.Row  # Critical: Mesh._load() indexes rows by column name

# ─── Health ────────────────────────────────────────────────────────────────

@app.route("/health", methods=["GET"])
def health():
    # Count nodes from the thread-safe db connection
    cur = mesh.db.execute("SELECT COUNT(*) FROM nodes")
    count = cur.fetchone()[0]
    return jsonify({
        "status": "ok",
        "nodes": count,
        "version": "0.8.0",
    })

# ─── Dashboard ─────────────────────────────────────────────────────────────

@app.route("/dashboard", methods=["GET"])
def dashboard():
    """Serve the public mesh dashboard."""
    return send_from_directory("static", "dashboard.html")

# ─── CRUD ──────────────────────────────────────────────────────────────────

@app.route("/mesh/add", methods=["POST"])
def add():
    """Body: {content, type, provenance?, supersedes?, meta?, by?}"""
    data = request.get_json()
    node = mesh.add(
        content=data["content"],
        memory_type=MemoryType(data.get("type", "semantic")),
        provenance=data.get("provenance"),
        supersedes=data.get("supersedes"),
        meta=data.get("meta"),
        by=data.get("by"),
    )
    return jsonify({"id": node.id, "content": node.content, "type": node.type.value})

@app.route("/mesh/recall", methods=["POST"])
def recall():
    """Body: {query, limit?, type_filter?, mode?} — mode: "resonance"|"dense"|"hybrid"|"lexical" """
    data = request.get_json()
    mode = data.get("mode", "resonance")
    limit = data.get("limit", 10)

    if mode == "dense":
        nodes = mesh.dense_recall(data["query"], top_k=limit)
    elif mode == "lexical":
        nodes = mesh.lexical_recall(data["query"], top_k=limit)
    elif mode == "hybrid":
        nodes = mesh.hybrid_recall(data["query"], top_k=limit, alpha=data.get("alpha", 0.9))
    else:
        nodes = mesh.recall(
            data["query"],
            limit=limit,
            type_filter=data.get("type_filter"),
        )

    return jsonify({
        "results": [
            {"id": n.id, "content": n.content, "type": n.type.value, "trust": n.trust}
            for n in nodes
        ]
    })

# ─── DREAM ─────────────────────────────────────────────────────────────────

@app.route("/mesh/dream", methods=["POST"])
def dream():
    """Run DREAM consolidation cycle. Body: {muse?: "template"|"llm"|false, options?}.

    Returns actionable report with insights, archived, reinforced counts.
    muse="template" (default) generates rule-based insights from surviving clusters.
    muse="llm" calls an LLM (requires OPENROUTER_API_KEY).
    muse=false skips insight generation.
    """
    data = request.get_json() or {}
    muse_mode = data.get("muse", "template")

    muse_fn = None
    if muse_mode == "template":
        from neural_mesh.muse import template_muse
        muse_fn = template_muse
    elif muse_mode == "llm":
        from neural_mesh.muse import llm_muse
        muse_fn = llm_muse

    from neural_mesh.dream import dream as run_dream
    report = run_dream(mesh, muse_fn=muse_fn)
    return jsonify(report)

# ─── Sharing ───────────────────────────────────────────────────────────────

@app.route("/mesh/export", methods=["POST"])
def export_mesh():
    """Export mesh to .mesh JSONL. Body: {path?}"""
    data = request.get_json() or {}
    path = data.get("path", "/tmp/mesh_export.mesh")
    from neural_mesh.meshfile import export_mesh as em
    em(mesh, path)
    return jsonify({"path": path, "ok": True})

@app.route("/mesh/merge", methods=["POST"])
def merge():
    """Merge peer mesh. Body: {path, policy?{min_trust, max_nodes, dedup_by_hash}}"""
    data = request.get_json()
    from neural_mesh.sharing import PeerPolicy, merge_peer_mesh
    policy = PeerPolicy(**data.get("policy", {})) if "policy" in data else None
    result = merge_peer_mesh(mesh, data["path"], policy=policy)
    return jsonify({"added": result.get("added", 0), "skipped": result.get("skipped", 0)})

# ─── Helixa Provenance ─────────────────────────────────────────────────────

@app.route("/mesh/stamp", methods=["POST"])
def stamp():
    """Add Helixa provenance stamp. Body: {node_id, agent_id, aura_score?, verified_handle?}"""
    data = request.get_json()
    from neural_mesh.integrations.helixa_provenance import stamp_node, HelixaStamp
    stamp_obj = HelixaStamp(
        agent_id=str(data["agent_id"]),
        aura_score=float(data.get("aura_score", 0.0)),
        source="mcp-server",
        vouched_at=__import__("time").time(),
        verified="verified" if data.get("verified_handle") else "unverified",
    )
    stamped = stamp_node(mesh=mesh, node_id=data["node_id"], stamp=stamp_obj)
    return jsonify({"stamped": stamped, "node_id": data["node_id"]})

# ─── Public Community Mesh ──────────────────────────────────────────────────

@app.route("/mesh/public", methods=["GET"])
def public_mesh():
    """Public read-only feed for community dashboard. No auth, rate-limited.
    Query params: q (search), limit (default 10, max 50)"""
    q = request.args.get("q", "")
    try:
        limit = min(int(request.args.get("limit", 10)), 50)
    except ValueError:
        limit = 10

    cur = mesh.db.execute(
        "SELECT id, content, type, meta FROM nodes ORDER BY id DESC LIMIT ?",
        (limit,)
    )
    rows = cur.fetchall()

    results = []
    import json
    for r in rows:
        content = r["content"]
        if q and q.lower() not in content.lower():
            continue
        meta = json.loads(r["meta"]) if r["meta"] else {}
        results.append({
            "id": r["id"],
            "content": content[:500],
            "type": r["type"],
            "provenance": meta.get("provenance", "unknown"),
            "by": meta.get("by", "unknown"),
            "trust": meta.get("trust", 1.0),
            "created_at": meta.get("created_at"),
            "helixa": meta.get("helixa_stamp", {}).get("agent_id") if meta.get("helixa_stamp") else None,
        })

    return jsonify({
        "total": len(results),
        "limit": limit,
        "query": q or None,
        "results": results,
    })

@app.route("/mesh/stats", methods=["GET"])
def mesh_stats():
    """Public stats for dashboard — node count, types, provenance breakdown."""
    import json
    cur = mesh.db.execute("SELECT COUNT(*) as cnt FROM nodes")
    total = cur.fetchone()["cnt"]
    cur = mesh.db.execute("SELECT meta FROM nodes")
    all_meta = [json.loads(r["meta"]) if r["meta"] else {} for r in cur.fetchall()]
    active = len([m for m in all_meta if not m.get("superseded_by")])

    prov_counts = {}
    for m in all_meta:
        src = m.get("provenance", "unknown")
        prov_counts[src] = prov_counts.get(src, 0) + 1
    provenance_breakdown = sorted(
        [{"source": k, "count": v} for k, v in prov_counts.items()],
        key=lambda x: x["count"], reverse=True
    )[:10]

    return jsonify({
        "total_nodes": total,
        "active_nodes": active,
        "consolidated": total - active,
        "version": "0.8.0",
        "provenance_breakdown": provenance_breakdown,
    })

# ─── Reader ────────────────────────────────────────────────────────────────

@app.route("/mesh/answer", methods=["POST"])
def answer():
    """Generate answer from retrieved context. Body: {query, context_chunks[], reader?}"""
    data = request.get_json()
    from neural_mesh.reader import ExtractiveReader
    reader = ExtractiveReader()
    answer = reader.answer(data["query"], data["context_chunks"])
    return jsonify({"answer": answer, "method": "extractive_proxy"})

# ─── Server ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=4021, debug=False)
