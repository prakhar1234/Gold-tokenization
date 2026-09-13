"""Tests for Merkle tree operations."""

import pytest
from blockchain.merkle import (
    build_merkle_tree,
    compute_merkle_root,
    get_merkle_proof,
    verify_merkle_proof,
)
from crypto.hashing import sha256


class TestMerkleTree:
    def test_empty(self):
        root = compute_merkle_root([])
        assert root == sha256(b"")

    def test_single_hash(self):
        hashes = ["abc123"]
        tree = build_merkle_tree(hashes)
        assert len(tree) == 1
        assert tree[0] == ["abc123"]
        assert compute_merkle_root(hashes) == "abc123"

    def test_two_hashes(self):
        hashes = ["aaa", "bbb"]
        root = compute_merkle_root(hashes)
        assert root is not None
        assert root != "aaa"
        assert root != "bbb"

    def test_three_hashes(self):
        hashes = ["aaa", "bbb", "ccc"]
        tree = build_merkle_tree(hashes)
        # Level 0: 3 leaves, Level 1: 2 nodes (ccc duplicated), Level 2: root
        assert len(tree) == 3
        assert len(tree[0]) == 3

    def test_four_hashes(self):
        hashes = ["a", "b", "c", "d"]
        tree = build_merkle_tree(hashes)
        assert len(tree) == 3  # 4 -> 2 -> 1
        assert len(tree[-1]) == 1  # root

    def test_deterministic(self):
        hashes = ["tx1", "tx2", "tx3"]
        root1 = compute_merkle_root(hashes)
        root2 = compute_merkle_root(hashes)
        assert root1 == root2

    def test_order_matters(self):
        root1 = compute_merkle_root(["a", "b"])
        root2 = compute_merkle_root(["b", "a"])
        assert root1 != root2


class TestMerkleProof:
    def test_proof_single(self):
        hashes = ["onlyone"]
        proof = get_merkle_proof(hashes, 0)
        assert proof == []
        assert verify_merkle_proof("onlyone", proof, "onlyone")

    def test_proof_two(self):
        hashes = ["aaa", "bbb"]
        root = compute_merkle_root(hashes)

        proof0 = get_merkle_proof(hashes, 0)
        assert verify_merkle_proof("aaa", proof0, root)

        proof1 = get_merkle_proof(hashes, 1)
        assert verify_merkle_proof("bbb", proof1, root)

    def test_proof_four(self):
        hashes = ["a", "b", "c", "d"]
        root = compute_merkle_root(hashes)

        for i in range(4):
            proof = get_merkle_proof(hashes, i)
            assert verify_merkle_proof(hashes[i], proof, root)

    def test_invalid_proof(self):
        hashes = ["a", "b", "c", "d"]
        root = compute_merkle_root(hashes)
        proof = get_merkle_proof(hashes, 0)
        # Wrong hash
        assert not verify_merkle_proof("wrong", proof, root)

    def test_invalid_index(self):
        assert get_merkle_proof(["a"], -1) == []
        assert get_merkle_proof(["a"], 1) == []
        assert get_merkle_proof([], 0) == []
