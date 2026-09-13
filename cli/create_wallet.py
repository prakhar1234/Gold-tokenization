"""Generate a new encrypted wallet."""

import argparse
import getpass
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wallet.wallet import Wallet
from config import DEFAULT_CONFIG


def main():
    parser = argparse.ArgumentParser(description="Create a new wallet")
    parser.add_argument("--name", type=str, default=None, help="Wallet name (for filename)")
    parser.add_argument("--dir", type=str, default=DEFAULT_CONFIG.wallet_dir, help="Wallet directory")
    parser.add_argument("--no-encrypt", action="store_true", help="Save unencrypted (for testing)")
    args = parser.parse_args()

    wallet = Wallet.create()

    print(f"New wallet created:")
    print(f"  Address:    {wallet.address}")
    print(f"  Public Key: {wallet.public_key[:32]}...")

    if args.no_encrypt:
        # Save as plaintext JSON (testing only)
        import json
        os.makedirs(args.dir, exist_ok=True)
        name = args.name or wallet.address[2:10]
        filepath = os.path.join(args.dir, f"{name}.json")
        with open(filepath, "w") as f:
            json.dump({
                "private_key": wallet.private_key,
                "public_key": wallet.public_key,
                "address": wallet.address,
            }, f, indent=2)
        print(f"  Saved to:   {filepath} (UNENCRYPTED)")
    else:
        password = getpass.getpass("Enter encryption password: ")
        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            print("ERROR: Passwords do not match")
            sys.exit(1)

        os.makedirs(args.dir, exist_ok=True)
        name = args.name or wallet.address[2:10]
        filepath = os.path.join(args.dir, f"{name}.json")
        wallet.save_encrypted(filepath, password)
        print(f"  Saved to:   {filepath} (encrypted)")

    print(f"\n  IMPORTANT: Back up your wallet file and remember your password!")


if __name__ == "__main__":
    main()
