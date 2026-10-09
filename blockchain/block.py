"""Block, BlockHeader, and Blockchain classes."""

import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import List, Optional

from blockchain.consensus import PoAConsensus
from blockchain.merkle import compute_merkle_root
from blockchain.state import AccountState
from blockchain.transaction import Transaction
from config import DEFAULT_CONFIG, NetworkConfig
from crypto.hashing import canonical_json, hash_string

logger = logging.getLogger(__name__)


@dataclass
class BlockHeader:
    """Header containing block metadata."""

    index: int
    timestamp: float
    previous_hash: str
    merkle_root: str
    validator: str  # address of the block validator
    nonce: int = 0  # used only for PoW

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "timestamp": self.timestamp,
            "previous_hash": self.previous_hash,
            "merkle_root": self.merkle_root,
            "validator": self.validator,
            "nonce": self.nonce,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BlockHeader":
        return cls(
            index=data["index"],
            timestamp=data["timestamp"],
            previous_hash=data["previous_hash"],
            merkle_root=data["merkle_root"],
            validator=data.get("validator", ""),
            nonce=data.get("nonce", 0),
        )


@dataclass
class Block:
    """A block in the blockchain containing a header and transactions."""

    header: BlockHeader
    transactions: List[Transaction] = field(default_factory=list)
    block_hash: str = ""

    def __post_init__(self):
        if not self.block_hash:
            self.block_hash = self.compute_hash()

    def compute_hash(self) -> str:
        data = canonical_json({
            "header": self.header.to_dict(),
            "transactions": [tx.to_dict() for tx in self.transactions],
        })
        return hash_string(data)

    def to_dict(self) -> dict:
        return {
            "header": self.header.to_dict(),
            "transactions": [tx.to_dict() for tx in self.transactions],
            "block_hash": self.block_hash,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Block":
        header = BlockHeader.from_dict(data["header"])
        transactions = [Transaction.from_dict(tx) for tx in data.get("transactions", [])]
        block = cls(
            header=header,
            transactions=transactions,
            block_hash=data.get("block_hash", ""),
        )
        # Recompute if missing
        if not block.block_hash:
            block.block_hash = block.compute_hash()
        return block


class Blockchain:
    """The main blockchain, managing blocks, state, and consensus."""

    def __init__(self, config: NetworkConfig = DEFAULT_CONFIG):
        self.config = config
        self.chain: List[Block] = []
        self.state = AccountState()
        self.consensus = PoAConsensus(validators=list(config.validators))
        self._create_genesis_block()

    def _create_genesis_block(self) -> None:
        """Create the genesis block (block 0)."""
        header = BlockHeader(
            index=0,
            timestamp=self.config.genesis_timestamp,
            previous_hash="0" * 64,
            merkle_root=compute_merkle_root([]),
            validator="genesis",
            nonce=0,
        )
        genesis = Block(header=header, transactions=[])
        self.chain.append(genesis)

    @property
    def last_block(self) -> Block:
        return self.chain[-1]

    @property
    def height(self) -> int:
        return len(self.chain)

    def create_block(
        self,
        transactions: List[Transaction],
        validator: str,
        timestamp: Optional[float] = None,
    ) -> Optional[Block]:
        """Create and add a new block to the chain.

        Returns:
            The new Block if successful, None if validation fails.
        """
        # Validate transactions against a copy of state
        temp_state = self.state.copy()
        for tx in transactions:
            if not tx.verify():
                logger.warning("Block creation failed: invalid tx signature %s", tx.tx_hash[:16])
                return None
            error = temp_state.apply_transaction(tx)
            if error:
                logger.warning("Block creation failed: %s (tx %s)", error, tx.tx_hash[:16])
                return None

        tx_hashes = [tx.tx_hash for tx in transactions]
        merkle_root = compute_merkle_root(tx_hashes)

        header = BlockHeader(
            index=self.height,
            timestamp=timestamp or time.time(),
            previous_hash=self.last_block.block_hash,
            merkle_root=merkle_root,
            validator=validator,
        )

        block = Block(header=header, transactions=transactions)

        # Apply to real state
        for tx in transactions:
            self.state.apply_transaction(tx)

        self.chain.append(block)
        return block

    def validate_block(self, block: Block, previous_block: Block) -> Optional[str]:
        """Validate a single block against the previous block.

        Returns:
            None if valid, error message if invalid.
        """
        # Check index
        if block.header.index != previous_block.header.index + 1:
            return f"Invalid index: expected {previous_block.header.index + 1}"

        # Check previous hash link
        if block.header.previous_hash != previous_block.block_hash:
            return "Previous hash mismatch"

        # Check block hash
        if block.block_hash != block.compute_hash():
            return "Block hash mismatch"

        # Verify merkle root
        tx_hashes = [tx.tx_hash for tx in block.transactions]
        expected_root = compute_merkle_root(tx_hashes)
        if block.header.merkle_root != expected_root:
            return "Merkle root mismatch"

        # Verify all transaction signatures
        for tx in block.transactions:
            if not tx.verify():
                return f"Invalid transaction signature: {tx.tx_hash}"

        return None

    def validate_chain(self, chain: Optional[List[Block]] = None) -> Optional[str]:
        """Validate the entire chain.

        Returns:
            None if valid, error message if invalid.
        """
        if chain is None:
            chain = self.chain

        if not chain:
            return "Empty chain"

        for i in range(1, len(chain)):
            error = self.validate_block(chain[i], chain[i - 1])
            if error:
                return f"Block {i}: {error}"

        # Rebuild and validate state
        temp_state = AccountState()
        for block in chain[1:]:  # skip genesis
            for tx in block.transactions:
                error = temp_state.apply_transaction(tx)
                if error:
                    return f"State error in block {block.header.index}: {error}"

        return None

    def replace_chain(self, new_chain: List[Block]) -> bool:
        """Replace the current chain if the new one is longer and valid.

        Returns:
            True if chain was replaced.
        """
        if len(new_chain) <= len(self.chain):
            return False

        error = self.validate_chain(new_chain)
        if error:
            logger.warning("Chain replacement rejected: %s", error)
            return False

        logger.info("Chain replaced: %d -> %d blocks", len(self.chain), len(new_chain))
        self.chain = new_chain
        # Rebuild state from new chain
        self.state = AccountState()
        for block in self.chain[1:]:
            for tx in block.transactions:
                self.state.apply_transaction(tx)

        return True

    def save_to_file(self, filepath: str) -> None:
        """Persist the chain to a JSON file."""
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
        data = {
            "chain": [block.to_dict() for block in self.chain],
            "consensus": self.consensus.to_dict(),
        }
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)
        logger.info("Chain saved to %s (%d blocks)", filepath, len(self.chain))

    def load_from_file(self, filepath: str) -> bool:
        """Load chain from a JSON file. Returns True if successful."""
        if not os.path.exists(filepath):
            logger.info("Chain file not found: %s", filepath)
            return False

        with open(filepath, "r") as f:
            data = json.load(f)

        chain = [Block.from_dict(b) for b in data["chain"]]
        error = self.validate_chain(chain)
        if error:
            logger.warning("Chain file %s failed validation: %s", filepath, error)
            return False

        self.chain = chain
        self.consensus = PoAConsensus.from_dict(data.get("consensus", {}))

        # Rebuild state
        self.state = AccountState()
        for block in self.chain[1:]:
            for tx in block.transactions:
                self.state.apply_transaction(tx)

        return True

    def to_dict(self) -> dict:
        return {
            "chain": [block.to_dict() for block in self.chain],
            "height": self.height,
            "consensus": self.consensus.to_dict(),
        }
