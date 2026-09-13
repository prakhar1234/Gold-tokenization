"""Tests for consensus engine."""

import pytest
from blockchain.consensus import PoAConsensus, PoWConsensus


class TestPoAConsensus:
    def test_round_robin(self):
        poa = PoAConsensus(validators=["A", "B", "C"])
        # Block 0 is genesis, no validator
        assert poa.get_validator_for_block(0) is None
        # Blocks 1, 2, 3 cycle through A, B, C
        assert poa.get_validator_for_block(1) == "A"
        assert poa.get_validator_for_block(2) == "B"
        assert poa.get_validator_for_block(3) == "C"
        # Wraps around
        assert poa.get_validator_for_block(4) == "A"
        assert poa.get_validator_for_block(7) == "A"

    def test_is_valid_validator(self):
        poa = PoAConsensus(validators=["A", "B"])
        assert poa.is_valid_validator("A", 1)
        assert not poa.is_valid_validator("B", 1)
        assert poa.is_valid_validator("B", 2)

    def test_add_remove_validator(self):
        poa = PoAConsensus()
        poa.add_validator("X")
        poa.add_validator("Y")
        assert poa.validators == ["X", "Y"]
        poa.add_validator("X")  # duplicate
        assert len(poa.validators) == 2
        poa.remove_validator("X")
        assert poa.validators == ["Y"]

    def test_empty_validators(self):
        poa = PoAConsensus()
        assert poa.get_validator_for_block(1) is None

    def test_to_from_dict(self):
        poa = PoAConsensus(validators=["A", "B"])
        d = poa.to_dict()
        restored = PoAConsensus.from_dict(d)
        assert restored.validators == ["A", "B"]


class TestPoWConsensus:
    def test_mine_and_validate(self):
        pow_c = PoWConsensus(difficulty=2)  # low difficulty for fast test
        nonce, h = pow_c.mine_block("test_header")
        assert h.startswith("00")
        assert pow_c.validate_pow("test_header", nonce, h)

    def test_invalid_pow(self):
        pow_c = PoWConsensus(difficulty=2)
        assert not pow_c.validate_pow("test", 0, "ffffff")
