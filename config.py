"""Network configuration for the Gold Tokenization blockchain."""

from dataclasses import dataclass, field
from typing import List


@dataclass
class NetworkConfig:
    """Configuration parameters for the blockchain network."""

    # Network identity
    network_id: str = "gold-mainnet"
    network_name: str = "Gold Tokenization Network"

    # Token
    token_name: str = "Aurum Token"
    token_symbol: str = "AUT"
    token_decimals: int = 4  # 0.0001 gram precision

    # Block parameters
    block_time_seconds: int = 10
    max_transactions_per_block: int = 100
    genesis_timestamp: float = 0.0

    # Consensus
    consensus_type: str = "poa"  # "poa" or "pow"
    pow_difficulty: int = 4  # leading zeros for PoW (if used)

    # Validators (PoA)
    validators: List[str] = field(default_factory=list)

    # Network
    default_port: int = 5100
    max_peers: int = 50
    sync_interval_seconds: int = 30

    # Mempool
    mempool_max_size: int = 5000
    mempool_tx_timeout_seconds: int = 3600

    # Paths
    chain_data_dir: str = "data"
    wallet_dir: str = "wallets"

    # Mining reward (in AUT) — set to 0 for pure gold-backed model
    mining_reward: float = 0.0


# Singleton default config
DEFAULT_CONFIG = NetworkConfig()
