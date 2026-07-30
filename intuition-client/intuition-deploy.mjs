// intuition-deploy.mjs — Deploy D0xedDev atoms + triples to Intuition TESTNET
import { createAtomFromThing, createAtomFromString, createTripleStatement, globalSearch } from '@0xintuition/sdk';
import { createPublicClient, createWalletClient, http, formatEther } from 'viem';
import { privateKeyToAccount } from 'viem/accounts';
import { readFileSync } from 'fs';

// ─── Config ────────────────────────────────────────────────────────────────
const TESTNET = {
  id: 13579,
  name: 'Intuition Testnet',
  nativeCurrency: { name: 'tTRUST', symbol: 'tTRUST', decimals: 18 },
  rpcUrls: { default: { http: ['https://testnet.rpc.intuition.systems'] } },
};

// Load controller wallet
const KEY_FILE = '/opt/data/D0XEDDEV/.agent_fresh_wallet.json';
const keyData = JSON.parse(readFileSync(KEY_FILE, 'utf8'));
const account = privateKeyToAccount(keyData.privateKey);

const publicClient = createPublicClient({ chain: TESTNET, transport: http() });
const walletClient = createWalletClient({ chain: TESTNET, transport: http(), account });

// MultiVault address for testnet
const TESTNET_MULTIVAULT = '0x3870419B49A7F9E26717cDf582dC1f8Ec8B13521'; // chain-specific

async function main() {
  console.log('🟦 D0XEDDEV → Intuition Testnet Deploy');
  console.log('========================================');
  console.log('Wallet:', account.address);
  
  const balance = await publicClient.getBalance({ address: account.address });
  console.log('Balance:', formatEther(balance), 'tTRUST\n');

  if (balance === 0n) {
    console.log('❌ No tTRUST! Get testnet tokens at https://testnet.hub.intuition.systems/');
    console.log('   Wallet address:', account.address);
    return;
  }

  // ─── Step 1: Create D0XDEDEV Agent Atom ───────────────────────────
  console.log('[1/4] Creating D0xed Dev agent atom...');
  try {
    const agentAtom = await createAtomFromThing(
      { walletClient, publicClient, address: TESTNET_MULTIVAULT },
      {
        url: 'https://d0xeddev.com',
        name: 'D0xed Dev',
        description: 'Autonomous AI agent on Base L2 — NEURAL_MESH associative memory, x402 payment routing, Helixa #5287 on-chain identity, scam detection pipeline. First agent to complete dual-chain x402 settlement (Solana+Base). 🟦😎',
        image: 'https://d0xeddev.com/agent.png',
      }
    );
    console.log('  ✅ Agent atom created!');
    console.log('     TX:', agentAtom.transactionHash);
    console.log('     Atom ID:', agentAtom.state?.termId || agentAtom.state, '\n');
  } catch (e) {
    console.log('  ⚠️ Agent atom:', e.message?.substring(0, 200), '\n');
  }

  // ─── Step 2: Create NEURAL_MESH Atom ──────────────────────────────
  console.log('[2/4] Creating NEURAL_MESH atom...');
  try {
    const meshAtom = await createAtomFromThing(
      { walletClient, publicClient, address: TESTNET_MULTIVAULT },
      {
        url: 'https://github.com/BasedNUKEM/NEURAL_MESH',
        name: 'NEURAL_MESH',
        description: 'Self-aware agent memory stack with Helixa on-chain attestation. 92+ active nodes, 10 provenance sources, LLM-powered DREAM synthesis, associative memory dynamics. First agent memory system mapped to Intuition Knowledge Graph.',
      }
    );
    console.log('  ✅ NEURAL_MESH atom created!');
    console.log('     TX:', meshAtom.transactionHash);
    console.log('     Atom ID:', meshAtom.state?.termId || meshAtom.state, '\n');
  } catch (e) {
    console.log('  ⚠️ NEURAL_MESH atom:', e.message?.substring(0, 200), '\n');
  }

  // ─── Step 3: Create Helixa Identity Atom ──────────────────────────
  console.log('[3/4] Creating Helixa #5287 identity atom...');
  try {
    const helixaAtom = await createAtomFromThing(
      { walletClient, publicClient, address: TESTNET_MULTIVAULT },
      {
        url: 'https://helixa.xyz/agent/5287',
        name: 'Helixa #5287',
        description: 'On-chain agent identity verified by Helixa. ERC-8004 agentId 60155, 24 verified skills, cred score 59. Controller: 0x789Bd4. Framework: custom. Soulbound. Registered on Intuition Knowledge Graph.',
      }
    );
    console.log('  ✅ Helixa atom created!');
    console.log('     TX:', helixaAtom.transactionHash);
    console.log('     Atom ID:', helixaAtom.state?.termId || helixaAtom.state, '\n');
  } catch (e) {
    console.log('  ⚠️ Helixa atom:', e.message?.substring(0, 200), '\n');
  }

  // ─── Step 4: Create Scam Detection Atom ───────────────────────────
  console.log('[4/4] Creating Scam Detection atom...');
  try {
    const scamAtom = await createAtomFromThing(
      { walletClient, publicClient, address: TESTNET_MULTIVAULT },
      {
        url: 'https://d0xeddev.com/api/scam-score',
        name: 'D0xedDev Scam Detection',
        description: '4-stage forensic scam detection pipeline: contract validation, source verification, on-chain forensics, narrative-vs-reality. Integrated with PCMedicalist anti-scam protocol. 0.01 USDC/ping via x402.',
      }
    );
    console.log('  ✅ Scam Detection atom created!');
    console.log('     TX:', scamAtom.transactionHash);
    console.log('     Atom ID:', scamAtom.state?.termId || scamAtom.state, '\n');
  } catch (e) {
    console.log('  ⚠️ Scam Detection atom:', e.message?.substring(0, 200), '\n');
  }

  // ─── Summary ──────────────────────────────────────────────────────
  console.log('========================================');
  console.log('✅ Deploy complete! Check explorer:');
  console.log('   https://testnet.explorer.intuition.systems/address/' + account.address);
}

main().catch(console.error);
