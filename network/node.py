"""Flask REST API for a blockchain node."""

import os

from flask import Flask, jsonify, request
from flask_cors import CORS

from blockchain.block import Blockchain
from blockchain.transaction import Transaction, TransactionType
from config import DEFAULT_CONFIG, NetworkConfig
from gold.reserve import ReserveLedger, ReserveProof
from gold.token import GoldTokenManager
from network.mempool import Mempool
from network.peer import PeerManager
from network.sync import ChainSynchronizer


def create_node(
    host: str = "127.0.0.1",
    port: int = 5100,
    config: NetworkConfig = DEFAULT_CONFIG,
) -> Flask:
    """Create and configure a Flask blockchain node."""

    app = Flask(__name__)
    CORS(app)

    node_url = f"http://{host}:{port}"

    # Core components
    blockchain = Blockchain(config=config)
    mempool = Mempool(
        max_size=config.mempool_max_size,
        tx_timeout_seconds=config.mempool_tx_timeout_seconds,
    )
    peer_manager = PeerManager(self_url=node_url, max_peers=config.max_peers)
    reserve_ledger = ReserveLedger()
    token_manager = GoldTokenManager(blockchain, reserve_ledger, config)
    synchronizer = ChainSynchronizer(blockchain, peer_manager, token_manager)

    # Store on app for access in tests
    app.blockchain = blockchain
    app.mempool = mempool
    app.peer_manager = peer_manager
    app.reserve_ledger = reserve_ledger
    app.token_manager = token_manager
    app.synchronizer = synchronizer
    app.node_url = node_url

    # ── Health ──────────────────────────────────────────────

    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({
            "status": "ok",
            "node_url": node_url,
            "chain_height": blockchain.height,
            "peers": peer_manager.peer_count,
            "mempool_size": mempool.size,
            "network_id": config.network_id,
        })

    # ── Chain ───────────────────────────────────────────────

    @app.route("/chain", methods=["GET"])
    def get_chain():
        return jsonify({
            "chain": [block.to_dict() for block in blockchain.chain],
            "length": blockchain.height,
        })

    @app.route("/chain/length", methods=["GET"])
    def get_chain_length():
        return jsonify({"length": blockchain.height})

    @app.route("/blocks/<int:index>", methods=["GET"])
    def get_block(index):
        if index < 0 or index >= blockchain.height:
            return jsonify({"error": "Block not found"}), 404
        return jsonify(blockchain.chain[index].to_dict())

    # ── Transactions ────────────────────────────────────────

    @app.route("/transactions", methods=["POST"])
    def submit_transaction():
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400

        try:
            tx = Transaction.from_dict(data)
        except (KeyError, ValueError) as e:
            return jsonify({"error": f"Invalid transaction: {e}"}), 400

        if not tx.verify():
            return jsonify({"error": "Invalid transaction signature"}), 400

        # Validate against state
        error = blockchain.state.validate_transaction(tx)
        if error:
            return jsonify({"error": error}), 400

        # Check reserve invariant for MINT
        if tx.tx_type == TransactionType.MINT:
            if not reserve_ledger.can_mint(tx.amount):
                return jsonify({"error": "Insufficient gold reserves for minting"}), 400

        # Add to mempool
        pool_error = mempool.add_transaction(tx)
        if pool_error:
            return jsonify({"error": pool_error}), 400

        # Broadcast to peers
        peer_manager.broadcast_transaction(data)

        return jsonify({"tx_hash": tx.tx_hash, "status": "pending"}), 201

    @app.route("/mempool", methods=["GET"])
    def get_mempool():
        return jsonify({
            "transactions": mempool.to_list(),
            "size": mempool.size,
        })

    # ── Balances ────────────────────────────────────────────

    @app.route("/balance/<address>", methods=["GET"])
    def get_balance(address):
        balance = blockchain.state.get_balance(address)
        nonce = blockchain.state.get_nonce(address)
        return jsonify({
            "address": address,
            "balance": balance,
            "nonce": nonce,
        })

    # ── Mining ──────────────────────────────────────────────

    @app.route("/mine", methods=["POST"])
    def mine_block():
        data = request.get_json() or {}
        validator = data.get("validator", "")

        if not validator:
            return jsonify({"error": "Validator address required"}), 400

        # Get transactions from mempool
        max_txs = config.max_transactions_per_block
        transactions = mempool.get_transactions(limit=max_txs)

        if not transactions:
            return jsonify({"error": "No transactions to mine"}), 400

        # Create the block
        block = blockchain.create_block(transactions, validator)
        if block is None:
            return jsonify({"error": "Failed to create block"}), 500

        # Update reserve ledger
        token_manager.process_minted_block(block)

        # Remove mined transactions from mempool
        mined_hashes = [tx.tx_hash for tx in transactions]
        mempool.remove_transactions(mined_hashes)

        # Broadcast new block to peers
        peer_manager.broadcast_block(block.to_dict())

        # Persist chain
        data_dir = config.chain_data_dir
        blockchain.save_to_file(os.path.join(data_dir, "chain.json"))

        return jsonify({
            "message": f"Block {block.header.index} mined",
            "block": block.to_dict(),
        })

    @app.route("/blocks/receive", methods=["POST"])
    def receive_block():
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400

        accepted, message = synchronizer.receive_block(data)
        if accepted:
            # Remove block transactions from mempool and update reserve ledger
            try:
                from blockchain.block import Block
                from blockchain.transaction import TransactionType as TxType
                block = Block.from_dict(data)
                mined_hashes = [tx.tx_hash for tx in block.transactions]
                mempool.remove_transactions(mined_hashes)
                # Force-record since block is already validated
                for tx in block.transactions:
                    if tx.tx_type == TxType.MINT:
                        reserve_ledger.force_record_mint(tx.amount)
                    elif tx.tx_type == TxType.BURN:
                        reserve_ledger.record_burn(tx.amount)
            except Exception:
                pass
            return jsonify({"accepted": True, "message": message})
        else:
            return jsonify({"accepted": False, "message": message}), 400

    # ── Peers ───────────────────────────────────────────────

    @app.route("/nodes/register", methods=["POST"])
    def register_node():
        data = request.get_json()
        if not data or "node_url" not in data:
            return jsonify({"error": "node_url required"}), 400

        node = data["node_url"]
        added = peer_manager.register_peer(node)
        return jsonify({
            "message": "Peer registered" if added else "Peer already known or rejected",
            "peers": peer_manager.to_list(),
        }), 201 if added else 200

    @app.route("/nodes", methods=["GET"])
    def get_nodes():
        return jsonify({
            "peers": peer_manager.to_list(),
            "count": peer_manager.peer_count,
        })

    # ── Sync ────────────────────────────────────────────────

    @app.route("/sync", methods=["POST"])
    def sync_chain():
        replaced, message = synchronizer.sync()
        return jsonify({"replaced": replaced, "message": message})

    # ── Token Info ──────────────────────────────────────────

    @app.route("/token/info", methods=["GET"])
    def token_info():
        return jsonify(token_manager.get_token_info())

    # ── Reserves ────────────────────────────────────────────

    @app.route("/reserves", methods=["GET"])
    def get_reserves():
        return jsonify({
            "reserves": [r.to_dict() for r in reserve_ledger.reserves.values()],
            "audit": reserve_ledger.get_audit_summary(),
        })

    @app.route("/reserves", methods=["POST"])
    def add_reserve():
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400

        required = ["custodian", "amount_grams"]
        for field in required:
            if field not in data:
                return jsonify({"error": f"Missing field: {field}"}), 400

        proof = token_manager.add_reserve(
            custodian=data["custodian"],
            amount_grams=float(data["amount_grams"]),
            purity=float(data.get("purity", 0.999)),
            certificate_ref=data.get("certificate_ref", ""),
        )
        return jsonify({
            "proof": proof.to_dict(),
            "total_reserved": reserve_ledger.total_reserved,
        }), 201

    return app
