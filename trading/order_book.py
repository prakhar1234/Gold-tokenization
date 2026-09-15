"""Thread-safe order book with price-time priority."""

import threading
from typing import Dict, List, Optional, Tuple

from trading.order import Order, OrderSide, OrderStatus


class OrderBook:
    """Thread-safe limit order book for AUT/USD trading.

    Bids (buy orders) are sorted highest price first (best bid at top).
    Asks (sell orders) are sorted lowest price first (best ask at top).
    Within the same price level, earlier orders have priority.
    """

    def __init__(self, max_size: int = 10000):
        self.max_size = max_size
        self._orders: Dict[str, Order] = {}  # order_id -> Order
        self._lock = threading.Lock()

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._orders)

    def add_order(self, order: Order) -> Optional[str]:
        """Add an order to the book.

        Returns:
            None if successful, error message if rejected.
        """
        if not order.verify():
            return "Invalid order signature"

        with self._lock:
            if order.order_id in self._orders:
                return "Order already in book"

            if len(self._orders) >= self.max_size:
                return "Order book is full"

            self._orders[order.order_id] = order
            return None

    def cancel_order(self, order_id: str, address: str) -> Optional[str]:
        """Cancel an open order. Only the owner can cancel.

        Returns:
            None if successful, error message if rejected.
        """
        with self._lock:
            order = self._orders.get(order_id)
            if order is None:
                return "Order not found"

            if order.address != address:
                return "Not authorized to cancel this order"

            if order.status in (OrderStatus.FILLED, OrderStatus.CANCELLED):
                return f"Order already {order.status.value.lower()}"

            order.status = OrderStatus.CANCELLED
            del self._orders[order_id]
            return None

    def get_order(self, order_id: str) -> Optional[Order]:
        with self._lock:
            return self._orders.get(order_id)

    def remove_order(self, order_id: str) -> Optional[Order]:
        """Remove an order from the book (used after full fill)."""
        with self._lock:
            return self._orders.pop(order_id, None)

    def get_sorted_bids(self) -> List[Order]:
        """Get buy orders sorted by price descending, then timestamp ascending."""
        with self._lock:
            bids = [
                o for o in self._orders.values()
                if o.side == OrderSide.BUY
                and o.status in (OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED)
            ]
        bids.sort(key=lambda o: (-o.price, o.timestamp))
        return bids

    def get_sorted_asks(self) -> List[Order]:
        """Get sell orders sorted by price ascending, then timestamp ascending."""
        with self._lock:
            asks = [
                o for o in self._orders.values()
                if o.side == OrderSide.SELL
                and o.status in (OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED)
            ]
        asks.sort(key=lambda o: (o.price, o.timestamp))
        return asks

    def get_spread(self) -> Tuple[Optional[float], Optional[float]]:
        """Return (best_bid_price, best_ask_price) or None if side is empty."""
        bids = self.get_sorted_bids()
        asks = self.get_sorted_asks()
        best_bid = bids[0].price if bids else None
        best_ask = asks[0].price if asks else None
        return best_bid, best_ask

    def get_open_orders(self, address: Optional[str] = None) -> List[Order]:
        """Get open/partially-filled orders, optionally filtered by address."""
        with self._lock:
            orders = [
                o for o in self._orders.values()
                if o.status in (OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED)
                and (address is None or o.address == address)
            ]
        orders.sort(key=lambda o: o.timestamp)
        return orders

    def to_dict(self) -> dict:
        """Snapshot of the order book."""
        bids = self.get_sorted_bids()
        asks = self.get_sorted_asks()
        return {
            "bids": [o.to_dict() for o in bids],
            "asks": [o.to_dict() for o in asks],
            "bid_count": len(bids),
            "ask_count": len(asks),
        }
