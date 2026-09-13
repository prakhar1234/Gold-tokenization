"""Proof of Authority consensus engine with round-robin validator selection."""

import time
from dataclasses import dataclass, field
from typing import List, Optional

from crypto.hashing import sha256


@dataclass
class PoAConsensus:
    """Proof of Authority consensus with round-robin validator rotation."""

    validators: List[str] = field(default_factory=list)

    def add_validator(self, address: str) -> None:
        if address not in self.validators:
            self.validators.append(address)

    def remove_validator(self, address: str) -> None:
        if address in self.validators:
            self.validators.remove(address)

    def get_validator_for_block(self, block_index: int) -> Optional[str]:
        """Get the expected validator for a given block index (round-robin)."""
        if not self.validators:
            return None
        # Block 0 (genesis) has no validator
        if block_index == 0:
            return None
        return self.validators[(block_index - 1) % len(self.validators)]

    def is_valid_validator(self, address: str, block_index: int) -> bool:
        """Check if the given address is the valid validator for this block."""
        expected = self.get_validator_for_block(block_index)
        return expected == address

    def to_dict(self) -> dict:
        return {"validators": list(self.validators)}

    @classmethod
    def from_dict(cls, data: dict) -> "PoAConsensus":
        return cls(validators=list(data.get("validators", [])))


@dataclass
class PoWConsensus:
    """Optional Proof of Work consensus (for testing/demo)."""

    difficulty: int = 4  # number of leading zeros required

    def mine_block(self, block_header_data: str) -> tuple:
        """Find a nonce that produces a hash with the required difficulty.

        Returns:
            (nonce, hash) tuple.
        """
        target = "0" * self.difficulty
        nonce = 0
        while True:
            candidate = f"{block_header_data}{nonce}"
            h = sha256(candidate.encode("utf-8"))
            if h.startswith(target):
                return nonce, h
            nonce += 1

    def validate_pow(self, block_header_data: str, nonce: int, block_hash: str) -> bool:
        """Validate that the PoW solution is correct."""
        target = "0" * self.difficulty
        candidate = f"{block_header_data}{nonce}"
        h = sha256(candidate.encode("utf-8"))
        return h == block_hash and h.startswith(target)
