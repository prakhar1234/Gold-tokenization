"""Tests for wallet creation and listing via the node API."""

import json
import os
import tempfile

import pytest

from config import NetworkConfig
from network.node import create_node
from wallet.wallet import Wallet


@pytest.fixture
def wallet_dir():
    """Temporary wallet directory."""
    with tempfile.TemporaryDirectory() as d:
        yield d


@pytest.fixture
def wallet_app(wallet_dir):
    """Flask app with a temporary wallet directory."""
    config = NetworkConfig(
        network_id="test-net",
        validators=["validator-0"],
        wallet_dir=wallet_dir,
    )
    app = create_node(host="127.0.0.1", port=5198, config=config)
    app.config["TESTING"] = True
    return app


@pytest.fixture
def wallet_client(wallet_app):
    return wallet_app.test_client()


class TestWalletCreation:
    def test_create_wallet_returns_keys(self, wallet_client):
        resp = wallet_client.post("/wallets", json={})
        assert resp.status_code == 201
        data = resp.get_json()
        assert "address" in data
        assert "public_key" in data
        assert "private_key" in data
        assert "name" in data

    def test_create_wallet_with_custom_name(self, wallet_client):
        resp = wallet_client.post("/wallets", json={"name": "alice"})
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["name"] == "alice"

    def test_create_wallet_default_name(self, wallet_client):
        resp = wallet_client.post("/wallets", json={})
        assert resp.status_code == 201
        data = resp.get_json()
        # Default name is first 8 chars of address (after 0x)
        assert data["name"] == data["address"][2:10]

    def test_address_format(self, wallet_client):
        resp = wallet_client.post("/wallets", json={})
        data = resp.get_json()
        address = data["address"]
        assert address.startswith("0x")
        assert len(address) == 42

    def test_wallet_file_persisted(self, wallet_client, wallet_dir):
        resp = wallet_client.post("/wallets", json={"name": "bob"})
        assert resp.status_code == 201
        filepath = os.path.join(wallet_dir, "bob.json")
        assert os.path.isfile(filepath)

        # Verify file is encrypted (has salt, nonce, ciphertext fields)
        with open(filepath, "r") as f:
            file_data = json.load(f)
        assert "salt" in file_data
        assert "nonce" in file_data
        assert "ciphertext" in file_data
        assert "address" in file_data

    def test_private_key_reconstructs_wallet(self, wallet_client):
        resp = wallet_client.post("/wallets", json={"name": "carol"})
        data = resp.get_json()

        # Reconstruct wallet from private key
        reconstructed = Wallet.from_private_key(data["private_key"])
        assert reconstructed.address == data["address"]
        assert reconstructed.public_key == data["public_key"]


class TestWalletListing:
    def test_list_empty(self, wallet_client):
        resp = wallet_client.get("/wallets")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["wallets"] == []

    def test_list_after_creation(self, wallet_client):
        wallet_client.post("/wallets", json={"name": "alice"})
        wallet_client.post("/wallets", json={"name": "bob"})

        resp = wallet_client.get("/wallets")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["wallets"]) == 2

        names = [w["name"] for w in data["wallets"]]
        assert "alice" in names
        assert "bob" in names

    def test_list_contains_addresses(self, wallet_client):
        create_resp = wallet_client.post("/wallets", json={"name": "dave"})
        created_address = create_resp.get_json()["address"]

        list_resp = wallet_client.get("/wallets")
        wallets = list_resp.get_json()["wallets"]
        addresses = [w["address"] for w in wallets]
        assert created_address in addresses

    def test_list_does_not_contain_private_keys(self, wallet_client):
        wallet_client.post("/wallets", json={"name": "eve"})

        resp = wallet_client.get("/wallets")
        for w in resp.get_json()["wallets"]:
            assert "private_key" not in w
