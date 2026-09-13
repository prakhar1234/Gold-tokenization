# Gold Tokenization — Architecture Document

DLT-based local blockchain network for on-chain tokens backed by physical gold reserves.

**Token:** AUT (Aurum Token) | **Precision:** 4 decimals (0.0001 grams)
**Consensus:** Proof of Authority (round-robin) | **Model:** Account-based
**Language:** Python 3 | **API:** Flask REST | **Crypto:** ECDSA secp256k1

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Module Reference](#2-module-reference)
3. [REST API Reference](#3-rest-api-reference)
4. [Data Flows](#4-data-flows)
5. [Reserve Invariant](#5-reserve-invariant)
6. [Cryptography](#6-cryptography)
7. [Network Protocol](#7-network-protocol)
8. [Configuration](#8-configuration)
9. [Test Suite](#9-test-suite)
10. [CLI Tools](#10-cli-tools)
11. [Dependency Graph](#11-dependency-graph)

---

## 1. System Overview

### Directory Structure

```
GoldTokenization/
  blockchain/
    __init__.py
    block.py              Block, BlockHeader, Blockchain classes
    transaction.py        Transaction model + TransactionType enum
    merkle.py             Merkle tree for transaction integrity
    consensus.py          PoA consensus engine (+ optional PoW)
    state.py              Account state management (balances, nonces)
  crypto/
    __init__.py
    keys.py               ECDSA key generation, signing, verification
    hashing.py            SHA-256, double hashing utilities
  network/
    __init__.py
    node.py               Flask REST API per node
    peer.py               Peer discovery and communication
    sync.py               Chain synchronization protocol
    mempool.py            Transaction pool management
  gold/
    __init__.py
    reserve.py            Gold reserve proof management + audit trail
    token.py              Token supply tracking, minting rules, burn logic
  wallet/
    __init__.py
    wallet.py             Wallet creation, encrypted storage, signing
  cli/
    __init__.py
    start_network.py      Spin up N local nodes
    create_wallet.py      Generate new wallet
    send_transaction.py   Submit transactions
    query_chain.py        Inspect chain state
  tests/
    conftest.py           Shared pytest fixtures
    test_block.py         test_transaction.py    test_merkle.py
    test_consensus.py     test_network.py        test_gold_reserve.py
    test_wallet.py        test_state.py          test_integration.py
  config.py               Network configuration
  requirements.txt
  .env.example
  .gitignore
```

### Component Wiring (per node)

```
┌─────────────────────────────────────────────────────────┐
│  Flask REST API  (network/node.py)                      │
│                                                         │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │  Blockchain  │  │   Mempool    │  │ PeerManager   │  │
│  │  (chain +   │  │  (pending    │  │ (peers, bcast │  │
│  │   state)    │  │   txs)       │  │  sync)        │  │
│  └──────┬──────┘  └──────┬───────┘  └───────┬───────┘  │
│         │                │                   │          │
│  ┌──────┴──────┐  ┌──────┴───────┐  ┌───────┴───────┐  │
│  │ GoldToken   │  │  ChainSync   │  │  Consensus    │  │
│  │ Manager     │  │  (longest    │  │  (PoA round   │  │
│  │ (reserve +  │  │   chain)     │  │   robin)      │  │
│  │  mint/burn) │  │              │  │               │  │
│  └──────┬──────┘  └──────────────┘  └───────────────┘  │
│         │                                               │
│  ┌──────┴──────┐                                        │
│  │ Reserve     │                                        │
│  │ Ledger      │                                        │
│  │ (invariant) │                                        │
│  └─────────────┘                                        │
└─────────────────────────────────────────────────────────┘
```

---

## 2. Module Reference

### 2.1 `config.py` — Network Configuration

**Dataclass: `NetworkConfig`**

| Field | Type | Default | Purpose |
|-------|------|---------|---------|
| `network_id` | str | `"gold-mainnet"` | Network identifier |
| `network_name` | str | `"Gold Tokenization Network"` | Display name |
| `token_name` | str | `"Aurum Token"` | Token name |
| `token_symbol` | str | `"AUT"` | Token ticker |
| `token_decimals` | int | `4` | Precision (0.0001g) |
| `block_time_seconds` | int | `10` | Target block interval |
| `max_transactions_per_block` | int | `100` | Max TXs per block |
| `genesis_timestamp` | float | `0.0` | Block 0 timestamp |
| `consensus_type` | str | `"poa"` | `"poa"` or `"pow"` |
| `pow_difficulty` | int | `4` | PoW leading zeros (if used) |
| `validators` | List[str] | `[]` | PoA validator addresses |
| `default_port` | int | `5100` | Node listen port |
| `max_peers` | int | `50` | Max peer connections |
| `sync_interval_seconds` | int | `30` | Sync frequency |
| `mempool_max_size` | int | `5000` | Max pending TXs |
| `mempool_tx_timeout_seconds` | int | `3600` | TX expiration (1hr) |
| `chain_data_dir` | str | `"data"` | Persistence directory |
| `wallet_dir` | str | `"wallets"` | Wallet storage |
| `mining_reward` | float | `0.0` | Mining reward (0 = pure gold model) |

**Constant:** `DEFAULT_CONFIG` — singleton default instance.

---

### 2.2 `crypto/hashing.py` — Hashing Utilities

| Function | Signature | Purpose |
|----------|-----------|---------|
| `sha256` | `(data: bytes) -> str` | SHA-256 hex digest |
| `double_sha256` | `(data: bytes) -> str` | Hash-of-hash (Bitcoin-style) |
| `hash_string` | `(s: str) -> str` | Hash UTF-8 string |
| `hash_dict` | `(d: dict) -> str` | Deterministic dict hash |
| `canonical_json` | `(obj: Any) -> str` | Sorted JSON, no whitespace |

### 2.3 `crypto/keys.py` — ECDSA Key Operations

| Function | Signature | Purpose |
|----------|-----------|---------|
| `generate_keypair` | `() -> Tuple[str, str, str]` | New secp256k1 keypair → (private_hex, public_hex, address) |
| `public_key_to_address` | `(public_key_hex: str) -> str` | `"0x"` + SHA-256(pubkey)[:40] |
| `sign_message` | `(private_key_hex: str, message: str) -> str` | Deterministic ECDSA signature (RFC 6979) |
| `verify_signature` | `(public_key_hex: str, message: str, signature_hex: str) -> bool` | Verify signature |
| `private_key_to_public_key` | `(private_key_hex: str) -> str` | Derive public key from private |

---

### 2.4 `blockchain/transaction.py` — Transaction Model

**Enum: `TransactionType`** — `MINT`, `TRANSFER`, `BURN`

**Dataclass: `Transaction`**

| Field | Type | Notes |
|-------|------|-------|
| `tx_type` | TransactionType | MINT / TRANSFER / BURN |
| `sender` | str | Address or `"NETWORK"` for mint |
| `recipient` | str | Address or `"BURN"` for burn |
| `amount` | float | Auto-rounded to 4 decimals |
| `nonce` | int | Replay protection counter |
| `timestamp` | float | Auto-set to `time.time()` |
| `public_key` | str | Sender's public key |
| `signature` | str | ECDSA signature |
| `tx_hash` | str | Hash of signable_data + signature |

| Method | Signature | Purpose |
|--------|-----------|---------|
| `signable_data` | `() -> str` | Canonical JSON of tx fields (excl. sig/hash) |
| `compute_hash` | `() -> str` | Hash(signable_data + signature) |
| `sign` | `(private_key_hex: str) -> None` | Sign and update hash |
| `verify` | `() -> bool` | Verify signature + basic validity |
| `to_dict` | `() -> dict` | Serialize |
| `from_dict` | `(data: dict) -> Transaction` | Deserialize |

---

### 2.5 `blockchain/state.py` — Account State

**Dataclass: `AccountState`**

| Field | Type | Purpose |
|-------|------|---------|
| `balances` | Dict[str, float] | Address → AUT balance |
| `nonces` | Dict[str, int] | Address → TX count |

| Method | Signature | Purpose |
|--------|-----------|---------|
| `get_balance` | `(address: str) -> float` | Balance (default 0.0, 4 decimals) |
| `get_nonce` | `(address: str) -> int` | Nonce (default 0) |
| `validate_transaction` | `(tx: Transaction) -> Optional[str]` | Pre-flight: amount > 0, sender rules, balance, nonce |
| `apply_transaction` | `(tx: Transaction) -> Optional[str]` | Validate then mutate state |
| `apply_transactions` | `(transactions: List[Transaction]) -> Optional[str]` | Apply list sequentially |
| `rebuild_from_chain` | `(blocks: list) -> None` | Reset and replay all blocks |
| `copy` | `() -> AccountState` | Deep copy |
| `to_dict` | `() -> dict` | Serialize |

**State transitions by TX type:**

| Type | Balances | Nonces |
|------|----------|--------|
| MINT | `recipient += amount` | — |
| TRANSFER | `sender -= amount`, `recipient += amount` | `sender += 1` |
| BURN | `sender -= amount` | `sender += 1` |

---

### 2.6 `blockchain/merkle.py` — Merkle Tree

| Function | Signature | Purpose |
|----------|-----------|---------|
| `build_merkle_tree` | `(tx_hashes: List[str]) -> List[List[str]]` | Full tree, leaves to root. Duplicates last leaf if odd count. |
| `compute_merkle_root` | `(tx_hashes: List[str]) -> str` | Root hash. Empty list → SHA-256("") |
| `get_merkle_proof` | `(tx_hashes: List[str], index: int) -> List[Tuple[str, str]]` | Proof path: list of (sibling_hash, "left"/"right") |
| `verify_merkle_proof` | `(tx_hash: str, proof: List[Tuple[str, str]], merkle_root: str) -> bool` | Verify inclusion proof |

---

### 2.7 `blockchain/consensus.py` — Consensus Engines

**Dataclass: `PoAConsensus`** (primary)

| Method | Signature | Purpose |
|--------|-----------|---------|
| `add_validator` | `(address: str) -> None` | Register validator (no dupes) |
| `remove_validator` | `(address: str) -> None` | Deregister validator |
| `get_validator_for_block` | `(block_index: int) -> Optional[str]` | Round-robin: `validators[(index - 1) % len]`. Genesis → None. |
| `is_valid_validator` | `(address: str, block_index: int) -> bool` | Check expected validator |
| `to_dict` / `from_dict` | — | Serialization |

**Dataclass: `PoWConsensus`** (optional/demo)

| Method | Signature | Purpose |
|--------|-----------|---------|
| `mine_block` | `(block_header_data: str) -> (nonce, hash)` | Find nonce with N leading zeros |
| `validate_pow` | `(block_header_data: str, nonce: int, block_hash: str) -> bool` | Verify PoW solution |

---

### 2.8 `blockchain/block.py` — Block & Blockchain

**Dataclass: `BlockHeader`**

| Field | Type | Purpose |
|-------|------|---------|
| `index` | int | Block height |
| `timestamp` | float | Creation time |
| `previous_hash` | str | Hash link to prior block |
| `merkle_root` | str | Merkle root of transactions |
| `validator` | str | PoA validator address |
| `nonce` | int | PoW nonce (0 for PoA) |

**Dataclass: `Block`**

| Field | Type | Purpose |
|-------|------|---------|
| `header` | BlockHeader | Block metadata |
| `transactions` | List[Transaction] | Block transactions |
| `block_hash` | str | SHA-256 of header + transactions |

**Class: `Blockchain`**

| Method | Signature | Purpose |
|--------|-----------|---------|
| `_create_genesis_block` | `() -> None` | Block 0: index=0, validator="genesis", previous_hash="0"*64 |
| `last_block` | `-> Block` (property) | Most recent block |
| `height` | `-> int` (property) | Chain length |
| `create_block` | `(transactions, validator, timestamp?) -> Optional[Block]` | Validate TXs against state copy; compute merkle root; apply state; append; return block or None |
| `validate_block` | `(block, previous_block) -> Optional[str]` | Check index, previous hash, block hash, merkle root, TX signatures |
| `validate_chain` | `(chain?) -> Optional[str]` | Validate entire chain + rebuild state |
| `replace_chain` | `(new_chain: List[Block]) -> bool` | Adopt if longer and valid; rebuild state |
| `save_to_file` | `(filepath: str) -> None` | Persist to JSON |
| `load_from_file` | `(filepath: str) -> bool` | Load, validate, rebuild state |
| `to_dict` | `() -> dict` | Serialize |

---

### 2.9 `gold/reserve.py` — Reserve Ledger

**Dataclass: `ReserveProof`**

| Field | Type | Default | Purpose |
|-------|------|---------|---------|
| `proof_id` | str | auto-computed | Unique ID (hash[:16]) |
| `custodian` | str | `""` | Entity holding gold |
| `amount_grams` | float | `0.0` | Physical gold weight |
| `purity` | float | `0.999` | Gold purity (0–1) |
| `certificate_ref` | str | `""` | External certificate reference |
| `timestamp` | float | now | Creation time |
| `verified` | bool | False | Verification flag |

| Method | Purpose |
|--------|---------|
| `effective_grams()` | `amount_grams * purity` (4 decimal precision) |

**Class: `ReserveLedger`**

| Field | Type | Purpose |
|-------|------|---------|
| `reserves` | Dict[str, ReserveProof] | proof_id → proof mapping |
| `total_minted` | float | Cumulative AUT minted |
| `total_burned` | float | Cumulative AUT burned |

| Property / Method | Signature | Purpose |
|-------------------|-----------|---------|
| `total_reserved` | `-> float` | Sum of effective_grams from all proofs |
| `circulating_supply` | `-> float` | `total_minted - total_burned` |
| `reserve_ratio` | `-> float` | `total_reserved / circulating_supply` |
| `add_reserve` | `(proof) -> None` | Register reserve proof |
| `remove_reserve` | `(proof_id) -> Optional[ReserveProof]` | Remove reserve |
| **`can_mint`** | **`(amount) -> bool`** | **INVARIANT CHECK: `(minted + amount - burned) <= reserved`** |
| `record_mint` | `(amount) -> bool` | Update counter if invariant holds |
| `force_record_mint` | `(amount) -> None` | Bypass check (chain replay) |
| `record_burn` | `(amount) -> None` | Update burned counter |
| `reset_counters` | `() -> None` | Zero both counters (for rebuild) |
| `get_audit_summary` | `() -> dict` | All key metrics |

---

### 2.10 `gold/token.py` — Token Manager

**Class: `GoldTokenManager`**

Coordinates `Blockchain` + `ReserveLedger` for high-level token operations.

| Method | Signature | Purpose |
|--------|-----------|---------|
| `add_reserve` | `(custodian, amount_grams, purity?, certificate_ref?) -> ReserveProof` | Register reserve |
| `create_mint_transaction` | `(recipient, amount, auth_priv, auth_pub) -> Optional[Transaction]` | **Checks `can_mint()` first.** Returns None if invariant violated. |
| `create_transfer_transaction` | `(sender, recipient, amount, priv, pub) -> Optional[Transaction]` | Checks balance. Gets nonce from state. |
| `create_burn_transaction` | `(sender, amount, priv, pub) -> Optional[Transaction]` | Checks balance. Gets nonce from state. |
| `process_minted_block` | `(block) -> None` | Record MINT/BURN after block is mined |
| `rebuild_from_chain` | `() -> None` | Reset counters, replay all blocks (force_record_mint) |
| `get_token_info` | `() -> dict` | Token metadata + supply metrics |

---

### 2.11 `wallet/wallet.py` — Wallet

**Key derivation:** PBKDF2-HMAC-SHA256, 100,000 iterations, random 16-byte salt.
**Encryption:** AES-256-GCM with random 12-byte nonce.

**Dataclass: `Wallet`**

| Field | Type | Purpose |
|-------|------|---------|
| `private_key` | str | Hex-encoded private key |
| `public_key` | str | Hex-encoded public key |
| `address` | str | `"0x"` + 40 hex chars |

| Method | Signature | Purpose |
|--------|-----------|---------|
| `create` | `() -> Wallet` | Generate fresh keypair |
| `from_private_key` | `(private_key_hex) -> Wallet` | Reconstruct from private key |
| `sign` | `(message: str) -> str` | Sign with private key |
| `save_encrypted` | `(filepath, password) -> None` | AES-256-GCM encrypted JSON |
| `load_encrypted` | `(filepath, password) -> Optional[Wallet]` | Decrypt; None on failure |
| `to_public_dict` | `() -> dict` | `{address, public_key}` (no private key) |

**Encrypted file format:**
```json
{
  "salt": "<hex>",
  "nonce": "<hex>",
  "ciphertext": "<hex>",
  "address": "0x..."
}
```

---

### 2.12 `network/mempool.py` — Transaction Pool

**Class: `Mempool`** (thread-safe via `threading.Lock`)

| Method | Signature | Purpose |
|--------|-----------|---------|
| `size` | `-> int` (property) | Pending TX count |
| `add_transaction` | `(tx) -> Optional[str]` | Verify sig; check dupe/capacity; add |
| `remove_transaction` | `(tx_hash) -> Optional[Transaction]` | Remove by hash |
| `remove_transactions` | `(tx_hashes: List[str]) -> None` | Batch remove (post-mining) |
| `get_transactions` | `(limit?) -> List[Transaction]` | Sorted by timestamp, optionally limited |
| `get_transaction` | `(tx_hash) -> Optional[Transaction]` | Lookup by hash |
| `contains` | `(tx_hash) -> bool` | Membership check |
| `clear_expired` | `() -> int` | Remove TXs older than timeout |
| `clear` | `() -> None` | Empty pool |
| `to_list` | `() -> List[dict]` | Serialize all TXs |

---

### 2.13 `network/peer.py` — Peer Manager

**Class: `PeerManager`** (thread-safe)

| Method | Signature | Purpose |
|--------|-----------|---------|
| `peers` | `-> List[str]` (property) | All peer URLs |
| `peer_count` | `-> int` (property) | Number of peers |
| `register_peer` | `(peer_url) -> bool` | Add peer (not self, not full) |
| `remove_peer` | `(peer_url) -> None` | Remove peer |
| `broadcast_transaction` | `(tx_dict) -> Dict[str, bool]` | POST /transactions to all peers |
| `broadcast_block` | `(block_dict) -> Dict[str, bool]` | POST /blocks/receive to all peers |
| `register_with_peer` | `(peer_url) -> bool` | Register this node with remote peer |
| `health_check` | `(peer_url) -> bool` | GET /health |
| `get_chain_length` | `(peer_url) -> Optional[int]` | GET /chain/length |
| `get_chain` | `(peer_url) -> Optional[list]` | GET /chain (full download) |
| `prune_dead_peers` | `() -> List[str]` | Remove unresponsive peers |

---

### 2.14 `network/sync.py` — Chain Synchronization

**Class: `ChainSynchronizer`**

| Method | Signature | Purpose |
|--------|-----------|---------|
| `sync` | `() -> Tuple[bool, str]` | Query all peers for chain length; download longest; validate; replace if longer; rebuild reserve ledger |
| `receive_block` | `(block_dict) -> Tuple[bool, str]` | Accept block if it extends chain; trigger sync if ahead; validate and apply state |

**Fork resolution:** longest valid chain wins. Full validation before adoption.

---

## 3. REST API Reference

All endpoints are per-node. Default base URL: `http://127.0.0.1:5100`

### Health & Status

| Method | Path | Response | Purpose |
|--------|------|----------|---------|
| GET | `/health` | `{status, node_url, chain_height, peers, mempool_size, network_id}` | Node health check |

### Chain

| Method | Path | Response | Purpose |
|--------|------|----------|---------|
| GET | `/chain` | `{chain: [Block], length: int}` | Full chain |
| GET | `/chain/length` | `{length: int}` | Chain height only |
| GET | `/blocks/<index>` | Block dict or 404 | Single block by index |

### Transactions

| Method | Path | Body | Response | Purpose |
|--------|------|------|----------|---------|
| POST | `/transactions` | Transaction dict | `{tx_hash, status}` (201) or error (400) | Submit TX to mempool + broadcast |
| GET | `/mempool` | — | `{transactions: [TX], size: int}` | Pending transactions |

### Balances

| Method | Path | Response | Purpose |
|--------|------|----------|---------|
| GET | `/balance/<address>` | `{address, balance, nonce}` | Account balance and nonce |

### Mining

| Method | Path | Body | Response | Purpose |
|--------|------|------|----------|---------|
| POST | `/mine` | `{validator: str}` | `{message, block: Block}` (200) or error (400) | Mine block from mempool TXs |
| POST | `/blocks/receive` | Block dict | `{accepted: bool, message}` | Receive block from peer |

### Peers

| Method | Path | Body | Response | Purpose |
|--------|------|------|----------|---------|
| POST | `/nodes/register` | `{node_url: str}` | `{message, peers}` (201) | Register peer |
| GET | `/nodes` | — | `{peers: [URLs], count}` | List peers |

### Sync

| Method | Path | Response | Purpose |
|--------|------|----------|---------|
| POST | `/sync` | `{replaced: bool, message}` | Trigger chain sync with peers |

### Token & Reserves

| Method | Path | Body | Response | Purpose |
|--------|------|------|----------|---------|
| GET | `/token/info` | — | `{name, symbol, decimals, total_minted, total_burned, circulating_supply, total_reserved_grams, reserve_ratio}` | Token supply metrics |
| GET | `/reserves` | — | `{reserves: [ReserveProof], audit: summary}` | All reserve proofs |
| POST | `/reserves` | `{custodian, amount_grams, purity?, certificate_ref?}` | `{proof, total_reserved}` (201) | Register reserve |

---

## 4. Data Flows

### 4.1 Mint Flow

```
Client                    Node API                 Blockchain          Reserve Ledger
  │                          │                        │                     │
  │  POST /reserves          │                        │                     │
  │  {custodian, grams}  ──> │                        │                     │
  │                          │ ─── add_reserve() ─────│─────────────────>   │
  │                          │                        │                     │
  │  POST /transactions      │                        │                     │
  │  {MINT, 500 AUT}    ──> │                        │                     │
  │                          │ ── verify signature ──>│                     │
  │                          │ ── validate state ────>│                     │
  │                          │ ── can_mint(500)? ─────│─────────────────>   │
  │                          │                        │    (minted+500      │
  │                          │                        │     - burned)       │
  │                          │                        │     ≤ reserved?     │
  │                          │ ── add to mempool ───> │     YES ✓           │
  │                          │ ── broadcast to peers  │                     │
  │  201 {tx_hash}       <── │                        │                     │
  │                          │                        │                     │
  │  POST /mine              │                        │                     │
  │  {validator}         ──> │                        │                     │
  │                          │ ── create_block() ────>│                     │
  │                          │    (validate + apply   │                     │
  │                          │     state: recipient   │                     │
  │                          │     += 500)            │                     │
  │                          │ ── process_minted ─────│─── record_mint ──> │
  │                          │ ── broadcast block     │                     │
  │  200 {block}         <── │                        │                     │
```

### 4.2 Transfer Flow

```
1. token_manager.create_transfer_transaction(sender, recipient, amount, ...)
   ├── Check: state.get_balance(sender) >= amount
   ├── Get: state.get_nonce(sender)
   ├── Create: Transaction(TRANSFER, sender, recipient, amount, nonce)
   └── Sign with sender's private key

2. POST /transactions → verify sig → validate state → mempool → broadcast

3. POST /mine → create_block()
   ├── state.balances[sender] -= amount
   ├── state.balances[recipient] += amount
   └── state.nonces[sender] += 1

Note: No reserve ledger interaction — transfers don't affect supply.
```

### 4.3 Burn Flow

```
1. token_manager.create_burn_transaction(sender, amount, ...)
   ├── Check: state.get_balance(sender) >= amount
   ├── Get: state.get_nonce(sender)
   ├── Create: Transaction(BURN, sender, "BURN", amount, nonce)
   └── Sign with sender's private key

2. POST /transactions → verify sig → validate state → mempool → broadcast

3. POST /mine → create_block()
   ├── state.balances[sender] -= amount
   ├── state.nonces[sender] += 1
   └── reserve_ledger.record_burn(amount)
       └── total_burned += amount → circulating_supply decreases
```

### 4.4 Chain Sync Flow

```
Node B                   Node A (longer chain)
  │                          │
  │  POST /sync (triggered)  │
  │                          │
  │  GET /chain/length ────> │
  │  <──── {length: 5}       │
  │                          │
  │  (local length: 2,       │
  │   A is longer)           │
  │                          │
  │  GET /chain ───────────> │
  │  <──── {chain: [...]}    │
  │                          │
  │  validate_chain(new)     │
  │  replace_chain(new)      │
  │    ├── self.chain = new  │
  │    └── rebuild state     │
  │                          │
  │  rebuild_from_chain()    │
  │    ├── reset_counters()  │
  │    └── replay all blocks │
  │        (force_record)    │
```

### 4.5 Block Reception Flow

```
Node A (miner)           Node B (peer)
  │                          │
  │  POST /blocks/receive    │
  │  {block}             ──> │
  │                          │ ── check: block.index == len(chain)?
  │                          │    ├── behind: "already known"
  │                          │    ├── ahead: trigger sync()
  │                          │    └── extends: continue ↓
  │                          │
  │                          │ ── validate_block(block, last_block)
  │                          │    ├── index link ✓
  │                          │    ├── previous_hash ✓
  │                          │    ├── block_hash ✓
  │                          │    ├── merkle_root ✓
  │                          │    └── TX signatures ✓
  │                          │
  │                          │ ── apply transactions to state
  │                          │ ── append to chain
  │                          │ ── remove TXs from mempool
  │                          │ ── update reserve counters
  │                          │    (force_record_mint / record_burn)
  │                          │
  │  <── {accepted: true}    │
```

---

## 5. Reserve Invariant

### The Golden Rule

```
total_minted - total_burned  ≤  total_reserved_gold_grams
```

Every AUT in circulation is backed by physical gold. Burning AUT releases reserve capacity for future minting.

### Enforcement Points

| # | Location | When | Mechanism |
|---|----------|------|-----------|
| 1 | `ReserveLedger.can_mint()` | Any mint check | `(minted + amount - burned) <= reserved` |
| 2 | `GoldTokenManager.create_mint_transaction()` | Creating MINT TX | Returns `None` if `can_mint()` is false |
| 3 | `node.py` POST `/transactions` | API submission | Rejects with 400 if `can_mint()` is false |
| 4 | `ReserveLedger.record_mint()` | Recording mint | Double-checks invariant before recording |
| 5 | `GoldTokenManager.rebuild_from_chain()` | After chain sync | Replays history to reconcile counters |

### Example Scenario

```
Reserve: 1000g gold (purity 1.0)

Mint 500 AUT → minted=500, burned=0   → 500 ≤ 1000 ✓  ratio=2.00
Burn 50 AUT  → minted=500, burned=50  → 450 ≤ 1000 ✓  ratio=2.22
Mint 550 AUT → minted=1050, burned=50 → 1000 ≤ 1000 ✓  ratio=1.00
Mint 1 AUT   → minted=1051, burned=50 → 1001 ≤ 1000 ✗  BLOCKED
```

---

## 6. Cryptography

### Key Generation & Signing

- **Curve:** secp256k1 (same as Bitcoin/Ethereum)
- **Key format:** Raw hex-encoded (no PEM/DER)
- **Address:** `"0x"` + first 40 hex chars of SHA-256(public_key) = 20 bytes
- **Signing:** Deterministic ECDSA (RFC 6979) over SHA-256(message)
- **Library:** `ecdsa` Python package

### Hashing

- **Block hash:** SHA-256 of canonical_json(header + transactions)
- **TX hash:** SHA-256 of signable_data + signature
- **Merkle tree:** Binary tree, SHA-256 pair hashing, leaf duplication for odd counts

### Wallet Encryption

- **KDF:** PBKDF2-HMAC-SHA256, 100,000 iterations, 16-byte random salt
- **Cipher:** AES-256-GCM, 12-byte random nonce
- **Library:** `cryptography` (hazmat primitives)
- **Stored fields:** salt, nonce, ciphertext (all hex), address (plaintext for identification)

---

## 7. Network Protocol

### Peer-to-Peer Communication

All inter-node communication uses HTTP/JSON via Flask endpoints:

| Action | Endpoint | Direction |
|--------|----------|-----------|
| Register peer | POST `/nodes/register` | Bidirectional (all-to-all at startup) |
| Health check | GET `/health` | Query → Response |
| Chain length | GET `/chain/length` | Query → Response |
| Full chain download | GET `/chain` | Query → Response |
| Broadcast transaction | POST `/transactions` | Originator → All peers |
| Broadcast block | POST `/blocks/receive` | Miner → All peers |

### Consensus: Proof of Authority

- **Validator selection:** Round-robin. Block N is validated by `validators[(N-1) % count]`.
- **Genesis block:** index=0, validator="genesis", no transactions.
- **Permissioned:** Validators are configured at network startup.

### Fork Resolution

- **Rule:** Longest valid chain wins.
- **Trigger:** Block received with index ahead of local chain.
- **Process:** Download full chain from longest peer → validate entirely → replace local chain → rebuild state + reserve counters.

---

## 8. Configuration

### Environment Variables (`.env.example`)

```
NODE_HOST=127.0.0.1
NODE_PORT=5100
NETWORK_ID=gold-mainnet
VALIDATOR_ADDRESS=
WALLET_PASSWORD=
```

### Dependencies (`requirements.txt`)

```
flask==3.1.1              Web framework (node API)
flask-cors==5.0.1         CORS support
requests==2.32.3          HTTP client (peer communication)
ecdsa==0.19.0             ECDSA signing/verification
cryptography==44.0.0      AES-256-GCM wallet encryption
python-dotenv==1.1.0      Environment variable loading
pytest==8.3.4             Test runner
pytest-flask==1.3.0       Flask test client fixtures
```

---

## 9. Test Suite

**80 tests** across 9 files. Run with: `pytest tests/ -v`

| File | Class | Tests | Coverage |
|------|-------|-------|----------|
| `test_block.py` | TestBlockHeader | 1 | Header serialization |
| | TestBlock | 2 | Hash determinism, serialization |
| | TestBlockchain | 5 | Genesis, create block, validate, save/load, replace chain |
| `test_transaction.py` | TestTransaction | 7 | MINT/TRANSFER/BURN creation, invalid sig, serialization, precision, unsigned |
| `test_merkle.py` | TestMerkleTree | 7 | Empty, single, 2/3/4 hashes, determinism, ordering |
| | TestMerkleProof | 5 | Proof generation/verification for 1/2/4 elements, invalid cases |
| `test_consensus.py` | TestPoAConsensus | 5 | Round-robin, validator check, add/remove, empty, serialization |
| | TestPoWConsensus | 2 | Mine and validate, invalid PoW |
| `test_state.py` | TestAccountState | 8 | Initial, mint, transfer, insufficient balance, invalid nonce, burn, copy, sender check |
| `test_gold_reserve.py` | TestReserveProof | 2 | Creation, serialization |
| | TestReserveLedger | 9 | Add, can_mint, capacity, burn recovery, supply, ratio, audit, invariant, serialization |
| | TestGoldTokenManager | 3 | Mint creation, reserve block, token info |
| `test_wallet.py` | TestWallet | 6 | Create, from_private_key, sign, encrypted save/load, wrong password, public dict |
| `test_network.py` | TestNodeAPI | 15 | All REST endpoints: health, chain, blocks, balance, submit+mine, peers, reserves, token info, error cases |
| `test_integration.py` | TestEndToEnd | 3 | Full lifecycle (reserve→mint→transfer→burn→verify), invariant enforcement, API lifecycle |

---

## 10. CLI Tools

### Start Network

```bash
python -m cli.start_network --nodes 3 --base-port 5100
```

Spins up N Flask nodes on sequential ports, creates validators `["validator-0", ...]`, registers all nodes as peers.

### Create Wallet

```bash
python -m cli.create_wallet --name alice --dir wallets
python -m cli.create_wallet --name alice --no-encrypt   # testing only
```

### Send Transaction

```bash
python -m cli.send_transaction --type mint --wallet wallets/authority.json \
  --recipient 0x... --amount 500.0 --node http://127.0.0.1:5100

python -m cli.send_transaction --type transfer --wallet wallets/alice.json \
  --recipient 0x... --amount 200.0

python -m cli.send_transaction --type burn --wallet wallets/bob.json \
  --amount 50.0
```

### Query Chain

```bash
python -m cli.query_chain health --node http://127.0.0.1:5100
python -m cli.query_chain chain
python -m cli.query_chain block 1
python -m cli.query_chain balance 0x...
python -m cli.query_chain token
python -m cli.query_chain reserves
python -m cli.query_chain mempool
python -m cli.query_chain peers
```

---

## 11. Dependency Graph

```
                    ┌─────────┐
                    │ config  │
                    └────┬────┘
                         │
         ┌───────────────┼───────────────┐
         │               │               │
    ┌────▼────┐    ┌─────▼─────┐   ┌─────▼─────┐
    │ crypto/ │    │blockchain/│   │  wallet/   │
    │ hashing │    │           │   │  wallet    │
    │  keys   │    │  tx       │   └─────┬─────┘
    └────┬────┘    │  state    │         │
         │        │  merkle   │    uses crypto/keys
         │        │  consensus│    uses cryptography
         │        │  block    │
         │        └─────┬─────┘
         │              │
         │    ┌─────────┼──────────┐
         │    │         │          │
    ┌────▼────▼┐  ┌─────▼─────┐ ┌─▼──────────┐
    │  gold/   │  │ network/  │ │  network/   │
    │ reserve  │  │  mempool  │ │   peer      │
    │  token   │  │  sync     │ │             │
    └────┬─────┘  └─────┬─────┘ └──────┬──────┘
         │              │              │
         └──────────┬───┴──────────────┘
                    │
              ┌─────▼─────┐
              │ network/  │
              │   node    │
              │ (Flask)   │
              └─────┬─────┘
                    │
              ┌─────▼─────┐
              │   cli/    │
              │ start     │
              │ wallet    │
              │ send_tx   │
              │ query     │
              └───────────┘
```

---

*Generated from the GoldTokenization codebase. 80 tests passing.*
