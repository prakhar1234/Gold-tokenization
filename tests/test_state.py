"""Tests for account state management."""

import pytest
from blockchain.state import AccountState
from blockchain.transaction import Transaction, TransactionType


class TestAccountState:
    def test_initial_balance(self):
        state = AccountState()
        assert state.get_balance("0x123") == 0.0
        assert state.get_nonce("0x123") == 0

    def test_apply_mint(self, authority_keypair, alice_keypair):
        state = AccountState()
        tx = Transaction(
            tx_type=TransactionType.MINT, sender="NETWORK",
            recipient=alice_keypair["address"], amount=100.0, nonce=0,
            public_key=authority_keypair["public_key"],
        )
        tx.sign(authority_keypair["private_key"])

        error = state.apply_transaction(tx)
        assert error is None
        assert state.get_balance(alice_keypair["address"]) == 100.0

    def test_apply_transfer(self, alice_keypair, bob_keypair, authority_keypair):
        state = AccountState()

        # Mint to alice first
        mint_tx = Transaction(
            tx_type=TransactionType.MINT, sender="NETWORK",
            recipient=alice_keypair["address"], amount=100.0, nonce=0,
            public_key=authority_keypair["public_key"],
        )
        mint_tx.sign(authority_keypair["private_key"])
        state.apply_transaction(mint_tx)

        # Transfer alice -> bob
        transfer_tx = Transaction(
            tx_type=TransactionType.TRANSFER,
            sender=alice_keypair["address"],
            recipient=bob_keypair["address"],
            amount=40.0, nonce=0,
            public_key=alice_keypair["public_key"],
        )
        transfer_tx.sign(alice_keypair["private_key"])

        error = state.apply_transaction(transfer_tx)
        assert error is None
        assert state.get_balance(alice_keypair["address"]) == 60.0
        assert state.get_balance(bob_keypair["address"]) == 40.0
        assert state.get_nonce(alice_keypair["address"]) == 1

    def test_insufficient_balance(self, alice_keypair, bob_keypair):
        state = AccountState()
        tx = Transaction(
            tx_type=TransactionType.TRANSFER,
            sender=alice_keypair["address"],
            recipient=bob_keypair["address"],
            amount=50.0, nonce=0,
            public_key=alice_keypair["public_key"],
        )
        tx.sign(alice_keypair["private_key"])

        error = state.apply_transaction(tx)
        assert error is not None
        assert "Insufficient balance" in error

    def test_invalid_nonce(self, alice_keypair, bob_keypair, authority_keypair):
        state = AccountState()

        # Mint to alice
        mint_tx = Transaction(
            tx_type=TransactionType.MINT, sender="NETWORK",
            recipient=alice_keypair["address"], amount=100.0, nonce=0,
            public_key=authority_keypair["public_key"],
        )
        mint_tx.sign(authority_keypair["private_key"])
        state.apply_transaction(mint_tx)

        # Transfer with wrong nonce
        tx = Transaction(
            tx_type=TransactionType.TRANSFER,
            sender=alice_keypair["address"],
            recipient=bob_keypair["address"],
            amount=10.0, nonce=5,  # wrong nonce
            public_key=alice_keypair["public_key"],
        )
        tx.sign(alice_keypair["private_key"])

        error = state.apply_transaction(tx)
        assert error is not None
        assert "nonce" in error.lower()

    def test_apply_burn(self, alice_keypair, authority_keypair):
        state = AccountState()

        mint_tx = Transaction(
            tx_type=TransactionType.MINT, sender="NETWORK",
            recipient=alice_keypair["address"], amount=100.0, nonce=0,
            public_key=authority_keypair["public_key"],
        )
        mint_tx.sign(authority_keypair["private_key"])
        state.apply_transaction(mint_tx)

        burn_tx = Transaction(
            tx_type=TransactionType.BURN,
            sender=alice_keypair["address"],
            recipient="BURN", amount=30.0, nonce=0,
            public_key=alice_keypair["public_key"],
        )
        burn_tx.sign(alice_keypair["private_key"])

        error = state.apply_transaction(burn_tx)
        assert error is None
        assert state.get_balance(alice_keypair["address"]) == 70.0

    def test_copy(self):
        state = AccountState()
        state.balances["0x1"] = 100.0
        state.nonces["0x1"] = 3

        copy = state.copy()
        copy.balances["0x1"] = 50.0

        assert state.get_balance("0x1") == 100.0  # original unchanged

    def test_mint_sender_must_be_network(self, alice_keypair):
        state = AccountState()
        tx = Transaction(
            tx_type=TransactionType.MINT,
            sender=alice_keypair["address"],  # wrong
            recipient="0x" + "b" * 40,
            amount=10.0, nonce=0,
            public_key=alice_keypair["public_key"],
        )
        tx.sign(alice_keypair["private_key"])
        error = state.validate_transaction(tx)
        assert error is not None
        assert "NETWORK" in error
