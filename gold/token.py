"""Gold token manager coordinating blockchain and reserve operations."""

import time
from typing import Optional

from blockchain.block import Blockchain
from blockchain.transaction import Transaction, TransactionType
from config import DEFAULT_CONFIG, NetworkConfig
from crypto.keys import public_key_to_address
from gold.reserve import ReserveLedger, ReserveProof


class GoldTokenManager:
    """High-level manager for the AUT gold token.

    Coordinates between the blockchain (for token state) and the reserve
    ledger (for gold backing enforcement).
    """

    def __init__(
        self,
        blockchain: Blockchain,
        reserve_ledger: Optional[ReserveLedger] = None,
        config: NetworkConfig = DEFAULT_CONFIG,
    ):
        self.blockchain = blockchain
        self.reserves = reserve_ledger or ReserveLedger()
        self.config = config

    def add_reserve(
        self,
        custodian: str,
        amount_grams: float,
        purity: float = 0.999,
        certificate_ref: str = "",
    ) -> ReserveProof:
        """Register a new gold reserve proof."""
        proof = ReserveProof(
            custodian=custodian,
            amount_grams=amount_grams,
            purity=purity,
            certificate_ref=certificate_ref,
        )
        self.reserves.add_reserve(proof)
        return proof

    def create_mint_transaction(
        self,
        recipient: str,
        amount: float,
        authority_private_key: str,
        authority_public_key: str,
    ) -> Optional[Transaction]:
        """Create a MINT transaction if reserve backing allows it.

        Returns:
            Signed Transaction, or None if reserve invariant would be violated.
        """
        if not self.reserves.can_mint(amount):
            return None

        tx = Transaction(
            tx_type=TransactionType.MINT,
            sender="NETWORK",
            recipient=recipient,
            amount=amount,
            nonce=0,  # MINT doesn't use nonces
            public_key=authority_public_key,
        )
        tx.sign(authority_private_key)
        return tx

    def create_transfer_transaction(
        self,
        sender: str,
        recipient: str,
        amount: float,
        sender_private_key: str,
        sender_public_key: str,
    ) -> Optional[Transaction]:
        """Create a TRANSFER transaction.

        Returns:
            Signed Transaction, or None if balance insufficient.
        """
        balance = self.blockchain.state.get_balance(sender)
        if balance < amount:
            return None

        nonce = self.blockchain.state.get_nonce(sender)
        tx = Transaction(
            tx_type=TransactionType.TRANSFER,
            sender=sender,
            recipient=recipient,
            amount=amount,
            nonce=nonce,
            public_key=sender_public_key,
        )
        tx.sign(sender_private_key)
        return tx

    def create_burn_transaction(
        self,
        sender: str,
        amount: float,
        sender_private_key: str,
        sender_public_key: str,
    ) -> Optional[Transaction]:
        """Create a BURN transaction.

        Returns:
            Signed Transaction, or None if balance insufficient.
        """
        balance = self.blockchain.state.get_balance(sender)
        if balance < amount:
            return None

        nonce = self.blockchain.state.get_nonce(sender)
        tx = Transaction(
            tx_type=TransactionType.BURN,
            sender=sender,
            recipient="BURN",
            amount=amount,
            nonce=nonce,
            public_key=sender_public_key,
        )
        tx.sign(sender_private_key)
        return tx

    def process_minted_block(self, block) -> None:
        """Update reserve ledger after a block is mined."""
        for tx in block.transactions:
            if tx.tx_type == TransactionType.MINT:
                self.reserves.record_mint(tx.amount)
            elif tx.tx_type == TransactionType.BURN:
                self.reserves.record_burn(tx.amount)

    def rebuild_from_chain(self) -> None:
        """Rebuild reserve ledger mint/burn counters from the full chain.

        Called after chain sync to reconcile the reserve ledger with
        the actual on-chain history.
        """
        self.reserves.reset_counters()
        for block in self.blockchain.chain[1:]:  # skip genesis
            for tx in block.transactions:
                if tx.tx_type == TransactionType.MINT:
                    self.reserves.force_record_mint(tx.amount)
                elif tx.tx_type == TransactionType.BURN:
                    self.reserves.record_burn(tx.amount)

    def get_token_info(self) -> dict:
        return {
            "name": self.config.token_name,
            "symbol": self.config.token_symbol,
            "decimals": self.config.token_decimals,
            "total_minted": self.reserves.total_minted,
            "total_burned": self.reserves.total_burned,
            "circulating_supply": self.reserves.circulating_supply,
            "total_reserved_grams": self.reserves.total_reserved,
            "reserve_ratio": self.reserves.reserve_ratio,
        }
