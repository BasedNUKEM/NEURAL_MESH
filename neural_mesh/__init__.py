"""NEURAL_MESH — a self-organizing, self-forgetting agentic memory mesh.

Pure-stdlib core (no pip installs required to run the demo).

The mesh models memory the way cognition actually works:
  * FIVE memory types with separate handling (CoALA / 2026 survey)
  * A MESH TOPOLOGY where nodes self-link by meaning (HippoRAG hippocampal indexing)
  * RESONANCE retrieval: a query seeds nodes, activation spreads to linked
    neighbours with decay — the differentiator vs flat cosine search
  * LANES: short-term HOT vs long-term COLD, bridged by a consolidation bus
  * POINTER protocol: big tool outputs never enter context (only a pointer does)
  * SLEEP cycle: replay -> strengthen -> PRUNE weak/aged/low-trust traces
  * PROSPECTIVE memory: intentions & futures, not just the past

Run `python -m neural_mesh.demo` to see it work.
"""

from .core import Mesh, MemoryType
from .meshfile import export_mesh, import_mesh
from .sharing import merge_peer_mesh, consensus_rank, PeerPolicy, export_for_peer
from .lora_dataset import write_jsonl, write_hf_jsonl, write_weights, summarize
from .integrations.helixa_provenance import (
    HelixaStamp, stamp_node, verify_stamp, aura_trust_weight,
    export_manifest, make_stamp,
)

__all__ = ["Mesh", "MemoryType", "export_mesh", "import_mesh",
           "merge_peer_mesh", "consensus_rank", "PeerPolicy", "export_for_peer",
           "write_jsonl", "write_hf_jsonl", "write_weights", "summarize",
           "HelixaStamp", "stamp_node", "verify_stamp", "aura_trust_weight",
           "export_manifest", "make_stamp"]
__version__ = "0.5.0"
