"""Tests for per-client portfolio tracking."""

import pytest
from blockchain.transaction import Transaction, TransactionType
from gold.reserve import ReserveLedger, ReserveProof


# ── ReserveProof with depositor_address ─────────────────────────


class TestReserveProofDepositor:
    def test_create_with_depositor(self):
        proof = ReserveProof(
            custodian="Vault A",
            amount_grams=500.0,
            purity=0.999,
            depositor_address="0xaaa",
        )
        assert proof.depositor_address == "0xaaa"
        assert proof.proof_id != ""

    def test_backward_compat_no_depositor(self):
        proof = ReserveProof(
            custodian="Vault B",
            amount_grams=250.0,
        )
        assert proof.depositor_address == ""
        assert proof.proof_id != ""

    def test_to_dict_includes_depositor(self):
        proof = ReserveProof(
            custodian="Vault", amount_grams=100.0, depositor_address="0xbbb",
        )
        d = proof.to_dict()
        assert d["depositor_address"] == "0xbbb"

    def test_from_dict_with_depositor(self):
        d = {
            "custodian": "V",
            "amount_grams": 100.0,
            "purity": 1.0,
            "depositor_address": "0xccc",
        }
        proof = ReserveProof.from_dict(d)
        assert proof.depositor_address == "0xccc"

    def test_from_dict_without_depositor(self):
        """Old data missing depositor_address should default to empty string."""
        d = {
            "custodian": "V",
            "amount_grams": 100.0,
            "purity": 1.0,
        }
        proof = ReserveProof.from_dict(d)
        assert proof.depositor_address == ""

    def test_depositor_affects_proof_id(self):
        """Two otherwise-identical proofs with different depositors get different IDs."""
        ts = 1000.0
        a = ReserveProof(custodian="V", amount_grams=100.0, timestamp=ts, depositor_address="0xA")
        b = ReserveProof(custodian="V", amount_grams=100.0, timestamp=ts, depositor_address="0xB")
        assert a.proof_id != b.proof_id


# ── ReserveLedger per-depositor methods ─────────────────────────


class TestDepositorTracking:
    def test_get_depositor_reserves(self):
        ledger = ReserveLedger()
        p1 = ReserveProof(custodian="V", amount_grams=100.0, purity=1.0, depositor_address="0xA")
        p2 = ReserveProof(custodian="V", amount_grams=200.0, purity=1.0, depositor_address="0xA")
        p3 = ReserveProof(custodian="V", amount_grams=300.0, purity=1.0, depositor_address="0xB")
        ledger.add_reserve(p1)
        ledger.add_reserve(p2)
        ledger.add_reserve(p3)

        a_reserves = ledger.get_depositor_reserves("0xA")
        assert len(a_reserves) == 2
        assert ledger.get_depositor_reserved("0xA") == 300.0
        assert ledger.get_depositor_reserved("0xB") == 300.0
        assert ledger.get_depositor_reserved("0xNONE") == 0.0

    def test_depositor_isolation(self):
        """Depositor A's reserves don't count for depositor B."""
        ledger = ReserveLedger()
        ledger.add_reserve(ReserveProof(custodian="V", amount_grams=500.0, purity=1.0, depositor_address="0xA"))
        ledger.add_reserve(ReserveProof(custodian="V", amount_grams=200.0, purity=1.0, depositor_address="0xB"))

        assert ledger.get_depositor_reserved("0xA") == 500.0
        assert ledger.get_depositor_reserved("0xB") == 200.0
        assert ledger.total_reserved == 700.0

    def test_can_mint_for_depositor(self):
        ledger = ReserveLedger()
        ledger.add_reserve(ReserveProof(custodian="V", amount_grams=100.0, purity=1.0, depositor_address="0xA"))

        assert ledger.can_mint_for_depositor("0xA", 100.0)
        assert not ledger.can_mint_for_depositor("0xA", 100.01)

        ledger.record_depositor_mint("0xA", 60.0)
        assert ledger.can_mint_for_depositor("0xA", 40.0)
        assert not ledger.can_mint_for_depositor("0xA", 40.01)

    def test_record_depositor_mint(self):
        ledger = ReserveLedger()
        ledger.add_reserve(ReserveProof(custodian="V", amount_grams=500.0, purity=1.0, depositor_address="0xA"))

        ledger.record_depositor_mint("0xA", 100.0)
        assert ledger.get_depositor_minted("0xA") == 100.0

        ledger.record_depositor_mint("0xA", 50.0)
        assert ledger.get_depositor_minted("0xA") == 150.0

    def test_get_depositor_minted_unknown(self):
        ledger = ReserveLedger()
        assert ledger.get_depositor_minted("0xNONE") == 0.0

    def test_get_depositor_portfolio(self):
        ledger = ReserveLedger()
        ledger.add_reserve(ReserveProof(custodian="V", amount_grams=1000.0, purity=0.999, depositor_address="0xA"))
        ledger.record_depositor_mint("0xA", 200.0)

        portfolio = ledger.get_depositor_portfolio("0xA")
        assert portfolio["address"] == "0xA"
        assert portfolio["reserved_grams"] == 999.0
        assert portfolio["total_minted"] == 200.0
        assert portfolio["mint_capacity"] == 799.0
        assert len(portfolio["reserves"]) == 1

    def test_remove_reserve_updates_index(self):
        ledger = ReserveLedger()
        p = ReserveProof(custodian="V", amount_grams=100.0, purity=1.0, depositor_address="0xA")
        ledger.add_reserve(p)
        assert ledger.get_depositor_reserved("0xA") == 100.0

        ledger.remove_reserve(p.proof_id)
        assert ledger.get_depositor_reserved("0xA") == 0.0
        assert ledger.get_depositor_reserves("0xA") == []

    def test_reserves_without_depositor_not_indexed(self):
        ledger = ReserveLedger()
        ledger.add_reserve(ReserveProof(custodian="V", amount_grams=500.0, purity=1.0))
        assert ledger.total_reserved == 500.0
        assert ledger.get_depositor_reserved("") == 0.0


# ── Serialization round-trip ────────────────────────────────────


class TestDepositorSerialization:
    def test_ledger_round_trip(self):
        ledger = ReserveLedger()
        ledger.add_reserve(ReserveProof(custodian="V", amount_grams=500.0, purity=1.0, depositor_address="0xA"))
        ledger.add_reserve(ReserveProof(custodian="V", amount_grams=300.0, purity=1.0, depositor_address="0xB"))
        ledger.record_mint(200.0)
        ledger.record_depositor_mint("0xA", 200.0)

        d = ledger.to_dict()
        restored = ReserveLedger.from_dict(d)

        assert restored.total_reserved == 800.0
        assert restored.total_minted == 200.0
        assert restored.get_depositor_reserved("0xA") == 500.0
        assert restored.get_depositor_reserved("0xB") == 300.0
        assert restored.get_depositor_minted("0xA") == 200.0

    def test_ledger_round_trip_backward_compat(self):
        """Old data without depositor_minted should still load."""
        d = {
            "reserves": {
                "abc": {
                    "proof_id": "abc",
                    "custodian": "V",
                    "amount_grams": 100.0,
                    "purity": 1.0,
                }
            },
            "total_minted": 50.0,
            "total_burned": 10.0,
        }
        restored = ReserveLedger.from_dict(d)
        assert restored.total_minted == 50.0
        assert restored.total_burned == 10.0
        assert restored.total_reserved == 100.0
        # No depositor data — should return empty
        assert restored.get_depositor_minted("anything") == 0.0


# ── API endpoint tests ──────────────────────────────────────────


class TestPortfolioAPI:
    def test_add_reserve_with_depositor(self, client):
        resp = client.post("/reserves", json={
            "custodian": "Vault",
            "amount_grams": 500.0,
            "purity": 1.0,
            "depositor_address": "0xAAA",
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["proof"]["depositor_address"] == "0xAAA"

    def test_add_reserve_without_depositor(self, client):
        resp = client.post("/reserves", json={
            "custodian": "Vault",
            "amount_grams": 500.0,
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["proof"]["depositor_address"] == ""

    def test_portfolio_endpoint(self, client):
        # Add reserve for a depositor
        client.post("/reserves", json={
            "custodian": "Vault",
            "amount_grams": 1000.0,
            "purity": 0.999,
            "depositor_address": "0xDEP",
        })

        resp = client.get("/portfolio/0xDEP")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["address"] == "0xDEP"
        assert data["reserved_grams"] == 999.0
        assert data["balance"] == 0.0
        assert data["nonce"] == 0
        assert len(data["reserves"]) == 1

    def test_portfolio_unknown_address(self, client):
        resp = client.get("/portfolio/0xUNKNOWN")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["reserved_grams"] == 0.0
        assert data["balance"] == 0.0

    def test_transactions_endpoint(self, client, authority_keypair, alice_keypair):
        # Setup: add reserve and mint
        client.post("/reserves", json={
            "custodian": "Vault",
            "amount_grams": 1000.0,
            "purity": 1.0,
        })

        tx = Transaction(
            tx_type=TransactionType.MINT, sender="NETWORK",
            recipient=alice_keypair["address"], amount=100.0, nonce=0,
            public_key=authority_keypair["public_key"],
        )
        tx.sign(authority_keypair["private_key"])
        client.post("/transactions", json=tx.to_dict())
        client.post("/mine", json={"validator": "validator-0"})

        resp = client.get(f"/transactions/{alice_keypair['address']}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["address"] == alice_keypair["address"]
        assert len(data["transactions"]) == 1
        assert data["transactions"][0]["recipient"] == alice_keypair["address"]
        assert data["transactions"][0]["block_index"] == 1

    def test_transactions_empty(self, client):
        resp = client.get("/transactions/0xNOBODY")
        assert resp.status_code == 200
        assert resp.get_json()["transactions"] == []


# ── Full lifecycle integration test ─────────────────────────────


class TestPortfolioLifecycle:
    def test_deposit_mint_transfer_burn(self, client, app, authority_keypair, alice_keypair, bob_keypair):
        # 1. Deposit gold for Alice
        resp = client.post("/reserves", json={
            "custodian": "Fort Knox",
            "amount_grams": 500.0,
            "purity": 1.0,
            "depositor_address": alice_keypair["address"],
        })
        assert resp.status_code == 201

        # Verify Alice's portfolio
        resp = client.get(f"/portfolio/{alice_keypair['address']}")
        data = resp.get_json()
        assert data["reserved_grams"] == 500.0
        assert data["mint_capacity"] == 500.0

        # 2. Mint tokens to Alice
        tx = Transaction(
            tx_type=TransactionType.MINT, sender="NETWORK",
            recipient=alice_keypair["address"], amount=200.0, nonce=0,
            public_key=authority_keypair["public_key"],
        )
        tx.sign(authority_keypair["private_key"])
        resp = client.post("/transactions", json=tx.to_dict())
        assert resp.status_code == 201
        resp = client.post("/mine", json={"validator": "validator-0"})
        assert resp.status_code == 200

        # Verify Alice has balance
        resp = client.get(f"/balance/{alice_keypair['address']}")
        assert resp.get_json()["balance"] == 200.0

        # 3. Transfer from Alice to Bob
        tx = Transaction(
            tx_type=TransactionType.TRANSFER, sender=alice_keypair["address"],
            recipient=bob_keypair["address"], amount=50.0, nonce=0,
            public_key=alice_keypair["public_key"],
        )
        tx.sign(alice_keypair["private_key"])
        resp = client.post("/transactions", json=tx.to_dict())
        assert resp.status_code == 201
        resp = client.post("/mine", json={"validator": "validator-0"})
        assert resp.status_code == 200

        # Verify balances
        resp = client.get(f"/balance/{alice_keypair['address']}")
        assert resp.get_json()["balance"] == 150.0
        resp = client.get(f"/balance/{bob_keypair['address']}")
        assert resp.get_json()["balance"] == 50.0

        # 4. Burn some of Alice's tokens
        tx = Transaction(
            tx_type=TransactionType.BURN, sender=alice_keypair["address"],
            recipient="BURN", amount=30.0, nonce=1,
            public_key=alice_keypair["public_key"],
        )
        tx.sign(alice_keypair["private_key"])
        resp = client.post("/transactions", json=tx.to_dict())
        assert resp.status_code == 201
        resp = client.post("/mine", json={"validator": "validator-0"})
        assert resp.status_code == 200

        # 5. Verify portfolios
        resp = client.get(f"/portfolio/{alice_keypair['address']}")
        data = resp.get_json()
        assert data["balance"] == 120.0
        assert data["reserved_grams"] == 500.0

        # Verify transaction history for Alice (should have MINT, TRANSFER, BURN)
        resp = client.get(f"/transactions/{alice_keypair['address']}")
        txs = resp.get_json()["transactions"]
        assert len(txs) == 3
        types = [t["tx_type"] for t in txs]
        assert "MINT" in types
        assert "TRANSFER" in types
        assert "BURN" in types

        # Bob should have 1 tx (the transfer received)
        resp = client.get(f"/transactions/{bob_keypair['address']}")
        txs = resp.get_json()["transactions"]
        assert len(txs) == 1
        assert txs[0]["tx_type"] == "TRANSFER"

        # Global invariant still holds
        resp = client.get("/reserves")
        audit = resp.get_json()["audit"]
        assert audit["circulating_supply"] <= audit["total_reserved_grams"]
