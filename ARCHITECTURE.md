# Gold Tokenization — Technical Architecture

A permissioned distributed ledger for gold-backed digital tokens. Physical gold reserves are registered on-chain as reserve proofs, and AUT (Aurum Token) issuance is constrained by a system-wide invariant: **circulating supply can never exceed total reserved gold grams**.

**Token:** AUT (Aurum Token) | **Precision:** 4 decimals (0.0001 grams)
**Consensus:** Proof of Authority (round-robin) | **Model:** Account-based
**Language:** Python 3 | **API:** Flask REST | **Crypto:** ECDSA secp256k1
**Frontend:** Next.js 14 | **Tests:** 187 passing

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Module Reference](#2-module-reference)
3. [Trading System](#3-trading-system)
4. [REST API Reference](#4-rest-api-reference)
5. [Data Flows](#5-data-flows)
6. [Reserve Invariant](#6-reserve-invariant)
7. [Cryptography](#7-cryptography)
8. [Network Protocol](#8-network-protocol)
9. [Logging & Observability](#9-logging--observability)
10. [Frontend](#10-frontend)
11. [Reconciliation & Audit](#11-reconciliation--audit)
12. [Configuration](#12-configuration)
13. [Test Suite](#13-test-suite)
14. [CLI Tools](#14-cli-tools)
15. [Dependency Graph](#15-dependency-graph)

---

## 1. System Overview

### Directory Structure

```
GoldTokenization/
  blockchain/
    block.py              Block, BlockHeader, Blockchain classes
    transaction.py        Transaction model + TransactionType enum
    merkle.py             Merkle tree for transaction integrity
    consensus.py          PoA consensus engine (+ optional PoW)
    state.py              Account state management (balances, nonces)
  crypto/
    keys.py               ECDSA key generation, signing, verification
    hashing.py            SHA-256, double hashing utilities
  network/
    node.py               Flask REST API per node
    peer.py               Peer discovery and communication
    sync.py               Chain synchronization protocol
    mempool.py            Transaction pool management
  gold/
    reserve.py            Gold reserve proof management + audit trail
    token.py              Token supply tracking, minting rules, burn logic
  trading/
    order.py              Limit order model with ECDSA signatures
    order_book.py         Thread-safe order book (price-time priority)
    matching_engine.py    Order matching + on-chain TRANSFER settlement
    trade.py              Executed trade records
  wallet/
    wallet.py             Wallet creation, encrypted storage, signing
  cli/
    start_network.py      Spin up N local nodes
    create_wallet.py      Generate new wallet
    send_transaction.py   Submit transactions
    query_chain.py        Inspect chain state
    reconcile.py          Cross-node reconciliation audit
  frontend/               Next.js 14 dashboard (port 3002)
    src/app/              Pages: vault, wallets, portfolio, trading
    src/app/api/vault/    Proxy routes to Flask backend
    src/components/       React components (TradingClient, etc.)
  tests/                  187 tests across 17 files
  logging_config.py       Structured logging (JSON file + console)
  config.py               Network configuration
  requirements.txt
```

### Component Wiring (per node)

```
┌──────────────────────────────────────────────────────────────────┐
│  Flask REST API  (network/node.py)                               │
│                                                                  │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────┐           │
│  │  Blockchain  │  │   Mempool    │  │ PeerManager   │           │
│  │  (chain +   │  │  (pending    │  │ (peers, bcast │           │
│  │   state)    │  │   txs)       │  │  sync)        │           │
│  └──────┬──────┘  └──────┬───────┘  └───────┬───────┘           │
│         │                │                   │                   │
│  ┌──────┴──────┐  ┌──────┴───────┐  ┌───────┴───────┐           │
│  │ GoldToken   │  │  ChainSync   │  │  Consensus    │           │
│  │ Manager     │  │  (longest    │  │  (PoA round   │           │
│  │ (reserve +  │  │   chain)     │  │   robin)      │           │
│  │  mint/burn) │  │              │  │               │           │
│  └──────┬──────┘  └──────────────┘  └───────────────┘           │
│         │                                                        │
│  ┌──────┴──────┐  ┌──────────────────────────────────┐           │
│  │ Reserve     │  │ Trading Engine                    │           │
│  │ Ledger      │  │  OrderBook + MatchingEngine       │           │
│  │ (invariant) │  │  (settle via on-chain TRANSFER)   │           │
│  └─────────────┘  └──────────────────────────────────┘           │
└──────────────────────────────────────────────────────────────────┘
         │
    ┌────▼──────────────────────────────────┐
    │  Structured Logging (logging_config)   │
    │  Console: human-readable (INFO)        │
    │  File:    JSON rotating (DEBUG)        │
    │  → logs/gold_node.log (10MB x 5)      │
    └───────────────────────────────────────┘
```

---

## 2. Module Reference

### 2.1 `config.py` — Network Configuration

**Dataclass: `NetworkConfig`**

| Field | Type | Default | Purpose |
|-------|------|---------|---------|
| `network_id` | str | `"gold-mainnet"` | Network identifier |
| `token_name` | str | `"Aurum Token"` | Token name |
| `token_symbol` | str | `"AUT"` | Token ticker |
| `token_decimals` | int | `4` | Precision (0.0001g) |
| `block_time_seconds` | int | `10` | Target block interval |
| `max_transactions_per_block` | int | `100` | Max TXs per block |
| `consensus_type` | str | `"poa"` | `"poa"` or `"pow"` |
| `validators` | List[str] | `[]` | PoA validator addresses |
| `default_port` | int | `5100` | Node listen port |
| `max_peers` | int | `50` | Max peer connections |
| `mempool_max_size` | int | `5000` | Max pending TXs |
| `mempool_tx_timeout_seconds` | int | `3600` | TX expiration (1hr) |
| `mining_reward` | float | `0.0` | Mining reward (0 = pure gold model) |

### 2.2 `crypto/` — Cryptographic Primitives

**`hashing.py`**

| Function | Purpose |
|----------|---------|
| `sha256(data: bytes) -> str` | SHA-256 hex digest |
| `double_sha256(data: bytes) -> str` | Hash-of-hash (Bitcoin-style) |
| `hash_string(s: str) -> str` | Hash UTF-8 string |
| `hash_dict(d: dict) -> str` | Deterministic dict hash |
| `canonical_json(obj) -> str` | Sorted JSON, no whitespace |

**`keys.py`**

| Function | Purpose |
|----------|---------|
| `generate_keypair() -> (priv, pub, addr)` | New secp256k1 keypair |
| `public_key_to_address(pub_hex) -> str` | `"0x"` + SHA-256(pubkey)[:40] |
| `sign_message(priv_hex, message) -> str` | Deterministic ECDSA (RFC 6979) |
| `verify_signature(pub_hex, message, sig_hex) -> bool` | Verify signature |
| `private_key_to_public_key(priv_hex) -> str` | Derive public key |

### 2.3 `blockchain/transaction.py` — Transaction Model

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

**State transitions by TX type:**

| Type | Balances | Nonces |
|------|----------|--------|
| MINT | `recipient += amount` | — |
| TRANSFER | `sender -= amount`, `recipient += amount` | `sender += 1` |
| BURN | `sender -= amount` | `sender += 1` |

### 2.4 `blockchain/state.py` — Account State

**Dataclass: `AccountState`** — manages `balances: Dict[str, float]` and `nonces: Dict[str, int]`.

Key methods: `validate_transaction()` pre-flight checks (amount > 0, balance, nonce), `apply_transaction()` validates then mutates state, `rebuild_from_chain()` replays all blocks.

### 2.5 `blockchain/merkle.py` — Merkle Tree

Binary hash tree using SHA-256 pair hashing with leaf duplication for odd counts.

| Function | Purpose |
|----------|---------|
| `compute_merkle_root(tx_hashes)` | Root hash of transactions |
| `get_merkle_proof(tx_hashes, index)` | Inclusion proof path |
| `verify_merkle_proof(tx_hash, proof, root)` | Verify inclusion |

### 2.6 `blockchain/consensus.py` — Consensus Engines

**`PoAConsensus`** (primary): Round-robin validator selection. Block N validated by `validators[(N-1) % count]`. Genesis block has validator="genesis".

**`PoWConsensus`** (optional): Find nonce producing hash with N leading zeros.

### 2.7 `blockchain/block.py` — Block & Blockchain

**`BlockHeader`**: index, timestamp, previous_hash, merkle_root, validator, nonce.

**`Block`**: header + transactions + block_hash (SHA-256 of canonical JSON).

**`Blockchain`**: chain of blocks + account state.

| Method | Purpose |
|--------|---------|
| `create_block(txs, validator)` | Validate TXs against state copy, compute merkle root, apply state, append |
| `validate_block(block, prev)` | Check index, previous hash, block hash, merkle root, TX signatures |
| `replace_chain(new_chain)` | Adopt if longer and valid; rebuild state |
| `save_to_file(path)` / `load_from_file(path)` | JSON persistence |

### 2.8 `gold/reserve.py` — Reserve Ledger

**`ReserveProof`**: custodian, amount_grams, purity, certificate_ref, depositor_address. `effective_grams() = amount_grams * purity`.

**`ReserveLedger`**: tracks all reserve proofs plus global `total_minted` / `total_burned` counters and per-depositor indexes.

| Method | Purpose |
|--------|---------|
| `can_mint(amount) -> bool` | **INVARIANT: `(minted + amount - burned) <= reserved`** |
| `record_mint(amount) -> bool` | Update counter if invariant holds |
| `record_burn(amount)` | Update burned counter |
| `get_depositor_portfolio(addr)` | Full depositor summary (reserved, minted, capacity) |
| `get_audit_summary()` | All key metrics |

### 2.9 `gold/token.py` — Token Manager

Coordinates `Blockchain` + `ReserveLedger` for high-level operations: `add_reserve()`, `create_mint_transaction()`, `create_transfer_transaction()`, `create_burn_transaction()`, `process_minted_block()`, `rebuild_from_chain()`.

### 2.10 `wallet/wallet.py` — Wallet

- **KDF:** PBKDF2-HMAC-SHA256, 100,000 iterations, 16-byte random salt
- **Cipher:** AES-256-GCM, 12-byte random nonce

Methods: `create()`, `from_private_key()`, `sign()`, `save_encrypted()`, `load_encrypted()`.

### 2.11 `network/mempool.py` — Transaction Pool

Thread-safe via `threading.Lock`. Methods: `add_transaction()` (verify sig, check dupe/capacity), `remove_transactions()` (batch post-mining), `get_transactions()`, `clear_expired()`.

### 2.12 `network/peer.py` — Peer Manager

Thread-safe. Methods: `register_peer()`, `broadcast_transaction()`, `broadcast_block()`, `register_with_peer()`, `health_check()`, `get_chain_length()`, `get_chain()`, `prune_dead_peers()`.

### 2.13 `network/sync.py` — Chain Synchronization

`sync()`: query all peers for chain length, download longest, validate, replace if longer, rebuild reserve ledger.

`receive_block()`: accept if extends chain, trigger sync if ahead, validate and apply state.

**Fork resolution:** longest valid chain wins. Full validation before adoption.

---

## 3. Trading System

The trading system implements a **central limit order book (CLOB)** for AUT/USD with on-chain settlement.

### 3.1 `trading/order.py` — Limit Order

| Field | Type | Purpose |
|-------|------|---------|
| `side` | OrderSide | `BUY` or `SELL` |
| `address` | str | Trader's blockchain address |
| `price` | float | USD per AUT |
| `amount` | float | Total AUT amount |
| `remaining_amount` | float | Unfilled portion |
| `status` | OrderStatus | `OPEN`, `PARTIALLY_FILLED`, `FILLED`, `CANCELLED` |
| `order_id` | str | UUID |
| `signature` | str | ECDSA signature over order fields |
| `_private_key` | str | Held in-memory for settlement signing (PoC) |

Orders are cryptographically signed to prove wallet ownership.

### 3.2 `trading/order_book.py` — Order Book

Thread-safe order book with price-time priority:

- **Bids** (buy): sorted by price descending, then timestamp ascending
- **Asks** (sell): sorted by price ascending, then timestamp ascending

Methods: `add_order()`, `cancel_order()` (owner-only), `get_sorted_bids()`, `get_sorted_asks()`, `get_spread()`.

### 3.3 `trading/matching_engine.py` — Matching Engine

When a new order arrives, `process_order()`:

1. Adds it to the order book
2. Attempts matching against the opposite side
3. **Crossing check**: BUY at $50 matches ASK at $48, not ASK at $52
4. **Maker price wins**: resting order's price used as execution price
5. **Self-trade prevention**: same-address orders don't match
6. **On-chain settlement**: creates a `TRANSFER` transaction (seller → buyer) and submits to mempool

The `_settle()` method:
- Verifies seller has sufficient balance
- Creates and signs a `TRANSFER` transaction
- Tracks pending nonces per seller to prevent collisions across multiple fills in the same block
- Submits to mempool for inclusion in the next mined block

### 3.4 `trading/trade.py` — Trade Record

Records: buyer_address, seller_address, price, amount, buy_order_id, sell_order_id, tx_hash (settlement transaction), trade_id, timestamp.

### 3.5 Trading Flow

```
Alice places SELL 50 AUT @ $55
  └─> OrderBook: ask added

Bob places BUY 30 AUT @ $55
  └─> OrderBook: bid added
  └─> MatchingEngine: prices cross ($55 >= $55)
      └─> _settle(): TRANSFER 30 AUT alice → bob
          └─> Mempool: settlement tx pending
      └─> Trade record created
      └─> Bob's order: FILLED
      └─> Alice's order: PARTIALLY_FILLED (20 remaining)

POST /mine
  └─> Settlement tx included in block
  └─> Balances updated on-chain
```

---

## 4. REST API Reference

All endpoints are per-node. Default base URL: `http://127.0.0.1:5100`

### Health & Chain

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Node health (status, chain_height, peers, mempool_size, network_id) |
| GET | `/chain` | Full chain with all blocks |
| GET | `/chain/length` | Chain height only |
| GET | `/blocks/<index>` | Single block by index |

### Transactions & Mining

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/transactions` | Submit TX to mempool + broadcast to peers |
| GET | `/mempool` | Pending transactions |
| POST | `/mine` | Mine block from mempool (body: `{validator}`) |
| POST | `/blocks/receive` | Receive block from peer |
| GET | `/balance/<address>` | Account balance and nonce |

### Token & Reserves

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/token/info` | Token supply metrics (minted, burned, circulating, reserved, ratio) |
| GET | `/reserves` | All reserve proofs + audit summary |
| POST | `/reserves` | Register gold reserve (body: `{custodian, amount_grams, purity?, certificate_ref?, depositor_address?}`) |

### Trading

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/orders` | Place limit order (body: `{side, address, price, amount, public_key, private_key}`) |
| GET | `/orders` | List open orders (query: `?address=` for filtering) |
| GET | `/orders/book` | Order book snapshot (bids + asks) |
| DELETE | `/orders/<order_id>` | Cancel order (body: `{address}`) |
| GET | `/trades` | Recent trades (query: `?limit=`) |
| GET | `/trades/<address>` | Trades for a specific address |
| GET | `/market/summary` | Market metrics (last_price, best_bid, best_ask, spread, volume_24h) |

### Peers & Sync

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/nodes/register` | Register peer (body: `{node_url}`) |
| GET | `/nodes` | List peers |
| POST | `/sync` | Trigger chain sync with peers |

### Wallets & Portfolio

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/wallets` | Create new wallet (body: `{name}`) |
| GET | `/wallets` | List all wallets (address only) |
| GET | `/portfolio/<address>` | Depositor portfolio (reserved, minted, capacity) |
| GET | `/transactions/<address>` | Transaction history for address |

---

## 5. Data Flows

### 5.1 Mint Flow

```
Client                    Node API                 Blockchain          Reserve Ledger
  │                          │                        │                     │
  │  POST /reserves          │                        │                     │
  │  {custodian, grams}  ──> │ ─── add_reserve() ─────│─────────────────>   │
  │                          │                        │                     │
  │  POST /transactions      │                        │                     │
  │  {MINT, 500 AUT}    ──> │ ── verify signature ──>│                     │
  │                          │ ── can_mint(500)? ─────│─────────────────>   │
  │                          │                        │     ≤ reserved?     │
  │                          │ ── add to mempool      │     YES ✓           │
  │                          │ ── broadcast to peers  │                     │
  │  201 {tx_hash}       <── │                        │                     │
  │                          │                        │                     │
  │  POST /mine              │                        │                     │
  │  {validator}         ──> │ ── create_block() ────>│                     │
  │                          │    (state: recipient   │                     │
  │                          │     += 500)            │                     │
  │                          │ ── process_minted ─────│─── record_mint ──> │
  │                          │ ── broadcast block     │                     │
  │  200 {block}         <── │                        │                     │
```

### 5.2 Transfer Flow

```
1. Create Transaction(TRANSFER, sender, recipient, amount, nonce)
   └── Sign with sender's private key

2. POST /transactions → verify sig → validate state → mempool → broadcast

3. POST /mine → create_block()
   ├── state.balances[sender] -= amount
   ├── state.balances[recipient] += amount
   └── state.nonces[sender] += 1

No reserve ledger interaction — transfers don't affect supply.
```

### 5.3 Burn Flow

```
1. Create Transaction(BURN, sender, "BURN", amount, nonce)
   └── Sign with sender's private key

2. POST /transactions → verify sig → validate state → mempool → broadcast

3. POST /mine → create_block()
   ├── state.balances[sender] -= amount
   ├── state.nonces[sender] += 1
   └── reserve_ledger.record_burn(amount) → circulating_supply decreases
```

### 5.4 Trade Settlement Flow

```
Trader A (seller)                 MatchingEngine                Trader B (buyer)
      │                                │                              │
      │  POST /orders {SELL}           │                              │
      │  ─────────────────────────>    │                              │
      │  order added to book           │                              │
      │                                │     POST /orders {BUY}       │
      │                                │  <───────────────────────    │
      │                                │                              │
      │                                │── prices cross?              │
      │                                │   YES: execute match         │
      │                                │                              │
      │                                │── _settle()                  │
      │                                │   ├── check seller balance   │
      │                                │   ├── create TRANSFER tx     │
      │                                │   │   (seller → buyer)       │
      │                                │   ├── sign with seller key   │
      │                                │   └── submit to mempool      │
      │                                │                              │
      │                                │── Trade record created       │
      │                                │                              │
      │              POST /mine → settlement tx in block              │
      │              balances update on-chain                         │
```

### 5.5 Chain Sync Flow

```
Node B                   Node A (longer chain)
  │                          │
  │  GET /chain/length ────> │
  │  <──── {length: 5}       │
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
```

### 5.6 Block Reception Flow

```
Node A (miner)           Node B (peer)
  │                          │
  │  POST /blocks/receive    │
  │  {block}             ──> │
  │                          │── block.index == len(chain)?
  │                          │   ├── behind: "already known"
  │                          │   ├── ahead: trigger sync()
  │                          │   └── extends: validate + append
  │                          │
  │                          │── validate_block()
  │                          │   ├── index link, previous_hash ✓
  │                          │   ├── block_hash, merkle_root ✓
  │                          │   └── TX signatures ✓
  │                          │
  │                          │── apply transactions to state
  │                          │── remove TXs from mempool
  │                          │── update reserve counters
  │                          │
  │  <── {accepted: true}    │
```

---

## 6. Reserve Invariant

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

### Example

```
Reserve: 1000g gold (purity 1.0)

Mint 500 AUT → minted=500, burned=0   → 500 ≤ 1000 ✓  ratio=2.00
Burn 50 AUT  → minted=500, burned=50  → 450 ≤ 1000 ✓  ratio=2.22
Mint 550 AUT → minted=1050, burned=50 → 1000 ≤ 1000 ✓  ratio=1.00
Mint 1 AUT   → minted=1051, burned=50 → 1001 ≤ 1000 ✗  BLOCKED
```

---

## 7. Cryptography

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
- **Stored fields:** salt, nonce, ciphertext (all hex), address (plaintext)

---

## 8. Network Protocol

### Peer-to-Peer Communication

All inter-node communication uses HTTP/JSON via Flask endpoints:

| Action | Endpoint | Direction |
|--------|----------|-----------|
| Register peer | POST `/nodes/register` | Bidirectional at startup |
| Health check | GET `/health` | Query → Response |
| Chain length | GET `/chain/length` | Query → Response |
| Full chain download | GET `/chain` | Query → Response |
| Broadcast transaction | POST `/transactions` | Originator → All peers |
| Broadcast block | POST `/blocks/receive` | Miner → All peers |

### Consensus: Proof of Authority

- **Validator selection:** Round-robin. Block N validated by `validators[(N-1) % count]`.
- **Genesis block:** index=0, validator="genesis", no transactions.
- **Permissioned:** Validators configured at network startup.

### Fork Resolution

- **Rule:** Longest valid chain wins.
- **Trigger:** Block received with index ahead of local chain.
- **Process:** Download full chain from longest peer → validate entirely → replace local chain → rebuild state + reserve counters.

---

## 9. Logging & Observability

### Configuration (`logging_config.py`)

`setup_logging()` configures the root logger with two handlers:

| Handler | Format | Level | Destination |
|---------|--------|-------|-------------|
| Console | `[timestamp] LEVEL logger: message` | INFO | stderr |
| Rotating File | JSON (one object per line) | DEBUG | `logs/gold_node.log` |

- **File rotation:** 10 MB per file, 5 backup files
- **Idempotent:** safe to call multiple times (guard flag prevents duplicate handlers)
- **Third-party quieting:** werkzeug and urllib3 loggers set to WARNING

### Log Levels by Category

| Level | What Gets Logged |
|-------|------------------|
| **DEBUG** | State validation failures, health check failures (expected), mempool add/remove |
| **INFO** | Node init, block mined/accepted, chain replaced, peer registered, tx submitted, trade executed, reserve added, wallet saved |
| **WARNING** | Network failures (peer broadcast/sync), malformed wallet files, order/settlement rejections, chain validation failures |
| **ERROR** | Silent exception catches (receive_block post-processing, wallet decryption — no traceback to avoid key material leak) |

### JSON Log Format

```json
{
  "timestamp": "2026-10-09 14:30:00,000",
  "level": "INFO",
  "logger": "network.node",
  "message": "Block 5 mined by validator-0 with 3 txs"
}
```

### Initialization Points

1. `cli/start_network.py` `main()` — primary entry point
2. `network/node.py` `create_node()` — defensive fallback (idempotent guard prevents duplicates)

---

## 10. Frontend

### Stack

- **Framework:** Next.js 14 (App Router) on port 3002
- **UI:** React 18, Tailwind CSS, IBM Plex Sans/Mono
- **Theme:** Dark background (`#0a0e14`)
- **API Proxy:** Next.js API routes forward requests to Flask (default `http://127.0.0.1:5100`)

### Pages

| Route | Page | Purpose |
|-------|------|---------|
| `/` | — | Redirects to `/vault` |
| `/vault` | Reserve Dashboard | Blockchain health, token info, gold reserves |
| `/wallets` | Wallet Manager | Create and list wallets |
| `/portfolio` | Client Portfolio | Per-depositor reserve and mint capacity |
| `/trading` | Trading Terminal | Order book, place orders, trade history |

### Trading UI (`TradingClient.tsx`)

- **Market metrics bar:** Last Price, Best Bid, Best Ask, Spread, 24h Volume
- **Order book:** Side-by-side bids (green) and asks (red) with price/amount/total
- **Place Order form:** Side toggle (BUY/SELL), price, amount, address, public key, private key
- **My Open Orders:** Filterable by address, with cancel buttons
- **Recent Trades:** Latest executed trades with buyer/seller/price/amount
- **Auto-refresh:** Polls market data every 5 seconds

### API Proxy Routes (`src/app/api/vault/`)

The frontend proxies all requests through Next.js API routes to the Flask backend:

| Frontend Route | Flask Endpoint |
|---------------|----------------|
| `GET /api/vault/trading` | `/market/summary` + `/orders/book` + `/trades` |
| `POST /api/vault/trading` | `POST /orders` |
| `DELETE /api/vault/trading` | `DELETE /orders/<id>` |

---

## 11. Reconciliation & Audit

### `cli/reconcile.py`

A standalone auditor that independently verifies the entire blockchain state across all nodes. Run with:

```bash
python -m cli.reconcile --base-port 5100 --num-nodes 3 --verbose
```

### Checks Performed (18 total)

| Category | Checks |
|----------|--------|
| **Chain Integrity** | Genesis block valid, all block hashes verified, previous-hash links verified, merkle roots verified |
| **Transactions** | All signatures verified, no duplicate tx hashes, no double-spends |
| **Balances** | All address balances match replayed state, all nonces match |
| **Reserves** | Total minted/burned/circulating match, reserve invariant holds, proof counts consistent |
| **Consensus** | All nodes agree on chain height, all nodes agree on tip hash |
| **Supply Conservation** | `sum(balances) == total_minted - total_burned`, no negative balances |

### How It Works

1. Downloads the full chain from the primary node
2. Replays every block from genesis, independently computing balances and nonces
3. Compares replayed state against node-reported state
4. Queries all nodes for chain height and tip hash to verify consensus
5. Validates the reserve invariant against on-chain supply data

### Output

```
========================================================================
  GOLD TOKENIZATION RECONCILIATION REPORT
========================================================================
  [CHAIN]     [+] PASS  All block hashes verified
  [BALANCE]   [+] PASS  All address balances match
  [RESERVE]   [+] PASS  Reserve invariant holds (ratio 4.25x)
  [CONSENSUS] [+] PASS  All 3 nodes agree on chain height
  [SUPPLY]    [+] PASS  Supply conservation verified

  Total checks: 18    Passed: 18    Failures: 0
  RESULT: RECONCILIATION PASSED
========================================================================
```

---

## 12. Configuration

### Environment Variables (`.env.example`)

```
NODE_HOST=127.0.0.1
NODE_PORT=5100
NETWORK_ID=gold-mainnet
VALIDATOR_ADDRESS=
WALLET_PASSWORD=
```

### Frontend Environment

```
BLOCKCHAIN_NODE_URL=http://127.0.0.1:5100   # Flask backend
BLOCKCHAIN_BASE_PORT=5100
BLOCKCHAIN_NUM_NODES=3
```

### Dependencies

**Python (`requirements.txt`)**:

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

**Frontend (`frontend/package.json`)**:

```
next@14.2.35              React framework
react@18                  UI library
tailwindcss@3.4           Utility-first CSS
typescript@5              Type safety
```

---

## 13. Test Suite

**187 tests** across 17 files. Run with: `pytest tests/ -v`

| File | Tests | Coverage |
|------|-------|----------|
| `test_block.py` | 8 | Block/header serialization, genesis, create, validate, save/load, replace |
| `test_transaction.py` | 7 | MINT/TRANSFER/BURN, invalid sig, serialization, precision |
| `test_merkle.py` | 12 | Tree construction (1-4 hashes), proofs, verification, invalid cases |
| `test_consensus.py` | 7 | PoA round-robin, validator check, add/remove, PoW mine/validate |
| `test_state.py` | 8 | Balances, nonces, mint/transfer/burn, insufficient balance, copy |
| `test_gold_reserve.py` | 14 | Reserve proofs, ledger, can_mint, invariant, depositor tracking, serialization |
| `test_wallet.py` | 6 | Create, from_private_key, sign, encrypted save/load, wrong password |
| `test_wallets.py` | 9 | Wallet creation API, listing, address format, private key isolation |
| `test_network.py` | 16 | All REST endpoints, error cases, mint rejection, portfolio, wallets |
| `test_integration.py` | 3 | Full lifecycle, invariant enforcement, API lifecycle |
| `test_matching.py` | 9 | Full/partial fills, self-trade prevention, maker price, market summary |
| `test_order_book.py` | 10 | Add/reject/cancel orders, sorting, spread, filtering |
| `test_trading_api.py` | 13 | Place/cancel orders, list/filter, book snapshot, trades, market summary |
| `test_trading_integration.py` | 5 | Full trade cycle, partial fills, market updates, no-cross |
| `test_portfolio.py` | 16 | Depositor proofs, tracking, portfolio API, lifecycle |
| `test_reconcile.py` | 17 | Replay state, chain integrity, tx audit, supply conservation, cross-node |

---

## 14. CLI Tools

### Start Network

```bash
python -m cli.start_network --nodes 3 --base-port 5100
```

Spins up N Flask nodes on sequential ports, creates validators, registers all nodes as peers.

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
python -m cli.query_chain health
python -m cli.query_chain chain
python -m cli.query_chain block 1
python -m cli.query_chain balance 0x...
python -m cli.query_chain token
python -m cli.query_chain reserves
python -m cli.query_chain mempool
python -m cli.query_chain peers
```

### Reconciliation Audit

```bash
python -m cli.reconcile --base-port 5100 --num-nodes 3 --verbose
```

---

## 15. Dependency Graph

```
                    ┌─────────┐
                    │ config  │
                    └────┬────┘
                         │
         ┌───────────────┼───────────────┐
         │               │               │
    ┌────▼────┐    ┌─────▼─────┐   ┌─────▼─────┐
    │ crypto/ │    │blockchain/│   │  wallet/   │
    │ hashing │    │ tx, state │   │  wallet    │
    │  keys   │    │ merkle    │   └─────┬─────┘
    └────┬────┘    │ consensus │         │
         │        │ block     │    uses crypto/keys
         │        └─────┬─────┘    uses cryptography
         │              │
         │    ┌─────────┼──────────┐
         │    │         │          │
    ┌────▼────▼┐  ┌─────▼─────┐ ┌─▼──────────┐
    │  gold/   │  │ network/  │ │  network/   │
    │ reserve  │  │  mempool  │ │   peer      │
    │  token   │  │  sync     │ │             │
    └────┬─────┘  └─────┬─────┘ └──────┬──────┘
         │              │              │
    ┌────▼────┐         │              │
    │trading/ │         │              │
    │ order   │         │              │
    │ book    │         │              │
    │ engine  │         │              │
    │ trade   │         │              │
    └────┬────┘         │              │
         │              │              │
         └──────────┬───┴──────────────┘
                    │
              ┌─────▼─────┐     ┌──────────────┐
              │ network/  │     │   logging     │
              │   node    │────>│   _config     │
              │ (Flask)   │     └──────────────┘
              └─────┬─────┘
                    │
         ┌──────────┼──────────┐
         │          │          │
   ┌─────▼───┐ ┌───▼───┐ ┌───▼────────┐
   │  cli/   │ │ tests │ │  frontend  │
   │ start   │ │  187  │ │  Next.js   │
   │ wallet  │ │ tests │ │  (proxy)   │
   │ send_tx │ │       │ │            │
   │ query   │ │       │ │            │
   │ recon   │ │       │ │            │
   └─────────┘ └───────┘ └────────────┘
```

---

*Generated from the GoldTokenization codebase. 187 tests passing.*
