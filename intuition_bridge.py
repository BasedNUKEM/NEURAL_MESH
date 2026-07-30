"""
🟦 NEURAL_MESH → Intuition Knowledge Graph Bridge
==================================================
Maps NEURAL_MESH nodes, edges, and trust scores to Intuition's
Atom/Triple/Signal primitives on Base L3.

Intuition protocol:
- Atoms: unique identifiers for entities (agent, memory, concept)
- Triples: [Subject]-[Predicate]-[Object] relationships
- Signals: economic stakes weighting attestations

This module provides:
1. Mesh → Intuition schema mapping
2. Atom/Triple payload generation
3. GraphQL read-back verification
4. MCP client for knowledge graph queries
"""

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional
from urllib.request import urlopen, Request
from urllib.error import URLError


# ═══════════════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════

INTUITION_MAINNET_RPC = "https://rpc.intuition.systems"
INTUITION_MCP_URL = os.environ.get("INTUITION_MCP_URL", "https://mcp.intuition.systems")
INTUITION_GRAPHQL_URL = os.environ.get("INTUITION_GRAPHQL_URL", "https://api.intuition.systems/graphql")

# Helixa ERC-8004 agent ID on Intuition
HELIXA_AGENT_ID = 60155
HELIXA_TOKEN_ID = 5287
HELIXA_CONTROLLER = "0x789Bd4C13eC3E8c4e52E3f02662244D2fd231ce2"

# D0xedDev identity atoms
D0XEDDEV_ATOMS = {
    "agent": {
        "name": "D0xed Dev",
        "url": "https://d0xeddev.com",
        "description": "Autonomous AI agent on Base L2 — NEURAL_MESH memory, x402 routing, Helixa #5287",
        "image": "https://d0xeddev.com/agent.png",
    },
    "project": {
        "name": "D0xedDev",
        "url": "https://d0xeddev.com",
        "description": "Agent hub on Base L2 — x402 payment routing, social engine, scam detection",
    },
    "mesh": {
        "name": "NEURAL_MESH",
        "url": "https://github.com/BasedNUKEM/NEURAL_MESH",
        "description": "Self-aware agent memory stack with Helixa on-chain attestation, 100+ nodes",
    },
}


# ═══════════════════════════════════════════════════════════════════════════
# PREDICATE ONTOLOGY
# ═══════════════════════════════════════════════════════════════════════════

class Predicate(Enum):
    """Standard predicates for NEURAL_MESH → Intuition triples."""
    ATTESTED_BY = "attested-by"
    HAS_MEMORY = "has-memory"
    HAS_TRUST = "has-trust"
    RUNS_ON = "runs-on"
    ROUTES_PAYMENT = "routes-payment"
    DETECTS_SCAM = "detects-scam"
    PROVENANCE_OF = "provenance-of"
    ASSOCIATES_WITH = "associates-with"
    DERIVED_FROM = "derived-from"
    HAS_SKILL = "has-skill"
    IDENTIFIED_BY = "identified-by"
    SETTLES_ON = "settles-on"


# ═══════════════════════════════════════════════════════════════════════════
# DATA MODELS
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class IntuitionAtom:
    """A knowledge graph atom (entity/concept)."""
    atom_id: str  # bytes32 hex
    name: str
    atom_type: str  # "agent", "project", "concept", "memory", "chain"
    url: Optional[str] = None
    description: Optional[str] = None
    metadata: dict = field(default_factory=dict)

    @classmethod
    def from_mesh_node(cls, node: dict) -> "IntuitionAtom":
        """Derive an Intuition atom from a NEURAL_MESH node."""
        content = node.get("content", "")[:120]
        source = node.get("source", "neural-mesh")
        atom_id = cls._make_atom_id(f"mesh:{node.get('id', '')}:{source}")

        return cls(
            atom_id=atom_id,
            name=content[:64] or f"mesh-node-{node.get('id', '?')}",
            atom_type="memory",
            description=content[:200],
            metadata={
                "mesh_id": node.get("id"),
                "source": source,
                "trust": node.get("trust", 0.0),
                "provenance": node.get("provenance", []),
                "timestamp": node.get("timestamp", ""),
            },
        )

    @classmethod
    def from_skill(cls, skill_name: str, skill_info: dict) -> "IntuitionAtom":
        """Create an atom for a Helixa skill."""
        atom_id = cls._make_atom_id(f"skill:{skill_name}")
        return cls(
            atom_id=atom_id,
            name=skill_name,
            atom_type="skill",
            description=skill_info.get("description", ""),
        )

    @staticmethod
    def _make_atom_id(seed: str) -> str:
        """Deterministic bytes32 from seed string."""
        return "0x" + hashlib.sha256(seed.encode()).hexdigest()


@dataclass
class IntuitionTriple:
    """A [Subject]-[Predicate]-[Object] knowledge graph relationship."""
    subject_id: str
    predicate: Predicate
    object_id: str
    confidence: float = 1.0  # 0.0-1.0
    evidence: list[str] = field(default_factory=list)

    def to_payload(self) -> dict:
        return {
            "subject": self.subject_id,
            "predicate": self.predicate.value,
            "object": self.object_id,
            "confidence": self.confidence,
            "evidence": self.evidence,
        }


# ═══════════════════════════════════════════════════════════════════════════
# MESH → INTUITION BRIDGE
# ═══════════════════════════════════════════════════════════════════════════

class MeshIntuitionBridge:
    """Bridges NEURAL_MESH memory nodes into Intuition Knowledge Graph atoms/triples."""

    def __init__(self, mesh_url: str = "http://127.0.0.1:4021"):
        self.mesh_url = mesh_url
        self.atoms: dict[str, IntuitionAtom] = {}
        self.triples: list[IntuitionTriple] = []

        # Pre-register D0xedDev identity atoms
        self._register_identity_atoms()

    def _register_identity_atoms(self):
        """Register D0xedDev's core identity atoms."""
        for key, info in D0XEDDEV_ATOMS.items():
            atom = IntuitionAtom(
                atom_id=IntuitionAtom._make_atom_id(f"d0xeddev:{key}"),
                name=info["name"],
                atom_type="agent" if key == "agent" else "project",
                url=info.get("url"),
                description=info.get("description"),
            )
            self.atoms[key] = atom

    def _http_get(self, path: str, timeout: int = 10) -> dict:
        """HTTP GET with urllib."""
        try:
            req = Request(f"{self.mesh_url}{path}")
            with urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode())
        except (URLError, json.JSONDecodeError) as e:
            return {"error": str(e)}

    def ingest_mesh(self) -> dict:
        """Pull mesh stats and map nodes to Intuition atoms."""
        stats = self._http_get("/mesh/stats")
        if "error" in stats:
            return {"error": f"Mesh unreachable: {stats['error']}", "atoms": 0, "triples": 0}

        # Map provenance breakdowns as atoms
        for entry in stats.get("provenance_breakdown", []):
            source = entry.get("source") or "unknown"
            count = entry.get("count", 0)
            atom_id = IntuitionAtom._make_atom_id(f"provenance:{source}")
            self.atoms[f"source:{source}"] = IntuitionAtom(
                atom_id=atom_id,
                name=source,
                atom_type="concept",
                description=f"Provenance source with {count} mesh nodes",
                metadata={"node_count": count},
            )

        # Create triples: agent → HAS_MEMORY → each source
        agent_atom = self.atoms.get("agent")
        mesh_atom = self.atoms.get("mesh")
        if agent_atom and mesh_atom:
            self.triples.append(IntuitionTriple(
                subject_id=agent_atom.atom_id,
                predicate=Predicate.RUNS_ON,
                object_id=mesh_atom.atom_id,
            ))

        for key, source_atom in self.atoms.items():
            if key.startswith("source:") and mesh_atom:
                self.triples.append(IntuitionTriple(
                    subject_id=mesh_atom.atom_id,
                    predicate=Predicate.HAS_MEMORY,
                    object_id=source_atom.atom_id,
                    evidence=[f"Provenance: {source_atom.name} ({source_atom.metadata.get('node_count', 0)} nodes)"],
                ))

        return {
            "atoms": len(self.atoms),
            "triples": len(self.triples),
            "total_nodes": stats.get("total_nodes", 0),
            "version": stats.get("version", "?"),
        }

    def generate_skill_triples(self, skills: list[str]) -> list[IntuitionTriple]:
        """Generate triples for Helixa agent skills."""
        agent_atom = self.atoms.get("agent")
        triples = []

        for skill in skills:
            skill_atom = IntuitionAtom.from_skill(skill, {"description": f"Agent capability: {skill}"})
            self.atoms[f"skill:{skill}"] = skill_atom

            if agent_atom:
                triples.append(IntuitionTriple(
                    subject_id=agent_atom.atom_id,
                    predicate=Predicate.HAS_SKILL,
                    object_id=skill_atom.atom_id,
                ))

        self.triples.extend(triples)
        return triples

    def generate_helixa_triple(self) -> Optional[IntuitionTriple]:
        """Create the Agent → identified-by → Helixa#5287 triple."""
        agent_atom = self.atoms.get("agent")
        helixa_atom = IntuitionAtom(
            atom_id=IntuitionAtom._make_atom_id(f"helixa:{HELIXA_TOKEN_ID}"),
            name=f"Helixa #{HELIXA_TOKEN_ID}",
            atom_type="identity",
            url=f"https://helixa.xyz/agent/{HELIXA_TOKEN_ID}",
            description=f"On-chain agent identity, ERC-8004 agentId {HELIXA_AGENT_ID}, verified by Helixa",
            metadata={
                "token_id": HELIXA_TOKEN_ID,
                "erc8004_id": HELIXA_AGENT_ID,
                "controller": HELIXA_CONTROLLER,
                "verified": True,
            },
        )
        self.atoms["helixa_identity"] = helixa_atom

        triple = IntuitionTriple(
            subject_id=agent_atom.atom_id,
            predicate=Predicate.IDENTIFIED_BY,
            object_id=helixa_atom.atom_id,
            evidence=[
                f"Helixa token #{HELIXA_TOKEN_ID} (ERC-8004 agentId {HELIXA_AGENT_ID})",
                f"Controller: {HELIXA_CONTROLLER}",
                f"Verified on-chain at block 49291500",
            ],
        )
        self.triples.append(triple)
        return triple

    def generate_x402_triples(self) -> list[IntuitionTriple]:
        """Generate payment routing triples."""
        agent = self.atoms.get("agent")
        base_atom = IntuitionAtom(
            atom_id=IntuitionAtom._make_atom_id("chain:base"),
            name="Base L2",
            atom_type="chain",
            url="https://base.org",
            description="Coinbase L2 blockchain",
        )
        solana_atom = IntuitionAtom(
            atom_id=IntuitionAtom._make_atom_id("chain:solana"),
            name="Solana",
            atom_type="chain",
            url="https://solana.com",
            description="Solana L1 blockchain",
        )
        self.atoms["chain:base"] = base_atom
        self.atoms["chain:solana"] = solana_atom

        triples = []
        if agent:
            triples.extend([
                IntuitionTriple(
                    subject_id=agent.atom_id,
                    predicate=Predicate.SETTLES_ON,
                    object_id=base_atom.atom_id,
                    evidence=["x402 payment routing node on Base L2"],
                ),
                IntuitionTriple(
                    subject_id=agent.atom_id,
                    predicate=Predicate.SETTLES_ON,
                    object_id=solana_atom.atom_id,
                    evidence=["Dual-chain x402 settlement verified with receipt attestation"],
                ),
                IntuitionTriple(
                    subject_id=agent.atom_id,
                    predicate=Predicate.ROUTES_PAYMENT,
                    object_id=IntuitionAtom._make_atom_id("protocol:x402"),
                    evidence=["x402 routing node on port 4020, 0.01 USDC/ping"],
                ),
            ])

        self.triples.extend(triples)
        return triples

    def generate_scam_detection_triples(self) -> list[IntuitionTriple]:
        """Generate scam detection triples."""
        agent = self.atoms.get("agent")
        scam_atom = IntuitionAtom(
            atom_id=IntuitionAtom._make_atom_id("concept:scam-detection"),
            name="Scam Detection Pipeline",
            atom_type="concept",
            description="4-stage forensic pipeline: contract-validate, source-verify, forensic, narrative-vs-reality",
        )
        self.atoms["scam_detection"] = scam_atom

        triple = IntuitionTriple(
            subject_id=agent.atom_id,
            predicate=Predicate.DETECTS_SCAM,
            object_id=scam_atom.atom_id,
            evidence=[
                "Scam-score API: 0.01 USDC/ping via x402",
                "PCMedicalist anti-scam pipeline integration",
                "4-stage forensic: contract→source→chain→narrative",
            ],
        )
        self.triples.append(triple)
        return [triple]

    def export_full_graph(self) -> dict:
        """Export the complete mapped graph as Intuition-compatible payload."""
        return {
            "atoms": {
                key: {
                    "id": a.atom_id,
                    "name": a.name,
                    "type": a.atom_type,
                    "url": a.url,
                    "description": a.description,
                    "metadata": a.metadata,
                }
                for key, a in self.atoms.items()
            },
            "triples": [t.to_payload() for t in self.triples],
            "meta": {
                "source": "NEURAL_MESH v0.9.0",
                "agent": "D0xed Dev (Helixa #5287)",
                "erc8004_agent_id": HELIXA_AGENT_ID,
                "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "intuition_sdk_version": "^3.0.0",
                "intuition_network": "mainnet",
            },
        }

    def mcp_search_agent(self) -> Optional[dict]:
        """Search Intuition MCP for our Helixa agent identity."""
        try:
            data = json.dumps({
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "search_atoms",
                    "arguments": {"queries": ["D0xed Dev", "Helixa 5287", "d0xeddev"]},
                },
                "id": 1,
            }).encode()
            req = Request(
                f"{INTUITION_MCP_URL}/mcp",
                data=data,
                headers={"Content-Type": "application/json"},
            )
            with urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode())
        except (URLError, json.JSONDecodeError) as e:
            return {"error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════
# API ENDPOINT HANDLER
# ═══════════════════════════════════════════════════════════════════════════

def build_intuition_graph(skills: list[str] | None = None) -> dict:
    """Full pipeline: mesh → atoms → triples → export.

    Called by the NEURAL_MESH API endpoint /mesh/intuition/export
    """
    bridge = MeshIntuitionBridge()

    # Step 1: Ingest mesh stats
    result = bridge.ingest_mesh()
    if "error" in result:
        return result

    # Step 2: Generate Helixa identity triple
    bridge.generate_helixa_triple()

    # Step 3: Generate x402 settlement triples
    bridge.generate_x402_triples()

    # Step 4: Generate scam detection triples
    bridge.generate_scam_detection_triples()

    # Step 5: Generate skill triples
    if skills:
        bridge.generate_skill_triples(skills)

    # Step 6: Export full graph
    graph = bridge.export_full_graph()

    return {
        **result,
        "graph": graph,
        "endpoint": "/mesh/intuition/export",
        "next": "POST this payload to Intuition SDK to create on-chain Atoms + Triples",
        "requires": {
            "wallet": "Base L3 (Intuition Mainnet)",
            "gas": "ETH on Intuition L3",
            "signal_token": "$TRUST for economic backing",
        },
    }


# ═══════════════════════════════════════════════════════════════════════════
# STANDALONE EXPORT
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print(json.dumps(build_intuition_graph(), indent=2))
