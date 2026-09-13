"""Tests for Flask node API endpoints."""

import json
import pytest
from blockchain.transaction import Transaction, TransactionType


class TestNodeAPI:
    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "ok"

    def test_get_chain(self, client):
        resp = client.get("/chain")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["length"] == 1  # genesis only
        assert len(data["chain"]) == 1

    def test_chain_length(self, client):
        resp = client.get("/chain/length")
        assert resp.status_code == 200
        assert resp.get_json()["length"] == 1

    def test_get_block(self, client):
        resp = client.get("/blocks/0")
        assert resp.status_code == 200
        assert resp.get_json()["header"]["index"] == 0

    def test_get_block_not_found(self, client):
        resp = client.get("/blocks/999")
        assert resp.status_code == 404

    def test_balance_empty(self, client):
        resp = client.get("/balance/0x" + "a" * 40)
        assert resp.status_code == 200
        assert resp.get_json()["balance"] == 0.0

    def test_submit_and_mine(self, client, app, authority_keypair, alice_keypair):
        # Add reserve first
        resp = client.post("/reserves", json={
            "custodian": "Test Vault",
            "amount_grams": 1000.0,
            "purity": 1.0,
        })
        assert resp.status_code == 201

        # Submit MINT transaction
        tx = Transaction(
            tx_type=TransactionType.MINT, sender="NETWORK",
            recipient=alice_keypair["address"], amount=100.0, nonce=0,
            public_key=authority_keypair["public_key"],
        )
        tx.sign(authority_keypair["private_key"])

        resp = client.post("/transactions", json=tx.to_dict())
        assert resp.status_code == 201

        # Check mempool
        resp = client.get("/mempool")
        assert resp.get_json()["size"] == 1

        # Mine block
        resp = client.post("/mine", json={"validator": "validator-0"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["block"]["header"]["index"] == 1

        # Verify balance
        resp = client.get(f"/balance/{alice_keypair['address']}")
        assert resp.get_json()["balance"] == 100.0

        # Mempool should be empty
        resp = client.get("/mempool")
        assert resp.get_json()["size"] == 0

    def test_register_peer(self, client):
        resp = client.post("/nodes/register", json={"node_url": "http://127.0.0.1:9999"})
        assert resp.status_code == 201

        resp = client.get("/nodes")
        assert "http://127.0.0.1:9999" in resp.get_json()["peers"]

    def test_add_reserve(self, client):
        resp = client.post("/reserves", json={
            "custodian": "Test Vault",
            "amount_grams": 500.0,
            "purity": 0.999,
            "certificate_ref": "CERT-001",
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["total_reserved"] == 499.5

    def test_get_reserves(self, client):
        client.post("/reserves", json={
            "custodian": "Vault", "amount_grams": 100.0, "purity": 1.0,
        })
        resp = client.get("/reserves")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["reserves"]) == 1
        assert data["audit"]["total_reserved_grams"] == 100.0

    def test_token_info(self, client):
        resp = client.get("/token/info")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["symbol"] == "AUT"

    def test_mine_no_transactions(self, client):
        resp = client.post("/mine", json={"validator": "v0"})
        assert resp.status_code == 400

    def test_mine_no_validator(self, client):
        resp = client.post("/mine", json={})
        assert resp.status_code == 400

    def test_submit_invalid_transaction(self, client):
        resp = client.post("/transactions", json={
            "tx_type": "TRANSFER",
            "sender": "0x" + "a" * 40,
            "recipient": "0x" + "b" * 40,
            "amount": 10.0,
            "nonce": 0,
            "timestamp": 1000.0,
            "public_key": "",
            "signature": "",
            "tx_hash": "",
        })
        assert resp.status_code == 400

    def test_mint_exceeding_reserves(self, client, authority_keypair, alice_keypair):
        # No reserves added — minting should fail
        tx = Transaction(
            tx_type=TransactionType.MINT, sender="NETWORK",
            recipient=alice_keypair["address"], amount=100.0, nonce=0,
            public_key=authority_keypair["public_key"],
        )
        tx.sign(authority_keypair["private_key"])

        resp = client.post("/transactions", json=tx.to_dict())
        assert resp.status_code == 400
        assert "reserves" in resp.get_json()["error"].lower()
