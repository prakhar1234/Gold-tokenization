'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { TopBar } from './TopBar';

// ── Types ────────────────────────────────────────────────────────

interface NodeStatus {
  url: string;
  status: string;
  chain_height: number;
  peers: number;
  mempool_size: number;
}

interface TokenInfo {
  name: string;
  symbol: string;
  decimals: number;
  total_minted: number;
  total_burned: number;
  circulating_supply: number;
  total_reserved_grams: number;
  reserve_ratio: number;
}

interface ReserveProof {
  proof_id: string;
  custodian: string;
  amount_grams: number;
  purity: number;
  certificate_ref: string;
  timestamp: number;
  verified: boolean;
}

interface AuditSummary {
  total_reserved_grams: number;
  total_minted: number;
  total_burned: number;
  circulating_supply: number;
  reserve_ratio: number;
  num_reserves: number;
}

interface DashboardData {
  health: { status: string; chain_height: number; peers: number; mempool_size: number };
  token: TokenInfo;
  reserves: { reserves: ReserveProof[]; audit: AuditSummary };
}

interface OnboardForm {
  custodian: string;
  amount_grams: string;
  purity: string;
  certificate_ref: string;
  depositor_address: string;
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

const MONO = { fontFamily: "'IBM Plex Mono', monospace" } as const;

// ── Main component ───────────────────────────────────────────────

export function GoldVaultClient() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [nodes, setNodes] = useState<NodeStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // Onboard form
  const [showOnboard, setShowOnboard] = useState(false);
  const [form, setForm] = useState<OnboardForm>({
    custodian: '', amount_grams: '', purity: '0.999', certificate_ref: '', depositor_address: '',
  });
  const [submitting, setSubmitting] = useState(false);
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' } | null>(null);
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ── Data fetching ──────────────────────────────────────────────

  const fetchData = useCallback(async () => {
    try {
      const [dashRes, nodesRes] = await Promise.all([
        fetch('/api/vault'),
        fetch('/api/vault/nodes'),
      ]);

      if (!dashRes.ok) throw new Error('Failed to fetch dashboard data');
      if (!nodesRes.ok) throw new Error('Failed to fetch node status');

      const [dash, nodeData] = await Promise.all([
        dashRes.json(),
        nodesRes.json(),
      ]);

      setData(dash);
      setNodes(nodeData.nodes || []);
      setError('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Connection error');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 15000);
    return () => clearInterval(interval);
  }, [fetchData]);

  // ── Toast ──────────────────────────────────────────────────────

  const showToast = useCallback((message: string, type: 'success' | 'error') => {
    setToast({ message, type });
    if (toastTimer.current) clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(null), 4000);
  }, []);

  // ── Onboard gold handler ──────────────────────────────────────

  const handleOnboard = useCallback(async () => {
    if (!form.custodian.trim() || !form.amount_grams.trim()) {
      showToast('Custodian and amount are required', 'error');
      return;
    }

    const amount = parseFloat(form.amount_grams);
    if (isNaN(amount) || amount <= 0) {
      showToast('Amount must be a positive number', 'error');
      return;
    }

    const purity = parseFloat(form.purity);
    if (isNaN(purity) || purity <= 0 || purity > 1) {
      showToast('Purity must be between 0 and 1', 'error');
      return;
    }

    setSubmitting(true);
    try {
      const res = await fetch('/api/vault', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          custodian: form.custodian.trim(),
          amount_grams: amount,
          purity,
          certificate_ref: form.certificate_ref.trim(),
          depositor_address: form.depositor_address.trim(),
        }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ error: 'Failed' }));
        throw new Error(err.error || 'Failed to register reserve');
      }

      showToast(`${formatNumber(amount)} grams of gold onboarded successfully`, 'success');
      setForm({ custodian: '', amount_grams: '', purity: '0.999', certificate_ref: '', depositor_address: '' });
      setShowOnboard(false);
      fetchData();
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Failed to onboard gold', 'error');
    } finally {
      setSubmitting(false);
    }
  }, [form, showToast, fetchData]);

  // ── Derived data ──────────────────────────────────────────────

  const token = data?.token;
  const audit = data?.reserves?.audit;
  const reserves = data?.reserves?.reserves || [];
  const onlineNodes = nodes.filter(n => n.status === 'ok').length;

  // ── Render ─────────────────────────────────────────────────────

  return (
    <div className="flex flex-col h-screen bg-[#0a0e14]">
      <TopBar />

      {/* Toast */}
      {toast && (
        <div
          className={`fixed top-16 right-4 z-50 px-4 py-2.5 rounded-lg text-[12px] font-medium shadow-xl border animate-fade-in ${
            toast.type === 'success'
              ? 'bg-[#0d2818] border-[#16a34a]/30 text-[#4ade80]'
              : 'bg-[#2a1215] border-[#dc2626]/30 text-[#f87171]'
          }`}
          style={MONO}
        >
          {toast.message}
        </div>
      )}

      {/* Main content */}
      <div className="flex-1 overflow-auto">
        {loading ? (
          <div className="flex items-center justify-center h-full">
            <div className="text-center">
              <div className="w-8 h-8 border-2 border-[#45c4b0] border-t-transparent rounded-full animate-spin mx-auto mb-3" />
              <span className="text-[12px] text-[#5b6577]" style={MONO}>
                Connecting to blockchain...
              </span>
            </div>
          </div>
        ) : error && !data ? (
          <div className="flex items-center justify-center h-full">
            <div className="text-center">
              <div className="text-[32px] mb-3 opacity-30">&#x26A0;</div>
              <p className="text-[13px] text-[#7a869a] mb-4">{error}</p>
              <button
                onClick={() => { setLoading(true); fetchData(); }}
                className="px-4 py-2 bg-[#182233] border border-[#232c3c] rounded-lg text-[12px] text-[#9fb0c6] hover:bg-[#1e2d42] transition-colors"
                style={MONO}
              >
                Retry
              </button>
            </div>
          </div>
        ) : (
          <div className="max-w-[1400px] mx-auto px-6 py-6">

            {/* Header row */}
            <div className="flex items-center justify-between mb-6">
              <div>
                <h1 className="text-[20px] font-bold text-[#e6edf7]" style={MONO}>
                  Reserve Dashboard
                </h1>
                <p className="text-[12px] text-[#5b6577] mt-0.5">
                  Onboard physical gold reserves and manage AUT token supply
                </p>
              </div>
              <button
                onClick={() => setShowOnboard(true)}
                className="px-5 py-2.5 bg-[#45c4b0] hover:bg-[#3aad9c] text-[#0a0e14] font-semibold text-[13px] rounded-lg transition-colors"
                style={MONO}
              >
                + Onboard Gold
              </button>
            </div>

            {/* Network status bar */}
            <div className="flex items-center gap-2 mb-6 px-4 py-2.5 bg-[#0c1018] border border-[#1e2736] rounded-lg">
              <div className={`w-2 h-2 rounded-full ${onlineNodes > 0 ? 'bg-[#22c55e]' : 'bg-[#ef4444]'}`} />
              <span className="text-[11px] text-[#7a869a]" style={MONO}>
                {onlineNodes}/{nodes.length} nodes online
              </span>
              <span className="text-[#2a3140] mx-1">|</span>
              <span className="text-[11px] text-[#5b6577]" style={MONO}>
                Height: {data?.health?.chain_height || 0}
              </span>
              <span className="text-[#2a3140] mx-1">|</span>
              <span className="text-[11px] text-[#5b6577]" style={MONO}>
                Mempool: {data?.health?.mempool_size || 0} txs
              </span>
              <div className="flex-1" />
              {nodes.map((node, i) => (
                <div key={node.url} className="flex items-center gap-1.5" title={node.url}>
                  <div className={`w-1.5 h-1.5 rounded-full ${node.status === 'ok' ? 'bg-[#22c55e]' : 'bg-[#ef4444]'}`} />
                  <span className="text-[10px] text-[#5b6577]" style={MONO}>N{i}</span>
                </div>
              ))}
            </div>

            {/* Metric cards */}
            <div className="grid grid-cols-5 gap-3 mb-6">
              <MetricCard label="Total Gold Reserved" value={`${formatNumber(audit?.total_reserved_grams || 0)} g`} accent="#d4a017" />
              <MetricCard label="Circulating Supply" value={`${formatNumber(audit?.circulating_supply || 0)} AUT`} accent="#45c4b0" />
              <MetricCard label="Total Minted" value={`${formatNumber(audit?.total_minted || 0)} AUT`} accent="#3b82f6" />
              <MetricCard label="Total Burned" value={`${formatNumber(audit?.total_burned || 0)} AUT`} accent="#f97316" />
              <MetricCard
                label="Reserve Ratio"
                value={
                  !audit?.circulating_supply || (audit?.reserve_ratio || 0) >= 999999
                    ? '\u221E'
                    : `${formatNumber(audit?.reserve_ratio || 0, 2)}x`
                }
                accent={
                  (audit?.reserve_ratio || 0) >= 1 || !audit?.circulating_supply
                    ? '#22c55e'
                    : '#ef4444'
                }
              />
            </div>

            {/* Main content: two columns */}
            <div className="grid grid-cols-[1fr_1fr] gap-6">

              {/* Left column: Reserve ledger */}
              <div className="bg-[#0c1018] border border-[#1e2736] rounded-lg overflow-hidden">
                <div className="flex items-center justify-between px-4 py-3 border-b border-[#1e2736]">
                  <h2 className="text-[13px] font-semibold text-[#e6edf7]" style={MONO}>
                    Reserve Ledger
                  </h2>
                  <span className="text-[10px] text-[#5b6577] px-2 py-0.5 bg-[#111823] rounded-full" style={MONO}>
                    {reserves.length} proof{reserves.length !== 1 ? 's' : ''}
                  </span>
                </div>

                {reserves.length === 0 ? (
                  <div className="px-4 py-12 text-center">
                    <div className="text-[28px] mb-2 opacity-30">&#x2B21;</div>
                    <p className="text-[12px] text-[#5b6577]">No gold reserves registered</p>
                    <p className="text-[11px] text-[#3d4654] mt-1">Onboard physical gold to get started</p>
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
                          <th className="text-left px-4 py-2 font-medium">Certificate</th>
                          <th className="text-left px-4 py-2 font-medium">Date</th>
                        </tr>
                      </thead>
                      <tbody>
                        {reserves.map((r) => (
                          <tr key={r.proof_id} className="border-b border-[#111823] hover:bg-[#111823] transition-colors">
                            <td className="px-4 py-2.5 text-[12px] text-[#dbe4f0]" style={MONO}>{r.custodian}</td>
                            <td className="px-4 py-2.5 text-[12px] text-[#d4a017] text-right" style={MONO}>{formatNumber(r.amount_grams)}</td>
                            <td className="px-4 py-2.5 text-[12px] text-[#7a869a] text-right" style={MONO}>{r.purity}</td>
                            <td className="px-4 py-2.5 text-[12px] text-[#45c4b0] text-right" style={MONO}>{formatNumber(r.amount_grams * r.purity)}</td>
                            <td className="px-4 py-2.5 text-[11px] text-[#5b6577]" style={MONO}>{r.certificate_ref || '-'}</td>
                            <td className="px-4 py-2.5 text-[11px] text-[#5b6577] whitespace-nowrap">{formatTimestamp(r.timestamp)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>

              {/* Right column: Token details + Node status */}
              <div className="flex flex-col gap-4">

                {/* Token info card */}
                <div className="bg-[#0c1018] border border-[#1e2736] rounded-lg px-4 py-3">
                  <h2 className="text-[13px] font-semibold text-[#e6edf7] mb-3" style={MONO}>Token Details</h2>
                  <div className="grid grid-cols-2 gap-x-6 gap-y-2">
                    <DetailRow label="Name" value={token?.name || 'Aurum Token'} />
                    <DetailRow label="Symbol" value={token?.symbol || 'AUT'} />
                    <DetailRow label="Decimals" value={String(token?.decimals ?? 4)} />
                    <DetailRow label="Model" value="Gold-backed" />
                  </div>
                </div>

                {/* Backing analysis card */}
                <div className="bg-[#0c1018] border border-[#1e2736] rounded-lg px-4 py-3">
                  <h2 className="text-[13px] font-semibold text-[#e6edf7] mb-3" style={MONO}>Backing Analysis</h2>
                  <div className="mb-3">
                    <div className="flex justify-between text-[10px] mb-1" style={MONO}>
                      <span className="text-[#7a869a]">Gold coverage</span>
                      <span className="text-[#9fb0c6]">
                        {audit?.circulating_supply
                          ? `${Math.min(100, ((audit.total_reserved_grams / audit.circulating_supply) * 100)).toFixed(1)}%`
                          : '100%'
                        }
                      </span>
                    </div>
                    <div className="h-2 bg-[#111823] rounded-full overflow-hidden">
                      <div
                        className="h-full rounded-full transition-all duration-500"
                        style={{
                          width: audit?.circulating_supply
                            ? `${Math.min(100, (audit.total_reserved_grams / audit.circulating_supply) * 100)}%`
                            : '100%',
                          background: (audit?.reserve_ratio || 0) >= 1 || !audit?.circulating_supply
                            ? 'linear-gradient(90deg, #22c55e, #45c4b0)'
                            : 'linear-gradient(90deg, #ef4444, #f97316)',
                        }}
                      />
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-x-6 gap-y-2">
                    <DetailRow label="Reserved gold" value={`${formatNumber(audit?.total_reserved_grams || 0)} g`} />
                    <DetailRow label="Backing tokens" value={`${formatNumber(audit?.circulating_supply || 0)} AUT`} />
                    <DetailRow label="Mint capacity" value={`${formatNumber(Math.max(0, (audit?.total_reserved_grams || 0) - (audit?.circulating_supply || 0)))} AUT`} />
                    <DetailRow label="Reserve proofs" value={String(audit?.num_reserves || 0)} />
                  </div>
                </div>

                {/* Node grid */}
                <div className="bg-[#0c1018] border border-[#1e2736] rounded-lg px-4 py-3">
                  <h2 className="text-[13px] font-semibold text-[#e6edf7] mb-3" style={MONO}>Network Nodes</h2>
                  <div className="grid gap-2">
                    {nodes.map((node, i) => (
                      <div key={node.url} className="flex items-center justify-between px-3 py-2 bg-[#111823] rounded-md">
                        <div className="flex items-center gap-2">
                          <div className={`w-2 h-2 rounded-full ${node.status === 'ok' ? 'bg-[#22c55e]' : 'bg-[#ef4444]'}`} />
                          <span className="text-[11px] text-[#9fb0c6]" style={MONO}>Node {i}</span>
                        </div>
                        <div className="flex items-center gap-4">
                          <span className="text-[10px] text-[#5b6577]" style={MONO}>H:{node.chain_height}</span>
                          <span className="text-[10px] text-[#5b6577]" style={MONO}>P:{node.peers}</span>
                          <span
                            className={`text-[10px] px-1.5 py-0.5 rounded ${
                              node.status === 'ok'
                                ? 'bg-[#0d2818] text-[#4ade80]'
                                : 'bg-[#2a1215] text-[#f87171]'
                            }`}
                            style={MONO}
                          >
                            {node.status === 'ok' ? 'ONLINE' : 'OFFLINE'}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Onboard Gold Modal */}
      {showOnboard && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="absolute inset-0 bg-black/60 animate-fade-in" onClick={() => !submitting && setShowOnboard(false)} />
          <div className="relative w-full max-w-lg bg-[#0c1018] border border-[#232c3c] rounded-xl shadow-2xl p-6 mx-4 animate-slide-up">

            <button
              onClick={() => !submitting && setShowOnboard(false)}
              className="absolute right-4 top-4 text-[#5b6577] hover:text-[#9fb0c6] transition-colors"
              disabled={submitting}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M18 6 6 18" /><path d="m6 6 12 12" />
              </svg>
            </button>

            <h2 className="text-[16px] font-bold text-[#e6edf7] mb-1" style={MONO}>Onboard Physical Gold</h2>
            <p className="text-[12px] text-[#5b6577] mb-6">
              Register a new gold reserve proof. This makes the gold available for backing AUT token minting.
            </p>

            <div className="space-y-4">
              <FormField label="Custodian" required>
                <input
                  type="text"
                  value={form.custodian}
                  onChange={e => setForm(f => ({ ...f, custodian: e.target.value }))}
                  placeholder="e.g. Fort Knox Vault A"
                  disabled={submitting}
                  className="w-full px-3 py-2.5 bg-[#111823] border border-[#232c3c] rounded-lg text-[13px] text-[#dbe4f0] placeholder-[#3d4654] focus:outline-none focus:border-[#45c4b0] disabled:opacity-50 transition-colors"
                  style={MONO}
                />
              </FormField>

              <div className="grid grid-cols-2 gap-3">
                <FormField label="Gold Amount (grams)" required>
                  <input
                    type="number"
                    value={form.amount_grams}
                    onChange={e => setForm(f => ({ ...f, amount_grams: e.target.value }))}
                    placeholder="1000.0000"
                    step="0.0001"
                    min="0.0001"
                    disabled={submitting}
                    className="w-full px-3 py-2.5 bg-[#111823] border border-[#232c3c] rounded-lg text-[13px] text-[#d4a017] placeholder-[#3d4654] focus:outline-none focus:border-[#45c4b0] disabled:opacity-50 transition-colors"
                    style={MONO}
                  />
                </FormField>

                <FormField label="Purity (0-1)" required>
                  <input
                    type="number"
                    value={form.purity}
                    onChange={e => setForm(f => ({ ...f, purity: e.target.value }))}
                    placeholder="0.999"
                    step="0.001"
                    min="0.001"
                    max="1"
                    disabled={submitting}
                    className="w-full px-3 py-2.5 bg-[#111823] border border-[#232c3c] rounded-lg text-[13px] text-[#dbe4f0] placeholder-[#3d4654] focus:outline-none focus:border-[#45c4b0] disabled:opacity-50 transition-colors"
                    style={MONO}
                  />
                </FormField>
              </div>

              <FormField label="Certificate Reference" required={false}>
                <input
                  type="text"
                  value={form.certificate_ref}
                  onChange={e => setForm(f => ({ ...f, certificate_ref: e.target.value }))}
                  placeholder="e.g. GLD-2026-001"
                  disabled={submitting}
                  className="w-full px-3 py-2.5 bg-[#111823] border border-[#232c3c] rounded-lg text-[13px] text-[#dbe4f0] placeholder-[#3d4654] focus:outline-none focus:border-[#45c4b0] disabled:opacity-50 transition-colors"
                  style={MONO}
                />
              </FormField>

              <FormField label="Depositor Address" required={false}>
                <input
                  type="text"
                  value={form.depositor_address}
                  onChange={e => setForm(f => ({ ...f, depositor_address: e.target.value }))}
                  placeholder="e.g. 0x1a2b3c..."
                  disabled={submitting}
                  className="w-full px-3 py-2.5 bg-[#111823] border border-[#232c3c] rounded-lg text-[13px] text-[#dbe4f0] placeholder-[#3d4654] focus:outline-none focus:border-[#45c4b0] disabled:opacity-50 transition-colors"
                  style={MONO}
                />
              </FormField>

              {form.amount_grams && form.purity && (
                <div className="px-3 py-2.5 bg-[#111823] border border-[#1e2736] rounded-lg">
                  <div className="flex justify-between">
                    <span className="text-[11px] text-[#5b6577]" style={MONO}>Effective gold (amount x purity)</span>
                    <span className="text-[12px] text-[#45c4b0] font-semibold" style={MONO}>
                      {formatNumber(parseFloat(form.amount_grams || '0') * parseFloat(form.purity || '0'))} g
                    </span>
                  </div>
                  <div className="flex justify-between mt-1">
                    <span className="text-[11px] text-[#5b6577]" style={MONO}>New mint capacity</span>
                    <span className="text-[12px] text-[#3b82f6] font-semibold" style={MONO}>
                      +{formatNumber(parseFloat(form.amount_grams || '0') * parseFloat(form.purity || '0'))} AUT
                    </span>
                  </div>
                </div>
              )}
            </div>

            <div className="flex justify-end gap-2 mt-6">
              <button
                onClick={() => setShowOnboard(false)}
                disabled={submitting}
                className="px-4 py-2 text-[12px] text-[#7a869a] hover:text-[#9fb0c6] transition-colors disabled:opacity-50"
                style={MONO}
              >
                Cancel
              </button>
              <button
                onClick={handleOnboard}
                disabled={submitting || !form.custodian.trim() || !form.amount_grams.trim()}
                className="px-5 py-2 bg-[#45c4b0] hover:bg-[#3aad9c] text-[#0a0e14] font-semibold text-[13px] rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                style={MONO}
              >
                {submitting && (
                  <div className="w-3.5 h-3.5 border-2 border-[#0a0e14] border-t-transparent rounded-full animate-spin" />
                )}
                {submitting ? 'Registering...' : 'Register Reserve'}
              </button>
            </div>
          </div>
        </div>
      )}
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

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between items-center py-1">
      <span className="text-[11px] text-[#5b6577]" style={MONO}>{label}</span>
      <span className="text-[11px] text-[#9fb0c6] font-medium" style={MONO}>{value}</span>
    </div>
  );
}

function FormField({ label, required, children }: { label: string; required: boolean; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-[11px] text-[#7a869a] mb-1.5" style={MONO}>
        {label}
        {required && <span className="text-[#ef4444] ml-0.5">*</span>}
      </label>
      {children}
    </div>
  );
}
