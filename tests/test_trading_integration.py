"""End-to-end integration tests: place orders → match → mine → verify balances."""

import pytest

from blockchain.transaction import Transaction, TransactionType
from crypto.keys import generate_keypair
from trading.order import Order, OrderSide


def _kp():
    priv, pub, addr = generate_keypair()
    return {"private_key": priv, "public_key": pub, "address": addr}


def _fund_via_api(client, authority_kp, recipient_address, amount, nonce=0):
    """Mint tokens via the API, then mine the block."""
    tx = Transaction(
        tx_type=TransactionType.MINT,
        sender="NETWORK",
        recipient=recipient_address,
        amount=amount,
        nonce=nonce,
        public_key=authority_kp["public_key"],
    )
    tx.sign(authority_kp["private_key"])

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
    order = Order(
        side=side,
        address=keypair["address"],
        price=price,
        amount=amount,
        public_key=keypair["public_key"],
    )
    order.sign(keypair["private_key"])
    data = order.to_dict()
    data["private_key"] = keypair["private_key"]
    return data


class TestEndToEndTrading:
    def test_full_trade_cycle(self, client):
        """Fund seller → place sell → place buy → match → mine → verify balances."""
        authority = _kp()
        buyer = _kp()
        seller = _kp()

        # Fund seller with 50 AUT
        _fund_via_api(client, authority, seller["address"], 50.0)

        # Verify seller balance
        resp = client.get(f"/balance/{seller['address']}")
        assert resp.get_json()["balance"] == 50.0

        # Seller places sell order for 10 AUT @ 100 USD
        sell_data = _make_order_payload(OrderSide.SELL, 100.0, 10.0, seller)
        resp = client.post("/orders", json=sell_data)
        assert resp.status_code == 201
        assert resp.get_json()["status"] == "OPEN"

        # Buyer places buy order for 10 AUT @ 100 USD -> immediate match
        buy_data = _make_order_payload(OrderSide.BUY, 100.0, 10.0, buyer)
        resp = client.post("/orders", json=buy_data)
        assert resp.status_code == 201
        body = resp.get_json()
        assert body["status"] == "FILLED"
        assert len(body["trades"]) == 1
        assert body["trades"][0]["amount"] == 10.0

        # Verify a TRANSFER tx is in the mempool
        resp = client.get("/mempool")
        mempool_txs = resp.get_json()["transactions"]
        transfer_txs = [t for t in mempool_txs if t["tx_type"] == "TRANSFER"]
        assert len(transfer_txs) == 1
        assert transfer_txs[0]["sender"] == seller["address"]
        assert transfer_txs[0]["recipient"] == buyer["address"]
        assert transfer_txs[0]["amount"] == 10.0

        # Mine the block to settle
        resp = client.post("/mine", json={"validator": "validator-0"})
        assert resp.status_code == 200

        # Verify final balances
        resp = client.get(f"/balance/{seller['address']}")
        assert resp.get_json()["balance"] == 40.0  # 50 - 10

        resp = client.get(f"/balance/{buyer['address']}")
        assert resp.get_json()["balance"] == 10.0

    def test_partial_fill_then_complete(self, client):
        """Sell 20, buy 10 (partial), buy 10 more (completes), mine all."""
        authority = _kp()
        buyer1 = _kp()
        buyer2 = _kp()
        seller = _kp()

        _fund_via_api(client, authority, seller["address"], 50.0)

        # Sell 20 AUT @ 100
        sell_data = _make_order_payload(OrderSide.SELL, 100.0, 20.0, seller)
        resp = client.post("/orders", json=sell_data)
        assert resp.status_code == 201

        # Buy 10 -> partial fill
        buy_data = _make_order_payload(OrderSide.BUY, 100.0, 10.0, buyer1)
        resp = client.post("/orders", json=buy_data)
        body = resp.get_json()
        assert body["status"] == "FILLED"
        assert len(body["trades"]) == 1

        # Mine first transfer so nonces/state are up to date
        resp = client.post("/mine", json={"validator": "validator-0"})
        assert resp.status_code == 200

        # Buy 10 more -> completes the sell order
        buy_data2 = _make_order_payload(OrderSide.BUY, 100.0, 10.0, buyer2)
        resp = client.post("/orders", json=buy_data2)
        body = resp.get_json()
        assert body["status"] == "FILLED"
        assert len(body["trades"]) == 1

        # Mine second transfer
        resp = client.post("/mine", json={"validator": "validator-0"})
        assert resp.status_code == 200

        # Verify balances
        resp = client.get(f"/balance/{seller['address']}")
        assert resp.get_json()["balance"] == 30.0  # 50 - 10 - 10

        resp = client.get(f"/balance/{buyer1['address']}")
        assert resp.get_json()["balance"] == 10.0

        resp = client.get(f"/balance/{buyer2['address']}")
        assert resp.get_json()["balance"] == 10.0

    def test_market_summary_updates(self, client):
        """After a trade, market summary reflects the execution."""
        authority = _kp()
        buyer = _kp()
        seller = _kp()

        _fund_via_api(client, authority, seller["address"], 50.0)

        # Place and match
        client.post("/orders", json=_make_order_payload(OrderSide.SELL, 150.0, 5.0, seller))
        client.post("/orders", json=_make_order_payload(OrderSide.BUY, 150.0, 5.0, buyer))

        resp = client.get("/market/summary")
        summary = resp.get_json()
        assert summary["last_price"] == 150.0
        assert summary["volume_24h"] == 5.0
        assert summary["trade_count"] == 1

    def test_order_book_state_after_trades(self, client):
        """After full fills, order book should be empty."""
        authority = _kp()
        buyer = _kp()
        seller = _kp()

        _fund_via_api(client, authority, seller["address"], 50.0)

        client.post("/orders", json=_make_order_payload(OrderSide.SELL, 100.0, 10.0, seller))
        client.post("/orders", json=_make_order_payload(OrderSide.BUY, 100.0, 10.0, buyer))

        resp = client.get("/orders/book")
        book = resp.get_json()
        assert book["bid_count"] == 0
        assert book["ask_count"] == 0

    def test_no_trade_without_crossing(self, client):
        """Non-crossing orders stay in the book, no trades."""
        authority = _kp()
        buyer = _kp()
        seller = _kp()

        _fund_via_api(client, authority, seller["address"], 50.0)

        # Sell at 200, buy at 100 -> no match
        client.post("/orders", json=_make_order_payload(OrderSide.SELL, 200.0, 10.0, seller))
        resp = client.post("/orders", json=_make_order_payload(OrderSide.BUY, 100.0, 10.0, buyer))
        assert resp.get_json()["status"] == "OPEN"
        assert len(resp.get_json()["trades"]) == 0

        resp = client.get("/orders/book")
        book = resp.get_json()
        assert book["bid_count"] == 1
        assert book["ask_count"] == 1
