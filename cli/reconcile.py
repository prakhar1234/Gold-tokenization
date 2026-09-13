"""Reconciliation script for the Gold Tokenization blockchain.

Performs comprehensive auditing by independently replaying the chain and
comparing computed state against node-reported state. Checks:

  1. Chain integrity    — block hashes, previous-hash links, merkle roots
  2. Transaction audit  — signature verification, double-spend detection
  3. Balance reconciliation — replay-computed vs node-reported balances
  4. Reserve reconciliation — computed mint/burn vs reported, invariant check
  5. Cross-node consensus   — all nodes agree on chain height and block hashes
  6. Supply conservation    — sum(balances) == circulating supply

Usage:
    python -m cli.reconcile --nodes http://127.0.0.1:5100,http://127.0.0.1:5101
    python -m cli.reconcile --base-port 5100 --num-nodes 3
"""

import argparse
import json
import sys
import os
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests

from blockchain.block import Block, BlockHeader
from blockchain.merkle import compute_merkle_root
from blockchain.transaction import Transaction, TransactionType
from crypto.hashing import canonical_json, hash_string


# ── Report structures ────────────────────────────────────────────

@dataclass
class Finding:
    """A single reconciliation finding."""
    severity: str  # PASS, WARN, FAIL
    category: str  # chain, transaction, balance, reserve, consensus, supply
    message: str
    detail: str = ""


@dataclass
class ReconciliationReport:
    """Aggregated reconciliation results."""
    timestamp: float = field(default_factory=time.time)
    findings: List[Finding] = field(default_factory=list)

    @property
    def passes(self) -> List[Finding]:
        return [f for f in self.findings if f.severity == "PASS"]

    @property
    def warnings(self) -> List[Finding]:
        return [f for f in self.findings if f.severity == "WARN"]

    @property
    def failures(self) -> List[Finding]:
        return [f for f in self.findings if f.severity == "FAIL"]

    @property
    def passed(self) -> bool:
        return len(self.failures) == 0

    def add(self, severity: str, category: str, message: str, detail: str = ""):
        self.findings.append(Finding(severity, category, message, detail))

    def print_report(self):
        width = 72
        print()
        print("=" * width)
        print("  GOLD TOKENIZATION RECONCILIATION REPORT")
        print(f"  {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self.timestamp))}")
        print("=" * width)

        categories = ["chain", "transaction", "balance", "reserve", "consensus", "supply"]
        for cat in categories:
            items = [f for f in self.findings if f.category == cat]
            if not items:
                continue
            print(f"\n  [{cat.upper()}]")
            for f in items:
                icon = {"PASS": "+", "WARN": "!", "FAIL": "X"}[f.severity]
                tag = {"PASS": "PASS", "WARN": "WARN", "FAIL": "FAIL"}[f.severity]
                print(f"    [{icon}] {tag}  {f.message}")
                if f.detail:
                    for line in f.detail.split("\n"):
                        print(f"              {line}")

        print()
        print("-" * width)
        total = len(self.findings)
        print(f"  Total checks: {total}    "
              f"Passed: {len(self.passes)}    "
              f"Warnings: {len(self.warnings)}    "
              f"Failures: {len(self.failures)}")

        if self.passed:
            print("\n  RESULT: RECONCILIATION PASSED")
        else:
            print("\n  RESULT: RECONCILIATION FAILED")
        print("=" * width)
        print()


# ── Node communication ───────────────────────────────────────────

def fetch_json(url: str, timeout: int = 15) -> Optional[dict]:
    """GET JSON from a node endpoint."""
    try:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException:
        return None


def fetch_chain(node_url: str) -> Optional[List[dict]]:
    """Download the full chain from a node."""
    data = fetch_json(f"{node_url}/chain")
    if data and "chain" in data:
        return data["chain"]
    return None


def fetch_balance(node_url: str, address: str) -> Optional[dict]:
    """Get balance and nonce for an address from a node."""
    return fetch_json(f"{node_url}/balance/{address}")


def fetch_reserves(node_url: str) -> Optional[dict]:
    """Get reserve proofs and audit summary from a node."""
    return fetch_json(f"{node_url}/reserves")


def fetch_token_info(node_url: str) -> Optional[dict]:
    """Get token supply metrics from a node."""
    return fetch_json(f"{node_url}/token/info")


def fetch_mempool(node_url: str) -> Optional[dict]:
    """Get pending transactions from a node."""
    return fetch_json(f"{node_url}/mempool")


# ── Reconciliation checks ────────────────────────────────────────

def check_chain_integrity(chain_data: List[dict], report: ReconciliationReport):
    """Verify block hash chain, merkle roots, and genesis block."""

    blocks = [Block.from_dict(b) for b in chain_data]

    if not blocks:
        report.add("FAIL", "chain", "Chain is empty")
        return blocks

    # Genesis block checks
    genesis = blocks[0]
    if genesis.header.index != 0:
        report.add("FAIL", "chain", "Genesis block index is not 0",
                    f"Got index {genesis.header.index}")
    elif genesis.header.previous_hash != "0" * 64:
        report.add("FAIL", "chain", "Genesis previous_hash is not all zeros")
    elif genesis.header.validator != "genesis":
        report.add("FAIL", "chain", "Genesis validator is not 'genesis'",
                    f"Got '{genesis.header.validator}'")
    else:
        report.add("PASS", "chain", "Genesis block is valid")

    # Walk the chain
    hash_errors = 0
    link_errors = 0
    merkle_errors = 0

    for i in range(1, len(blocks)):
        block = blocks[i]
        prev = blocks[i - 1]

        # Index continuity
        if block.header.index != prev.header.index + 1:
            report.add("FAIL", "chain",
                        f"Block {i}: index gap",
                        f"Expected {prev.header.index + 1}, got {block.header.index}")

        # Previous hash link
        if block.header.previous_hash != prev.block_hash:
            link_errors += 1
            report.add("FAIL", "chain",
                        f"Block {block.header.index}: previous_hash mismatch",
                        f"Expected {prev.block_hash[:16]}..., "
                        f"got {block.header.previous_hash[:16]}...")

        # Block hash recomputation
        recomputed = block.compute_hash()
        if block.block_hash != recomputed:
            hash_errors += 1
            report.add("FAIL", "chain",
                        f"Block {block.header.index}: block_hash mismatch",
                        f"Stored  {block.block_hash[:16]}...\n"
                        f"Computed {recomputed[:16]}...")

        # Merkle root verification
        tx_hashes = [tx.tx_hash for tx in block.transactions]
        expected_root = compute_merkle_root(tx_hashes)
        if block.header.merkle_root != expected_root:
            merkle_errors += 1
            report.add("FAIL", "chain",
                        f"Block {block.header.index}: merkle root mismatch",
                        f"Stored  {block.header.merkle_root[:16]}...\n"
                        f"Computed {expected_root[:16]}...")

    num_blocks = len(blocks) - 1  # excluding genesis
    if hash_errors == 0 and num_blocks > 0:
        report.add("PASS", "chain",
                    f"All {num_blocks} block hashes verified")
    if link_errors == 0 and num_blocks > 0:
        report.add("PASS", "chain",
                    f"All {num_blocks} previous-hash links verified")
    if merkle_errors == 0 and num_blocks > 0:
        report.add("PASS", "chain",
                    f"All merkle roots verified across {num_blocks} blocks")
    if num_blocks == 0:
        report.add("PASS", "chain", "Chain has only genesis block (no blocks to verify)")

    return blocks


def check_transactions(blocks: List[Block], report: ReconciliationReport):
    """Verify all transaction signatures and detect double-spends."""

    total_txs = 0
    sig_failures = 0
    nonce_map: Dict[str, List[int]] = defaultdict(list)  # sender -> [nonces used]
    tx_hashes_seen = set()
    duplicate_hashes = 0

    for block in blocks[1:]:  # skip genesis
        for tx in block.transactions:
            total_txs += 1

            # Signature verification
            if not tx.verify():
                sig_failures += 1
                report.add("FAIL", "transaction",
                            f"Block {block.header.index}: invalid signature",
                            f"tx_hash={tx.tx_hash[:16]}... "
                            f"type={tx.tx_type.value} "
                            f"sender={tx.sender[:12]}...")

            # Duplicate tx_hash detection
            if tx.tx_hash in tx_hashes_seen:
                duplicate_hashes += 1
                report.add("FAIL", "transaction",
                            f"Duplicate tx_hash detected",
                            f"tx_hash={tx.tx_hash[:16]}... in block {block.header.index}")
            tx_hashes_seen.add(tx.tx_hash)

            # Nonce tracking (TRANSFER and BURN only)
            if tx.tx_type in (TransactionType.TRANSFER, TransactionType.BURN):
                nonce_map[tx.sender].append(tx.nonce)

    # Check nonce sequences for double-spend
    double_spend_count = 0
    for sender, nonces in nonce_map.items():
        seen = set()
        for n in nonces:
            if n in seen:
                double_spend_count += 1
                report.add("FAIL", "transaction",
                            f"Double-spend: nonce {n} reused by {sender[:16]}...")
            seen.add(n)

        # Check nonce continuity (should be 0, 1, 2, ...)
        sorted_nonces = sorted(nonces)
        expected = list(range(len(sorted_nonces)))
        if sorted_nonces != expected:
            report.add("WARN", "transaction",
                        f"Nonce gap for {sender[:16]}...",
                        f"Expected {expected}, got {sorted_nonces}")

    if sig_failures == 0 and total_txs > 0:
        report.add("PASS", "transaction",
                    f"All {total_txs} transaction signatures verified")
    elif total_txs == 0:
        report.add("PASS", "transaction", "No transactions to verify")

    if duplicate_hashes == 0:
        report.add("PASS", "transaction", "No duplicate transaction hashes")

    if double_spend_count == 0 and len(nonce_map) > 0:
        report.add("PASS", "transaction",
                    f"No double-spends detected across {len(nonce_map)} senders")
    elif len(nonce_map) == 0 and total_txs > 0:
        report.add("PASS", "transaction", "No nonce-based transactions to check")

    return total_txs


def replay_state(blocks: List[Block]) -> Tuple[Dict[str, float], Dict[str, int], float, float]:
    """Replay all transactions to compute balances, nonces, and mint/burn totals.

    Returns:
        (balances, nonces, total_minted, total_burned)
    """
    balances: Dict[str, float] = {}
    nonces: Dict[str, int] = {}
    total_minted = 0.0
    total_burned = 0.0

    for block in blocks[1:]:  # skip genesis
        for tx in block.transactions:
            if tx.tx_type == TransactionType.MINT:
                balances[tx.recipient] = round(
                    balances.get(tx.recipient, 0.0) + tx.amount, 4
                )
                total_minted = round(total_minted + tx.amount, 4)

            elif tx.tx_type == TransactionType.TRANSFER:
                balances[tx.sender] = round(
                    balances.get(tx.sender, 0.0) - tx.amount, 4
                )
                balances[tx.recipient] = round(
                    balances.get(tx.recipient, 0.0) + tx.amount, 4
                )
                nonces[tx.sender] = nonces.get(tx.sender, 0) + 1

            elif tx.tx_type == TransactionType.BURN:
                balances[tx.sender] = round(
                    balances.get(tx.sender, 0.0) - tx.amount, 4
                )
                nonces[tx.sender] = nonces.get(tx.sender, 0) + 1
                total_burned = round(total_burned + tx.amount, 4)

    return balances, nonces, total_minted, total_burned


def check_balances(
    blocks: List[Block],
    node_url: str,
    report: ReconciliationReport,
) -> Tuple[Dict[str, float], Dict[str, int], float, float]:
    """Replay chain and compare balances against node-reported state."""

    balances, nonces, total_minted, total_burned = replay_state(blocks)

    # Collect all addresses that appear in transactions
    addresses = set()
    for block in blocks[1:]:
        for tx in block.transactions:
            if tx.sender != "NETWORK":
                addresses.add(tx.sender)
            if tx.recipient != "BURN":
                addresses.add(tx.recipient)

    balance_mismatches = 0
    nonce_mismatches = 0

    for addr in sorted(addresses):
        node_data = fetch_balance(node_url, addr)
        if node_data is None:
            report.add("WARN", "balance",
                        f"Could not fetch balance for {addr[:16]}...")
            continue

        computed_bal = round(balances.get(addr, 0.0), 4)
        reported_bal = round(node_data.get("balance", 0.0), 4)

        if computed_bal != reported_bal:
            balance_mismatches += 1
            report.add("FAIL", "balance",
                        f"Balance mismatch for {addr[:16]}...",
                        f"Computed: {computed_bal} AUT\n"
                        f"Reported: {reported_bal} AUT\n"
                        f"Delta:    {round(computed_bal - reported_bal, 4)} AUT")

        computed_nonce = nonces.get(addr, 0)
        reported_nonce = node_data.get("nonce", 0)
        if computed_nonce != reported_nonce:
            nonce_mismatches += 1
            report.add("FAIL", "balance",
                        f"Nonce mismatch for {addr[:16]}...",
                        f"Computed: {computed_nonce}, Reported: {reported_nonce}")

    if balance_mismatches == 0 and len(addresses) > 0:
        report.add("PASS", "balance",
                    f"All {len(addresses)} address balances match")
    elif len(addresses) == 0:
        report.add("PASS", "balance", "No addresses to reconcile")

    if nonce_mismatches == 0 and len(addresses) > 0:
        report.add("PASS", "balance",
                    f"All {len(addresses)} address nonces match")

    return balances, nonces, total_minted, total_burned


def check_reserves(
    node_url: str,
    total_minted: float,
    total_burned: float,
    report: ReconciliationReport,
):
    """Compare replay-computed mint/burn against reserve ledger and verify invariant."""

    reserves_data = fetch_reserves(node_url)
    token_data = fetch_token_info(node_url)

    if reserves_data is None or token_data is None:
        report.add("WARN", "reserve", "Could not fetch reserve/token data from node")
        return

    audit = reserves_data.get("audit", {})
    reported_minted = audit.get("total_minted", 0.0)
    reported_burned = audit.get("total_burned", 0.0)
    reported_supply = audit.get("circulating_supply", 0.0)
    total_reserved = audit.get("total_reserved_grams", 0.0)

    # Compare minted totals
    if round(total_minted, 4) != round(reported_minted, 4):
        report.add("FAIL", "reserve",
                    "Total minted mismatch",
                    f"Computed: {total_minted} AUT\n"
                    f"Reported: {reported_minted} AUT")
    else:
        report.add("PASS", "reserve",
                    f"Total minted matches: {total_minted} AUT")

    # Compare burned totals
    if round(total_burned, 4) != round(reported_burned, 4):
        report.add("FAIL", "reserve",
                    "Total burned mismatch",
                    f"Computed: {total_burned} AUT\n"
                    f"Reported: {reported_burned} AUT")
    else:
        report.add("PASS", "reserve",
                    f"Total burned matches: {total_burned} AUT")

    # Circulating supply cross-check
    computed_supply = round(total_minted - total_burned, 4)
    if computed_supply != round(reported_supply, 4):
        report.add("FAIL", "reserve",
                    "Circulating supply mismatch",
                    f"Computed: {computed_supply} AUT\n"
                    f"Reported: {reported_supply} AUT")
    else:
        report.add("PASS", "reserve",
                    f"Circulating supply matches: {computed_supply} AUT")

    # Reserve invariant: circulating_supply <= total_reserved_grams
    if computed_supply > 0 and total_reserved > 0:
        if computed_supply <= total_reserved:
            ratio = round(total_reserved / computed_supply, 4)
            report.add("PASS", "reserve",
                        f"Reserve invariant holds (ratio {ratio}x)",
                        f"Circulating: {computed_supply} AUT\n"
                        f"Reserved:    {total_reserved} grams gold")
        else:
            shortfall = round(computed_supply - total_reserved, 4)
            report.add("FAIL", "reserve",
                        "RESERVE INVARIANT VIOLATED",
                        f"Circulating: {computed_supply} AUT\n"
                        f"Reserved:    {total_reserved} grams gold\n"
                        f"Shortfall:   {shortfall} grams")
    elif computed_supply == 0:
        report.add("PASS", "reserve",
                    "No circulating supply; invariant trivially holds")
    elif total_reserved == 0 and computed_supply > 0:
        report.add("FAIL", "reserve",
                    "RESERVE INVARIANT VIOLATED",
                    f"Circulating supply is {computed_supply} AUT with 0 gold reserves")

    # Reserve proof count
    num_proofs = audit.get("num_reserves", 0)
    reserve_list = reserves_data.get("reserves", [])
    if len(reserve_list) == num_proofs:
        report.add("PASS", "reserve",
                    f"Reserve proof count consistent: {num_proofs}")
    else:
        report.add("FAIL", "reserve",
                    "Reserve proof count mismatch",
                    f"List length: {len(reserve_list)}, Reported: {num_proofs}")


def check_supply_conservation(
    balances: Dict[str, float],
    total_minted: float,
    total_burned: float,
    report: ReconciliationReport,
):
    """Verify sum of all balances equals circulating supply (conservation of tokens)."""

    balance_sum = round(sum(balances.values()), 4)
    circulating = round(total_minted - total_burned, 4)

    if balance_sum == circulating:
        report.add("PASS", "supply",
                    f"Supply conservation verified: {balance_sum} AUT",
                    f"sum(balances) == total_minted - total_burned")
    else:
        delta = round(balance_sum - circulating, 4)
        report.add("FAIL", "supply",
                    "Supply conservation VIOLATED",
                    f"sum(balances):       {balance_sum} AUT\n"
                    f"circulating_supply:  {circulating} AUT\n"
                    f"Discrepancy:         {delta} AUT")

    # Check for negative balances
    negative = {addr: bal for addr, bal in balances.items() if bal < 0}
    if negative:
        for addr, bal in negative.items():
            report.add("FAIL", "supply",
                        f"Negative balance: {addr[:16]}...",
                        f"Balance: {bal} AUT")
    else:
        addr_count = len([b for b in balances.values() if b != 0])
        report.add("PASS", "supply",
                    f"No negative balances across {addr_count} funded addresses")


def check_cross_node_consensus(
    node_urls: List[str],
    report: ReconciliationReport,
):
    """Verify all nodes agree on chain height and block hashes."""

    if len(node_urls) < 2:
        report.add("PASS", "consensus", "Single node; cross-node check skipped")
        return

    heights = {}
    tip_hashes = {}
    reachable = []

    for url in node_urls:
        health = fetch_json(f"{url}/health")
        if health is None:
            report.add("WARN", "consensus", f"Node unreachable: {url}")
            continue
        reachable.append(url)
        heights[url] = health.get("chain_height", -1)

        chain_data = fetch_json(f"{url}/chain")
        if chain_data and chain_data.get("chain"):
            last_block = chain_data["chain"][-1]
            tip_hashes[url] = last_block.get("block_hash", "unknown")

    if len(reachable) < 2:
        report.add("WARN", "consensus",
                    f"Only {len(reachable)} node(s) reachable; cannot compare")
        return

    # Check height agreement
    unique_heights = set(heights.values())
    if len(unique_heights) == 1:
        h = list(unique_heights)[0]
        report.add("PASS", "consensus",
                    f"All {len(reachable)} nodes agree on chain height: {h}")
    else:
        detail_lines = [f"  {url}: height {h}" for url, h in heights.items()]
        report.add("FAIL", "consensus",
                    "Chain height disagreement",
                    "\n".join(detail_lines))

    # Check tip hash agreement
    unique_tips = set(tip_hashes.values())
    if len(unique_tips) == 1:
        report.add("PASS", "consensus",
                    f"All {len(reachable)} nodes agree on chain tip hash")
    elif len(unique_tips) > 1:
        detail_lines = [f"  {url}: {h[:16]}..." for url, h in tip_hashes.items()]
        report.add("FAIL", "consensus",
                    "Chain tip hash disagreement (possible fork)",
                    "\n".join(detail_lines))

    # Check peer connectivity
    for url in reachable:
        nodes_data = fetch_json(f"{url}/nodes")
        if nodes_data:
            peer_count = nodes_data.get("count", 0)
            expected_peers = len(reachable) - 1
            if peer_count < expected_peers:
                report.add("WARN", "consensus",
                            f"{url} has {peer_count}/{expected_peers} expected peers")


# ── Transaction ledger summary ────────────────────────────────────

def print_transaction_ledger(blocks: List[Block]):
    """Print a human-readable ledger of all on-chain transactions."""

    txs = []
    for block in blocks[1:]:
        for tx in block.transactions:
            txs.append((block.header.index, tx))

    if not txs:
        print("\n  No transactions on chain.\n")
        return

    print()
    print("-" * 72)
    print("  TRANSACTION LEDGER")
    print("-" * 72)
    print(f"  {'Block':>5}  {'Type':>8}  {'From':>14}  {'To':>14}  {'Amount':>12}  Hash")
    print(f"  {'-----':>5}  {'--------':>8}  {'-'*14:>14}  {'-'*14:>14}  {'------------':>12}  {'-'*16}")

    for block_idx, tx in txs:
        sender = tx.sender[:14] if tx.sender != "NETWORK" else "NETWORK"
        recip = tx.recipient[:14] if tx.recipient != "BURN" else "BURN"
        print(f"  {block_idx:>5}  {tx.tx_type.value:>8}  {sender:>14}  "
              f"{recip:>14}  {tx.amount:>12.4f}  {tx.tx_hash[:16]}...")
    print()


# ── Main ──────────────────────────────────────────────────────────

def run_reconciliation(node_urls: List[str], verbose: bool = False):
    """Execute all reconciliation checks and print the report."""

    report = ReconciliationReport()
    primary_url = node_urls[0]

    print(f"\n  Primary node:   {primary_url}")
    print(f"  Nodes to check: {len(node_urls)}")

    # 1. Fetch chain from primary node
    print("\n  Downloading chain...")
    chain_data = fetch_chain(primary_url)
    if chain_data is None:
        report.add("FAIL", "chain",
                    f"Cannot fetch chain from {primary_url}")
        report.print_report()
        return report

    print(f"  Chain downloaded: {len(chain_data)} blocks")

    # 2. Chain integrity
    print("  Checking chain integrity...")
    blocks = check_chain_integrity(chain_data, report)
    if not blocks:
        report.print_report()
        return report

    # 3. Transaction audit
    print("  Auditing transactions...")
    total_txs = check_transactions(blocks, report)
    print(f"  Transactions audited: {total_txs}")

    # 4. Balance reconciliation
    print("  Reconciling balances...")
    balances, nonces, total_minted, total_burned = check_balances(
        blocks, primary_url, report
    )

    # 5. Reserve reconciliation
    print("  Reconciling reserves...")
    check_reserves(primary_url, total_minted, total_burned, report)

    # 6. Supply conservation
    print("  Verifying supply conservation...")
    check_supply_conservation(balances, total_minted, total_burned, report)

    # 7. Cross-node consensus
    if len(node_urls) > 1:
        print("  Checking cross-node consensus...")
        check_cross_node_consensus(node_urls, report)

    # Print transaction ledger in verbose mode
    if verbose:
        print_transaction_ledger(blocks)

    # Print final report
    report.print_report()
    return report


def main():
    parser = argparse.ArgumentParser(
        description="Reconcile gold transfers and transactions on the AUT blockchain"
    )
    parser.add_argument(
        "--nodes",
        type=str,
        default=None,
        help="Comma-separated node URLs (e.g. http://127.0.0.1:5100,http://127.0.0.1:5101)",
    )
    parser.add_argument(
        "--base-port",
        type=int,
        default=5100,
        help="Base port for auto-discovering nodes (default: 5100)",
    )
    parser.add_argument(
        "--num-nodes",
        type=int,
        default=3,
        help="Number of nodes to check when using --base-port (default: 3)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print full transaction ledger",
    )

    args = parser.parse_args()

    # Build node list
    if args.nodes:
        node_urls = [u.strip() for u in args.nodes.split(",")]
    else:
        node_urls = [
            f"http://127.0.0.1:{args.base_port + i}"
            for i in range(args.num_nodes)
        ]

    # Filter to reachable nodes
    reachable = []
    for url in node_urls:
        health = fetch_json(f"{url}/health", timeout=3)
        if health:
            reachable.append(url)
        else:
            print(f"  [skip] {url} is unreachable")

    if not reachable:
        print("ERROR: No reachable nodes found.")
        sys.exit(1)

    report = run_reconciliation(reachable, verbose=args.verbose)
    sys.exit(0 if report.passed else 1)


if __name__ == "__main__":
    main()
