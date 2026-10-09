"""Peer discovery, registration, and broadcast communication."""

import logging
import threading
from typing import Dict, List, Optional, Set

import requests

logger = logging.getLogger(__name__)


class PeerManager:
    """Manages peer connections and broadcasts for a node."""

    def __init__(self, self_url: str, max_peers: int = 50):
        self.self_url = self_url
        self.max_peers = max_peers
        self._peers: Set[str] = set()
        self._lock = threading.Lock()

    @property
    def peers(self) -> List[str]:
        with self._lock:
            return list(self._peers)

    @property
    def peer_count(self) -> int:
        with self._lock:
            return len(self._peers)

    def register_peer(self, peer_url: str) -> bool:
        """Register a new peer. Returns True if added, False if already known or full."""
        if peer_url == self.self_url:
            return False

        with self._lock:
            if len(self._peers) >= self.max_peers:
                return False
            if peer_url in self._peers:
                return False
            self._peers.add(peer_url)
            logger.info("Peer registered: %s", peer_url)
            return True

    def remove_peer(self, peer_url: str) -> None:
        with self._lock:
            self._peers.discard(peer_url)

    def broadcast_transaction(self, tx_dict: dict) -> Dict[str, bool]:
        """Broadcast a transaction to all peers.

        Returns:
            Dict mapping peer_url -> success boolean.
        """
        results = {}
        peers = self.peers

        for peer in peers:
            try:
                resp = requests.post(
                    f"{peer}/transactions",
                    json=tx_dict,
                    timeout=5,
                )
                results[peer] = resp.status_code == 201
            except requests.RequestException as e:
                logger.warning("Failed to broadcast tx to %s: %s", peer, e)
                results[peer] = False

        return results

    def broadcast_block(self, block_dict: dict) -> Dict[str, bool]:
        """Broadcast a new block to all peers.

        Returns:
            Dict mapping peer_url -> success boolean.
        """
        results = {}
        peers = self.peers

        for peer in peers:
            try:
                resp = requests.post(
                    f"{peer}/blocks/receive",
                    json=block_dict,
                    timeout=5,
                )
                results[peer] = resp.status_code == 200
            except requests.RequestException as e:
                logger.warning("Failed to broadcast block to %s: %s", peer, e)
                results[peer] = False

        return results

    def register_with_peer(self, peer_url: str) -> bool:
        """Register this node with a remote peer.

        Returns:
            True if registration succeeded.
        """
        try:
            resp = requests.post(
                f"{peer_url}/nodes/register",
                json={"node_url": self.self_url},
                timeout=5,
            )
            if resp.status_code == 201:
                self.register_peer(peer_url)
                return True
            return False
        except requests.RequestException as e:
            logger.warning("Failed to register with peer %s: %s", peer_url, e)
            return False

    def health_check(self, peer_url: str) -> bool:
        """Check if a peer is alive."""
        try:
            resp = requests.get(f"{peer_url}/health", timeout=3)
            return resp.status_code == 200
        except requests.RequestException as e:
            logger.debug("Health check failed for %s: %s", peer_url, e)
            return False

    def get_chain_length(self, peer_url: str) -> Optional[int]:
        """Get the chain length from a peer."""
        try:
            resp = requests.get(f"{peer_url}/chain/length", timeout=5)
            if resp.status_code == 200:
                return resp.json().get("length")
            return None
        except requests.RequestException as e:
            logger.warning("Failed to get chain length from %s: %s", peer_url, e)
            return None

    def get_chain(self, peer_url: str) -> Optional[list]:
        """Download the full chain from a peer."""
        try:
            resp = requests.get(f"{peer_url}/chain", timeout=30)
            if resp.status_code == 200:
                return resp.json().get("chain")
            return None
        except requests.RequestException as e:
            logger.warning("Failed to download chain from %s: %s", peer_url, e)
            return None

    def prune_dead_peers(self) -> List[str]:
        """Remove peers that fail health checks. Returns list of removed peers."""
        removed = []
        peers = self.peers
        for peer in peers:
            if not self.health_check(peer):
                self.remove_peer(peer)
                removed.append(peer)
        if removed:
            logger.info("Pruned %d dead peer(s): %s", len(removed), removed)
        return removed

    def to_list(self) -> List[str]:
        return self.peers
