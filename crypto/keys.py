"""ECDSA key generation, signing, and verification on secp256k1."""

import hashlib
from typing import Tuple

from ecdsa import SECP256k1, BadSignatureError, SigningKey, VerifyingKey

from crypto.hashing import sha256


def generate_keypair() -> Tuple[str, str, str]:
    """Generate a new ECDSA keypair on secp256k1.

    Returns:
        (private_key_hex, public_key_hex, address)
    """
    sk = SigningKey.generate(curve=SECP256k1)
    vk = sk.get_verifying_key()
    private_hex = sk.to_string().hex()
    public_hex = vk.to_string().hex()
    address = public_key_to_address(public_hex)
    return private_hex, public_hex, address


def public_key_to_address(public_key_hex: str) -> str:
    """Derive an address from a public key (truncated SHA-256 hash)."""
    pub_bytes = bytes.fromhex(public_key_hex)
    full_hash = hashlib.sha256(pub_bytes).hexdigest()
    # Use first 40 hex chars (20 bytes) prefixed with "0x"
    return "0x" + full_hash[:40]


def sign_message(private_key_hex: str, message: str) -> str:
    """Sign a message string with the given private key.

    Returns:
        Signature as hex string.
    """
    sk = SigningKey.from_string(bytes.fromhex(private_key_hex), curve=SECP256k1)
    msg_hash = hashlib.sha256(message.encode("utf-8")).digest()
    signature = sk.sign_deterministic(msg_hash)
    return signature.hex()


def verify_signature(public_key_hex: str, message: str, signature_hex: str) -> bool:
    """Verify an ECDSA signature against a public key and message."""
    try:
        vk = VerifyingKey.from_string(bytes.fromhex(public_key_hex), curve=SECP256k1)
        msg_hash = hashlib.sha256(message.encode("utf-8")).digest()
        return vk.verify(bytes.fromhex(signature_hex), msg_hash)
    except (BadSignatureError, ValueError):
        return False


def private_key_to_public_key(private_key_hex: str) -> str:
    """Derive public key hex from private key hex."""
    sk = SigningKey.from_string(bytes.fromhex(private_key_hex), curve=SECP256k1)
    vk = sk.get_verifying_key()
    return vk.to_string().hex()
