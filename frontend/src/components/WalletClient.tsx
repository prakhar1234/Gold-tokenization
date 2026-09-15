'use client';

import { useState, useCallback, useEffect } from 'react';
import Link from 'next/link';
import { TopBar } from './TopBar';

// ── Types ────────────────────────────────────────────────────────

interface WalletInfo {
  address: string;
  public_key: string;
  private_key: string;
  name: string;
}

interface WalletEntry {
  name: string;
  address: string;
}

// ── Helpers ──────────────────────────────────────────────────────

const MONO = { fontFamily: "'IBM Plex Mono', monospace" } as const;

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(async () => {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }, [text]);

  return (
    <button
      onClick={handleCopy}
      className="ml-2 px-2 py-0.5 text-[10px] rounded border transition-colors"
      style={{
        ...MONO,
        borderColor: copied ? '#45c4b0' : '#232c3c',
        color: copied ? '#45c4b0' : '#7a869a',
        backgroundColor: copied ? '#45c4b0' + '10' : 'transparent',
      }}
    >
      {copied ? 'Copied' : 'Copy'}
    </button>
  );
}

// ── Main component ───────────────────────────────────────────────

export function WalletClient() {
  const [walletName, setWalletName] = useState('');
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState('');
  const [createdWallet, setCreatedWallet] = useState<WalletInfo | null>(null);
  const [wallets, setWallets] = useState<WalletEntry[]>([]);
  const [loadingList, setLoadingList] = useState(true);

  const fetchWallets = useCallback(async () => {
    setLoadingList(true);
    try {
      const res = await fetch('/api/vault/wallets');
      if (res.ok) {
        const data = await res.json();
        setWallets(data.wallets || []);
      }
    } catch {
      // silently fail — list is non-critical
    } finally {
      setLoadingList(false);
    }
  }, []);

  useEffect(() => {
    fetchWallets();
  }, [fetchWallets]);

  const handleCreate = useCallback(async () => {
    setCreating(true);
    setError('');
    setCreatedWallet(null);

    try {
      const res = await fetch('/api/vault/wallets', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: walletName.trim() || undefined }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ error: 'Failed to create wallet' }));
        throw new Error(err.error || 'Failed to create wallet');
      }

      const data: WalletInfo = await res.json();
      setCreatedWallet(data);
      setWalletName('');
      // Refresh wallet list
      fetchWallets();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Connection error');
    } finally {
      setCreating(false);
    }
  }, [walletName, fetchWallets]);

  const handleDownload = useCallback(() => {
    if (!createdWallet) return;

    const blob = new Blob(
      [JSON.stringify({
        address: createdWallet.address,
        public_key: createdWallet.public_key,
        private_key: createdWallet.private_key,
        name: createdWallet.name,
      }, null, 2)],
      { type: 'application/json' }
    );
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `wallet-${createdWallet.name}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }, [createdWallet]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter') handleCreate();
  }, [handleCreate]);

  return (
    <div className="flex flex-col h-screen bg-[#0a0e14]">
      <TopBar />

      <div className="flex-1 overflow-auto">
        <div className="max-w-[1400px] mx-auto px-6 py-6">

          {/* Header */}
          <div className="mb-6">
            <h1 className="text-[20px] font-bold text-[#e6edf7]" style={MONO}>
              Wallets
            </h1>
            <p className="text-[12px] text-[#5b6577] mt-0.5">
              Create and manage ECDSA wallets for the AUT tokenization network
            </p>
          </div>

          {/* Create Wallet */}
          <div className="mb-6 bg-[#0c1018] border border-[#1e2736] rounded-lg p-5">
            <h2 className="text-[13px] font-semibold text-[#e6edf7] mb-3" style={MONO}>
              Create New Wallet
            </h2>
            <div className="flex gap-3">
              <input
                type="text"
                value={walletName}
                onChange={e => setWalletName(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Wallet name (optional, e.g. alice)"
                className="flex-1 px-4 py-2.5 bg-[#0a0e14] border border-[#232c3c] rounded-lg text-[13px] text-[#dbe4f0] placeholder-[#3d4654] focus:outline-none focus:border-[#45c4b0] transition-colors"
                style={MONO}
              />
              <button
                onClick={handleCreate}
                disabled={creating}
                className="px-6 py-2.5 bg-[#45c4b0] hover:bg-[#3aad9c] text-[#0a0e14] font-semibold text-[13px] rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                style={MONO}
              >
                {creating && (
                  <div className="w-3.5 h-3.5 border-2 border-[#0a0e14] border-t-transparent rounded-full animate-spin" />
                )}
                {creating ? 'Creating...' : 'Create Wallet'}
              </button>
            </div>

            {error && (
              <div className="mt-3 px-4 py-3 bg-[#2a1215] border border-[#dc2626]/30 rounded-lg">
                <p className="text-[12px] text-[#f87171]" style={MONO}>{error}</p>
              </div>
            )}
          </div>

          {/* Key Reveal Panel */}
          {createdWallet && (
            <div className="mb-6 bg-[#0c1018] border border-[#d4a017]/30 rounded-lg overflow-hidden">
              {/* Warning banner */}
              <div className="px-5 py-3 bg-[#2a1a0a] border-b border-[#d4a017]/20">
                <p className="text-[12px] font-semibold text-[#f87171]" style={MONO}>
                  Save your private key now. It will not be shown again.
                </p>
              </div>

              <div className="p-5 space-y-4">
                {/* Name */}
                <div>
                  <label className="text-[10px] uppercase tracking-wider text-[#5b6577] mb-1 block" style={MONO}>
                    Name
                  </label>
                  <div className="flex items-center">
                    <span className="text-[13px] text-[#dbe4f0]" style={MONO}>{createdWallet.name}</span>
                  </div>
                </div>

                {/* Address */}
                <div>
                  <label className="text-[10px] uppercase tracking-wider text-[#5b6577] mb-1 block" style={MONO}>
                    Address
                  </label>
                  <div className="flex items-center">
                    <span className="text-[13px] text-[#45c4b0] break-all" style={MONO}>{createdWallet.address}</span>
                    <CopyButton text={createdWallet.address} />
                  </div>
                </div>

                {/* Public Key */}
                <div>
                  <label className="text-[10px] uppercase tracking-wider text-[#5b6577] mb-1 block" style={MONO}>
                    Public Key
                  </label>
                  <div className="flex items-center">
                    <span className="text-[12px] text-[#9fb0c6] break-all" style={MONO}>{createdWallet.public_key}</span>
                    <CopyButton text={createdWallet.public_key} />
                  </div>
                </div>

                {/* Private Key */}
                <div>
                  <label className="text-[10px] uppercase tracking-wider text-[#f87171] mb-1 block" style={MONO}>
                    Private Key
                  </label>
                  <div className="flex items-center">
                    <span className="text-[12px] text-[#d4a017] break-all" style={MONO}>{createdWallet.private_key}</span>
                    <CopyButton text={createdWallet.private_key} />
                  </div>
                </div>

                {/* Actions */}
                <div className="flex gap-3 pt-2">
                  <button
                    onClick={handleDownload}
                    className="px-5 py-2 bg-[#182233] hover:bg-[#1e2d42] border border-[#2a3a50] text-[#dbe4f0] text-[12px] rounded-lg transition-colors"
                    style={MONO}
                  >
                    Download Wallet JSON
                  </button>
                  <button
                    onClick={() => setCreatedWallet(null)}
                    className="px-5 py-2 bg-[#111823] hover:bg-[#182233] border border-[#232c3c] text-[#7a869a] text-[12px] rounded-lg transition-colors"
                    style={MONO}
                  >
                    I&apos;ve Saved My Key
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Wallet Directory */}
          <div className="bg-[#0c1018] border border-[#1e2736] rounded-lg overflow-hidden">
            <div className="flex items-center justify-between px-4 py-3 border-b border-[#1e2736]">
              <h2 className="text-[13px] font-semibold text-[#e6edf7]" style={MONO}>Wallet Directory</h2>
              <span className="text-[10px] text-[#5b6577] px-2 py-0.5 bg-[#111823] rounded-full" style={MONO}>
                {wallets.length} wallet{wallets.length !== 1 ? 's' : ''}
              </span>
            </div>

            {loadingList ? (
              <div className="flex items-center justify-center py-12">
                <div className="w-6 h-6 border-2 border-[#45c4b0] border-t-transparent rounded-full animate-spin" />
              </div>
            ) : wallets.length === 0 ? (
              <div className="px-4 py-12 text-center">
                <div className="text-[28px] mb-2 opacity-30">&#x2B21;</div>
                <p className="text-[12px] text-[#5b6577]">No wallets created yet</p>
              </div>
            ) : (
              <table className="w-full">
                <thead>
                  <tr className="text-[10px] text-[#5b6577] border-b border-[#1e2736]" style={MONO}>
                    <th className="text-left px-4 py-2 font-medium">Name</th>
                    <th className="text-left px-4 py-2 font-medium">Address</th>
                    <th className="text-right px-4 py-2 font-medium">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {wallets.map((w) => (
                    <tr key={w.address} className="border-b border-[#111823] hover:bg-[#111823] transition-colors">
                      <td className="px-4 py-2.5 text-[12px] text-[#dbe4f0]" style={MONO}>{w.name}</td>
                      <td className="px-4 py-2.5 text-[12px] text-[#45c4b0]" style={MONO}>{w.address}</td>
                      <td className="px-4 py-2.5 text-right">
                        <Link
                          href={`/portfolio?address=${encodeURIComponent(w.address)}`}
                          className="text-[11px] px-3 py-1 rounded-md bg-[#182233] hover:bg-[#1e2d42] border border-[#2a3a50] text-[#9fb0c6] hover:text-[#dbe4f0] transition-colors"
                          style={MONO}
                        >
                          View Portfolio
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

        </div>
      </div>
    </div>
  );
}
