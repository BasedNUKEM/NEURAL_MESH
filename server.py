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
from neural_mesh.server_security import RateLimiter, auth_ok, origin_allowed, safe_path

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = int(os.environ.get("NEURAL_MESH_MAX_JSON_BYTES", "1048576"))

API_TOKEN = os.environ.get("NEURAL_MESH_API_TOKEN", "")
SAFE_IO_DIR = os.environ.get("NEURAL_MESH_SAFE_IO_DIR", os.path.join(os.path.dirname(__file__), "runtime"))
ALLOWED_ORIGINS = {o.strip() for o in os.environ.get("NEURAL_MESH_CORS_ORIGINS", "").split(",") if o.strip()}
RATE_LIMITER = RateLimiter(
    limit=int(os.environ.get("NEURAL_MESH_RATE_LIMIT", "120")),
    window_seconds=int(os.environ.get("NEURAL_MESH_RATE_WINDOW", "60")),
)
AUTH_ENDPOINTS = {"add", "dream", "export_mesh", "merge", "stamp", "intuition_ingest_receipts"}
POLICY_FIELDS = {"trust", "cap_trust", "allow_new", "allow_merge"}


def _json_error(message: str, status: int):
    return jsonify({"ok": False, "error": message}), status


@app.before_request
def harden_request():
    if not RATE_LIMITER.allow(request.remote_addr or "local"):
        return _json_error("rate limit exceeded", 429)
    if request.method in {"POST", "PUT", "PATCH"} and request.is_json is False:
        return _json_error("JSON body required", 415)
    if request.endpoint in AUTH_ENDPOINTS and not auth_ok(request.headers, API_TOKEN):
        return _json_error("authorization required", 401)
    origin = request.headers.get("Origin", "")
    if ALLOWED_ORIGINS and not origin_allowed(origin, ALLOWED_ORIGINS):
        return _json_error("origin not allowed", 403)


@app.after_request
def harden_response(resp):
    origin = request.headers.get("Origin", "")
    if ALLOWED_ORIGINS and origin_allowed(origin, ALLOWED_ORIGINS):
        resp.headers["Access-Control-Allow-Origin"] = origin
        resp.headers["Vary"] = "Origin"
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    return resp

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
        "version": "0.15.0",
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
        try:
            from neural_mesh.muse import llm_muse
            # Quick test to see if LLM is reachable
            import os
            if not os.environ.get("OPENROUTER_API_KEY"):
                print("[WARN] LLM muse requested but OPENROUTER_API_KEY not set — falling back to template", flush=True)
            else:
                muse_fn = llm_muse
        except Exception as e:
            print(f"[WARN] LLM muse init failed: {e} — falling back to template", flush=True)

    from neural_mesh.dream import dream as run_dream
    report = run_dream(mesh, muse_fn=muse_fn)
    if muse_mode == "llm" and muse_fn is None:
        report["muse_fallback"] = "template (LLM unavailable)"
    return jsonify(report)

# ─── Sharing ───────────────────────────────────────────────────────────────

@app.route("/mesh/export", methods=["POST"])
def export_mesh():
    """Export mesh to .mesh JSONL. Body: {path?}"""
    data = request.get_json() or {}
    try:
        path = safe_path(SAFE_IO_DIR, data.get("path", "exports/mesh_export.mesh"))
    except ValueError as e:
        return _json_error(str(e), 400)
    from neural_mesh.meshfile import export_mesh as em
    em(mesh, path)
    return jsonify({"path": path, "ok": True})

@app.route("/mesh/merge", methods=["POST"])
def merge():
    """Merge peer mesh. Body: {path, policy?{min_trust, max_nodes, dedup_by_hash}}"""
    data = request.get_json()
    from neural_mesh.sharing import PeerPolicy, merge_peer_mesh
    raw_policy = data.get("policy", {})
    unknown = set(raw_policy) - POLICY_FIELDS
    if unknown:
        return _json_error(f"unknown policy fields: {sorted(unknown)}", 400)
    policy = PeerPolicy(**raw_policy) if raw_policy else None
    try:
        path = safe_path(SAFE_IO_DIR, data["path"])
    except (KeyError, ValueError) as e:
        return _json_error(str(e), 400)
    result = merge_peer_mesh(mesh, path, policy=policy)
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
        "version": "0.15.0",
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

@app.route("/mesh/recall-proof", methods=["POST"])
def recall_proof():
    """Recall memories with compact proof cards next to each hit.

    Body: {query, top_k?, mode?, alpha?}. mode = hybrid|dense|lexical|resonance.
    """
    data = request.get_json() or {}
    from neural_mesh.proof_cards import recall_with_proofs
    return jsonify(recall_with_proofs(
        mesh,
        data.get("query", ""),
        top_k=int(data.get("top_k", 5)),
        mode=data.get("mode", "hybrid"),
        alpha=float(data.get("alpha", 0.5)),
    ))

@app.route("/mesh/answer-proof", methods=["POST"])
def answer_proof():
    """Answer from recalled mesh context and attach supporting proof cards.

    Body: {query, top_k?, mode?, alpha?, reader_mode?}. mode = hybrid|dense|lexical|resonance.
    reader_mode = "extractive" (default) | "llm".
    """
    data = request.get_json() or {}
    from neural_mesh.proof_cards import answer_with_proofs
    reader_mode = data.get("reader_mode", "extractive")
    reader = None
    if reader_mode == "llm":
        try:
            from neural_mesh.reader_llm import LLMReader
            reader = LLMReader()
        except Exception:
            pass  # fall back to extractive
    return jsonify(answer_with_proofs(
        mesh,
        data.get("query", ""),
        top_k=int(data.get("top_k", 5)),
        mode=data.get("mode", "hybrid"),
        alpha=float(data.get("alpha", 0.5)),
        reader=reader,
    ))

# ─── Intuition Bridge ────────────────────────────────────────────────────

@app.route("/mesh/intuition/export", methods=["GET"])
def intuition_export():
    """Export NEURAL_MESH as Intuition Knowledge Graph Atoms + Triples."""
    from intuition_bridge import build_intuition_graph
    skills = request.args.get("skills", "")
    skills_list = [s.strip() for s in skills.split(",") if s.strip()] if skills else None
    return jsonify(build_intuition_graph(skills_list))

@app.route("/mesh/intuition/ingest-receipts", methods=["POST"])
def intuition_ingest_receipts():
    """Ingest public Intuition receipt markdown as high-trust mesh memories.

    Body: {path?: string}. Defaults to the local deployment receipt file.
    Idempotent: tx/term-derived conflict groups prevent duplicate proof nodes.
    """
    data = request.get_json() or {}
    default_path = os.path.join(os.path.dirname(__file__), "intuition-client", "INTUITION_DEPLOY_RECEIPTS.md")
    raw_path = data.get("path")
    if raw_path:
        try:
            path = safe_path(SAFE_IO_DIR, raw_path)
        except ValueError as e:
            return _json_error(str(e), 400)
    else:
        path = default_path
    from neural_mesh.onchain_provenance import ingest_intuition_receipts
    return jsonify(ingest_intuition_receipts(mesh, path))

@app.route("/eval/qa", methods=["POST"])
def eval_qa():
    """Evaluate mesh QA performance with an LLM judge.

    Body: {examples: [{query, gold}, ...], judge_model?, top_k?}
    Loads a test set into the mesh, runs recall+answer for each question,
    and scores every answer against ground truth via LLM judge.

    Returns aggregated metrics (mean, median, min, max) plus per-item scores.
    Falls back to simple keyword-overlap scoring when no LLM key is available.
    """
    import json as _json
    data = request.get_json() or {}

    examples = data.get("examples")
    if not examples or not isinstance(examples, list):
        return _json_error("required: {examples: [{query, gold}, ...]}", 400)

    from neural_mesh.eval import QAJudge, run_qa_eval
    judge_model = data.get("judge_model")
    top_k = int(data.get("top_k", 5))

    # Wire up LLM judge if env has a key (same detection as LLMReader)
    judge = QAJudge(model=judge_model) if judge_model else QAJudge()

    test_set = [
        {"query": str(ex.get("query", ex.get("q", ""))),
         "gold": str(ex.get("gold", ex.get("answer", ex.get("a", ""))))}
        for ex in examples
    ]

    try:
        metrics = run_qa_eval(mesh, test_set, judge=judge, top_k=top_k)
        return jsonify(metrics)
    except Exception as exc:
        return _json_error(str(exc), 500)

@app.route("/helixa/signer-status", methods=["GET"])
def helixa_signer_status():
    """Report the Helixa signer status without exposing the key."""
    from neural_mesh.integrations.helixa_signer import HelixaSigner, HELIXA_AGENT_ID
    try:
        signer = HelixaSigner()
        return jsonify({
            "ok": True,
            "address": signer.address,
            "agent_id": HELIXA_AGENT_ID,
            "note": "Signer loaded. Use POST /helixa/attest-node for attestation (dry_run=true by default).",
        })
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)})

@app.route("/helixa/attest-node", methods=["POST"])
def helixa_attest_node():
    """Sign a mesh node attestation with the live Helixa agent wallet.

    Body: {node_id, dry_run? default=true, aura_score?}

    dry_run=false COMMITS a real signature from the agent wallet.
    The private key is NEVER returned — only the signature + tx hash.
    """
    data = request.get_json() or {}
    node_id = data.get("node_id", "")
    if not node_id:
        return _json_error("required: {node_id}", 400)

    dry_run = data.get("dry_run", True)
    aura_score = float(data.get("aura_score", 0.0))

    from neural_mesh.integrations.helixa_signer import HelixaSigner
    try:
        signer = HelixaSigner()
        result = signer.attest_mesh_node(mesh, node_id, dry_run=dry_run, aura_score=aura_score)
        return jsonify(result)
    except Exception as exc:
        return _json_error(str(exc), 500)

# ─── Server ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Source env vars for LLM muse (OpenRouter key)
    env_file = os.path.expanduser("/opt/data/.env.d0xeddev_populated")
    if os.path.exists(env_file):
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    if line.startswith("export "):
                        line = line[7:]
                    key, _, val = line.partition("=")
                    val = val.strip().strip('"').strip("'")
                    if key and val:
                        os.environ[key] = val
    app.run(host="0.0.0.0", port=4021, debug=False)
