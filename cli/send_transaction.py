"""Submit transactions via CLI."""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
from blockchain.transaction import Transaction, TransactionType
from wallet.wallet import Wallet


def load_wallet(filepath: str, password: str = None) -> Wallet:
    """Load a wallet from file."""
    with open(filepath, "r") as f:
        data = json.load(f)

    # Check if encrypted (has 'ciphertext' field)
    if "ciphertext" in data:
        if not password:
            import getpass
            password = getpass.getpass("Wallet password: ")
        wallet = Wallet.load_encrypted(filepath, password)
        if wallet is None:
            print("ERROR: Failed to decrypt wallet")
            sys.exit(1)
        return wallet
    else:
        return Wallet(
            private_key=data["private_key"],
            public_key=data["public_key"],
            address=data["address"],
        )


def get_nonce(node_url: str, address: str) -> int:
    """Get current nonce for an address from a node."""
    resp = requests.get(f"{node_url}/balance/{address}", timeout=5)
    return resp.json().get("nonce", 0)


def main():
    parser = argparse.ArgumentParser(description="Send a transaction")
    parser.add_argument("--type", choices=["mint", "transfer", "burn"], required=True)
    parser.add_argument("--wallet", type=str, required=True, help="Path to wallet file")
    parser.add_argument("--recipient", type=str, default="", help="Recipient address")
    parser.add_argument("--amount", type=float, required=True, help="Amount in AUT")
    parser.add_argument("--node", type=str, default="http://127.0.0.1:5100", help="Node URL")
    parser.add_argument("--password", type=str, default=None, help="Wallet password")
    args = parser.parse_args()

    wallet = load_wallet(args.wallet, args.password)

    tx_type = TransactionType(args.type.upper())

    if tx_type == TransactionType.TRANSFER and not args.recipient:
        print("ERROR: --recipient required for TRANSFER")
        sys.exit(1)

    # Get nonce from chain
    if tx_type in (TransactionType.TRANSFER, TransactionType.BURN):
        nonce = get_nonce(args.node, wallet.address)
    else:
        nonce = 0

    # Build transaction
    recipient = args.recipient if tx_type == TransactionType.TRANSFER else (
        "BURN" if tx_type == TransactionType.BURN else args.recipient
    )
    sender = "NETWORK" if tx_type == TransactionType.MINT else wallet.address

    tx = Transaction(
        tx_type=tx_type,
        sender=sender,
        recipient=recipient,
        amount=args.amount,
        nonce=nonce,
        public_key=wallet.public_key,
    )
    tx.sign(wallet.private_key)

    # Submit to node
    resp = requests.post(
        f"{args.node}/transactions",
        json=tx.to_dict(),
        timeout=10,
    )

    result = resp.json()
    if resp.status_code == 201:
        print(f"Transaction submitted: {result.get('tx_hash')}")
    else:
        print(f"ERROR: {result.get('error')}")
        sys.exit(1)


if __name__ == "__main__":
    main()
