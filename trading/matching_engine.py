"""Matching engine for limit orders with TRANSFER settlement."""

import threading
import time
from typing import Dict, List, Optional

from blockchain.block import Blockchain
from blockchain.transaction import Transaction, TransactionType
from network.mempool import Mempool
from trading.order import Order, OrderSide, OrderStatus
from trading.order_book import OrderBook
from trading.trade import Trade


class MatchingEngine:
    """Matches crossing orders and settles via TRANSFER transactions.

    Price-time priority: maker price wins on crossing orders.
    Self-trade prevention: orders from the same address cannot match.
    Settlement: creates a signed TRANSFER from seller to buyer, submitted to mempool.
    """

    def __init__(
        self,
        order_book: OrderBook,
        blockchain: Blockchain,
        mempool: Mempool,
    ):
        self.order_book = order_book
        self.blockchain = blockchain
        self.mempool = mempool
        self._trades: List[Trade] = []
        self._lock = threading.Lock()
        self._last_price: Optional[float] = None
        self._volume_24h: float = 0.0
        self._volume_reset_time: float = time.time()
        self._pending_nonces: Dict[str, int] = {}  # address -> next nonce to use

    def process_order(self, order: Order) -> List[Trade]:
        """Process a new order: add to book and attempt matching.

        Returns list of trades generated (may be empty if no match).
        """
        # Add to order book first
        error = self.order_book.add_order(order)
        if error:
            raise ValueError(error)

        # Attempt matching
        if order.side == OrderSide.BUY:
            trades = self._match_buy(order)
        else:
            trades = self._match_sell(order)

        return trades

    def _match_buy(self, buy_order: Order) -> List[Trade]:
        """Match a buy order against existing asks (lowest ask first)."""
        trades = []
        asks = self.order_book.get_sorted_asks()

        for ask in asks:
            if buy_order.remaining_amount <= 0:
                break

            # Skip self-trades
            if ask.address == buy_order.address:
                continue

            # Buy price must be >= ask price for a match
            if buy_order.price < ask.price:
                break  # No more matches possible (asks are sorted ascending)

            # Maker price wins (the ask was there first)
            exec_price = ask.price
            fill_amount = round(min(buy_order.remaining_amount, ask.remaining_amount), 4)

            trade = self._settle(buy_order, ask, exec_price, fill_amount)
            if trade:
                trades.append(trade)

        # Remove fully filled orders from book
        if buy_order.status == OrderStatus.FILLED:
            self.order_book.remove_order(buy_order.order_id)
        if trades:
            for ask in asks:
                if ask.status == OrderStatus.FILLED:
                    self.order_book.remove_order(ask.order_id)

        return trades

    def _match_sell(self, sell_order: Order) -> List[Trade]:
        """Match a sell order against existing bids (highest bid first)."""
        trades = []
        bids = self.order_book.get_sorted_bids()

        for bid in bids:
            if sell_order.remaining_amount <= 0:
                break

            # Skip self-trades
            if bid.address == sell_order.address:
                continue

            # Sell price must be <= bid price for a match
            if sell_order.price > bid.price:
                break  # No more matches possible (bids are sorted descending)

            # Maker price wins (the bid was there first)
            exec_price = bid.price
            fill_amount = round(min(sell_order.remaining_amount, bid.remaining_amount), 4)

            trade = self._settle(bid, sell_order, exec_price, fill_amount)
            if trade:
                trades.append(trade)

        # Remove fully filled orders from book
        if sell_order.status == OrderStatus.FILLED:
            self.order_book.remove_order(sell_order.order_id)
        if trades:
            for bid in bids:
                if bid.status == OrderStatus.FILLED:
                    self.order_book.remove_order(bid.order_id)

        return trades

    def _settle(
        self,
        buy_order: Order,
        sell_order: Order,
        exec_price: float,
        fill_amount: float,
    ) -> Optional[Trade]:
        """Create a TRANSFER transaction to settle the match."""
        # Verify seller has enough balance
        seller_balance = self.blockchain.state.get_balance(sell_order.address)
        if seller_balance < fill_amount:
            return None

        # Verify seller has private key for signing
        if not sell_order._private_key:
            return None

        # Use pending nonce tracker to avoid collisions for multiple fills
        state_nonce = self.blockchain.state.get_nonce(sell_order.address)
        seller_nonce = self._pending_nonces.get(sell_order.address, state_nonce)
        tx = Transaction(
            tx_type=TransactionType.TRANSFER,
            sender=sell_order.address,
            recipient=buy_order.address,
            amount=fill_amount,
            nonce=seller_nonce,
            public_key=sell_order.public_key,
        )
        tx.sign(sell_order._private_key)

        # Submit to mempool
        pool_error = self.mempool.add_transaction(tx)
        if pool_error:
            return None

        # Track nonce for future settlements from same seller
        self._pending_nonces[sell_order.address] = seller_nonce + 1

        # Update order states
        buy_order.remaining_amount = round(buy_order.remaining_amount - fill_amount, 4)
        sell_order.remaining_amount = round(sell_order.remaining_amount - fill_amount, 4)

        if buy_order.remaining_amount <= 0:
            buy_order.status = OrderStatus.FILLED
        else:
            buy_order.status = OrderStatus.PARTIALLY_FILLED

        if sell_order.remaining_amount <= 0:
            sell_order.status = OrderStatus.FILLED
        else:
            sell_order.status = OrderStatus.PARTIALLY_FILLED

        # Record trade
        trade = Trade(
            buyer_address=buy_order.address,
            seller_address=sell_order.address,
            price=exec_price,
            amount=fill_amount,
            buy_order_id=buy_order.order_id,
            sell_order_id=sell_order.order_id,
            tx_hash=tx.tx_hash,
        )

        with self._lock:
            self._trades.append(trade)
            self._last_price = exec_price
            self._volume_24h += fill_amount

        return trade

    def get_trades(self, limit: int = 50, address: Optional[str] = None) -> List[dict]:
        """Get recent trades, optionally filtered by address."""
        with self._lock:
            trades = self._trades.copy()

        if address:
            trades = [
                t for t in trades
                if t.buyer_address == address or t.seller_address == address
            ]

        # Most recent first
        trades.sort(key=lambda t: t.timestamp, reverse=True)
        return [t.to_dict() for t in trades[:limit]]

    def get_market_summary(self) -> dict:
        """Return last price, bid/ask spread, and 24h volume."""
        # Reset 24h volume if stale
        with self._lock:
            now = time.time()
            if now - self._volume_reset_time > 86400:
                self._volume_24h = 0.0
                self._volume_reset_time = now
            last_price = self._last_price
            volume_24h = self._volume_24h

        best_bid, best_ask = self.order_book.get_spread()

        return {
            "last_price": last_price,
            "best_bid": best_bid,
            "best_ask": best_ask,
            "spread": round(best_ask - best_bid, 4) if best_bid is not None and best_ask is not None else None,
            "volume_24h": round(volume_24h, 4),
            "trade_count": len(self._trades),
        }
