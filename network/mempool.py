"""Thread-safe transaction pool (mempool) management."""

import logging
import threading
import time
from typing import Dict, List, Optional

from blockchain.transaction import Transaction

logger = logging.getLogger(__name__)


class Mempool:
    """Thread-safe pool of pending transactions awaiting inclusion in a block."""

    def __init__(self, max_size: int = 5000, tx_timeout_seconds: int = 3600):
        self.max_size = max_size
        self.tx_timeout_seconds = tx_timeout_seconds
        self._transactions: Dict[str, Transaction] = {}
        self._lock = threading.Lock()

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._transactions)

    def add_transaction(self, tx: Transaction) -> Optional[str]:
        """Add a transaction to the mempool.

        Returns:
            None if successful, error message if rejected.
        """
        if not tx.verify():
            return "Invalid transaction signature"

        with self._lock:
            if tx.tx_hash in self._transactions:
                return "Transaction already in mempool"

            if len(self._transactions) >= self.max_size:
                logger.warning("Mempool full (%d), rejecting tx %s", self.max_size, tx.tx_hash[:16])
                return "Mempool is full"

            self._transactions[tx.tx_hash] = tx
            logger.debug("Mempool add: %s (size=%d)", tx.tx_hash[:16], len(self._transactions))
            return None

    def remove_transaction(self, tx_hash: str) -> Optional[Transaction]:
        """Remove and return a transaction by hash."""
        with self._lock:
            return self._transactions.pop(tx_hash, None)

    def remove_transactions(self, tx_hashes: List[str]) -> None:
        """Remove multiple transactions (e.g., after block is mined)."""
        with self._lock:
            for h in tx_hashes:
                self._transactions.pop(h, None)

    def get_transactions(self, limit: Optional[int] = None) -> List[Transaction]:
        """Get pending transactions, ordered by timestamp.

        Args:
            limit: Max number of transactions to return.
        """
        with self._lock:
            txs = sorted(
                self._transactions.values(), key=lambda tx: tx.timestamp
            )
            if limit:
                txs = txs[:limit]
            return txs

    def get_transaction(self, tx_hash: str) -> Optional[Transaction]:
        with self._lock:
            return self._transactions.get(tx_hash)

    def contains(self, tx_hash: str) -> bool:
        with self._lock:
            return tx_hash in self._transactions

    def clear_expired(self) -> int:
        """Remove transactions that have exceeded the timeout. Returns count removed."""
        cutoff = time.time() - self.tx_timeout_seconds
        removed = 0
        with self._lock:
            expired = [
                h for h, tx in self._transactions.items()
                if tx.timestamp < cutoff
            ]
            for h in expired:
                del self._transactions[h]
                removed += 1
        if removed:
            logger.debug("Mempool: cleared %d expired transactions", removed)
        return removed

    def clear(self) -> None:
        with self._lock:
            self._transactions.clear()

    def to_list(self) -> List[dict]:
        with self._lock:
            return [tx.to_dict() for tx in self._transactions.values()]
