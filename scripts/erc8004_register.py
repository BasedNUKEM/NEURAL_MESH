#!/usr/bin/env python3
"""ERC-8004 Agent Registration — mint NEURAL_MESH identity NFT on Base Mainnet.

ERC-8004 defines three on-chain registries per chain:
  IdentityRegistry  (ERC-721) — agent identity, tokenURI → manifest
  ReputationRegistry         — feedback aggregation
  ValidationRegistry         — verification requests/results

This script registers NEURAL_MESH with the IdentityRegistry on Base Mainnet.
The registration mints an ERC-721 NFT whose tokenURI points to our manifest:
  https://api.d0xeddev.com/mesh/erc8004/manifest

The manifest is already live (GET /mesh/erc8004/manifest in server.py, v0.27.0).
This script performs the ON-CHAIN step: calling ``register(agentURI)`` on the
IdentityRegistry contract and linking the return token ID to Helixa agent #5287.

=== REQUIREMENTS ===
  • funded Base wallet (gas for the mint transaction — ~0.0001-0.0005 ETH)
  • eth-account (pip install eth-account web3)
  • wallet key at /opt/data/.secrets/agent-wallet.key
  • GO signal from D0xedDev (this is an on-chain, gas-costing, public action)

Usage:
  # Dry-run — validates everything, prints what WOULD happen
  python3 scripts/erc8004_register.py --dry-run

  # Execute (REQUIRES user confirmation + funded wallet)
  python3 scripts/erc8004_register.py --execute --manifest-url https://api.d0xeddev.com/mesh/erc8004/manifest
"""
import argparse
import json
import os
import sys

# ─── Constants ─────────────────────────────────────────────────────────────
BASE_RPC = "https://mainnet.base.org"
CHAIN_ID_CAIP = "eip155:8453"
IDENTITY_REGISTRY = "0x8004A169FB4a3325136EB29fA0ceB6D2e539a432"
HELIXA_AGENT_ID = 5287          # user-facing agent identity
HELIXA_AGENT_ID_ALT = 60155     # Helixa internal
DEFAULT_MANIFEST_URL = "https://api.d0xeddev.com/mesh/erc8004/manifest"

# ERC-8004 IdentityRegistry ABI — register(string agentURI) returns uint256
# From: https://eips.ethereum.org/EIPS/eip-8004
REGISTRY_ABI = [
    {
        "inputs": [{"internalType": "string", "name": "agentURI", "type": "string"}],
        "name": "register",
        "outputs": [{"internalType": "uint256", "name": "agentId", "type": "uint256"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "uint256", "name": "tokenId", "type": "uint256"}],
        "name": "tokenURI",
        "outputs": [{"internalType": "string", "name": "", "type": "string"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "totalSupply",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
]


def load_wallet(key_path: str):
    """Load private key, return Account object."""
    with open(key_path) as f:
        key = f.readline().strip()
    if not key.startswith("0x"):
        key = "0x" + key
    from eth_account import Account
    return Account.from_key(key)


def check_manifest(url: str) -> bool:
    """Fetch the manifest and validate structure."""
    import urllib.request
    try:
        req = urllib.request.urlopen(url, timeout=15)
        data = json.loads(req.read())
    except Exception as e:
        print(f"❌ Cannot fetch manifest at {url}: {e}")
        return False
    if data.get("type") != "https://eips.ethereum.org/EIPS/eip-8004#registration-v1":
        print(f"❌ Manifest type mismatch: {data.get('type')}")
        return False
    print(f"✅ Manifest OK — {data.get('name')} ({data.get('registrations', [{}])[0].get('agentId')})")
    print(f"   Services: {[s['name'] for s in data.get('services', [])]}")
    return True


def register(account, manifest_url: str, gas_limit: int = 300000):
    """Call IdentityRegistry.register(agentURI) on Base Mainnet.

    Returns the new token ID (agent ID) or raises."""
    from web3 import Web3
    w3 = Web3(Web3.HTTPProvider(BASE_RPC))
    if not w3.is_connected():
        raise RuntimeError(f"Cannot connect to Base RPC: {BASE_RPC}")

    contract = w3.eth.contract(
        address=Web3.to_checksum_address(IDENTITY_REGISTRY),
        abi=REGISTRY_ABI,
    )

    # Estimated gas
    try:
        gas_est = contract.functions.register(manifest_url).estimate_gas({
            "from": account.address,
        })
        print(f"   Estimated gas: {gas_est}")
    except Exception as e:
        print(f"   ⚠️ Gas estimation failed (will use {gas_limit}): {e}")

    # Build + sign + broadcast
    nonce = w3.eth.get_transaction_count(account.address)
    gas_price = w3.eth.gas_price
    tx = contract.functions.register(manifest_url).build_transaction({
        "from": account.address,
        "nonce": nonce,
        "gas": gas_limit,
        "gasPrice": gas_price,
    })
    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    print(f"   📡 Broadcast: {tx_hash.hex()}")

    # Wait for receipt
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
    if receipt.status != 1:
        raise RuntimeError(f"Transaction reverted! hash={tx_hash.hex()}")

    # Decode the return value
    try:
        log_entry = contract.events.Transfer().process_receipt(receipt)
        if log_entry:
            token_id = log_entry[0]["args"]["tokenId"]
        else:
            # Fallback: parse from receipt logs (topic-3 of Transfer event)
            token_id = int(receipt.logs[0].topics[3].hex(), 16)
    except Exception:
        token_id = "unknown"
    return token_id, tx_hash.hex(), receipt.gasUsed


def main():
    parser = argparse.ArgumentParser(description="ERC-8004 Agent Registration")
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="Validate everything, report, don't send tx (DEFAULT)")
    parser.add_argument("--execute", action="store_true",
                        help="BROADCAST the transaction (costs real gas on Base Mainnet)")
    parser.add_argument("--manifest-url", default=DEFAULT_MANIFEST_URL,
                        help="URI for the registration file (must return valid ERC-8004 manifest)")
    parser.add_argument("--key-path", default="/opt/data/.secrets/agent-wallet.key",
                        help="Path to wallet private key file")
    parser.add_argument("--gas-limit", type=int, default=300000)
    args = parser.parse_args()

    if not args.execute and not args.dry_run:
        args.dry_run = True

    print("=" * 60)
    print("ERC-8004 Agent Registration — NEURAL_MESH on Base")
    print(f"  IdentityRegistry: {IDENTITY_REGISTRY}")
    print("=" * 60)

    # 1. Validate manifest
    print("\n📋 CHECKING MANIFEST")
    if not check_manifest(args.manifest_url):
        sys.exit(1)

    # 2. Load wallet
    print(f"\n🔑 LOADING WALLET from {args.key_path}")
    try:
        account = load_wallet(args.key_path)
        print(f"   Address: {account.address}")
    except Exception as e:
        print(f"   ❌ {e}")
        sys.exit(1)

    # 3. Check balance
    print("\n💰 CHECKING BALANCE (Base Mainnet)")
    from web3 import Web3
    w3 = Web3(Web3.HTTPProvider(BASE_RPC))
    bal = w3.eth.get_balance(account.address)
    bal_eth = w3.from_wei(bal, "ether")
    print(f"   Balance: {bal_eth:.6f} ETH (wei: {bal})")
    if args.execute and bal_eth < 0.0005:
        print(f"   ⚠️  BALANCE TOO LOW for mint (~0.0002-0.0005 ETH needed).")
        print(f"   Fund the wallet first, then rerun with --execute.")
        sys.exit(1)

    # 4. Registration contract status
    print(f"\n📊 CONTRACT STATUS")
    contract = w3.eth.contract(
        address=Web3.to_checksum_address(IDENTITY_REGISTRY),
        abi=REGISTRY_ABI,
    )
    try:
        total = contract.functions.totalSupply().call()
        print(f"   Total agents registered: {total}")
    except Exception as e:
        print(f"   totalSupply() call failed: {e}")

    # 5. Execute or dry-run
    if args.execute:
        print("\n⛓️  BROADCASTING REGISTRATION (this costs gas)")
        try:
            token_id, tx_hash, gas_used = register(account, args.manifest_url, args.gas_limit)
            print(f"\n🎉 REGISTERED!")
            print(f"   Transaction: {tx_hash}")
            print(f"   Agent ID (token): {token_id}")
            print(f"   Gas used: {gas_used}")
            print(f"   View on BaseScan: https://basescan.org/tx/{tx_hash}")
            print(f"   Agent profile: https://basescan.org/nft/{IDENTITY_REGISTRY}/{token_id}")
            print(f"\n🟦 Next: wire the agent ID {token_id} into the manifest registrations.")
            print(f"   Helmixa agent #5287 / {HELIXA_AGENT_ID_ALT} now has on-chain identity.")

            # Update manifest with the new registration
            print(f"\n💡 To update the manifest endpoint, add to registrations:")
            print(f'   {{"agentId": {token_id}, "agentRegistry": "{CHAIN_ID_CAIP}:{IDENTITY_REGISTRY}"}}')
        except Exception as e:
            print(f"\n❌ Registration failed: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
    else:
        print(f"\n🧪 DRY-RUN — would call:")
        print(f"   IdentityRegistry.register(\"{args.manifest_url}\")")
        print(f"   From: {account.address}")
        print(f"   Gas limit: {args.gas_limit}")
        print(f"   Chain: Base Mainnet ({CHAIN_ID_CAIP})")
        print(f"\n   ✅ Everything validates. To execute:")
        print(f"   python3 scripts/erc8004_register.py --execute")
        print(f"   (Requires ~0.0003 ETH on {account.address})")


if __name__ == "__main__":
    main()
