"""Gold reserve proof management and audit trail."""

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from crypto.hashing import hash_dict


@dataclass
class ReserveProof:
    """Proof of a gold reserve deposit."""

    proof_id: str = ""
    custodian: str = ""  # entity holding the gold
    amount_grams: float = 0.0
    purity: float = 0.999  # gold purity (0.0 - 1.0)
    certificate_ref: str = ""  # external certificate reference
    timestamp: float = field(default_factory=time.time)
    verified: bool = False
    depositor_address: str = ""  # wallet address of the depositor

    def __post_init__(self):
        self.amount_grams = round(self.amount_grams, 4)
        if not self.proof_id:
            self.proof_id = self._compute_id()

    def _compute_id(self) -> str:
        return hash_dict({
            "custodian": self.custodian,
            "amount_grams": self.amount_grams,
            "purity": self.purity,
            "certificate_ref": self.certificate_ref,
            "timestamp": self.timestamp,
            "depositor_address": self.depositor_address,
        })[:16]

    def effective_grams(self) -> float:
        """Gold amount adjusted for purity."""
        return round(self.amount_grams * self.purity, 4)

    def to_dict(self) -> dict:
        return {
            "proof_id": self.proof_id,
            "custodian": self.custodian,
            "amount_grams": self.amount_grams,
            "purity": self.purity,
            "certificate_ref": self.certificate_ref,
            "timestamp": self.timestamp,
            "verified": self.verified,
            "depositor_address": self.depositor_address,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ReserveProof":
        return cls(
            proof_id=data.get("proof_id", ""),
            custodian=data.get("custodian", ""),
            amount_grams=data.get("amount_grams", 0.0),
            purity=data.get("purity", 0.999),
            certificate_ref=data.get("certificate_ref", ""),
            timestamp=data.get("timestamp", time.time()),
            verified=data.get("verified", False),
            depositor_address=data.get("depositor_address", ""),
        )


class ReserveLedger:
    """Manages gold reserve proofs and enforces the backing invariant.

    Invariant: total_minted - total_burned <= total_reserved_gold_grams
    """

    def __init__(self):
        self.reserves: Dict[str, ReserveProof] = {}
        self.total_minted: float = 0.0
        self.total_burned: float = 0.0
        # Per-depositor tracking
        self._depositor_reserves: Dict[str, List[str]] = {}  # address → proof_ids
        self._depositor_minted: Dict[str, float] = {}  # address → minted amount

    @property
    def total_reserved(self) -> float:
        """Total gold grams in reserves (adjusted for purity)."""
        return round(
            sum(r.effective_grams() for r in self.reserves.values()), 4
        )

    @property
    def circulating_supply(self) -> float:
        """AUT currently in circulation."""
        return round(self.total_minted - self.total_burned, 4)

    @property
    def reserve_ratio(self) -> float:
        """Ratio of reserved gold to circulating supply."""
        if self.circulating_supply <= 0:
            return float("inf") if self.total_reserved > 0 else 0.0
        return round(self.total_reserved / self.circulating_supply, 4)

    def add_reserve(self, proof: ReserveProof) -> None:
        """Register a new gold reserve proof."""
        self.reserves[proof.proof_id] = proof
        if proof.depositor_address:
            self._depositor_reserves.setdefault(proof.depositor_address, []).append(proof.proof_id)

    def remove_reserve(self, proof_id: str) -> Optional[ReserveProof]:
        """Remove a reserve proof (e.g., gold withdrawn)."""
        proof = self.reserves.pop(proof_id, None)
        if proof and proof.depositor_address:
            ids = self._depositor_reserves.get(proof.depositor_address, [])
            if proof_id in ids:
                ids.remove(proof_id)
                if not ids:
                    del self._depositor_reserves[proof.depositor_address]
        return proof

    def can_mint(self, amount: float) -> bool:
        """Check if minting the given amount would violate the invariant.

        Invariant: total_minted - total_burned <= total_reserved_gold_grams
        """
        new_minted = self.total_minted + amount
        return (new_minted - self.total_burned) <= self.total_reserved

    def record_mint(self, amount: float) -> bool:
        """Record a mint operation. Returns False if it violates the invariant."""
        if not self.can_mint(amount):
            return False
        self.total_minted = round(self.total_minted + amount, 4)
        return True

    def force_record_mint(self, amount: float) -> None:
        """Record a mint without checking the invariant (used during chain replay)."""
        self.total_minted = round(self.total_minted + amount, 4)

    def record_burn(self, amount: float) -> None:
        """Record a burn operation."""
        self.total_burned = round(self.total_burned + amount, 4)

    def reset_counters(self) -> None:
        """Reset minted/burned counters (for rebuild from chain)."""
        self.total_minted = 0.0
        self.total_burned = 0.0

    # ── Per-depositor methods ────────────────────────────────────

    def get_depositor_reserves(self, address: str) -> List[ReserveProof]:
        """Return all reserve proofs belonging to a depositor."""
        proof_ids = self._depositor_reserves.get(address, [])
        return [self.reserves[pid] for pid in proof_ids if pid in self.reserves]

    def get_depositor_reserved(self, address: str) -> float:
        """Total effective gold grams reserved by a depositor."""
        return round(
            sum(r.effective_grams() for r in self.get_depositor_reserves(address)), 4
        )

    def get_depositor_minted(self, address: str) -> float:
        """Total AUT minted against a depositor's reserves."""
        return self._depositor_minted.get(address, 0.0)

    def can_mint_for_depositor(self, address: str, amount: float) -> bool:
        """Check if minting amount for a depositor would exceed their reserves."""
        reserved = self.get_depositor_reserved(address)
        already_minted = self.get_depositor_minted(address)
        return (already_minted + amount) <= reserved

    def record_depositor_mint(self, address: str, amount: float) -> None:
        """Record that AUT was minted against a depositor's reserves."""
        current = self._depositor_minted.get(address, 0.0)
        self._depositor_minted[address] = round(current + amount, 4)

    def get_depositor_portfolio(self, address: str) -> dict:
        """Return a full portfolio summary for a depositor."""
        reserved = self.get_depositor_reserved(address)
        minted = self.get_depositor_minted(address)
        return {
            "address": address,
            "reserved_grams": reserved,
            "total_minted": minted,
            "mint_capacity": round(max(0.0, reserved - minted), 4),
            "reserves": [r.to_dict() for r in self.get_depositor_reserves(address)],
        }

    def get_audit_summary(self) -> dict:
        return {
            "total_reserved_grams": self.total_reserved,
            "total_minted": self.total_minted,
            "total_burned": self.total_burned,
            "circulating_supply": self.circulating_supply,
            "reserve_ratio": self.reserve_ratio,
            "num_reserves": len(self.reserves),
        }

    def to_dict(self) -> dict:
        return {
            "reserves": {k: v.to_dict() for k, v in self.reserves.items()},
            "total_minted": self.total_minted,
            "total_burned": self.total_burned,
            "depositor_minted": dict(self._depositor_minted),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ReserveLedger":
        ledger = cls()
        for k, v in data.get("reserves", {}).items():
            proof = ReserveProof.from_dict(v)
            ledger.reserves[k] = proof
            # Rebuild depositor index
            if proof.depositor_address:
                ledger._depositor_reserves.setdefault(proof.depositor_address, []).append(k)
        ledger.total_minted = data.get("total_minted", 0.0)
        ledger.total_burned = data.get("total_burned", 0.0)
        ledger._depositor_minted = data.get("depositor_minted", {})
        return ledger
