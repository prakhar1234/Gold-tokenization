"""Tests for the trading Flask API endpoints."""

import pytest

from blockchain.transaction import Transaction, TransactionType
from crypto.keys import generate_keypair
from trading.order import Order, OrderSide


def _kp():
    priv, pub, addr = generate_keypair()
    return {"private_key": priv, "public_key": pub, "address": addr}


def _fund_via_api(client, authority_kp, recipient_address, amount):
    """Mint tokens via the API, then mine the block."""
    tx = Transaction(
        tx_type=TransactionType.MINT,
        sender="NETWORK",
        recipient=recipient_address,
        amount=amount,
        nonce=0,
        public_key=authority_kp["public_key"],
    )
    tx.sign(authority_kp["private_key"])

    # Add reserve first
    client.post("/reserves", json={
        "custodian": "Test Vault",
        "amount_grams": amount * 2,
        "purity": 1.0,
    })

    resp = client.post("/transactions", json=tx.to_dict())
    assert resp.status_code == 201

    resp = client.post("/mine", json={"validator": "validator-0"})
    assert resp.status_code == 200


def _make_order_payload(side, price, amount, keypair):
    """Create a signed order dict ready for the API."""
    order = Order(
        side=side,
        address=keypair["address"],
        price=price,
        amount=amount,
        public_key=keypair["public_key"],
    )
    order.sign(keypair["private_key"])
    data = order.to_dict()
    data["private_key"] = keypair["private_key"]  # PoC: for settlement
    return data


class TestPlaceOrder:
    def test_place_buy_order(self, client):
        kp = _kp()
        data = _make_order_payload(OrderSide.BUY, 100.0, 10.0, kp)
        resp = client.post("/orders", json=data)
        assert resp.status_code == 201
        body = resp.get_json()
        assert body["order_id"]
        assert body["status"] == "OPEN"

    def test_place_sell_order_with_balance(self, client):
        authority = _kp()
        seller = _kp()
        _fund_via_api(client, authority, seller["address"], 50.0)

        data = _make_order_payload(OrderSide.SELL, 200.0, 10.0, seller)
        resp = client.post("/orders", json=data)
        assert resp.status_code == 201

    def test_reject_sell_insufficient_balance(self, client):
        seller = _kp()  # No funds
        data = _make_order_payload(OrderSide.SELL, 200.0, 10.0, seller)
        resp = client.post("/orders", json=data)
        assert resp.status_code == 400
        assert "Insufficient balance" in resp.get_json()["error"]

    def test_reject_missing_fields(self, client):
        resp = client.post("/orders", json={"side": "BUY"})
        assert resp.status_code == 400

    def test_reject_invalid_signature(self, client):
        kp = _kp()
        data = _make_order_payload(OrderSide.BUY, 100.0, 10.0, kp)
        data["signature"] = "0" * 128
        resp = client.post("/orders", json=data)
        assert resp.status_code == 400


class TestCancelOrder:
    def test_cancel_own_order(self, client):
        kp = _kp()
        data = _make_order_payload(OrderSide.BUY, 100.0, 10.0, kp)
        resp = client.post("/orders", json=data)
        order_id = resp.get_json()["order_id"]

        resp = client.delete(f"/orders/{order_id}", json={"address": kp["address"]})
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "CANCELLED"

    def test_cancel_without_address(self, client):
        kp = _kp()
        data = _make_order_payload(OrderSide.BUY, 100.0, 10.0, kp)
        resp = client.post("/orders", json=data)
        order_id = resp.get_json()["order_id"]

        resp = client.delete(f"/orders/{order_id}", json={})
        assert resp.status_code == 400


class TestListOrders:
    def test_list_all(self, client):
        kp = _kp()
        client.post("/orders", json=_make_order_payload(OrderSide.BUY, 100.0, 5.0, kp))
        client.post("/orders", json=_make_order_payload(OrderSide.BUY, 101.0, 3.0, kp))

        resp = client.get("/orders")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["count"] == 2

    def test_list_filtered_by_address(self, client):
        kp1 = _kp()
        kp2 = _kp()
        client.post("/orders", json=_make_order_payload(OrderSide.BUY, 100.0, 5.0, kp1))
        client.post("/orders", json=_make_order_payload(OrderSide.BUY, 101.0, 3.0, kp2))

        resp = client.get(f"/orders?address={kp1['address']}")
        body = resp.get_json()
        assert body["count"] == 1


class TestOrderBook:
    def test_book_snapshot(self, client):
        kp = _kp()
        client.post("/orders", json=_make_order_payload(OrderSide.BUY, 99.0, 5.0, kp))

        authority = _kp()
        seller = _kp()
        _fund_via_api(client, authority, seller["address"], 50.0)
        client.post("/orders", json=_make_order_payload(OrderSide.SELL, 101.0, 3.0, seller))

        resp = client.get("/orders/book")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["bid_count"] == 1
        assert body["ask_count"] == 1


class TestTrades:
    def test_trades_after_match(self, client):
        authority = _kp()
        buyer = _kp()
        seller = _kp()
        _fund_via_api(client, authority, seller["address"], 50.0)

        # Sell order (maker)
        client.post("/orders", json=_make_order_payload(OrderSide.SELL, 100.0, 5.0, seller))
        # Buy order (taker) -> match
        client.post("/orders", json=_make_order_payload(OrderSide.BUY, 100.0, 5.0, buyer))

        resp = client.get("/trades")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["count"] == 1
        assert body["trades"][0]["amount"] == 5.0

    def test_trades_by_address(self, client):
        authority = _kp()
        buyer = _kp()
        seller = _kp()
        _fund_via_api(client, authority, seller["address"], 50.0)

        client.post("/orders", json=_make_order_payload(OrderSide.SELL, 100.0, 5.0, seller))
        client.post("/orders", json=_make_order_payload(OrderSide.BUY, 100.0, 5.0, buyer))

        resp = client.get(f"/trades/{buyer['address']}")
        assert resp.status_code == 200
        assert resp.get_json()["count"] == 1

    def test_empty_trades(self, client):
        resp = client.get("/trades")
        assert resp.status_code == 200
        assert resp.get_json()["count"] == 0


class TestMarketSummary:
    def test_summary(self, client):
        resp = client.get("/market/summary")
        assert resp.status_code == 200
        body = resp.get_json()
        assert "last_price" in body
        assert "volume_24h" in body
        assert "best_bid" in body
        assert "best_ask" in body
