"""Tests for Transaction model."""

import pytest
from blockchain.transaction import Transaction, TransactionType
from crypto.keys import generate_keypair


class TestTransaction:
    def test_create_mint(self, authority_keypair, alice_keypair):
        tx = Transaction(
            tx_type=TransactionType.MINT,
            sender="NETWORK",
            recipient=alice_keypair["address"],
            amount=100.0,
            nonce=0,
            public_key=authority_keypair["public_key"],
        )
        tx.sign(authority_keypair["private_key"])

        assert tx.tx_type == TransactionType.MINT
        assert tx.amount == 100.0
        assert tx.signature != ""
        assert tx.tx_hash != ""
        assert tx.verify()

    def test_create_transfer(self, alice_keypair, bob_keypair):
        tx = Transaction(
            tx_type=TransactionType.TRANSFER,
            sender=alice_keypair["address"],
            recipient=bob_keypair["address"],
            amount=50.0,
            nonce=0,
            public_key=alice_keypair["public_key"],
        )
        tx.sign(alice_keypair["private_key"])
        assert tx.verify()

    def test_create_burn(self, alice_keypair):
        tx = Transaction(
            tx_type=TransactionType.BURN,
            sender=alice_keypair["address"],
            recipient="BURN",
            amount=25.0,
            nonce=0,
            public_key=alice_keypair["public_key"],
        )
        tx.sign(alice_keypair["private_key"])
        assert tx.verify()

    def test_invalid_signature(self, alice_keypair, bob_keypair):
        tx = Transaction(
            tx_type=TransactionType.TRANSFER,
            sender=alice_keypair["address"],
            recipient=bob_keypair["address"],
            amount=50.0,
            nonce=0,
            public_key=alice_keypair["public_key"],
        )
        # Sign with wrong key
        tx.sign(bob_keypair["private_key"])
        assert not tx.verify()

    def test_to_from_dict(self, alice_keypair, bob_keypair):
        tx = Transaction(
            tx_type=TransactionType.TRANSFER,
            sender=alice_keypair["address"],
            recipient=bob_keypair["address"],
            amount=33.3333,
            nonce=5,
            public_key=alice_keypair["public_key"],
        )
        tx.sign(alice_keypair["private_key"])

        d = tx.to_dict()
        restored = Transaction.from_dict(d)
        assert restored.tx_type == TransactionType.TRANSFER
        assert restored.amount == 33.3333
        assert restored.nonce == 5
        assert restored.verify()

    def test_amount_precision(self):
        tx = Transaction(
            tx_type=TransactionType.MINT,
            sender="NETWORK",
            recipient="0x" + "a" * 40,
            amount=1.00005,  # more than 4 decimals
            nonce=0,
        )
        assert tx.amount == 1.0001  # rounded to 4 decimals

    def test_unsigned_transaction_fails_verify(self, alice_keypair, bob_keypair):
        tx = Transaction(
            tx_type=TransactionType.TRANSFER,
            sender=alice_keypair["address"],
            recipient=bob_keypair["address"],
            amount=10.0,
            nonce=0,
        )
        assert not tx.verify()
