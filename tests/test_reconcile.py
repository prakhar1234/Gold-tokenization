"""Tests for the reconciliation script."""

import json
import pytest
from unittest.mock import patch, MagicMock

from blockchain.block import Block, BlockHeader, Blockchain
from blockchain.merkle import compute_merkle_root
from blockchain.transaction import Transaction, TransactionType
from config import NetworkConfig
from crypto.keys import generate_keypair
from gold.reserve import ReserveLedger, ReserveProof
from gold.token import GoldTokenManager

from cli.reconcile import (
    ReconciliationReport,
    check_chain_integrity,
    check_transactions,
    check_balances,
    check_reserves,
    check_supply_conservation,
    check_cross_node_consensus,
    replay_state,
)


# ── Helpers ──────────────────────────────────────────────────────

def _build_test_chain():
    """Build a 4-block chain: genesis + mint + transfer + burn.

    Returns (blockchain, token_manager, reserve_ledger, keypairs)
    """
    config = NetworkConfig(validators=["v-0", "v-1", "v-2"])
    blockchain = Blockchain(config=config)
    reserve_ledger = ReserveLedger()
    token_manager = GoldTokenManager(blockchain, reserve_ledger, config)

    auth_priv, auth_pub, auth_addr = generate_keypair()
    alice_priv, alice_pub, alice_addr = generate_keypair()
    bob_priv, bob_pub, bob_addr = generate_keypair()

    # 1000g gold reserve
    proof = ReserveProof(custodian="Vault", amount_grams=1000.0, purity=1.0)
    reserve_ledger.add_reserve(proof)

    # Block 1: Mint 500 AUT to Alice
    mint_tx = token_manager.create_mint_transaction(
        alice_addr, 500.0, auth_priv, auth_pub
    )
    block1 = blockchain.create_block([mint_tx], "v-0")
    token_manager.process_minted_block(block1)

    # Block 2: Alice transfers 200 AUT to Bob
    transfer_tx = token_manager.create_transfer_transaction(
        alice_addr, bob_addr, 200.0, alice_priv, alice_pub
    )
    block2 = blockchain.create_block([transfer_tx], "v-1")
    token_manager.process_minted_block(block2)

    # Block 3: Bob burns 50 AUT
    burn_tx = token_manager.create_burn_transaction(
        bob_addr, 50.0, bob_priv, bob_pub
    )
    block3 = blockchain.create_block([burn_tx], "v-2")
    token_manager.process_minted_block(block3)

    keypairs = {
        "authority": {"private": auth_priv, "public": auth_pub, "address": auth_addr},
        "alice": {"private": alice_priv, "public": alice_pub, "address": alice_addr},
        "bob": {"private": bob_priv, "public": bob_pub, "address": bob_addr},
    }

    return blockchain, token_manager, reserve_ledger, keypairs


class TestReplayState:
    """Test independent state replay from chain data."""

    def test_replay_produces_correct_balances(self):
        blockchain, _, _, kp = _build_test_chain()
        chain_data = [b.to_dict() for b in blockchain.chain]
        blocks = [Block.from_dict(d) for d in chain_data]

        balances, nonces, total_minted, total_burned = replay_state(blocks)

        assert round(balances[kp["alice"]["address"]], 4) == 300.0
        assert round(balances[kp["bob"]["address"]], 4) == 150.0
        assert total_minted == 500.0
        assert total_burned == 50.0

    def test_replay_nonces(self):
        blockchain, _, _, kp = _build_test_chain()
        chain_data = [b.to_dict() for b in blockchain.chain]
        blocks = [Block.from_dict(d) for d in chain_data]

        balances, nonces, _, _ = replay_state(blocks)

        # Alice did 1 transfer, Bob did 1 burn
        assert nonces.get(kp["alice"]["address"], 0) == 1
        assert nonces.get(kp["bob"]["address"], 0) == 1

    def test_empty_chain_replay(self):
        config = NetworkConfig(validators=["v-0"])
        blockchain = Blockchain(config=config)
        chain_data = [b.to_dict() for b in blockchain.chain]
        blocks = [Block.from_dict(d) for d in chain_data]

        balances, nonces, total_minted, total_burned = replay_state(blocks)

        assert balances == {}
        assert nonces == {}
        assert total_minted == 0.0
        assert total_burned == 0.0


class TestChainIntegrity:
    """Test chain integrity verification."""

    def test_valid_chain_passes(self):
        blockchain, _, _, _ = _build_test_chain()
        chain_data = [b.to_dict() for b in blockchain.chain]
        report = ReconciliationReport()

        blocks = check_chain_integrity(chain_data, report)

        assert len(report.failures) == 0
        assert len(blocks) == 4
        # Should have PASS for genesis, hashes, links, merkle
        assert len(report.passes) >= 4

    def test_tampered_block_hash_detected(self):
        blockchain, _, _, _ = _build_test_chain()
        chain_data = [b.to_dict() for b in blockchain.chain]
        # Tamper with block 2's hash
        chain_data[2]["block_hash"] = "deadbeef" * 8
        report = ReconciliationReport()

        check_chain_integrity(chain_data, report)

        hash_failures = [f for f in report.failures if "block_hash" in f.message]
        assert len(hash_failures) >= 1

    def test_broken_previous_hash_link_detected(self):
        blockchain, _, _, _ = _build_test_chain()
        chain_data = [b.to_dict() for b in blockchain.chain]
        # Break the previous_hash link on block 2
        chain_data[2]["header"]["previous_hash"] = "0" * 64
        report = ReconciliationReport()

        check_chain_integrity(chain_data, report)

        link_failures = [f for f in report.failures if "previous_hash" in f.message]
        assert len(link_failures) >= 1

    def test_bad_merkle_root_detected(self):
        blockchain, _, _, _ = _build_test_chain()
        chain_data = [b.to_dict() for b in blockchain.chain]
        # Corrupt merkle root on block 1
        chain_data[1]["header"]["merkle_root"] = "baad" * 16
        report = ReconciliationReport()

        check_chain_integrity(chain_data, report)

        merkle_failures = [f for f in report.failures if "merkle" in f.message]
        assert len(merkle_failures) >= 1

    def test_empty_chain_fails(self):
        report = ReconciliationReport()
        blocks = check_chain_integrity([], report)
        assert len(report.failures) == 1
        assert "empty" in report.failures[0].message.lower()


class TestTransactionAudit:
    """Test transaction signature and double-spend checks."""

    def test_valid_transactions_pass(self):
        blockchain, _, _, _ = _build_test_chain()
        chain_data = [b.to_dict() for b in blockchain.chain]
        blocks = [Block.from_dict(d) for d in chain_data]
        report = ReconciliationReport()

        total = check_transactions(blocks, report)

        assert total == 3  # mint, transfer, burn
        assert len(report.failures) == 0

    def test_tampered_signature_detected(self):
        blockchain, _, _, _ = _build_test_chain()
        chain_data = [b.to_dict() for b in blockchain.chain]
        # Tamper with the signature on block 1's transaction
        chain_data[1]["transactions"][0]["signature"] = "ff" * 64
        blocks = [Block.from_dict(d) for d in chain_data]
        report = ReconciliationReport()

        check_transactions(blocks, report)

        sig_failures = [f for f in report.failures if "signature" in f.message]
        assert len(sig_failures) >= 1

    def test_duplicate_tx_hash_detected(self):
        blockchain, _, _, _ = _build_test_chain()
        chain_data = [b.to_dict() for b in blockchain.chain]
        # Duplicate block 1's transaction into block 2
        chain_data[2]["transactions"].append(chain_data[1]["transactions"][0])
        blocks = [Block.from_dict(d) for d in chain_data]
        report = ReconciliationReport()

        check_transactions(blocks, report)

        dup_failures = [f for f in report.failures if "Duplicate" in f.message]
        assert len(dup_failures) >= 1


class TestSupplyConservation:
    """Test that sum(balances) == circulating supply."""

    def test_conservation_holds(self):
        blockchain, _, _, kp = _build_test_chain()
        chain_data = [b.to_dict() for b in blockchain.chain]
        blocks = [Block.from_dict(d) for d in chain_data]
        balances, _, total_minted, total_burned = replay_state(blocks)

        report = ReconciliationReport()
        check_supply_conservation(balances, total_minted, total_burned, report)

        assert len(report.failures) == 0
        # sum(300 + 150) = 450 = 500 - 50
        assert report.passes[0].message.startswith("Supply conservation verified")

    def test_conservation_violated(self):
        report = ReconciliationReport()
        # Artificially break conservation
        balances = {"0xaaa": 500.0}
        check_supply_conservation(balances, 400.0, 0.0, report)

        assert len(report.failures) == 1
        assert "VIOLATED" in report.failures[0].message

    def test_negative_balance_detected(self):
        report = ReconciliationReport()
        balances = {"0xaaa": -10.0, "0xbbb": 60.0}
        check_supply_conservation(balances, 50.0, 0.0, report)

        neg_failures = [f for f in report.failures if "Negative" in f.message]
        assert len(neg_failures) == 1


class TestReserveReconciliation:
    """Test reserve invariant and mint/burn reconciliation."""

    @patch("cli.reconcile.fetch_reserves")
    @patch("cli.reconcile.fetch_token_info")
    def test_matching_reserves_pass(self, mock_token, mock_reserves):
        mock_reserves.return_value = {
            "reserves": [{"proof_id": "p1"}],
            "audit": {
                "total_reserved_grams": 1000.0,
                "total_minted": 500.0,
                "total_burned": 50.0,
                "circulating_supply": 450.0,
                "reserve_ratio": 2.2222,
                "num_reserves": 1,
            },
        }
        mock_token.return_value = {
            "circulating_supply": 450.0,
            "total_minted": 500.0,
            "total_burned": 50.0,
        }

        report = ReconciliationReport()
        check_reserves("http://fake", 500.0, 50.0, report)

        assert len(report.failures) == 0
        assert len(report.passes) >= 4  # minted, burned, supply, invariant, proof count

    @patch("cli.reconcile.fetch_reserves")
    @patch("cli.reconcile.fetch_token_info")
    def test_minted_mismatch_detected(self, mock_token, mock_reserves):
        mock_reserves.return_value = {
            "reserves": [],
            "audit": {
                "total_reserved_grams": 0,
                "total_minted": 999.0,  # wrong
                "total_burned": 0.0,
                "circulating_supply": 999.0,
                "reserve_ratio": 0.0,
                "num_reserves": 0,
            },
        }
        mock_token.return_value = {"total_minted": 999.0, "total_burned": 0.0}

        report = ReconciliationReport()
        check_reserves("http://fake", 500.0, 0.0, report)  # computed=500, reported=999

        minted_fail = [f for f in report.failures if "minted" in f.message.lower()]
        assert len(minted_fail) >= 1

    @patch("cli.reconcile.fetch_reserves")
    @patch("cli.reconcile.fetch_token_info")
    def test_invariant_violation_detected(self, mock_token, mock_reserves):
        mock_reserves.return_value = {
            "reserves": [],
            "audit": {
                "total_reserved_grams": 100.0,
                "total_minted": 500.0,
                "total_burned": 0.0,
                "circulating_supply": 500.0,
                "reserve_ratio": 0.2,
                "num_reserves": 0,
            },
        }
        mock_token.return_value = {"total_minted": 500.0, "total_burned": 0.0}

        report = ReconciliationReport()
        check_reserves("http://fake", 500.0, 0.0, report)

        invariant_fail = [f for f in report.failures if "INVARIANT" in f.message]
        assert len(invariant_fail) >= 1


class TestCrossNodeConsensus:
    """Test cross-node chain agreement checks."""

    @patch("cli.reconcile.fetch_json")
    def test_nodes_in_agreement(self, mock_fetch):
        mock_fetch.side_effect = [
            # health for node 1
            {"chain_height": 4, "status": "ok"},
            # chain for node 1
            {"chain": [{"block_hash": "aaa"}]},
            # health for node 2
            {"chain_height": 4, "status": "ok"},
            # chain for node 2
            {"chain": [{"block_hash": "aaa"}]},
            # nodes for node 1
            {"count": 1},
            # nodes for node 2
            {"count": 1},
        ]

        report = ReconciliationReport()
        check_cross_node_consensus(
            ["http://node1", "http://node2"], report
        )

        assert len(report.failures) == 0
        height_pass = [f for f in report.passes if "height" in f.message.lower()]
        tip_pass = [f for f in report.passes if "tip" in f.message.lower()]
        assert len(height_pass) == 1
        assert len(tip_pass) == 1

    @patch("cli.reconcile.fetch_json")
    def test_height_disagreement_detected(self, mock_fetch):
        mock_fetch.side_effect = [
            {"chain_height": 4, "status": "ok"},
            {"chain": [{"block_hash": "aaa"}]},
            {"chain_height": 2, "status": "ok"},  # different height
            {"chain": [{"block_hash": "bbb"}]},
            {"count": 1},
            {"count": 1},
        ]

        report = ReconciliationReport()
        check_cross_node_consensus(
            ["http://node1", "http://node2"], report
        )

        height_fail = [f for f in report.failures if "height" in f.message.lower()]
        assert len(height_fail) == 1


class TestBalanceReconciliation:
    """Test balance reconciliation against a mock node."""

    @patch("cli.reconcile.fetch_balance")
    def test_matching_balances_pass(self, mock_balance):
        blockchain, _, _, kp = _build_test_chain()
        chain_data = [b.to_dict() for b in blockchain.chain]
        blocks = [Block.from_dict(d) for d in chain_data]

        def balance_response(url, addr):
            if addr == kp["alice"]["address"]:
                return {"balance": 300.0, "nonce": 1}
            elif addr == kp["bob"]["address"]:
                return {"balance": 150.0, "nonce": 1}
            return {"balance": 0.0, "nonce": 0}

        mock_balance.side_effect = balance_response

        report = ReconciliationReport()
        check_balances(blocks, "http://fake", report)

        assert len(report.failures) == 0
        bal_pass = [f for f in report.passes if "balance" in f.message.lower()]
        assert len(bal_pass) >= 1

    @patch("cli.reconcile.fetch_balance")
    def test_balance_mismatch_detected(self, mock_balance):
        blockchain, _, _, kp = _build_test_chain()
        chain_data = [b.to_dict() for b in blockchain.chain]
        blocks = [Block.from_dict(d) for d in chain_data]

        def balance_response(url, addr):
            if addr == kp["alice"]["address"]:
                return {"balance": 999.0, "nonce": 1}  # wrong
            elif addr == kp["bob"]["address"]:
                return {"balance": 150.0, "nonce": 1}
            return {"balance": 0.0, "nonce": 0}

        mock_balance.side_effect = balance_response

        report = ReconciliationReport()
        check_balances(blocks, "http://fake", report)

        bal_fail = [f for f in report.failures if "Balance mismatch" in f.message]
        assert len(bal_fail) >= 1


class TestReconciliationReport:
    """Test the report aggregation."""

    def test_report_pass_status(self):
        report = ReconciliationReport()
        report.add("PASS", "chain", "All good")
        report.add("WARN", "balance", "Minor thing")
        assert report.passed is True

    def test_report_fail_status(self):
        report = ReconciliationReport()
        report.add("PASS", "chain", "OK")
        report.add("FAIL", "reserve", "Invariant violated")
        assert report.passed is False

    def test_report_categories(self):
        report = ReconciliationReport()
        report.add("PASS", "chain", "A")
        report.add("FAIL", "reserve", "B")
        report.add("WARN", "consensus", "C")
        assert len(report.passes) == 1
        assert len(report.failures) == 1
        assert len(report.warnings) == 1
