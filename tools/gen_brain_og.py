#!/usr/bin/env python3
"""Generate static/brain-og.svg — 1200x630 NEURAL_MESH social preview card.
Brain-shaped node mesh (deterministic) + wordmark + live badge.
"""
import math, random

W, H = 1200, 630
random.seed(42)

# ---- brain region: two lobes + cerebellum (union of ellipses) ----
LOBES = [(380, 290, 150, 195), (560, 290, 150, 195)]          # (cx, cy, rx, ry)
STEM   = (470, 452, 122, 52)

def in_brain(x, y):
    def inside(e):
        cx, cy, rx, ry = e
        return ((x-cx)/rx)**2 + ((y-cy)/ry)**2 <= 1.0
    return any(inside(e) for e in LOBES) or inside(STEM)

# ---- sample evenly-spread nodes inside the brain ----
nodes, tries = [], 0
while len(nodes) < 82 and tries < 20000:
    tries += 1
    x = random.uniform(210, 750); y = random.uniform(95, 505)
    if not in_brain(x, y): continue
    if all(math.hypot(x-a, y-b) > 26 for a, b in nodes):
        nodes.append((x, y))

COLORS = [  # lane -> color
    ("#22d3ee", 0.30), ("#ff6b35", 0.22), ("#4dabf7", 0.22),
    ("#9775fa", 0.14), ("#4ade80", 0.12),
]

def dist(a, b): return math.hypot(a[0]-b[0], a[1]-b[1])

# ---- edges: 2-3 nearest neighbors within radius ----
edges = set()
for i, (x, y) in enumerate(nodes):
    nb = sorted(range(len(nodes)), key=lambda j: dist(nodes[i], nodes[j]))
    for j in nb[1:4]:
        if dist(nodes[i], nodes[j]) < 78:
            edges.add((min(i, j), max(i, j)))

def esc(s): return s

svg = []
svg.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">')
svg.append('<defs>')
svg.append('''  <radialGradient id="bg" cx="38%" cy="45%" r="75%">
    <stop offset="0%" stop-color="#0d1526"/><stop offset="60%" stop-color="#080c16"/><stop offset="100%" stop-color="#05070d"/>
  </radialGradient>
  <linearGradient id="title" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0%" stop-color="#22d3ee"/><stop offset="55%" stop-color="#7dd3fc"/><stop offset="100%" stop-color="#e879f9"/>
  </linearGradient>
  <filter id="glow" x="-60%" y="-60%" width="220%" height="220%">
    <feGaussianBlur stdDeviation="6" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
  </filter>
  <filter id="soft" x="-80%" y="-80%" width="260%" height="260%">
    <feGaussianBlur stdDeviation="3" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
  </filter>
  <pattern id="dots" width="26" height="26" patternUnits="userSpaceOnUse">
    <circle cx="1.5" cy="1.5" r="1" fill="#131c30"/>
  </pattern>''')
svg.append('</defs>')
svg.append(f'<rect width="{W}" height="{H}" fill="url(#bg)"/>')
svg.append(f'<rect width="{W}" height="{H}" fill="url(#dots)"/>')

# corner HUD brackets
b = 26; L = 46
for (x, y, sx, sy) in [(22, 22, 1, 1), (W-22, 22, -1, 1), (22, H-22, 1, -1), (W-22, H-22, -1, -1)]:
    svg.append(f'<path d="M {x+sx*L} {y} L {x} {y} L {x} {y+sy*L}" fill="none" stroke="#4ade80" stroke-opacity="0.8" stroke-width="2.5"/>')

# scanlines
for yy in range(8, H, 14):
    svg.append(f'<rect x="0" y="{yy}" width="{W}" height="1" fill="#ffffff" opacity="0.018"/>')

# edges
for (i, j) in sorted(edges):
    x1, y1 = nodes[i]; x2, y2 = nodes[j]
    svg.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="#9fb4d8" stroke-opacity="0.16" stroke-width="1"/>')

# node halos + cores
for (x, y) in nodes:
    c = random.choices(COLORS, weights=[w for _, w in COLORS])[0][0]
    r = random.uniform(3.0, 5.6)
    svg.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r*3.1:.1f}" fill="{c}" opacity="0.10"/>')
    svg.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="{c}" filter="url(#soft)"/>')
    svg.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{max(r*0.45, 1.4):.1f}" fill="#f8fafc" opacity="0.9"/>')

# ---- right-side wordmark block ----
MONO = "'DejaVu Sans Mono',Menlo,Consolas,monospace"
svg.append(f'<text x="830" y="248" font-family="{MONO}" font-size="47" font-weight="bold" fill="url(#title)" filter="url(#glow)" letter-spacing="2">NEURAL_MESH</text>')
svg.append(f'<text x="830" y="290" font-family="{MONO}" font-size="19" fill="#8a93a6">self-organizing · self-forgetting</text>')
svg.append(f'<text x="830" y="316" font-family="{MONO}" font-size="19" fill="#8a93a6">agentic memory mesh</text>')
svg.append(f'<line x1="830" y1="352" x2="1145" y2="352" stroke="#1e293b" stroke-width="1.5"/>')
svg.append(f'<circle cx="838" cy="396" r="6" fill="#4ade80" filter="url(#soft)"/>')
svg.append(f'<text x="856" y="402" font-family="{MONO}" font-size="18" font-weight="bold" fill="#d7e2f4">LIVE</text>')
svg.append(f'<text x="908" y="402" font-family="{MONO}" font-size="17" fill="#8a93a6">· rust backend · v0.21.0</text>')
svg.append(f'<text x="830" y="436" font-family="{MONO}" font-size="15" fill="#5b6478">api.d0xeddev.com/brain</text>')
svg.append(f'<text x="830" y="474" font-family="{MONO}" font-size="14" fill="#454e63">for agents, by agents</text>')
svg.append('</svg>')

with open("static/brain-og.svg", "w") as f:
    f.write("\n".join(svg))
print(f"nodes={len(nodes)} edges={len(edges)}")
print("wrote static/brain-og.svg")
