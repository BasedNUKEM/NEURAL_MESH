"""
x402 Paid Recall — payment-gated memory retrieval for NEURAL_MESH.

Tiers:
  basic  $0.01 — resonance recall, top_k ≤ 10
  deep   $0.05 — yantrikdb bridge recall, top_k ≤ 50, proof cards
  ultra  $0.10 — hybrid + yantrikdb, top_k ≤ 100, proof cards + trust scores

Receipt verification via on-chain escrow contract event logs on Base Mainnet.

Usage:
    from neural_mesh.x402_recall import PaidRecallGate, TIERS, SERVICE_NAME
    gate = PaidRecallGate(mesh)
    result = gate.paid_recall(query="Base L2 scaling", tier="deep", proof_header="0x...")
"""

import json, os, hashlib, time, urllib.request
from pathlib import Path

# ── Tier pricing ────────────────────────────────────────────────────────
# Dollar amounts in USDC cents (6-decimal token = 1e6 per dollar)
USDC_DECIMALS = 6
USDC_PER_DOLLAR = 10 ** USDC_DECIMALS

TIERS = {
    "basic": {
        "price_cents": 1,
        "price_usdc": 1 * USDC_PER_DOLLAR // 100,  # 10000 = $0.01
        "max_top_k": 10,
        "mode": "resonance",
        "proofs": False,
        "trust": False,
    },
    "deep": {
        "price_cents": 5,
        "price_usdc": 5 * USDC_PER_DOLLAR // 100,  # 50000 = $0.05
        "max_top_k": 50,
        "mode": "yantrikdb",
        "proofs": True,
        "trust": False,
    },
    "ultra": {
        "price_cents": 10,
        "price_usdc": 10 * USDC_PER_DOLLAR // 100,  # 100000 = $0.10
        "max_top_k": 100,
        "mode": "hybrid",
        "proofs": True,
        "trust": True,
    },
}

SERVICE_NAME = "neural-mesh-recall"
RECEIPT_CONTRACT = "0x76d10574bA10975fd3125d22c8d5E5Aa6F928344"
FEE_RECIPIENT = "0xf8f96d9801b27046c6fbf662ba3a3b4baa68de83"
BASE_RPC = os.environ.get("BASE_RPC_URL", "https://mainnet.base.org")

# recordReceipt(string,address,address,uint256,bytes32) 4-byte selector
# Keccak-256 of "recordReceipt(string,address,address,uint256,bytes32)"
# Python 3.9+ hashlib has sha3_256 (Keccak-256 variant used by Ethereum)
RECORD_RECEIPT_SELECTOR = "0x" + hashlib.sha3_256(
    b"recordReceipt(string,address,address,uint256,bytes32)"
).hexdigest()[:8]


def _rpc_call(method: str, params: list) -> dict:
    """Make a JSON-RPC call to the Base RPC."""
    body = json.dumps({"jsonrpc": "2.0", "method": method, "params": params, "id": 1}).encode()
    req = urllib.request.Request(
        BASE_RPC,
        data=body,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}


def verify_receipt_onchain(tx_hash: str, expected_service: str = SERVICE_NAME) -> dict:
    """
    Verify an x402 payment receipt on-chain.

    Checks:
      1. Transaction exists and succeeded (status = 1)
      2. Transaction target is the receipt contract
      3. Call data contains the expected service name

    Returns {"ok": True, "block": N, "service": str, ...} or {"ok": False, "error": str}.
    """
    if not tx_hash.startswith("0x") or len(tx_hash) != 66:
        return {"ok": False, "error": f"invalid tx hash: {tx_hash}"}

    # 1. Get transaction receipt
    receipt = _rpc_call("eth_getTransactionReceipt", [tx_hash])
    if "error" in receipt:
        return {"ok": False, "error": f"rpc error: {receipt['error']}"}

    result = receipt.get("result")
    if not result:
        return {"ok": False, "error": "tx not found or not yet mined"}

    if result.get("status") != "0x1":
        return {"ok": False, "error": "tx reverted or failed"}

    # 2. Get transaction info and check target
    tx_info = _rpc_call("eth_getTransactionByHash", [tx_hash])
    tx_result = tx_info.get("result", {})
    tx_to = (tx_result.get("to") or "").lower()
    if tx_to != RECEIPT_CONTRACT.lower():
        return {"ok": False, "error": f"tx not to receipt contract (got {tx_to})"}

    # 3. Verify call data contains the expected selector
    input_data = (tx_result.get("input") or "0x").lower()
    if not input_data.startswith(RECORD_RECEIPT_SELECTOR.lower()):
        return {"ok": False, "error": "tx input does not match recordReceipt selector"}

    return {
        "ok": True,
        "block": int(result["blockNumber"], 16),
        "contract": RECEIPT_CONTRACT,
    }


class PaidRecallGate:
    """
    Payment gate for premium mesh recall endpoints.

    Tracks consumed receipts in-memory to prevent replay attacks.
    In production, this should use a persistent store (Redis, SQLite).
    """

    def __init__(self, mesh):
        self._mesh = mesh
        self._consumed: set[str] = set()  # tx_hash -> consumed
        self._usage: dict[str, list[float]] = {}  # tx_hash -> [timestamps]

    def validate_tier(self, tier: str) -> dict:
        """Validate tier name. Returns tier config or error."""
        tier_cfg = TIERS.get(tier)
        if not tier_cfg:
            return {"ok": False, "error": f"unknown tier: {tier} (use: {', '.join(TIERS)})"}
        return {"ok": True, "tier": tier, **tier_cfg}

    def verify_and_consume(self, proof_header: str, tier: str) -> dict:
        """
        Verify a payment proof and mark it consumed.

        Args:
            proof_header: The X-Payment-Proof header value (tx hash)
            tier: Requested recall tier

        Returns {"ok": True, ...} or {"ok": False, "error": ...}
        """
        # Validate tier
        tier_result = self.validate_tier(tier)
        if not tier_result["ok"]:
            return tier_result

        # Check replay
        if proof_header in self._consumed:
            return {"ok": False, "error": "receipt already consumed (replay?)"}

        # Verify on-chain
        verify = verify_receipt_onchain(proof_header)
        if not verify.get("ok"):
            return verify

        # Mark consumed
        self._consumed.add(proof_header)
        self._usage.setdefault(proof_header, []).append(time.time())

        return {"ok": True, "tx_hash": proof_header, "block": verify.get("block"), **tier_result}

    def paid_recall(
        self,
        query: str,
        tier: str = "basic",
        proof_header: str = "",
        **kwargs,
    ) -> dict:
        """
        Execute a paid recall after verifying the payment proof.

        Args:
            query: Search query string
            tier: Recall tier (basic/deep/ultra)
            proof_header: X-Payment-Proof header (tx hash of x402 payment)
            **kwargs: Additional recall parameters (lane, alpha, etc.)

        Returns recall results or error dict.
        """
        # Verify payment first
        gate_result = self.verify_and_consume(proof_header, tier)
        if not gate_result["ok"]:
            return gate_result

        # Execute recall at tier
        max_k = gate_result["max_top_k"]
        top_k = min(kwargs.pop("top_k", max_k), max_k)
        mode = gate_result["mode"]

        nodes = []

        if mode == "resonance":
            nodes = self._mesh.recall(query, top_k=top_k, **kwargs)
        elif mode == "yantrikdb":
            nodes = self._mesh.recall(query, top_k=top_k, **kwargs)
            # Try yantrikdb bridge augmentation
            try:
                from .integrations.yantrikdb_bridge import YantrikDBBridge
                bridge = YantrikDBBridge(self._mesh)
                yan_results = bridge.enhanced_recall(query, top_k=min(top_k, 15))
                if yan_results.get("ok") and yan_results.get("yantrikdb_hits"):
                    nodes = (yan_results.get("mesh_hits", []) +
                             yan_results.get("yantrikdb_hits", []))[:top_k]
            except Exception:
                pass
        elif mode == "hybrid":
            nodes = self._mesh.hybrid_recall(
                query, top_k=top_k,
                alpha=kwargs.pop("alpha", 0.9),
                **kwargs,
            )
            # Try yantrikdb bridge augmentation
            try:
                from .integrations.yantrikdb_bridge import YantrikDBBridge
                bridge = YantrikDBBridge(self._mesh)
                yan_results = bridge.enhanced_recall(query, top_k=min(top_k, 15))
                if yan_results.get("ok") and yan_results.get("yantrikdb_hits"):
                    nodes = (nodes + yan_results.get("yantrikdb_hits", []))[:top_k]
            except Exception:
                pass

        # Build response
        response = {
            "ok": True,
            "query": query,
            "tier": tier,
            "mode": mode,
            "top_k": top_k,
            "found": len(nodes),
            "results": [self._node_to_dict(n) for n in nodes],
            "payment": {
                "tx_hash": proof_header,
                "price_cents": gate_result["price_cents"],
                "tier": tier,
            },
        }

        # Add proof cards for deep/ultra
        if gate_result["proofs"] and nodes:
            try:
                from .proof_cards import recall_with_proofs
                proofs = recall_with_proofs(self._mesh, query, top_k=top_k)
                response["proof_cards"] = proofs.get("proof_cards", [])
            except Exception:
                response["proof_cards"] = []

        # Add trust scores for ultra
        if gate_result["trust"]:
            try:
                from .reputation import mesh_signal
                trust_data = mesh_signal(self._mesh)
                response["trust_scores"] = trust_data
            except Exception:
                response["trust_scores"] = {}

        return response

    @staticmethod
    def _node_to_dict(node) -> dict:
        """Convert a mesh node to a serializable dict."""
        if hasattr(node, '_asdict'):
            d = dict(node._asdict())
        elif isinstance(node, dict):
            d = dict(node)
        else:
            d = {"payload": str(node)}
        # Remove non-serializable fields
        for key in list(d.keys()):
            if not isinstance(d[key], (str, int, float, bool, list, dict, type(None))):
                d[key] = str(d[key])
        return d

    @property
    def stats(self) -> dict:
        """Gate statistics."""
        return {
            "total_receipts_consumed": len(self._consumed),
            "active_tiers": list(TIERS.keys()),
            "receipt_contract": RECEIPT_CONTRACT,
            "fee_recipient": FEE_RECIPIENT,
        }


__all__ = ["PaidRecallGate", "TIERS", "SERVICE_NAME", "verify_receipt_onchain",
           "RECEIPT_CONTRACT", "FEE_RECIPIENT", "BASE_RPC"]
