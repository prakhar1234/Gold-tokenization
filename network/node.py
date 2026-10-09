"""Flask REST API for a blockchain node."""

import logging
import os

from flask import Flask, jsonify, request
from flask_cors import CORS

from blockchain.block import Blockchain
from blockchain.transaction import Transaction, TransactionType
from config import DEFAULT_CONFIG, NetworkConfig
from gold.reserve import ReserveLedger, ReserveProof
from gold.token import GoldTokenManager
from logging_config import setup_logging
from network.mempool import Mempool
from network.peer import PeerManager
from network.sync import ChainSynchronizer
from trading.matching_engine import MatchingEngine
from trading.order import Order, OrderSide
from trading.order_book import OrderBook
from wallet.wallet import Wallet

logger = logging.getLogger(__name__)


def create_node(
    host: str = "127.0.0.1",
    port: int = 5100,
    config: NetworkConfig = DEFAULT_CONFIG,
) -> Flask:
    """Create and configure a Flask blockchain node."""

    setup_logging()

    app = Flask(__name__)
    CORS(app)

    node_url = f"http://{host}:{port}"
    logger.info("Initializing node at %s (network_id=%s)", node_url, config.network_id)

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

    # Trading components
    order_book = OrderBook()
    matching_engine = MatchingEngine(order_book, blockchain, mempool)

    # Store on app for access in tests
    app.blockchain = blockchain
    app.mempool = mempool
    app.peer_manager = peer_manager
    app.reserve_ledger = reserve_ledger
    app.token_manager = token_manager
    app.synchronizer = synchronizer
    app.order_book = order_book
    app.matching_engine = matching_engine
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

        logger.info("Transaction submitted: %s type=%s amount=%.4f", tx.tx_hash[:16], tx.tx_type.value, tx.amount)
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

        logger.info("Block %d mined by %s with %d txs", block.header.index, validator, len(transactions))

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
                logger.error("Failed to process received block post-accept", exc_info=True)
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
            depositor_address=data.get("depositor_address", ""),
        )
        return jsonify({
            "proof": proof.to_dict(),
            "total_reserved": reserve_ledger.total_reserved,
        }), 201

    # ── Portfolio ─────────────────────────────────────────────

    @app.route("/portfolio/<address>", methods=["GET"])
    def get_portfolio(address):
        balance = blockchain.state.get_balance(address)
        nonce = blockchain.state.get_nonce(address)
        portfolio = reserve_ledger.get_depositor_portfolio(address)
        portfolio["balance"] = balance
        portfolio["nonce"] = nonce
        return jsonify(portfolio)

    # ── Wallets ───────────────────────────────────────────────

    @app.route("/wallets", methods=["POST"])
    def create_wallet():
        data = request.get_json() or {}
        name = data.get("name", "").strip()

        wallet = Wallet.create()

        if not name:
            name = wallet.address[2:10]

        # Save encrypted wallet (use name as passphrase for PoC)
        wallet_dir = config.wallet_dir
        os.makedirs(wallet_dir, exist_ok=True)
        filepath = os.path.join(wallet_dir, f"{name}.json")
        wallet.save_encrypted(filepath, name)

        return jsonify({
            "address": wallet.address,
            "public_key": wallet.public_key,
            "private_key": wallet.private_key,
            "name": name,
        }), 201

    @app.route("/wallets", methods=["GET"])
    def list_wallets():
        import json as _json

        wallet_dir = config.wallet_dir
        wallets = []

        if os.path.isdir(wallet_dir):
            for filename in sorted(os.listdir(wallet_dir)):
                if not filename.endswith(".json"):
                    continue
                filepath = os.path.join(wallet_dir, filename)
                try:
                    with open(filepath, "r") as f:
                        wdata = _json.load(f)
                    wallets.append({
                        "name": filename[:-5],  # strip .json
                        "address": wdata.get("address", ""),
                    })
                except Exception:
                    logger.warning("Skipping malformed wallet file: %s", filename, exc_info=True)
                    continue

        return jsonify({"wallets": wallets})

    # ── Transactions by address ──────────────────────────────

    @app.route("/transactions/<address>", methods=["GET"])
    def get_transactions(address):
        txs = []
        for block in blockchain.chain[1:]:  # skip genesis
            for tx in block.transactions:
                if tx.sender == address or tx.recipient == address:
                    txs.append({
                        **tx.to_dict(),
                        "block_index": block.header.index,
                        "block_timestamp": block.header.timestamp,
                    })
        return jsonify({"address": address, "transactions": txs})

    # ── Trading: Orders ──────────────────────────────────────

    @app.route("/orders", methods=["POST"])
    def place_order():
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400

        required_base = ["side", "address", "price", "amount", "public_key"]
        for f in required_base:
            if f not in data:
                return jsonify({"error": f"Missing field: {f}"}), 400

        private_key = data.get("private_key", "")

        # If no signature provided, sign server-side using private_key (PoC)
        if not data.get("signature") and private_key:
            try:
                order = Order.from_dict({**data, "signature": ""})
                order.sign(private_key)
            except Exception as e:
                return jsonify({"error": f"Failed to sign order: {e}"}), 400
        else:
            if not data.get("signature"):
                return jsonify({"error": "Missing field: signature"}), 400
            try:
                order = Order.from_dict(data)
            except (KeyError, ValueError) as e:
                return jsonify({"error": f"Invalid order: {e}"}), 400

        if not order.verify():
            return jsonify({"error": "Invalid order signature"}), 400

        # Balance check for sell orders
        if order.side == OrderSide.SELL:
            balance = blockchain.state.get_balance(order.address)
            if balance < order.amount:
                return jsonify({"error": "Insufficient balance for sell order"}), 400

        # Store private key for settlement signing (PoC: in-memory only)
        if private_key:
            order._private_key = private_key

        try:
            trades = matching_engine.process_order(order)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

        return jsonify({
            "order_id": order.order_id,
            "status": order.status.value,
            "trades": [t.to_dict() for t in trades],
        }), 201

    @app.route("/orders/<order_id>", methods=["DELETE"])
    def cancel_order(order_id):
        data = request.get_json() or {}
        address = data.get("address", "")
        if not address:
            return jsonify({"error": "address is required"}), 400

        error = order_book.cancel_order(order_id, address)
        if error:
            return jsonify({"error": error}), 400

        return jsonify({"order_id": order_id, "status": "CANCELLED"})

    @app.route("/orders", methods=["GET"])
    def list_orders():
        address = request.args.get("address")
        orders = order_book.get_open_orders(address=address)
        return jsonify({
            "orders": [o.to_dict() for o in orders],
            "count": len(orders),
        })

    @app.route("/orders/book", methods=["GET"])
    def get_order_book():
        return jsonify(order_book.to_dict())

    # ── Trading: Trades ──────────────────────────────────────

    @app.route("/trades", methods=["GET"])
    def get_trades():
        limit = request.args.get("limit", 50, type=int)
        trades = matching_engine.get_trades(limit=limit)
        return jsonify({"trades": trades, "count": len(trades)})

    @app.route("/trades/<address>", methods=["GET"])
    def get_trades_by_address(address):
        limit = request.args.get("limit", 50, type=int)
        trades = matching_engine.get_trades(limit=limit, address=address)
        return jsonify({"address": address, "trades": trades, "count": len(trades)})

    # ── Trading: Market ──────────────────────────────────────

    @app.route("/market/summary", methods=["GET"])
    def market_summary():
        return jsonify(matching_engine.get_market_summary())

    return app
