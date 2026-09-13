"""Merkle tree for transaction integrity verification."""

from typing import List, Optional, Tuple

from crypto.hashing import sha256


def _hash_pair(left: str, right: str) -> str:
    """Hash two hex strings together."""
    combined = (left + right).encode("utf-8")
    return sha256(combined)


def build_merkle_tree(tx_hashes: List[str]) -> List[List[str]]:
    """Build a complete Merkle tree from transaction hashes.

    Returns:
        List of levels, from leaves (index 0) to root (last index).
        Empty list if no hashes provided.
    """
    if not tx_hashes:
        return []

    # Level 0: leaves
    current_level = list(tx_hashes)
    tree = [current_level[:]]

    while len(current_level) > 1:
        next_level = []
        # Duplicate last element if odd number
        if len(current_level) % 2 == 1:
            current_level.append(current_level[-1])

        for i in range(0, len(current_level), 2):
            next_level.append(_hash_pair(current_level[i], current_level[i + 1]))

        tree.append(next_level[:])
        current_level = next_level

    return tree


def compute_merkle_root(tx_hashes: List[str]) -> str:
    """Compute the Merkle root from a list of transaction hashes.

    Returns:
        The root hash, or SHA-256 of empty string if no transactions.
    """
    if not tx_hashes:
        return sha256(b"")

    tree = build_merkle_tree(tx_hashes)
    return tree[-1][0]


def get_merkle_proof(tx_hashes: List[str], index: int) -> List[Tuple[str, str]]:
    """Generate a Merkle proof for a transaction at the given index.

    Returns:
        List of (hash, side) tuples where side is "left" or "right",
        indicating which side the sibling hash goes on.
    """
    if not tx_hashes or index < 0 or index >= len(tx_hashes):
        return []

    tree = build_merkle_tree(tx_hashes)
    proof = []
    idx = index

    for level in tree[:-1]:  # skip root level
        # Pad if odd
        working = list(level)
        if len(working) % 2 == 1:
            working.append(working[-1])

        if idx % 2 == 0:
            sibling_idx = idx + 1
            proof.append((working[sibling_idx], "right"))
        else:
            sibling_idx = idx - 1
            proof.append((working[sibling_idx], "left"))

        idx = idx // 2

    return proof


def verify_merkle_proof(
    tx_hash: str, proof: List[Tuple[str, str]], merkle_root: str
) -> bool:
    """Verify a Merkle proof for a given transaction hash."""
    current = tx_hash

    for sibling_hash, side in proof:
        if side == "left":
            current = _hash_pair(sibling_hash, current)
        else:
            current = _hash_pair(current, sibling_hash)

    return current == merkle_root
