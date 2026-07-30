"""Live Helixa signer — loads the agent wallet key and signs Helixa API calls.

SAFETY CONTRACT (NON-NEGOTIABLE)
---------------------------------
1. The private key is loaded from ``/opt/data/.env.d0xeddev_populated``
   into an ``eth_account.Account`` object ONCE at init and NEVER leaves
   the object.
2. No method in this module prints, logs, returns, or serializes the
   private key. All external outputs contain ONLY signatures, tx hashes,
   and status — never key material.
3. Every on-chain write (verify, update) requires ``dry_run=False``.
   Set ``dry_run=True`` (the default) to simulate and review before
   committing real state changes to Helixa.

USAGE::

    from neural_mesh.integrations.helixa_signer import HelixaSigner
    signer = HelixaSigner()          # loads key from env file
    signer.verify_agent("5287")      # dry_run=True by default — simulates
    signer.verify_agent("5287", dry_run=False)  # ACTUAL on-chain write
"""

from __future__ import annotations

import json
import os
import time
import hashlib
import urllib.request
from typing import Any

from eth_account import Account

from .helixa_attest import (
    build_attestation_message,
    sign_attestation,
    record_onchain_attestation,
    AttestationMessage,
)

# ── constants ──────────────────────────────────────────────────────────

ENV_FILE = "/opt/data/.env.d0xeddev_populated"
HELIXA_API_BASE = "https://helixa.xyz/api/v2"
HELIXA_AGENT_ID = "5287"  # canonical D0xed Dev agent

# Helixa SIWA domain
SIWA_DOMAIN = {
    "name": "Helixa",
    "version": "1",
    "chainId": 8453,  # Base mainnet
}

SIWA_TYPES = {
    "EIP712Domain": [
        {"name": "name", "type": "string"},
        {"name": "version", "type": "string"},
        {"name": "chainId", "type": "uint256"},
    ],
    "SiwaMessage": [
        {"name": "uri", "type": "string"},
        {"name": "issuedAt", "type": "string"},
        {"name": "nonce", "type": "string"},
    ],
}


# ── key loading (private — never exposed) ──────────────────────────────

def _load_private_key() -> str:
    """Load the Helixa agent wallet private key from the env file.

    Returns the hex key string. Caller MUST NOT log or expose it.
    """
    if not os.path.exists(ENV_FILE):
        raise FileNotFoundError(
            f"Helixa env file not found: {ENV_FILE}. "
            "Ensure the agent wallet key is configured at this path."
        )

    key = ""
    with open(ENV_FILE) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[7:]
            if "=" not in line:
                continue
            var, _, val = line.partition("=")
            val = val.strip().strip('"').strip("'")
            if var in ("TRADING_WALLET_PRIVATE_KEY", "WALLET_PRIVATE_KEY"):
                if val and len(val) == 64:  # 32-byte hex key
                    key = val
                    break

    if not key:
        raise ValueError(
            "No valid private key found in env file. "
            "Expected TRADING_WALLET_PRIVATE_KEY with a 64-char hex value."
        )
    return key


# ── Helixa signer ──────────────────────────────────────────────────────

class HelixaSigner:
    """Live Helixa API signer — holds the agent wallet key in memory.

    All on-chain write methods default to ``dry_run=True``.
    Pass ``dry_run=False`` to commit real state changes.
    """

    def __init__(self, base_url: str = HELIXA_API_BASE):
        self.base_url = base_url.rstrip("/")
        self._account = Account.from_key(_load_private_key())
        self.address = self._account.address

    # ── SIWA auth header ────────────────────────────────────────────

    def _siwa_header(self) -> dict[str, str]:
        """Build the SIWA (Sign-In With Ethereum) authorization header."""
        from eth_account.messages import encode_typed_data
        now = int(time.time())
        nonce = hashlib.sha256(str(now).encode()).hexdigest()[:16]

        message = {
            "uri": f"{self.base_url}/agent/verify",
            "issuedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
            "nonce": nonce,
        }

        full_msg = {
            "types": SIWA_TYPES,
            "domain": SIWA_DOMAIN,
            "primaryType": "SiwaMessage",
            "message": message,
        }
        encoded = encode_typed_data(full_msg)
        signed = self._account.sign_message(encoded)
        sig = signed.signature.hex()

        # Helixa expects: SIWA address=<hex>,signature=<hex>,nonce=<str>,issuedAt=<iso>
        header = (
            f"SIWA address={self.address},"
            f"signature=0x{sig},"
            f"nonce={nonce},"
            f"issuedAt={message['issuedAt']}"
        )
        return {"Authorization": header, "Content-Type": "application/json"}

    # ── API calls ───────────────────────────────────────────────────

    def _post(self, path: str, body: dict | None = None) -> dict:
        """POST to Helixa API with SIWA auth. Returns parsed JSON."""
        url = f"{self.base_url}{path}"
        headers = self._siwa_header()
        data = json.dumps(body or {}).encode() if body else None

        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            error_body = e.read().decode(errors="replace")
            try:
                return json.loads(error_body)
            except json.JSONDecodeError:
                return {"error": str(e), "detail": error_body[:500]}

    def verify_agent(self, agent_id: str, *, dry_run: bool = True) -> dict[str, Any]:
        """Verify the agent on-chain via ``POST /agent/{id}/verify``.

        This writes ``verified:true`` on-chain and returns a txHash.
        Costs Base L2 gas (dust ETH).

        Set ``dry_run=False`` to actually broadcast.
        """
        if dry_run:
            return {
                "ok": False,
                "dry_run": True,
                "agent_id": agent_id,
                "address": self.address,
                "action": "POST /agent/{id}/verify",
                "note": "Set dry_run=False to execute the on-chain verification.",
            }

        path = f"/agent/{agent_id}/verify"
        result = self._post(path)

        return {
            "ok": result.get("success", False) or "txHash" in str(result),
            "dry_run": False,
            "agent_id": agent_id,
            "address": self.address,
            "tx_hash": result.get("txHash") or result.get("tx_hash"),
            "response": result,
        }

    def update_agent_profile(
        self, agent_id: str, payload: dict, *, dry_run: bool = True
    ) -> dict[str, Any]:
        """Update agent profile via ``POST /agent/{id}/update``.

        Acceptable fields: personality, narrative, skills, domains, metadata.
        ``framework`` and ``soulbound`` are IMMUTABLE — ignored by the API.
        This writes OFF-CHAIN (no gas cost).

        Set ``dry_run=False`` to actually write.
        """
        if dry_run:
            return {
                "ok": False,
                "dry_run": True,
                "agent_id": agent_id,
                "payload_keys": list(payload.keys()),
                "action": "POST /agent/{id}/update",
                "note": "Set dry_run=False to write the profile update.",
            }

        path = f"/agent/{agent_id}/update"
        result = self._post(path, payload)

        return {
            "ok": result.get("success", False) or bool(result.get("updated")),
            "dry_run": False,
            "agent_id": agent_id,
            "updated": result.get("updated", []),
            "response": result,
        }

    def get_agent_status(self, agent_id: str) -> dict[str, Any]:
        """Read agent status from ``GET /agent/{id}`` (no signing needed)."""
        url = f"{self.base_url}/agent/{agent_id}"
        try:
            with urllib.request.urlopen(url, timeout=15) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            return {"error": str(e), "detail": e.read().decode(errors="replace")[:300]}

    # ── attestation integration ─────────────────────────────────────

    def attest_mesh_node(
        self,
        mesh,
        node_id: str,
        *,
        dry_run: bool = True,
        aura_score: float = 0.0,
    ) -> dict[str, Any]:
        """Full Helixa attestation flow: sign locally → record in mesh.

        Optionally verifies on-chain (if ``dry_run=False``).
        NEVER exposes the private key.
        """
        agent_id = HELIXA_AGENT_ID

        if dry_run:
            nodes = mesh._load()
            node = nodes.get(node_id)
            if node is None:
                return {"ok": False, "error": f"node not found: {node_id}"}
            message = build_attestation_message(node, agent_id)
            return {
                "ok": False,
                "dry_run": True,
                "node_id": node_id,
                "agent_id": agent_id,
                "address": self.address,
                "message_hash": message.signing_hash(),
                "action": "attest_mesh_node",
                "note": "Set dry_run=False to sign and record the attestation.",
            }

        # Sign locally
        nodes = mesh._load()
        node = nodes.get(node_id)
        if node is None:
            return {"ok": False, "error": f"node not found: {node_id}"}

        message = build_attestation_message(node, agent_id)

        def eth_sign(hash_hex: str) -> str:
            from eth_account.messages import encode_defunct
            msg = encode_defunct(hexstr="0x" + hash_hex)
            signed = self._account.sign_message(msg)
            return "0x" + signed.signature.hex()

        signature = sign_attestation(message, eth_sign)

        result = record_onchain_attestation(
            mesh, node_id, signature,
            agent_id=agent_id, aura_score=aura_score,
        )
        result["message_hash"] = message.signing_hash()
        result["address"] = self.address
        return result


__all__ = ["HelixaSigner", "HELIXA_AGENT_ID", "HELIXA_API_BASE"]
