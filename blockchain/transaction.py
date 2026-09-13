"""Transaction model for the Gold Tokenization blockchain."""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from crypto.hashing import canonical_json, hash_string
from crypto.keys import sign_message, verify_signature


class TransactionType(Enum):
    MINT = "MINT"
    TRANSFER = "TRANSFER"
    BURN = "BURN"


@dataclass
class Transaction:
    """A single blockchain transaction."""

    tx_type: TransactionType
    sender: str  # address ("0x...") or "NETWORK" for minting
    recipient: str  # address
    amount: float  # AUT amount (4 decimal precision)
    nonce: int  # sender's transaction count (replay protection)
    timestamp: float = field(default_factory=time.time)
    public_key: str = ""  # sender's public key (for verification)
    signature: str = ""  # ECDSA signature
    tx_hash: str = ""  # computed hash

    def __post_init__(self):
        self.amount = round(self.amount, 4)
        if not self.tx_hash:
            self.tx_hash = self.compute_hash()

    def signable_data(self) -> str:
        """Data that gets signed (everything except signature and hash)."""
        return canonical_json({
            "tx_type": self.tx_type.value,
            "sender": self.sender,
            "recipient": self.recipient,
            "amount": self.amount,
            "nonce": self.nonce,
            "timestamp": self.timestamp,
        })

    def compute_hash(self) -> str:
        """Compute transaction hash from signable data + signature."""
        data = self.signable_data() + self.signature
        return hash_string(data)

    def sign(self, private_key_hex: str) -> None:
        """Sign this transaction with the given private key."""
        self.signature = sign_message(private_key_hex, self.signable_data())
        self.tx_hash = self.compute_hash()

    def verify(self) -> bool:
        """Verify the transaction signature and basic validity."""
        # MINT transactions are signed by the network authority
        if self.tx_type == TransactionType.MINT:
            if not self.public_key or not self.signature:
                return False
            return verify_signature(
                self.public_key, self.signable_data(), self.signature
            )

        # TRANSFER and BURN must have valid signatures
        if not self.public_key or not self.signature:
            return False

        if self.amount <= 0:
            return False

        return verify_signature(
            self.public_key, self.signable_data(), self.signature
        )

    def to_dict(self) -> dict:
        return {
            "tx_type": self.tx_type.value,
            "sender": self.sender,
            "recipient": self.recipient,
            "amount": self.amount,
            "nonce": self.nonce,
            "timestamp": self.timestamp,
            "public_key": self.public_key,
            "signature": self.signature,
            "tx_hash": self.tx_hash,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Transaction":
        tx = cls(
            tx_type=TransactionType(data["tx_type"]),
            sender=data["sender"],
            recipient=data["recipient"],
            amount=data["amount"],
            nonce=data["nonce"],
            timestamp=data["timestamp"],
            public_key=data.get("public_key", ""),
            signature=data.get("signature", ""),
            tx_hash=data.get("tx_hash", ""),
        )
        return tx
