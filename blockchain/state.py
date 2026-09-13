"""Account state management for balances and nonces."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from blockchain.transaction import Transaction, TransactionType


@dataclass
class AccountState:
    """Tracks balances and nonces for all accounts."""

    balances: Dict[str, float] = field(default_factory=dict)
    nonces: Dict[str, int] = field(default_factory=dict)

    def get_balance(self, address: str) -> float:
        return round(self.balances.get(address, 0.0), 4)

    def get_nonce(self, address: str) -> int:
        return self.nonces.get(address, 0)

    def validate_transaction(self, tx: Transaction) -> Optional[str]:
        """Validate a transaction against current state.

        Returns:
            None if valid, error message string if invalid.
        """
        if tx.amount <= 0:
            return "Amount must be positive"

        if tx.tx_type == TransactionType.MINT:
            # Minting: sender is "NETWORK", no balance check needed
            if tx.sender != "NETWORK":
                return "MINT sender must be NETWORK"
            return None

        if tx.tx_type == TransactionType.TRANSFER:
            # Check sender has sufficient balance
            balance = self.get_balance(tx.sender)
            if balance < tx.amount:
                return f"Insufficient balance: {balance} < {tx.amount}"
            # Check nonce
            expected_nonce = self.get_nonce(tx.sender)
            if tx.nonce != expected_nonce:
                return f"Invalid nonce: expected {expected_nonce}, got {tx.nonce}"
            return None

        if tx.tx_type == TransactionType.BURN:
            # Check sender has sufficient balance
            balance = self.get_balance(tx.sender)
            if balance < tx.amount:
                return f"Insufficient balance: {balance} < {tx.amount}"
            expected_nonce = self.get_nonce(tx.sender)
            if tx.nonce != expected_nonce:
                return f"Invalid nonce: expected {expected_nonce}, got {tx.nonce}"
            return None

        return f"Unknown transaction type: {tx.tx_type}"

    def apply_transaction(self, tx: Transaction) -> Optional[str]:
        """Apply a transaction to the state, modifying balances and nonces.

        Returns:
            None if successful, error message string if failed.
        """
        error = self.validate_transaction(tx)
        if error:
            return error

        if tx.tx_type == TransactionType.MINT:
            self.balances[tx.recipient] = round(
                self.balances.get(tx.recipient, 0.0) + tx.amount, 4
            )

        elif tx.tx_type == TransactionType.TRANSFER:
            self.balances[tx.sender] = round(
                self.balances[tx.sender] - tx.amount, 4
            )
            self.balances[tx.recipient] = round(
                self.balances.get(tx.recipient, 0.0) + tx.amount, 4
            )
            self.nonces[tx.sender] = self.nonces.get(tx.sender, 0) + 1

        elif tx.tx_type == TransactionType.BURN:
            self.balances[tx.sender] = round(
                self.balances[tx.sender] - tx.amount, 4
            )
            self.nonces[tx.sender] = self.nonces.get(tx.sender, 0) + 1

        return None

    def apply_transactions(self, transactions: List[Transaction]) -> Optional[str]:
        """Apply a list of transactions in order."""
        for tx in transactions:
            error = self.apply_transaction(tx)
            if error:
                return f"Transaction {tx.tx_hash}: {error}"
        return None

    def rebuild_from_chain(self, blocks: list) -> None:
        """Rebuild state from a list of blocks (each with .transactions)."""
        self.balances.clear()
        self.nonces.clear()
        for block in blocks:
            for tx in block.transactions:
                self.apply_transaction(tx)

    def copy(self) -> "AccountState":
        """Create a deep copy of the state."""
        return AccountState(
            balances=dict(self.balances),
            nonces=dict(self.nonces),
        )

    def to_dict(self) -> dict:
        return {
            "balances": {k: round(v, 4) for k, v in self.balances.items()},
            "nonces": dict(self.nonces),
        }
