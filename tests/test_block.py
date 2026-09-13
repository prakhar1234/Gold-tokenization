"""Tests for Block, BlockHeader, and Blockchain."""

import os
import pytest
from blockchain.block import Block, BlockHeader, Blockchain
from blockchain.transaction import Transaction, TransactionType
from config import NetworkConfig


class TestBlockHeader:
    def test_to_from_dict(self):
        header = BlockHeader(
            index=1, timestamp=1000.0, previous_hash="abc",
            merkle_root="def", validator="v1", nonce=0,
        )
        d = header.to_dict()
        restored = BlockHeader.from_dict(d)
        assert restored.index == 1
        assert restored.previous_hash == "abc"
        assert restored.validator == "v1"


class TestBlock:
    def test_compute_hash_deterministic(self):
        header = BlockHeader(
            index=1, timestamp=1000.0, previous_hash="0" * 64,
            merkle_root="abc", validator="v1",
        )
        b1 = Block(header=header, transactions=[])
        b2 = Block(header=header, transactions=[])
        assert b1.block_hash == b2.block_hash

    def test_to_from_dict(self):
        header = BlockHeader(
            index=1, timestamp=1000.0, previous_hash="0" * 64,
            merkle_root="abc", validator="v1",
        )
        block = Block(header=header, transactions=[])
        d = block.to_dict()
        restored = Block.from_dict(d)
        assert restored.block_hash == block.block_hash
        assert restored.header.index == 1


class TestBlockchain:
    def test_genesis_block_created(self, blockchain):
        assert blockchain.height == 1
        assert blockchain.chain[0].header.index == 0
        assert blockchain.chain[0].header.validator == "genesis"

    def test_create_block(self, blockchain, authority_keypair, alice_keypair):
        tx = Transaction(
            tx_type=TransactionType.MINT, sender="NETWORK",
            recipient=alice_keypair["address"], amount=50.0, nonce=0,
            public_key=authority_keypair["public_key"],
        )
        tx.sign(authority_keypair["private_key"])

        block = blockchain.create_block([tx], "validator-0")
        assert block is not None
        assert block.header.index == 1
        assert blockchain.height == 2
        assert blockchain.state.get_balance(alice_keypair["address"]) == 50.0

    def test_validate_chain(self, blockchain, authority_keypair, alice_keypair):
        tx = Transaction(
            tx_type=TransactionType.MINT, sender="NETWORK",
            recipient=alice_keypair["address"], amount=100.0, nonce=0,
            public_key=authority_keypair["public_key"],
        )
        tx.sign(authority_keypair["private_key"])
        blockchain.create_block([tx], "validator-0")

        assert blockchain.validate_chain() is None

    def test_save_and_load(self, blockchain, authority_keypair, alice_keypair, tmp_dir):
        tx = Transaction(
            tx_type=TransactionType.MINT, sender="NETWORK",
            recipient=alice_keypair["address"], amount=75.0, nonce=0,
            public_key=authority_keypair["public_key"],
        )
        tx.sign(authority_keypair["private_key"])
        blockchain.create_block([tx], "validator-0")

        filepath = os.path.join(tmp_dir, "chain.json")
        blockchain.save_to_file(filepath)

        config = NetworkConfig(validators=["validator-0", "validator-1", "validator-2"])
        new_chain = Blockchain(config=config)
        assert new_chain.load_from_file(filepath)
        assert new_chain.height == 2
        assert new_chain.state.get_balance(alice_keypair["address"]) == 75.0

    def test_replace_chain(self, config, authority_keypair, alice_keypair):
        chain1 = Blockchain(config=config)
        chain2 = Blockchain(config=config)

        # Add 2 blocks to chain2
        for amount in [50.0, 30.0]:
            tx = Transaction(
                tx_type=TransactionType.MINT, sender="NETWORK",
                recipient=alice_keypair["address"], amount=amount, nonce=0,
                public_key=authority_keypair["public_key"],
            )
            tx.sign(authority_keypair["private_key"])
            chain2.create_block([tx], "validator-0")

        assert chain2.height == 3

        # chain1 should adopt chain2's longer chain
        replaced = chain1.replace_chain(list(chain2.chain))
        assert replaced
        assert chain1.height == 3
