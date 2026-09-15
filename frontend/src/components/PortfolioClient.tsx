'use client';

import { useState, useCallback, useEffect, useRef } from 'react';
import { TopBar } from './TopBar';

// ── Types ────────────────────────────────────────────────────────

interface ReserveProof {
  proof_id: string;
  custodian: string;
  amount_grams: number;
  purity: number;
  certificate_ref: string;
  timestamp: number;
  verified: boolean;
  depositor_address: string;
}

interface TransactionRecord {
  tx_type: string;
  sender: string;
  recipient: string;
  amount: number;
  timestamp: number;
  tx_hash: string;
  block_index: number;
  block_timestamp: number;
}

interface PortfolioData {
  address: string;
  balance: number;
  nonce: number;
  reserved_grams: number;
  total_minted: number;
  mint_capacity: number;
  reserves: ReserveProof[];
  transactions: TransactionRecord[];
}

// ── Helpers ──────────────────────────────────────────────────────

function formatNumber(n: number, decimals = 4): string {
  return n.toLocaleString('en-US', { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

function formatTimestamp(ts: number): string {
  if (!ts) return '-';
  return new Date(ts * 1000).toLocaleString('en-US', {
    month: 'short', day: 'numeric', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });
}

function txTypeColor(txType: string): string {
  switch (txType) {
    case 'MINT': return '#4ade80';
    case 'BURN': return '#f87171';
    case 'TRANSFER': return '#60a5fa';
    default: return '#7a869a';
  }
}

function txTypeBg(txType: string): string {
  switch (txType) {
    case 'MINT': return 'bg-[#0d2818]';
    case 'BURN': return 'bg-[#2a1215]';
    case 'TRANSFER': return 'bg-[#111d33]';
    default: return 'bg-[#111823]';
  }
}

const MONO = { fontFamily: "'IBM Plex Mono', monospace" } as const;

// ── Main component ───────────────────────────────────────────────

export function PortfolioClient({ initialAddress }: { initialAddress?: string } = {}) {
  const [address, setAddress] = useState(initialAddress || '');
  const [data, setData] = useState<PortfolioData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const didAutoFetch = useRef(false);

  const fetchPortfolio = useCallback(async (overrideAddress?: string) => {
    const trimmed = (overrideAddress ?? address).trim();
    if (!trimmed) return;

    setLoading(true);
    setError('');
    setData(null);

    try {
      const res = await fetch(`/api/vault/portfolio?address=${encodeURIComponent(trimmed)}`);
      if (!res.ok) {
        const err = await res.json().catch(() => ({ error: 'Failed to fetch' }));
        throw new Error(err.error || 'Failed to fetch portfolio');
      }
      const portfolio: PortfolioData = await res.json();
      setData(portfolio);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Connection error');
    } finally {
      setLoading(false);
    }
  }, [address]);

  // Auto-fetch when initialAddress is provided
  useEffect(() => {
    if (initialAddress && !didAutoFetch.current) {
      didAutoFetch.current = true;
      fetchPortfolio(initialAddress);
    }
  }, [initialAddress, fetchPortfolio]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter') fetchPortfolio();
  }, [fetchPortfolio]);

  // Derived
  const mintedPercent = data && data.reserved_grams > 0
    ? Math.min(100, (data.total_minted / data.reserved_grams) * 100)
    : 0;

  return (
    <div className="flex flex-col h-screen bg-[#0a0e14]">
      <TopBar />

      <div className="flex-1 overflow-auto">
        <div className="max-w-[1400px] mx-auto px-6 py-6">

          {/* Header */}
          <div className="mb-6">
            <h1 className="text-[20px] font-bold text-[#e6edf7]" style={MONO}>
              Client Portfolio
            </h1>
            <p className="text-[12px] text-[#5b6577] mt-0.5">
              View per-client gold reserves, AUT balance, and transaction history
            </p>
          </div>

          {/* Address input bar */}
          <div className="flex gap-3 mb-6">
            <input
              type="text"
              value={address}
              onChange={e => setAddress(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Enter wallet address (e.g. 0x...)"
              className="flex-1 px-4 py-2.5 bg-[#0c1018] border border-[#232c3c] rounded-lg text-[13px] text-[#dbe4f0] placeholder-[#3d4654] focus:outline-none focus:border-[#45c4b0] transition-colors"
              style={MONO}
            />
            <button
              onClick={fetchPortfolio}
              disabled={loading || !address.trim()}
              className="px-6 py-2.5 bg-[#45c4b0] hover:bg-[#3aad9c] text-[#0a0e14] font-semibold text-[13px] rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
              style={MONO}
            >
              {loading && (
                <div className="w-3.5 h-3.5 border-2 border-[#0a0e14] border-t-transparent rounded-full animate-spin" />
              )}
              {loading ? 'Loading...' : 'View Portfolio'}
            </button>
          </div>

          {/* Error state */}
          {error && (
            <div className="px-4 py-3 mb-6 bg-[#2a1215] border border-[#dc2626]/30 rounded-lg">
              <p className="text-[12px] text-[#f87171]" style={MONO}>{error}</p>
            </div>
          )}

          {/* Empty state */}
          {!data && !loading && !error && (
            <div className="flex items-center justify-center py-24">
              <div className="text-center">
                <div className="text-[48px] mb-3 opacity-20">&#x2B21;</div>
                <p className="text-[13px] text-[#5b6577]">Enter a wallet address to view its portfolio</p>
              </div>
            </div>
          )}

          {/* Loading spinner */}
          {loading && (
            <div className="flex items-center justify-center py-24">
              <div className="text-center">
                <div className="w-8 h-8 border-2 border-[#45c4b0] border-t-transparent rounded-full animate-spin mx-auto mb-3" />
                <span className="text-[12px] text-[#5b6577]" style={MONO}>
                  Fetching portfolio...
                </span>
              </div>
            </div>
          )}

          {/* Portfolio data */}
          {data && !loading && (
            <>
              {/* Metric cards */}
              <div className="grid grid-cols-4 gap-3 mb-6">
                <MetricCard label="My Gold Reserved" value={`${formatNumber(data.reserved_grams)} g`} accent="#d4a017" />
                <MetricCard label="AUT Balance" value={`${formatNumber(data.balance)} AUT`} accent="#45c4b0" />
                <MetricCard label="Total Minted" value={`${formatNumber(data.total_minted)} AUT`} accent="#3b82f6" />
                <MetricCard label="Mint Capacity" value={`${formatNumber(data.mint_capacity)} AUT`} accent="#22c55e" />
              </div>

              {/* Tokenization progress bar */}
              <div className="mb-6 px-4 py-3 bg-[#0c1018] border border-[#1e2736] rounded-lg">
                <div className="flex justify-between text-[10px] mb-1.5" style={MONO}>
                  <span className="text-[#7a869a]">Tokenization progress</span>
                  <span className="text-[#9fb0c6]">
                    {data.reserved_grams > 0 ? `${mintedPercent.toFixed(1)}%` : '0%'} minted
                  </span>
                </div>
                <div className="h-2.5 bg-[#111823] rounded-full overflow-hidden">
                  <div
                    className="h-full rounded-full transition-all duration-500"
                    style={{
                      width: `${mintedPercent}%`,
                      background: 'linear-gradient(90deg, #3b82f6, #45c4b0)',
                    }}
                  />
                </div>
                <div className="flex justify-between text-[10px] mt-1" style={MONO}>
                  <span className="text-[#3d4654]">{formatNumber(data.total_minted)} AUT minted</span>
                  <span className="text-[#3d4654]">{formatNumber(data.reserved_grams)} g reserved</span>
                </div>
              </div>

              {/* Two-column layout */}
              <div className="grid grid-cols-[1fr_1fr] gap-6">

                {/* Left: My Reserves */}
                <div className="bg-[#0c1018] border border-[#1e2736] rounded-lg overflow-hidden">
                  <div className="flex items-center justify-between px-4 py-3 border-b border-[#1e2736]">
                    <h2 className="text-[13px] font-semibold text-[#e6edf7]" style={MONO}>My Reserves</h2>
                    <span className="text-[10px] text-[#5b6577] px-2 py-0.5 bg-[#111823] rounded-full" style={MONO}>
                      {data.reserves.length} proof{data.reserves.length !== 1 ? 's' : ''}
                    </span>
                  </div>

                  {data.reserves.length === 0 ? (
                    <div className="px-4 py-12 text-center">
                      <div className="text-[28px] mb-2 opacity-30">&#x2B21;</div>
                      <p className="text-[12px] text-[#5b6577]">No gold reserves for this address</p>
                    </div>
                  ) : (
                    <div className="max-h-[420px] overflow-auto">
                      <table className="w-full">
                        <thead>
                          <tr className="text-[10px] text-[#5b6577] border-b border-[#1e2736]" style={MONO}>
                            <th className="text-left px-4 py-2 font-medium">Custodian</th>
                            <th className="text-right px-4 py-2 font-medium">Gold (g)</th>
                            <th className="text-right px-4 py-2 font-medium">Purity</th>
                            <th className="text-right px-4 py-2 font-medium">Effective</th>
                            <th className="text-left px-4 py-2 font-medium">Date</th>
                          </tr>
                        </thead>
                        <tbody>
                          {data.reserves.map((r) => (
                            <tr key={r.proof_id} className="border-b border-[#111823] hover:bg-[#111823] transition-colors">
                              <td className="px-4 py-2.5 text-[12px] text-[#dbe4f0]" style={MONO}>{r.custodian}</td>
                              <td className="px-4 py-2.5 text-[12px] text-[#d4a017] text-right" style={MONO}>{formatNumber(r.amount_grams)}</td>
                              <td className="px-4 py-2.5 text-[12px] text-[#7a869a] text-right" style={MONO}>{r.purity}</td>
                              <td className="px-4 py-2.5 text-[12px] text-[#45c4b0] text-right" style={MONO}>{formatNumber(r.amount_grams * r.purity)}</td>
                              <td className="px-4 py-2.5 text-[11px] text-[#5b6577] whitespace-nowrap">{formatTimestamp(r.timestamp)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>

                {/* Right: Transaction History */}
                <div className="bg-[#0c1018] border border-[#1e2736] rounded-lg overflow-hidden">
                  <div className="flex items-center justify-between px-4 py-3 border-b border-[#1e2736]">
                    <h2 className="text-[13px] font-semibold text-[#e6edf7]" style={MONO}>Transaction History</h2>
                    <span className="text-[10px] text-[#5b6577] px-2 py-0.5 bg-[#111823] rounded-full" style={MONO}>
                      {data.transactions.length} tx{data.transactions.length !== 1 ? 's' : ''}
                    </span>
                  </div>

                  {data.transactions.length === 0 ? (
                    <div className="px-4 py-12 text-center">
                      <div className="text-[28px] mb-2 opacity-30">&#x21C4;</div>
                      <p className="text-[12px] text-[#5b6577]">No transactions for this address</p>
                    </div>
                  ) : (
                    <div className="max-h-[420px] overflow-auto">
                      <div className="divide-y divide-[#111823]">
                        {data.transactions.map((tx) => (
                          <div key={tx.tx_hash} className="px-4 py-3 hover:bg-[#111823] transition-colors">
                            <div className="flex items-center justify-between mb-1.5">
                              <span
                                className={`text-[10px] font-semibold px-2 py-0.5 rounded ${txTypeBg(tx.tx_type)}`}
                                style={{ ...MONO, color: txTypeColor(tx.tx_type) }}
                              >
                                {tx.tx_type}
                              </span>
                              <span className="text-[10px] text-[#3d4654]" style={MONO}>
                                Block #{tx.block_index}
                              </span>
                            </div>
                            <div className="flex items-center justify-between">
                              <span className="text-[12px] font-semibold" style={{ ...MONO, color: txTypeColor(tx.tx_type) }}>
                                {tx.tx_type === 'BURN' ? '-' : tx.tx_type === 'TRANSFER' && tx.sender === data.address ? '-' : '+'}
                                {formatNumber(tx.amount)} AUT
                              </span>
                              <span className="text-[10px] text-[#5b6577]" style={MONO}>
                                {tx.tx_hash.slice(0, 10)}...
                              </span>
                            </div>
                            {tx.tx_type === 'TRANSFER' && (
                              <p className="text-[10px] text-[#5b6577] mt-1" style={MONO}>
                                {tx.sender === data.address
                                  ? `To: ${tx.recipient.slice(0, 14)}...`
                                  : `From: ${tx.sender.slice(0, 14)}...`
                                }
                              </p>
                            )}
                            <p className="text-[10px] text-[#3d4654] mt-0.5">
                              {formatTimestamp(tx.block_timestamp)}
                            </p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Sub-components ───────────────────────────────────────────────

function MetricCard({ label, value, accent }: { label: string; value: string; accent: string }) {
  return (
    <div className="bg-[#0c1018] border border-[#1e2736] rounded-lg px-4 py-3">
      <p className="text-[10px] text-[#5b6577] mb-1.5 uppercase tracking-wider" style={MONO}>{label}</p>
      <p className="text-[18px] font-bold" style={{ ...MONO, color: accent }}>{value}</p>
    </div>
  );
}
