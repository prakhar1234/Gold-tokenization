"""SHA-256 hashing utilities for the blockchain."""

import hashlib
import json
from typing import Any


def sha256(data: bytes) -> str:
    """Compute SHA-256 hash and return hex digest."""
    return hashlib.sha256(data).hexdigest()


def double_sha256(data: bytes) -> str:
    """Compute double SHA-256 (hash of hash) and return hex digest."""
    first = hashlib.sha256(data).digest()
    return hashlib.sha256(first).hexdigest()


def hash_string(s: str) -> str:
    """Hash a UTF-8 string with SHA-256."""
    return sha256(s.encode("utf-8"))


def hash_dict(d: dict) -> str:
    """Deterministically serialize a dict and hash it."""
    serialized = canonical_json(d)
    return sha256(serialized.encode("utf-8"))


def canonical_json(obj: Any) -> str:
    """Produce a deterministic JSON string (sorted keys, no whitespace)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)
