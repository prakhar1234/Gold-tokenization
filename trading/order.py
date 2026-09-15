"""Limit order model with ECDSA signature verification."""

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from crypto.hashing import canonical_json, hash_string
from crypto.keys import sign_message, verify_signature


class OrderSide(Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(Enum):
    OPEN = "OPEN"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"


@dataclass
class Order:
    """A limit order for AUT tokens priced in USD."""

    side: OrderSide
    address: str  # trader's blockchain address ("0x...")
    price: float  # USD per AUT
    amount: float  # total AUT amount
    remaining_amount: float = 0.0
    status: OrderStatus = OrderStatus.OPEN
    order_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    public_key: str = ""
    signature: str = ""
    _private_key: Optional[str] = field(default=None, repr=False)

    def __post_init__(self):
        self.price = round(self.price, 4)
        self.amount = round(self.amount, 4)
        if self.remaining_amount == 0.0:
            self.remaining_amount = self.amount

    def signable_data(self) -> str:
        """Canonical JSON of fields that get signed."""
        return canonical_json({
            "side": self.side.value,
            "address": self.address,
            "price": self.price,
            "amount": self.amount,
            "order_id": self.order_id,
            "timestamp": self.timestamp,
        })

    def sign(self, private_key_hex: str) -> None:
        """Sign this order and store private key for settlement."""
        self.signature = sign_message(private_key_hex, self.signable_data())
        self._private_key = private_key_hex

    def verify(self) -> bool:
        """Verify the order signature."""
        if not self.public_key or not self.signature:
            return False
        if self.price <= 0 or self.amount <= 0:
            return False
        return verify_signature(
            self.public_key, self.signable_data(), self.signature
        )

    def to_dict(self) -> dict:
        return {
            "order_id": self.order_id,
            "side": self.side.value,
            "address": self.address,
            "price": self.price,
            "amount": self.amount,
            "remaining_amount": self.remaining_amount,
            "status": self.status.value,
            "timestamp": self.timestamp,
            "public_key": self.public_key,
            "signature": self.signature,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Order":
        return cls(
            side=OrderSide(data["side"]),
            address=data["address"],
            price=data["price"],
            amount=data["amount"],
            remaining_amount=data.get("remaining_amount", data["amount"]),
            status=OrderStatus(data.get("status", "OPEN")),
            order_id=data.get("order_id", str(uuid.uuid4())),
            timestamp=data.get("timestamp", time.time()),
            public_key=data.get("public_key", ""),
            signature=data.get("signature", ""),
        )
