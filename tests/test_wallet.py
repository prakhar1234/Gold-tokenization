"""Tests for wallet creation and encrypted storage."""

import os
import pytest
from wallet.wallet import Wallet
from crypto.keys import verify_signature


class TestWallet:
    def test_create(self):
        w = Wallet.create()
        assert w.address.startswith("0x")
        assert len(w.address) == 42
        assert len(w.private_key) > 0
        assert len(w.public_key) > 0

    def test_from_private_key(self):
        w1 = Wallet.create()
        w2 = Wallet.from_private_key(w1.private_key)
        assert w2.address == w1.address
        assert w2.public_key == w1.public_key

    def test_sign(self):
        w = Wallet.create()
        sig = w.sign("hello world")
        assert sig != ""
        assert verify_signature(w.public_key, "hello world", sig)

    def test_encrypted_save_load(self, tmp_dir):
        w = Wallet.create()
        filepath = os.path.join(tmp_dir, "test_wallet.json")
        password = "test-password-123"

        w.save_encrypted(filepath, password)
        assert os.path.exists(filepath)

        loaded = Wallet.load_encrypted(filepath, password)
        assert loaded is not None
        assert loaded.address == w.address
        assert loaded.private_key == w.private_key

    def test_wrong_password(self, tmp_dir):
        w = Wallet.create()
        filepath = os.path.join(tmp_dir, "test_wallet2.json")
        w.save_encrypted(filepath, "correct")

        loaded = Wallet.load_encrypted(filepath, "wrong")
        assert loaded is None

    def test_public_dict(self):
        w = Wallet.create()
        d = w.to_public_dict()
        assert "address" in d
        assert "public_key" in d
        assert "private_key" not in d
