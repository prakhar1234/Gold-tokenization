"""Tests for gold reserve management."""

import pytest
from gold.reserve import ReserveLedger, ReserveProof
from gold.token import GoldTokenManager


class TestReserveProof:
    def test_create(self):
        proof = ReserveProof(
            custodian="Vault A",
            amount_grams=500.0,
            purity=0.999,
            certificate_ref="CERT-001",
        )
        assert proof.proof_id != ""
        assert proof.effective_grams() == 499.5

    def test_to_from_dict(self):
        proof = ReserveProof(
            custodian="Vault B",
            amount_grams=250.0,
            purity=1.0,
        )
        d = proof.to_dict()
        restored = ReserveProof.from_dict(d)
        assert restored.custodian == "Vault B"
        assert restored.amount_grams == 250.0
        assert restored.effective_grams() == 250.0


class TestReserveLedger:
    def test_add_reserve(self):
        ledger = ReserveLedger()
        proof = ReserveProof(custodian="V", amount_grams=1000.0, purity=1.0)
        ledger.add_reserve(proof)
        assert ledger.total_reserved == 1000.0

    def test_can_mint(self, reserve_ledger):
        assert reserve_ledger.can_mint(500.0)
        assert reserve_ledger.can_mint(1000.0)
        assert not reserve_ledger.can_mint(1001.0)

    def test_mint_reduces_capacity(self, reserve_ledger):
        reserve_ledger.record_mint(600.0)
        assert not reserve_ledger.can_mint(401.0)
        assert reserve_ledger.can_mint(400.0)

    def test_burn_increases_capacity(self, reserve_ledger):
        reserve_ledger.record_mint(1000.0)
        assert not reserve_ledger.can_mint(1.0)

        reserve_ledger.record_burn(200.0)
        assert reserve_ledger.can_mint(200.0)
        assert not reserve_ledger.can_mint(201.0)

    def test_circulating_supply(self, reserve_ledger):
        reserve_ledger.record_mint(500.0)
        reserve_ledger.record_burn(50.0)
        assert reserve_ledger.circulating_supply == 450.0

    def test_reserve_ratio(self, reserve_ledger):
        reserve_ledger.record_mint(500.0)
        # 1000 / 500 = 2.0
        assert reserve_ledger.reserve_ratio == 2.0

    def test_audit_summary(self, reserve_ledger):
        reserve_ledger.record_mint(500.0)
        reserve_ledger.record_burn(50.0)
        summary = reserve_ledger.get_audit_summary()
        assert summary["total_reserved_grams"] == 1000.0
        assert summary["total_minted"] == 500.0
        assert summary["total_burned"] == 50.0
        assert summary["circulating_supply"] == 450.0

    def test_invariant_enforced(self, reserve_ledger):
        # Can't mint more than reserved
        assert not reserve_ledger.record_mint(1001.0)
        assert reserve_ledger.total_minted == 0.0

    def test_to_from_dict(self, reserve_ledger):
        reserve_ledger.record_mint(300.0)
        d = reserve_ledger.to_dict()
        restored = ReserveLedger.from_dict(d)
        assert restored.total_minted == 300.0
        assert restored.total_reserved == 1000.0


class TestGoldTokenManager:
    def test_create_mint_transaction(self, token_manager, authority_keypair, alice_keypair):
        tx = token_manager.create_mint_transaction(
            recipient=alice_keypair["address"],
            amount=100.0,
            authority_private_key=authority_keypair["private_key"],
            authority_public_key=authority_keypair["public_key"],
        )
        assert tx is not None
        assert tx.verify()
        assert tx.amount == 100.0

    def test_mint_blocked_by_reserves(self, token_manager, authority_keypair, alice_keypair):
        # Try to mint more than reserve
        tx = token_manager.create_mint_transaction(
            recipient=alice_keypair["address"],
            amount=2000.0,
            authority_private_key=authority_keypair["private_key"],
            authority_public_key=authority_keypair["public_key"],
        )
        assert tx is None

    def test_token_info(self, token_manager):
        info = token_manager.get_token_info()
        assert info["symbol"] == "AUT"
        assert info["circulating_supply"] == 0.0
        assert info["total_reserved_grams"] == 1000.0
