"""Spin up N local blockchain nodes and register them as peers."""

import argparse
import logging
import sys
import threading
import time

# Ensure project root is on sys.path
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
from config import NetworkConfig
from logging_config import setup_logging
from network.node import create_node

logger = logging.getLogger(__name__)


def start_node(host: str, port: int, config: NetworkConfig) -> None:
    """Start a single Flask node in a thread."""
    app = create_node(host=host, port=port, config=config)
    app.run(host=host, port=port, debug=False, use_reloader=False)


def wait_for_node(url: str, timeout: int = 10) -> bool:
    """Wait for a node to become responsive."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            resp = requests.get(f"{url}/health", timeout=2)
            if resp.status_code == 200:
                return True
        except requests.RequestException:
            pass
        time.sleep(0.5)
    return False


def register_peers(node_urls: list) -> None:
    """Register all nodes with each other."""
    for i, url in enumerate(node_urls):
        for j, peer_url in enumerate(node_urls):
            if i != j:
                try:
                    requests.post(
                        f"{url}/nodes/register",
                        json={"node_url": peer_url},
                        timeout=5,
                    )
                except requests.RequestException:
                    logger.warning("Failed to register %s with %s", peer_url, url)
                    print(f"  Warning: Failed to register {peer_url} with {url}")


def main():
    setup_logging()

    parser = argparse.ArgumentParser(description="Start a local blockchain network")
    parser.add_argument("--nodes", type=int, default=3, help="Number of nodes")
    parser.add_argument("--base-port", type=int, default=5100, help="Base port number")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host address")
    args = parser.parse_args()

    node_urls = []
    validators = []

    # Create validator addresses (for PoA, we use node URLs as identifiers)
    for i in range(args.nodes):
        port = args.base_port + i
        url = f"http://{args.host}:{port}"
        node_urls.append(url)
        validators.append(f"validator-{i}")

    config = NetworkConfig(validators=validators)

    print(f"Starting {args.nodes} nodes on ports {args.base_port}-{args.base_port + args.nodes - 1}")
    print()

    # Start each node in a thread
    threads = []
    for i, url in enumerate(node_urls):
        port = args.base_port + i
        t = threading.Thread(
            target=start_node,
            args=(args.host, port, config),
            daemon=True,
        )
        t.start()
        threads.append(t)

    # Wait for all nodes to be ready
    print("Waiting for nodes to start...")
    for url in node_urls:
        if not wait_for_node(url):
            logger.error("Node %s failed to start", url)
            print(f"  ERROR: Node {url} failed to start")
            sys.exit(1)
        print(f"  {url} ready")

    # Register peers
    print("\nRegistering peers...")
    register_peers(node_urls)
    print("  Peer registration complete")

    # Print summary
    print(f"\n{'='*50}")
    print(f"Network running with {args.nodes} nodes")
    print(f"Validators: {validators}")
    for url in node_urls:
        print(f"  {url}")
    print(f"{'='*50}")
    print("\nPress Ctrl+C to stop the network")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...")


if __name__ == "__main__":
    main()
