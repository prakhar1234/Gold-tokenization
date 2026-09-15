"""Tests for the MatchingEngine class."""

import pytest

from blockchain.transaction import Transaction, TransactionType
from crypto.keys import generate_keypair
from trading.order import Order, OrderSide, OrderStatus
from trading.matching_engine import MatchingEngine


def _kp():
    """Generate a fresh keypair dict."""
    priv, pub, addr = generate_keypair()
    return {"private_key": priv, "public_key": pub, "address": addr}


def _make_signed_order(side, price, amount, keypair):
    """Create and sign an order, storing the private key for settlement."""
    order = Order(
        side=side,
        address=keypair["address"],
        price=price,
        amount=amount,
        public_key=keypair["public_key"],
    )
    order.sign(keypair["private_key"])
    return order


def _fund_address(blockchain, authority_kp, address, amount):
    """Mint tokens to an address by creating a MINT tx and mining a block."""
    tx = Transaction(
        tx_type=TransactionType.MINT,
        sender="NETWORK",
        recipient=address,
        amount=amount,
        nonce=0,
        public_key=authority_kp["public_key"],
    )
    tx.sign(authority_kp["private_key"])
    block = blockchain.create_block([tx], "validator-0")
    assert block is not None
    return block


class TestFullFill:
    def test_exact_match(self, order_book, matching_engine, blockchain):
        """Buy 10 @ 100, Sell 10 @ 100 -> one trade for 10 @ 100."""
        authority = _kp()
        buyer = _kp()
        seller = _kp()

        # Fund seller
        _fund_address(blockchain, authority, seller["address"], 100.0)

        # Place sell order first (maker)
        sell = _make_signed_order(OrderSide.SELL, 100.0, 10.0, seller)
        trades_sell = matching_engine.process_order(sell)
        assert len(trades_sell) == 0  # No match yet

        # Place buy order (taker)
        buy = _make_signed_order(OrderSide.BUY, 100.0, 10.0, buyer)
        trades_buy = matching_engine.process_order(buy)

        assert len(trades_buy) == 1
        trade = trades_buy[0]
        assert trade.price == 100.0
        assert trade.amount == 10.0
        assert trade.buyer_address == buyer["address"]
        assert trade.seller_address == seller["address"]
        assert trade.tx_hash != ""

        # Both orders should be fully filled
        assert buy.status == OrderStatus.FILLED
        assert sell.status == OrderStatus.FILLED


class TestPartialFill:
    def test_partial_fill_buy(self, order_book, matching_engine, blockchain):
        """Buy 20 @ 100, Sell 10 @ 100 -> partial fill, remainder stays."""
        authority = _kp()
        buyer = _kp()
        seller = _kp()

        _fund_address(blockchain, authority, seller["address"], 100.0)

        sell = _make_signed_order(OrderSide.SELL, 100.0, 10.0, seller)
        matching_engine.process_order(sell)

        buy = _make_signed_order(OrderSide.BUY, 100.0, 20.0, buyer)
        trades = matching_engine.process_order(buy)

        assert len(trades) == 1
        assert trades[0].amount == 10.0
        assert buy.status == OrderStatus.PARTIALLY_FILLED
        assert buy.remaining_amount == 10.0
        assert sell.status == OrderStatus.FILLED

    def test_partial_fill_sell(self, order_book, matching_engine, blockchain):
        """Buy 10 @ 100, Sell 20 @ 100 -> partial fill of sell."""
        authority = _kp()
        buyer = _kp()
        seller = _kp()

        _fund_address(blockchain, authority, seller["address"], 100.0)

        buy = _make_signed_order(OrderSide.BUY, 100.0, 10.0, buyer)
        matching_engine.process_order(buy)

        sell = _make_signed_order(OrderSide.SELL, 100.0, 20.0, seller)
        trades = matching_engine.process_order(sell)

        assert len(trades) == 1
        assert trades[0].amount == 10.0
        assert sell.status == OrderStatus.PARTIALLY_FILLED
        assert sell.remaining_amount == 10.0


class TestSelfTradePrevention:
    def test_no_self_trade(self, order_book, matching_engine, blockchain):
        """Orders from the same address should not match each other."""
        authority = _kp()
        trader = _kp()

        _fund_address(blockchain, authority, trader["address"], 100.0)

        buy = _make_signed_order(OrderSide.BUY, 100.0, 10.0, trader)
        sell = _make_signed_order(OrderSide.SELL, 100.0, 10.0, trader)

        matching_engine.process_order(buy)
        trades = matching_engine.process_order(sell)

        assert len(trades) == 0
        assert buy.status == OrderStatus.OPEN
        assert sell.status == OrderStatus.OPEN


class TestMakerPriceWins:
    def test_maker_price_on_crossing_buy(self, order_book, matching_engine, blockchain):
        """Ask at 95, buy at 100 -> executes at 95 (maker price)."""
        authority = _kp()
        buyer = _kp()
        seller = _kp()

        _fund_address(blockchain, authority, seller["address"], 100.0)

        sell = _make_signed_order(OrderSide.SELL, 95.0, 5.0, seller)
        matching_engine.process_order(sell)

        buy = _make_signed_order(OrderSide.BUY, 100.0, 5.0, buyer)
        trades = matching_engine.process_order(buy)

        assert len(trades) == 1
        assert trades[0].price == 95.0  # Maker (ask) price wins

    def test_maker_price_on_crossing_sell(self, order_book, matching_engine, blockchain):
        """Bid at 105, sell at 100 -> executes at 105 (maker price)."""
        authority = _kp()
        buyer = _kp()
        seller = _kp()

        _fund_address(blockchain, authority, seller["address"], 100.0)

        buy = _make_signed_order(OrderSide.BUY, 105.0, 5.0, buyer)
        matching_engine.process_order(buy)

        sell = _make_signed_order(OrderSide.SELL, 100.0, 5.0, seller)
        trades = matching_engine.process_order(sell)

        assert len(trades) == 1
        assert trades[0].price == 105.0  # Maker (bid) price wins


class TestNoMatchWhenPricesDontCross:
    def test_buy_below_ask(self, order_book, matching_engine, blockchain):
        """Buy at 90, Sell at 100 -> no match."""
        authority = _kp()
        buyer = _kp()
        seller = _kp()

        _fund_address(blockchain, authority, seller["address"], 100.0)

        sell = _make_signed_order(OrderSide.SELL, 100.0, 10.0, seller)
        matching_engine.process_order(sell)

        buy = _make_signed_order(OrderSide.BUY, 90.0, 10.0, buyer)
        trades = matching_engine.process_order(buy)

        assert len(trades) == 0


class TestMarketSummary:
    def test_summary_after_trade(self, order_book, matching_engine, blockchain):
        authority = _kp()
        buyer = _kp()
        seller = _kp()

        _fund_address(blockchain, authority, seller["address"], 100.0)

        sell = _make_signed_order(OrderSide.SELL, 100.0, 5.0, seller)
        matching_engine.process_order(sell)

        buy = _make_signed_order(OrderSide.BUY, 100.0, 5.0, buyer)
        matching_engine.process_order(buy)

        summary = matching_engine.get_market_summary()
        assert summary["last_price"] == 100.0
        assert summary["volume_24h"] == 5.0
        assert summary["trade_count"] == 1

    def test_empty_summary(self, matching_engine):
        summary = matching_engine.get_market_summary()
        assert summary["last_price"] is None
        assert summary["volume_24h"] == 0.0
        assert summary["best_bid"] is None
        assert summary["best_ask"] is None
