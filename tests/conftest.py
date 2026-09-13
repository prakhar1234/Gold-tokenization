"""Shared pytest fixtures for the Gold Tokenization test suite."""

import os
import sys
import tempfile

import pytest

# Ensure project root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from blockchain.block import Blockchain
from blockchain.transaction import Transaction, TransactionType
from config import NetworkConfig
from crypto.keys import generate_keypair
from gold.reserve import ReserveLedger, ReserveProof
from gold.token import GoldTokenManager
from network.mempool import Mempool
from network.node import create_node
from wallet.wallet import Wallet


@pytest.fixture
def config():
    """Test network config."""
    return NetworkConfig(
        network_id="test-net",
        validators=["validator-0", "validator-1", "validator-2"],
    )


@pytest.fixture
def blockchain(config):
    """Fresh blockchain instance."""
    return Blockchain(config=config)


@pytest.fixture
def keypair():
    """Generate a fresh ECDSA keypair."""
    private_key, public_key, address = generate_keypair()
    return {"private_key": private_key, "public_key": public_key, "address": address}


@pytest.fixture
def authority_keypair():
    """Keypair for the minting authority."""
    private_key, public_key, address = generate_keypair()
    return {"private_key": private_key, "public_key": public_key, "address": address}


@pytest.fixture
def alice_keypair():
    private_key, public_key, address = generate_keypair()
    return {"private_key": private_key, "public_key": public_key, "address": address}


@pytest.fixture
def bob_keypair():
    private_key, public_key, address = generate_keypair()
    return {"private_key": private_key, "public_key": public_key, "address": address}


@pytest.fixture
def reserve_ledger():
    """Fresh reserve ledger with 1000g gold."""
    ledger = ReserveLedger()
    proof = ReserveProof(
        custodian="Test Vault",
        amount_grams=1000.0,
        purity=1.0,
        certificate_ref="TEST-001",
    )
    ledger.add_reserve(proof)
    return ledger


@pytest.fixture
def token_manager(blockchain, reserve_ledger, config):
    return GoldTokenManager(blockchain, reserve_ledger, config)


@pytest.fixture
def mempool():
    return Mempool(max_size=100)


@pytest.fixture
def mint_transaction(authority_keypair, alice_keypair):
    """Create a signed MINT transaction."""
    tx = Transaction(
        tx_type=TransactionType.MINT,
        sender="NETWORK",
        recipient=alice_keypair["address"],
        amount=100.0,
        nonce=0,
        public_key=authority_keypair["public_key"],
    )
    tx.sign(authority_keypair["private_key"])
    return tx


@pytest.fixture
def app(config):
    """Flask test app."""
    app = create_node(host="127.0.0.1", port=5199, config=config)
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app):
    """Flask test client."""
    return app.test_client()


@pytest.fixture
def tmp_dir():
    """Temporary directory for file operations."""
    with tempfile.TemporaryDirectory() as d:
        yield d
