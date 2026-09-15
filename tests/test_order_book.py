"""Tests for the OrderBook class."""

import pytest

from crypto.keys import generate_keypair
from trading.order import Order, OrderSide, OrderStatus
from trading.order_book import OrderBook


def _make_order(side, price, amount, keypair=None):
    """Helper to create a signed order."""
    if keypair is None:
        from crypto.keys import generate_keypair
        keypair = dict(zip(["private_key", "public_key", "address"], generate_keypair()))

    order = Order(
        side=side,
        address=keypair["address"],
        price=price,
        amount=amount,
        public_key=keypair["public_key"],
    )
    order.sign(keypair["private_key"])
    return order


class TestOrderPlacement:
    def test_add_valid_order(self, order_book):
        order = _make_order(OrderSide.BUY, 100.0, 10.0)
        error = order_book.add_order(order)
        assert error is None
        assert order_book.size == 1

    def test_reject_duplicate(self, order_book):
        order = _make_order(OrderSide.BUY, 100.0, 10.0)
        order_book.add_order(order)
        error = order_book.add_order(order)
        assert error == "Order already in book"

    def test_reject_invalid_signature(self, order_book):
        order = _make_order(OrderSide.BUY, 100.0, 10.0)
        order.signature = "bad"
        error = order_book.add_order(order)
        assert error == "Invalid order signature"

    def test_reject_when_full(self):
        book = OrderBook(max_size=1)
        o1 = _make_order(OrderSide.BUY, 100.0, 10.0)
        o2 = _make_order(OrderSide.BUY, 101.0, 5.0)
        book.add_order(o1)
        error = book.add_order(o2)
        assert error == "Order book is full"


class TestOrderCancellation:
    def test_cancel_own_order(self, order_book):
        kp = dict(zip(["private_key", "public_key", "address"], generate_keypair()))
        order = _make_order(OrderSide.SELL, 200.0, 5.0, kp)
        order_book.add_order(order)

        error = order_book.cancel_order(order.order_id, kp["address"])
        assert error is None
        assert order_book.size == 0

    def test_cannot_cancel_others_order(self, order_book):
        kp1 = dict(zip(["private_key", "public_key", "address"], generate_keypair()))
        kp2 = dict(zip(["private_key", "public_key", "address"], generate_keypair()))
        order = _make_order(OrderSide.BUY, 100.0, 10.0, kp1)
        order_book.add_order(order)

        error = order_book.cancel_order(order.order_id, kp2["address"])
        assert error == "Not authorized to cancel this order"

    def test_cancel_nonexistent(self, order_book):
        error = order_book.cancel_order("no-such-id", "0xabc")
        assert error == "Order not found"


class TestSorting:
    def test_bids_sorted_price_descending(self, order_book):
        kp = dict(zip(["private_key", "public_key", "address"], generate_keypair()))
        for price in [100, 105, 102]:
            order_book.add_order(_make_order(OrderSide.BUY, price, 1.0, kp))

        bids = order_book.get_sorted_bids()
        prices = [b.price for b in bids]
        assert prices == [105.0, 102.0, 100.0]

    def test_asks_sorted_price_ascending(self, order_book):
        kp = dict(zip(["private_key", "public_key", "address"], generate_keypair()))
        for price in [200, 195, 198]:
            order_book.add_order(_make_order(OrderSide.SELL, price, 1.0, kp))

        asks = order_book.get_sorted_asks()
        prices = [a.price for a in asks]
        assert prices == [195.0, 198.0, 200.0]

    def test_spread(self, order_book):
        kp = dict(zip(["private_key", "public_key", "address"], generate_keypair()))
        order_book.add_order(_make_order(OrderSide.BUY, 99.0, 1.0, kp))
        order_book.add_order(_make_order(OrderSide.SELL, 101.0, 1.0, kp))

        best_bid, best_ask = order_book.get_spread()
        assert best_bid == 99.0
        assert best_ask == 101.0

    def test_empty_spread(self, order_book):
        best_bid, best_ask = order_book.get_spread()
        assert best_bid is None
        assert best_ask is None


class TestOpenOrders:
    def test_filter_by_address(self, order_book):
        kp1 = dict(zip(["private_key", "public_key", "address"], generate_keypair()))
        kp2 = dict(zip(["private_key", "public_key", "address"], generate_keypair()))
        order_book.add_order(_make_order(OrderSide.BUY, 100.0, 1.0, kp1))
        order_book.add_order(_make_order(OrderSide.SELL, 200.0, 1.0, kp2))

        orders = order_book.get_open_orders(address=kp1["address"])
        assert len(orders) == 1
        assert orders[0].address == kp1["address"]
