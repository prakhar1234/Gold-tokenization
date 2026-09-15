"""Trade record for executed order matches."""

import time
import uuid
from dataclasses import dataclass, field


@dataclass
class Trade:
    """Record of an executed match between a buy and sell order."""

    buyer_address: str
    seller_address: str
    price: float  # execution price (USD per AUT)
    amount: float  # AUT amount traded
    buy_order_id: str
    sell_order_id: str
    tx_hash: str = ""  # hash of the settlement TRANSFER transaction
    trade_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)

    def __post_init__(self):
        self.price = round(self.price, 4)
        self.amount = round(self.amount, 4)

    def to_dict(self) -> dict:
        return {
            "trade_id": self.trade_id,
            "buyer_address": self.buyer_address,
            "seller_address": self.seller_address,
            "price": self.price,
            "amount": self.amount,
            "buy_order_id": self.buy_order_id,
            "sell_order_id": self.sell_order_id,
            "tx_hash": self.tx_hash,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Trade":
        return cls(
            buyer_address=data["buyer_address"],
            seller_address=data["seller_address"],
            price=data["price"],
            amount=data["amount"],
            buy_order_id=data["buy_order_id"],
            sell_order_id=data["sell_order_id"],
            tx_hash=data.get("tx_hash", ""),
            trade_id=data.get("trade_id", str(uuid.uuid4())),
            timestamp=data.get("timestamp", time.time()),
        )
