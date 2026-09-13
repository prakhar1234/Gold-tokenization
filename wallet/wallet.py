"""Wallet creation, encrypted key storage, and transaction signing."""

import json
import os
from dataclasses import dataclass
from typing import Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

from crypto.keys import (
    generate_keypair,
    private_key_to_public_key,
    public_key_to_address,
    sign_message,
)


def _derive_key(password: str, salt: bytes) -> bytes:
    """Derive a 256-bit AES key from a password using PBKDF2."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100_000,
    )
    return kdf.derive(password.encode("utf-8"))


@dataclass
class Wallet:
    """A wallet holding ECDSA keys for signing transactions."""

    private_key: str
    public_key: str
    address: str

    @classmethod
    def create(cls) -> "Wallet":
        """Generate a new wallet with fresh keypair."""
        private_key, public_key, address = generate_keypair()
        return cls(private_key=private_key, public_key=public_key, address=address)

    @classmethod
    def from_private_key(cls, private_key_hex: str) -> "Wallet":
        """Reconstruct a wallet from a private key."""
        public_key = private_key_to_public_key(private_key_hex)
        address = public_key_to_address(public_key)
        return cls(
            private_key=private_key_hex,
            public_key=public_key,
            address=address,
        )

    def sign(self, message: str) -> str:
        """Sign a message with the wallet's private key."""
        return sign_message(self.private_key, message)

    def save_encrypted(self, filepath: str, password: str) -> None:
        """Save the wallet to an AES-256-GCM encrypted file."""
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)

        salt = os.urandom(16)
        nonce = os.urandom(12)
        key = _derive_key(password, salt)

        plaintext = json.dumps({
            "private_key": self.private_key,
            "public_key": self.public_key,
            "address": self.address,
        }).encode("utf-8")

        aesgcm = AESGCM(key)
        ciphertext = aesgcm.encrypt(nonce, plaintext, None)

        with open(filepath, "w") as f:
            json.dump({
                "salt": salt.hex(),
                "nonce": nonce.hex(),
                "ciphertext": ciphertext.hex(),
                "address": self.address,  # stored unencrypted for identification
            }, f, indent=2)

    @classmethod
    def load_encrypted(cls, filepath: str, password: str) -> Optional["Wallet"]:
        """Load a wallet from an encrypted file.

        Returns:
            Wallet if decryption succeeds, None otherwise.
        """
        with open(filepath, "r") as f:
            data = json.load(f)

        salt = bytes.fromhex(data["salt"])
        nonce = bytes.fromhex(data["nonce"])
        ciphertext = bytes.fromhex(data["ciphertext"])

        key = _derive_key(password, salt)
        aesgcm = AESGCM(key)

        try:
            plaintext = aesgcm.decrypt(nonce, ciphertext, None)
        except Exception:
            return None

        wallet_data = json.loads(plaintext.decode("utf-8"))
        return cls(
            private_key=wallet_data["private_key"],
            public_key=wallet_data["public_key"],
            address=wallet_data["address"],
        )

    def to_public_dict(self) -> dict:
        """Return public wallet info (no private key)."""
        return {
            "address": self.address,
            "public_key": self.public_key,
        }
