"""Query the blockchain state via CLI."""

import argparse
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests


def pp(data):
    """Pretty-print JSON data."""
    print(json.dumps(data, indent=2))


def main():
    parser = argparse.ArgumentParser(description="Query blockchain state")
    sub = parser.add_subparsers(dest="command", required=True)

    # chain
    chain_p = sub.add_parser("chain", help="Show full chain")
    chain_p.add_argument("--node", default="http://127.0.0.1:5100")

    # block
    block_p = sub.add_parser("block", help="Show specific block")
    block_p.add_argument("index", type=int)
    block_p.add_argument("--node", default="http://127.0.0.1:5100")

    # balance
    bal_p = sub.add_parser("balance", help="Show address balance")
    bal_p.add_argument("address", type=str)
    bal_p.add_argument("--node", default="http://127.0.0.1:5100")

    # token
    token_p = sub.add_parser("token", help="Show token info")
    token_p.add_argument("--node", default="http://127.0.0.1:5100")

    # reserves
    res_p = sub.add_parser("reserves", help="Show reserve proofs")
    res_p.add_argument("--node", default="http://127.0.0.1:5100")

    # mempool
    mem_p = sub.add_parser("mempool", help="Show pending transactions")
    mem_p.add_argument("--node", default="http://127.0.0.1:5100")

    # peers
    peer_p = sub.add_parser("peers", help="Show connected peers")
    peer_p.add_argument("--node", default="http://127.0.0.1:5100")

    # health
    health_p = sub.add_parser("health", help="Show node health")
    health_p.add_argument("--node", default="http://127.0.0.1:5100")

    args = parser.parse_args()

    endpoints = {
        "chain": "/chain",
        "block": f"/blocks/{getattr(args, 'index', 0)}",
        "balance": f"/balance/{getattr(args, 'address', '')}",
        "token": "/token/info",
        "reserves": "/reserves",
        "mempool": "/mempool",
        "peers": "/nodes",
        "health": "/health",
    }

    url = f"{args.node}{endpoints[args.command]}"

    try:
        resp = requests.get(url, timeout=10)
        pp(resp.json())
    except requests.RequestException as e:
        print(f"ERROR: Could not connect to {args.node}: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
