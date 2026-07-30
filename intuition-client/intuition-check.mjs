// intuition-check.mjs — verify SDK, network, and wallet readiness
import { intuitionMainnet, createAtomFromThing } from '@0xintuition/sdk';
import { createPublicClient, http, formatEther } from 'viem';
import { privateKeyToAccount } from 'viem/accounts';
import { readFileSync } from 'fs';

async function main() {
  // 1. Verify network connection
  console.log('=== Intuition Mainnet ===');
  console.log('Chain ID:', intuitionMainnet.id);
  console.log('Name:', intuitionMainnet.name);
  console.log('RPC:', intuitionMainnet.rpcUrls.default.http[0]);

  const publicClient = createPublicClient({
    chain: intuitionMainnet,
    transport: http(),
  });

  try {
    const block = await publicClient.getBlockNumber();
    console.log('Block:', block);
    console.log('✅ Network reachable\n');
  } catch (e) {
    console.log('❌ Network unreachable:', e.message);
    return;
  }

  // 2. Check wallet balances
  const CONTROLLER_KEY = '/opt/data/D0XEDDEV/.agent_fresh_wallet.json';
  const TRADING_KEY = '/opt/data/.env.d0xeddev_populated';

  // Helixa controller wallet
  try {
    const keyData = JSON.parse(readFileSync(CONTROLLER_KEY, 'utf8'));
    const account = privateKeyToAccount(keyData.privateKey);
    const addr = account.address;
    console.log('=== Controller Wallet ===');
    console.log('Address:', addr);
    
    const eth = await publicClient.getBalance({ address: addr });
    console.log('ETH:', formatEther(eth), '(on Intuition L3)');

    // Check USDC (Base USDC might not be on Intuition)
    // Check $TRUST token if known
    console.log('');
  } catch (e) {
    console.log('❌ Controller wallet:', e.message, '\n');
  }

  // 3. Check what our wallets look like
  const wallets = [
    { name: 'Vault/EOA', addr: '0x23129c0472172d75bed1e6dd061301796760ecd9' },
    { name: 'Agent Controller', addr: '0x789Bd4C13eC3E8c4e52E3f02662244D2fd231ce2' },
  ];

  for (const w of wallets) {
    try {
      const eth = await publicClient.getBalance({ address: w.addr });
      console.log(`${w.name}: ${w.addr} — ${formatEther(eth)} ETH on Intuition`);
    } catch (e) {
      console.log(`${w.name}: check failed — ${e.message}`);
    }
  }
}

main().catch(console.error);
