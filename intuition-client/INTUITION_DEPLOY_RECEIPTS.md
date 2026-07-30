# Intuition Mainnet Deployment Receipts

Date: 2026-07-30
Network: Intuition Mainnet
Chain ID: 1155
RPC: https://rpc.intuition.systems
Explorer: https://explorer.intuition.systems
Signer / creator: `0x23129c0472172D75bEd1e6dd061301796760Ecd9`
MultiVault: `0x6E35cF57A41fA15eA0EaE9C33e751b01A784Fe7e`

## Entity Atoms

| Label | Tx | Term ID |
|---|---|---|
| D0xedDev | `0xd01d24d148e0b2b2e7364b7ab69a2547a0d053a965bbd9684da7974b570c8a7a` | `0x0d2a3c63c6edee7e1113ddb55b3d6884c0da23505c21df29ce7834937ba0b466` |
| NEURAL_MESH | `0xc66522a0d8c8ca7462292c92637d6970771b3d7c68bcaa8618a919a73fda46d2` | `0xc306d7c016e7edc78eced957d95fd8e909fd8deeb176000ac61da5c6b0b0dde8` |
| Helixa #5287 | `0x8dab8c3397b35acdf04c1a77c87536b03079a815a6af42fbd5c46d6431a71955` | `0x52eb08d2846b91aa6adf85c74ad91309b8b51194b16768f7ec0de21483ffab29` |
| Scam Detection Agent | `0xba4af75f063ca8b060ebcf11e852d9a82490b9469613906dae97749e869a78cf` | `0x16fc6806fcd4f6855139ac26aae731da3ccd17929e20549a5848ef7532fa9c94` |

## Predicate Atoms

| Label | Tx | Term ID |
|---|---|---|
| composedOf | `0x6feeb0e08a46400df02a6250c45e7db2b4985c5f2a583963a49f25d9ae23a45d` | `0x10a9c91f16b59d6d13868961a4f617a3a687ccebbc5f798547f6a9530335ff83` |
| identifiedBy | `0xfb451833a52f70b9c283f6bdfc9b0e8a68fae8f2594f0cf9c3677fc70e020ed8` | `0x2300fe05850919051753574837c2f5146fd5260957479acf3e1ef3ee3a56c57d` |
| provides | `0xf8ab9d60eea0c8773d397eab275112c52bdf5c2626e9d59bc9bb8e91ad8a817d` | `0x0c491df3d39c1427d41f8bd263a9a818cbd71f4d317b78768c9067a5fb4249d7` |
| powers | `0xd2dc3842b1b4d0043f14292854d647a1d1de0e375b5e9c474165519a896102f9` | `0xefca4e759fb62aeb103a8b5ad7481bf2349c5ddf3964455e2d40a8bb97b5cd53` |

## Triple Batch

Tx: `0x7b063ec91bb832661243bb3d2919ed48ec6cdc93d2d6298e60b32bff91865cde`
Block: `7875199`
Status: success
Cost math: `triple_cost + min_deposit = 0.100000000002 + 0.01 = 0.110000000002 TRUST` per triple.
Batch value: `0.440000000008 TRUST`.

| Statement | Triple term ID |
|---|---|
| D0xedDev → composedOf → NEURAL_MESH | `0x9bca7031cac3d6c29339c901a746dac88cbf58b511a5d2d2782bbda0581f7727` |
| D0xedDev → identifiedBy → Helixa #5287 | `0xd2569c98216a7f2ee9dc2aa7b6e4a0fe351c542e52c315a1b46f9d40d2bc808b` |
| D0xedDev → provides → Scam Detection Agent | `0x86353065c8f8b390667fa48b5706afaffb546e87652d0aac5474e77901fa4aec` |
| NEURAL_MESH → powers → Scam Detection Agent | `0xae5a695d550e65af0dc27cb3432cabec5586a446832c94537eee154db854838e` |

## Balance

Before triple batch: `80.823816218967923549 TRUST`
After triple batch: `80.383798249269923549 TRUST`

## Explorer Links

- Triple batch: https://explorer.intuition.systems/tx/0x7b063ec91bb832661243bb3d2919ed48ec6cdc93d2d6298e60b32bff91865cde
- Creator address: https://explorer.intuition.systems/address/0x23129c0472172D75bEd1e6dd061301796760Ecd9?tab=txs
