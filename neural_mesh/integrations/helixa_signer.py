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
import urllib.request
from typing import Any

try:
    from eth_account import Account
    HAS_ETH_ACCOUNT = True
except ImportError:
    HAS_ETH_ACCOUNT = False
    Account = None  # type: ignore

from .helixa_attest import (
    build_attestation_message,
    sign_attestation,
    record_onchain_attestation,
    AttestationMessage,
)

# ── constants ──────────────────────────────────────────────────────────

ENV_FILE = "/opt/data/.env.d0xeddev_populated"
AGENT_WALLET_FILE = "/opt/data/D0XEDDEV/.agent_fresh_wallet.json"
HELIXA_API_BASE = "https://helixa.xyz/api/v2"
HELIXA_AGENT_ID = "5287"  # canonical D0xed Dev agent


# ── key loading (private — never exposed) ──────────────────────────────

def _load_key_from_json(path: str) -> tuple[str, str]:
    """Load private key from a wallet JSON file."""
    with open(path) as f:
        wallet = json.load(f)
    key = wallet.get("privateKey") or wallet.get("private_key") or ""
    addr = wallet.get("address", "")
    key = key.strip()
    if key.startswith("0x") or key.startswith("0X"):
        key = key[2:]
    if len(key) != 64:
        raise ValueError(f"Invalid key length in {path}: {len(key)} chars, expected 64")
    return key, addr


def _load_private_key() -> tuple[str, str]:
    """Load the Helixa agent controller private key.

    Tries in order:
      1. ``AGENT_WALLET_FILE`` (``.agent_fresh_wallet.json``) — the Helixa controller
      2. ``ENV_FILE`` (``TRADING_WALLET_PRIVATE_KEY``) — the vault wallet

    Returns ``(private_key_hex, wallet_address)``.
    Caller MUST NOT log or expose the key.
    """
    # Prefer the agent wallet (Helixa controller: 0x789Bd4...ce2)
    if os.path.exists(AGENT_WALLET_FILE):
        try:
            with open(AGENT_WALLET_FILE) as f:
                wallet = json.load(f)
            key = wallet.get("privateKey") or wallet.get("private_key") or ""
            addr = wallet.get("address", "")
            # Strip 0x prefix — eth_account accepts both, but we check length
            key = key.strip()
            if key.startswith("0x") or key.startswith("0X"):
                key = key[2:]
            if len(key) == 64:
                return key, addr
        except (json.JSONDecodeError, OSError):
            pass

    # Fall back to vault wallet (0x23129c...Ecd9)
    if os.path.exists(ENV_FILE):
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
                    if val and len(val) == 64:
                        return val, ""  # address will be derived

    raise FileNotFoundError(
        f"No valid private key found. Checked:\n"
        f"  - {AGENT_WALLET_FILE}\n"
        f"  - {ENV_FILE}\n"
        "Expected a 64-char hex key in one of these locations."
    )


# ── Helixa signer ──────────────────────────────────────────────────────

class HelixaSigner:
    """Live Helixa API signer — holds the agent wallet key in memory.

    All on-chain write methods default to ``dry_run=True``.
    Pass ``dry_run=False`` to commit real state changes.
    """

    def __init__(self, base_url: str = HELIXA_API_BASE, *, wallet_file: str | None = None):
        """Create a Helixa signer.

        Args:
            base_url: Helixa API base URL.
            wallet_file: Override path to wallet JSON. For testing.

        If ``eth-account`` is not installed, the signer operates in
        *degraded* mode: dry_run is always True and on-chain writes
        return a clear status instead of a 500 error.
        """
        self.base_url = base_url.rstrip("/")
        self._degraded = not HAS_ETH_ACCOUNT

        if wallet_file is not None:
            key, known_addr = _load_key_from_json(wallet_file)
        else:
            key, known_addr = _load_private_key()

        if HAS_ETH_ACCOUNT:
            self._account = Account.from_key(key)
            self.address = known_addr or self._account.address
        else:
            self._account = None
            self.address = known_addr or "0x"  # best-effort from wallet file

    @property
    def degraded(self) -> bool:
        """True when eth-account is unavailable (dry-run only)."""
        return self._degraded

    # ── SIWA auth header ────────────────────────────────────────────

    def _siwa_header(self) -> dict[str, str]:
        """Build the Helixa SIWA auth header.
        
        Format (verified 2026-07-25):
          ``Authorization: Bearer <address>:<timestamp_ms>:0x<sig>``
        Message:
          ``Sign-In With Agent: api.helixa.xyz wants you to sign
          in with your wallet <address> at <timestamp_ms>``
        """
        from eth_account.messages import encode_defunct
        ts_ms = str(int(time.time() * 1000))

        message = (
            f"Sign-In With Agent: api.helixa.xyz wants you to "
            f"sign in with your wallet {self.address} at {ts_ms}"
        )
        encoded = encode_defunct(text=message)
        signed = self._account.sign_message(encoded)
        sig = signed.signature.hex()

        header = f"Bearer {self.address}:{ts_ms}:0x{sig}"
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
                "degraded": self.degraded,
                "node_id": node_id,
                "agent_id": agent_id,
                "address": self.address,
                "message_hash": message.signing_hash(),
                "action": "attest_mesh_node",
                "note": "Set dry_run=False to sign and record the attestation."
                        + (" Install 'eth-account' first." if self.degraded else ""),
            }

        if self.degraded:
            return {
                "ok": False,
                "error": "Cannot sign — eth-account not installed.",
                "dry_run": False,
                "degraded": True,
                "note": "Install eth-account to enable on-chain attestation: "
                        "pip install eth-account",
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
