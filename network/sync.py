"""Chain synchronization protocol — longest valid chain wins."""

from typing import List, Optional, Tuple

from blockchain.block import Block, Blockchain
from network.peer import PeerManager


class ChainSynchronizer:
    """Handles chain synchronization across the peer network."""

    def __init__(self, blockchain: Blockchain, peer_manager: PeerManager, token_manager=None):
        self.blockchain = blockchain
        self.peer_manager = peer_manager
        self.token_manager = token_manager

    def sync(self) -> Tuple[bool, str]:
        """Synchronize chain with peers, adopting the longest valid chain.

        Returns:
            (replaced, message) — whether the chain was replaced and a status message.
        """
        peers = self.peer_manager.peers
        if not peers:
            return False, "No peers to sync with"

        # Find the peer with the longest chain
        best_peer = None
        best_length = len(self.blockchain.chain)

        for peer in peers:
            length = self.peer_manager.get_chain_length(peer)
            if length is not None and length > best_length:
                best_length = length
                best_peer = peer

        if best_peer is None:
            return False, "Local chain is already the longest"

        # Download chain from the best peer
        chain_data = self.peer_manager.get_chain(best_peer)
        if chain_data is None:
            return False, f"Failed to download chain from {best_peer}"

        # Parse blocks
        try:
            new_chain = [Block.from_dict(b) for b in chain_data]
        except (KeyError, ValueError) as e:
            return False, f"Invalid chain data from {best_peer}: {e}"

        # Validate and replace
        replaced = self.blockchain.replace_chain(new_chain)
        if replaced:
            # Rebuild reserve ledger counters from the new chain
            if self.token_manager:
                self.token_manager.rebuild_from_chain()
            return True, f"Chain replaced from {best_peer} (length {best_length})"
        else:
            return False, f"Chain from {best_peer} was invalid or not longer"

    def receive_block(self, block_dict: dict) -> Tuple[bool, str]:
        """Handle a block received from a peer.

        Returns:
            (accepted, message)
        """
        try:
            block = Block.from_dict(block_dict)
        except (KeyError, ValueError) as e:
            return False, f"Invalid block data: {e}"

        # Check if it extends our chain
        if block.header.index != len(self.blockchain.chain):
            if block.header.index < len(self.blockchain.chain):
                return False, "Block already known"
            # Block is ahead — need to sync
            self.sync()
            return False, "Block ahead of local chain, triggered sync"

        # Validate against our last block
        last_block = self.blockchain.last_block
        error = self.blockchain.validate_block(block, last_block)
        if error:
            return False, f"Invalid block: {error}"

        # Apply transactions to state
        for tx in block.transactions:
            apply_error = self.blockchain.state.apply_transaction(tx)
            if apply_error:
                return False, f"State error: {apply_error}"

        self.blockchain.chain.append(block)
        return True, f"Block {block.header.index} accepted"
