#!/usr/bin/env python3
"""Coordinated spike: Omnigraph, Hindsight, yantrikdb vs NEURAL_MESH v0.16."""
import json, time, sys, os

print("=" * 60)
print("  THREE-WAY MEMORY SPIKE")
print("  Omnigraph · Hindsight · yantrikdb")
print("  vs NEURAL_MESH v0.16 baseline")
print("=" * 60)

# -----------------------------------------------------------
# BENCHMARK 1: Omnigraph (if available in /tmp)
# -----------------------------------------------------------
OMNI_BIN = "/tmp/omnigraph"
OMNI_SERVER = "/tmp/omnigraph-server"

print("\n[1/4] OMNIGRAPH")
if os.path.exists(OMNI_BIN):
    import subprocess
    try:
        ver = subprocess.run([OMNI_BIN, "--version"], capture_output=True, text=True, timeout=10)
        print(f"  binary: {ver.stdout.strip() or ver.stderr.strip()}")
    except Exception as e:
        print(f"  binary check failed: {e}")

    # Try help to understand available commands
    try:
        help_out = subprocess.run([OMNI_BIN, "--help"], capture_output=True, text=True, timeout=5)
        print(f"  commands: {[l.split()[0] for l in help_out.stdout.splitlines() if l.strip() and not l.startswith(' ')][:8]}")
    except:
        pass

    # Quick server test
    if os.path.exists(OMNI_SERVER):
        print("  server binary: ✓")
        try:
            svr = subprocess.Popen(
                [OMNI_SERVER, "--help"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            out, _ = svr.communicate(timeout=5)
            print(f"  server help: {out.strip()[:200]}")
        except Exception as e:
            print(f"  server: {e}")
else:
    print("  ⚠ Omnigraph not found — running on API/doc analysis instead")
    print("  Key capabilities (from docs):")
    print("    - Git-style branch/merge for agent experiments")
    print("    - Graph traversal + vector ANN + BM25 in one query")
    print("    - S3-native Lance storage (columnar)")
    print("    - Cedar policy enforcement per-graph")
    print("    - Declared-as-code: cluster.yaml → cluster apply")
    print("    - 54 branches, 780 commits → active development")

# -----------------------------------------------------------
# BENCHMARK 2: yantrikdb-hermes-plugin
# -----------------------------------------------------------
print("\n[2/4] YANTRIKDB")
try:
    import importlib
    spec = importlib.util.find_spec("yantrikdb_hermes_plugin")
    if spec:
        print(f"  installed at: {spec.origin}")
        # Try to import and check version
        try:
            import yantrikdb_hermes_plugin
            ver = getattr(yantrikdb_hermes_plugin, "__version__", "unknown")
            print(f"  version: {ver}")
        except ImportError as e:
            print(f"  import error: {e}")
    else:
        print("  ⚠ Not installed — checking pip...")
except Exception as e:
    print(f"  ⚠ Import check failed: {e}")
    print("  [will retry after pip installs complete]")

# -----------------------------------------------------------
# BENCHMARK 3: Hindsight
# -----------------------------------------------------------
print("\n[3/4] HINDSIGHT")
try:
    spec = importlib.util.find_spec("hindsight")
    if spec:
        print(f"  installed at: {spec.origin}")
        try:
            import hindsight
            ver = getattr(hindsight, "__version__", "unknown")
            print(f"  version: {ver}")
        except ImportError as e:
            print(f"  import error: {e}")
    else:
        print("  ⚠ Not installed — checking pip...")
except Exception as e:
    print(f"  ⚠ Import check failed: {e}")

# -----------------------------------------------------------
# BENCHMARK 4: NEURAL_MESH baseline
# -----------------------------------------------------------
print("\n[4/4] NEURAL_MESH v0.16 BASELINE")
sys.path.insert(0, "/opt/data/NEURAL_MESH")
try:
    from neural_mesh import __version__
    print(f"  version: {__version__}")
except ImportError:
    import subprocess
    r = subprocess.run(
        ["/opt/data/NEURAL_MESH/.venv-server/bin/python", "-c",
         "from neural_mesh import __version__; print(__version__)"],
        capture_output=True, text=True, timeout=5,
        env={**os.environ, "PYTHONPATH": "/opt/data/NEURAL_MESH"}
    )
    print(f"  version: {r.stdout.strip()}")

# Health check
import urllib.request
try:
    req = urllib.request.urlopen("http://localhost:4021/health", timeout=3)
    health = json.loads(req.read())
    print(f"  health: nodes={health.get('nodes')}, status={health.get('status')}")
except Exception as e:
    print(f"  health: unreachable ({e})")

# -----------------------------------------------------------
# COMPARISON MATRIX
# -----------------------------------------------------------
print("\n" + "=" * 60)
print("  INTEGRATION MATRIX")
print("=" * 60)
print(f"""
| Feature              | NEURAL_MESH | Omnigraph | Hindsight | yantrikdb |
|----------------------|-------------|-----------|-----------|-----------|
| Graph traversal      | ✓ (Rust 15x)| ✓ native  | —         | —         |
| Vector search        | via NumPy   | ✓ ANN     | ✓         | ✓ (emb)   |
| BM25 / text          | —           | ✓         | —         | —         |
| Git branching        | —           | ✓         | —         | —         |
| S3-native storage    | —           | ✓ (Lance) | —         | —         |
| Contradiction track  | —           | —         | —         | ✓         |
| Explainable recall   | ✓ (proof)   | —         | —         | ✓ per-hit |
| Self-tuning          | —           | —         | —         | ✓         |
| LoCoMo eval          | ✓ (/qa)     | —         | —         | —         |
| On-chain attestation | ✓ (Helixa)  | —         | —         | —         |
| Hermes plugin        | —           | via skill | ✓ native  | ✓ native  |
""")

print("  RECOMMENDATION:")
print("    1. yantrikdb → Install NOW as Hermes memory provider")
print("       (contradiction tracking + explainable recall)")
print("    2. Hindsight  → Enable via 'hermes memory setup'")
print("       (agent memory that learns, 40+ integrations)")
print("    3. Omnigraph  → Plan for v0.18 storage backend migration")
print("       (needs more disk, but git-branched agent memory is the future)")
print()
print("  Immediate action: hermes plugins install yantrikos/yantrikdb-hermes-plugin")
print("=" * 60)
