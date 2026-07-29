"""
NEURAL_MESH muse functions — generate insights from surviving dream clusters.

Muse functions receive `survivors: list[MemoryNode]` and yield insight strings.
Each insight becomes a new `by="dream"` node (trust=0.85, lane="cold") in the mesh.

Usage:
    from neural_mesh.muse import template_muse, llm_muse
    mesh.dream(muse_fn=template_muse)
"""
import os
import json
from collections import Counter

def template_muse(survivors: list, min_cluster: int = 3) -> list[str]:
    """Rule-based muse: group survivors by provenance, extract topical patterns.

    Produces:
    1. A provenance-summary node per cluster with >= min_cluster members
    2. A cross-cluster bridge node if multiple provenance clusters exist
    """
    insights = []

    # Cluster by provenance
    clusters: dict[str, list] = {}
    for n in survivors:
        prov = getattr(n, 'provenance', 'unknown') or 'unknown'
        clusters.setdefault(prov, []).append(n)

    # Per-cluster summary
    for prov, nodes in clusters.items():
        if len(nodes) < min_cluster:
            continue
        # Extract top terms
        words = Counter()
        for n in nodes:
            for w in n.content.lower().split():
                if len(w) > 3 and w not in ('this', 'that', 'with', 'from', 'have', 'been', 'were', 'they', 'their', 'about', 'which'):
                    words[w] += 1
        top_terms = [w for w, _ in words.most_common(5)]
        total_trust = sum(n.trust for n in nodes) / len(nodes)

        insights.append(
            f"[dream summary] {prov} cluster ({len(nodes)} memories, "
            f"avg trust {total_trust:.2f}): key topics — {', '.join(top_terms)}"
        )

    # Cross-cluster bridge
    if len(clusters) >= 2:
        prov_names = list(clusters.keys())
        insights.append(
            f"[dream bridge] {len(clusters)} provenance clusters survived pruning: "
            f"{', '.join(prov_names[:5])}. "
            f"Total survivor count: {len(survivors)}"
        )

    # Resonance leaderboard
    top_res = sorted(survivors, key=lambda n: n.resonance, reverse=True)[:3]
    if top_res:
        insights.append(
            f"[dream leaderboard] top resonance: "
            + " | ".join(f"{n.content[:80]}... (r={n.resonance:.3f})" for n in top_res)
        )

    return insights


def llm_muse(survivors: list, model: str = None, min_cluster: int = 3) -> list[str]:
    """LLM-powered muse: call an LLM to synthesize insights from survivors.

    Requires OPENROUTER_API_KEY or OPENAI_API_KEY in environment.
    Falls back to template_muse if no API key or LLM call fails.
    """
    import urllib.request

    api_key = os.environ.get('OPENROUTER_API_KEY') or os.environ.get('OPENAI_API_KEY')
    if not api_key:
        return template_muse(survivors, min_cluster=min_cluster)

    # Build prompt from survivors
    survivor_texts = []
    for n in survivors[:20]:  # Cap at 20 for token budget
        prov = getattr(n, 'provenance', '?') or '?'
        survivor_texts.append(f"[{prov}] (trust={n.trust:.2f}) {n.content[:200]}")

    prompt = (
        "You are NEURAL_MESH's dream muse. Given these surviving memories after pruning, "
        "generate 2-4 concise insight nodes (1-2 sentences each) that synthesize patterns, "
        "contradictions, or new knowledge. Be specific and factual.\n\n"
        "SURVIVORS:\n" + "\n".join(survivor_texts) + "\n\n"
        "INSIGHTS (one per line, no numbering):"
    )

    model = model or os.environ.get('NEURAL_MESH_LLM', 'deepseek/deepseek-v4-flash')
    base_url = os.environ.get('OPENROUTER_BASE', 'https://openrouter.ai/api/v1')

    try:
        req = urllib.request.Request(
            f"{base_url}/chat/completions",
            data=json.dumps({
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 300,
                "temperature": 0.7,
            }).encode(),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read())
            content = body.get("choices", [{}])[0].get("message", {}).get("content")
            if not content:
                raise ValueError(f"Empty LLM response: {json.dumps(body)[:200]}")
            text = content.strip()
            insights = [line.strip("- •") for line in text.split("\n") if line.strip()]
            if insights:
                return insights
    except Exception as e:
        print(f"[muse] LLM call failed ({e}), falling back to template", flush=True)

    return template_muse(survivors, min_cluster=min_cluster)
