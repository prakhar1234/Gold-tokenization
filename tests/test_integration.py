"""End-to-end integration test: multi-block scenario matching the verification plan."""

import pytest
from blockchain.block import Blockchain
from blockchain.transaction import Transaction, TransactionType
from config import NetworkConfig
from crypto.keys import generate_keypair
from gold.reserve import ReserveLedger, ReserveProof
from gold.token import GoldTokenManager


class TestEndToEnd:
    """Full scenario: reserve -> mint -> transfer -> burn -> verify."""

    def test_full_gold_token_lifecycle(self):
        """
        1. Register 1000g gold reserve
        2. Mint 500 AUT to Alice (block 1, validator A)
        3. Alice transfers 200 AUT to Bob (block 2, validator B)
        4. Bob burns 50 AUT (block 3, validator C)
        5. Verify: Alice=300, Bob=150, circulating=450, burned=50, ratio≈2.22
        """
        # Setup
        config = NetworkConfig(
            validators=["validator-A", "validator-B", "validator-C"]
        )
        blockchain = Blockchain(config=config)
        reserve_ledger = ReserveLedger()
        token_manager = GoldTokenManager(blockchain, reserve_ledger, config)

        # Keys
        auth_priv, auth_pub, auth_addr = generate_keypair()
        alice_priv, alice_pub, alice_addr = generate_keypair()
        bob_priv, bob_pub, bob_addr = generate_keypair()

        # Step 1: Register 1000g gold reserve
        proof = ReserveProof(
            custodian="Fort Knox",
            amount_grams=1000.0,
            purity=1.0,
            certificate_ref="FK-2024-001",
        )
        reserve_ledger.add_reserve(proof)
        assert reserve_ledger.total_reserved == 1000.0

        # Step 2: Mint 500 AUT to Alice
        mint_tx = token_manager.create_mint_transaction(
            recipient=alice_addr,
            amount=500.0,
            authority_private_key=auth_priv,
            authority_public_key=auth_pub,
        )
        assert mint_tx is not None
        assert mint_tx.verify()

        block1 = blockchain.create_block([mint_tx], "validator-A")
        assert block1 is not None
        assert block1.header.index == 1
        token_manager.process_minted_block(block1)

        assert blockchain.state.get_balance(alice_addr) == 500.0

        # Step 3: Alice transfers 200 AUT to Bob
        transfer_tx = token_manager.create_transfer_transaction(
            sender=alice_addr,
            recipient=bob_addr,
            amount=200.0,
            sender_private_key=alice_priv,
            sender_public_key=alice_pub,
        )
        assert transfer_tx is not None
        assert transfer_tx.verify()

        block2 = blockchain.create_block([transfer_tx], "validator-B")
        assert block2 is not None
        assert block2.header.index == 2
        token_manager.process_minted_block(block2)

        assert blockchain.state.get_balance(alice_addr) == 300.0
        assert blockchain.state.get_balance(bob_addr) == 200.0

        # Step 4: Bob burns 50 AUT
        burn_tx = token_manager.create_burn_transaction(
            sender=bob_addr,
            amount=50.0,
            sender_private_key=bob_priv,
            sender_public_key=bob_pub,
        )
        assert burn_tx is not None
        assert burn_tx.verify()

        block3 = blockchain.create_block([burn_tx], "validator-C")
        assert block3 is not None
        assert block3.header.index == 3
        token_manager.process_minted_block(block3)

        # Step 5: Verify final state
        assert blockchain.state.get_balance(alice_addr) == 300.0
        assert blockchain.state.get_balance(bob_addr) == 150.0

        info = token_manager.get_token_info()
        assert info["circulating_supply"] == 450.0
        assert info["total_burned"] == 50.0
        assert info["total_minted"] == 500.0

        # Reserve ratio: 1000 / 450 ≈ 2.2222
        assert abs(info["reserve_ratio"] - 2.2222) < 0.001

        # Chain validation
        assert blockchain.validate_chain() is None
        assert blockchain.height == 4  # genesis + 3 blocks

    def test_reserve_invariant_prevents_overminting(self):
        """Ensure minting beyond reserve capacity is blocked."""
        config = NetworkConfig(validators=["v0"])
        blockchain = Blockchain(config=config)
        reserve_ledger = ReserveLedger()
        token_manager = GoldTokenManager(blockchain, reserve_ledger, config)

        auth_priv, auth_pub, auth_addr = generate_keypair()
        _, _, alice_addr = generate_keypair()

        # Only 100g reserved
        proof = ReserveProof(custodian="Small Vault", amount_grams=100.0, purity=1.0)
        reserve_ledger.add_reserve(proof)

        # Try to mint 200 AUT — should fail
        tx = token_manager.create_mint_transaction(
            recipient=alice_addr,
            amount=200.0,
            authority_private_key=auth_priv,
            authority_public_key=auth_pub,
        )
        assert tx is None

        # Mint exactly 100 — should succeed
        tx = token_manager.create_mint_transaction(
            recipient=alice_addr,
            amount=100.0,
            authority_private_key=auth_priv,
            authority_public_key=auth_pub,
        )
        assert tx is not None

    def test_api_full_lifecycle(self, client, authority_keypair, alice_keypair, bob_keypair):
        """Test the full lifecycle through the Flask API."""
        # 1. Add reserve
        resp = client.post("/reserves", json={
            "custodian": "API Vault",
            "amount_grams": 1000.0,
            "purity": 1.0,
        })
        assert resp.status_code == 201

        # 2. Mint 500 AUT to Alice
        mint_tx = Transaction(
            tx_type=TransactionType.MINT, sender="NETWORK",
            recipient=alice_keypair["address"], amount=500.0, nonce=0,
            public_key=authority_keypair["public_key"],
        )
        mint_tx.sign(authority_keypair["private_key"])

        resp = client.post("/transactions", json=mint_tx.to_dict())
        assert resp.status_code == 201

        resp = client.post("/mine", json={"validator": "validator-0"})
        assert resp.status_code == 200

        # 3. Transfer 200 from Alice to Bob
        transfer_tx = Transaction(
            tx_type=TransactionType.TRANSFER,
            sender=alice_keypair["address"],
            recipient=bob_keypair["address"],
            amount=200.0, nonce=0,
            public_key=alice_keypair["public_key"],
        )
        transfer_tx.sign(alice_keypair["private_key"])

        resp = client.post("/transactions", json=transfer_tx.to_dict())
        assert resp.status_code == 201

        resp = client.post("/mine", json={"validator": "validator-1"})
        assert resp.status_code == 200

        # 4. Bob burns 50
        burn_tx = Transaction(
            tx_type=TransactionType.BURN,
            sender=bob_keypair["address"],
            recipient="BURN", amount=50.0, nonce=0,
            public_key=bob_keypair["public_key"],
        )
        burn_tx.sign(bob_keypair["private_key"])

        resp = client.post("/transactions", json=burn_tx.to_dict())
        assert resp.status_code == 201

        resp = client.post("/mine", json={"validator": "validator-2"})
        assert resp.status_code == 200

        # 5. Verify balances
        resp = client.get(f"/balance/{alice_keypair['address']}")
        assert resp.get_json()["balance"] == 300.0

        resp = client.get(f"/balance/{bob_keypair['address']}")
        assert resp.get_json()["balance"] == 150.0

        # 6. Verify token info
        resp = client.get("/token/info")
        info = resp.get_json()
        assert info["circulating_supply"] == 450.0
        assert info["total_burned"] == 50.0
        assert abs(info["reserve_ratio"] - 2.2222) < 0.001

        # 7. Verify chain
        resp = client.get("/chain")
        assert resp.get_json()["length"] == 4  # genesis + 3
