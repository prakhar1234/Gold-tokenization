'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { TopBar } from './TopBar';

// ── Types ────────────────────────────────────────────────────────

interface OrderEntry {
  order_id: string;
  side: 'BUY' | 'SELL';
  address: string;
  price: number;
  amount: number;
  remaining_amount: number;
  status: string;
  timestamp: number;
}

interface TradeEntry {
  trade_id: string;
  buyer_address: string;
  seller_address: string;
  price: number;
  amount: number;
  tx_hash: string;
  timestamp: number;
}

interface MarketSummary {
  last_price: number | null;
  best_bid: number | null;
  best_ask: number | null;
  spread: number | null;
  volume_24h: number;
  trade_count: number;
}

interface TradingData {
  summary: MarketSummary;
  book: { bids: OrderEntry[]; asks: OrderEntry[]; bid_count: number; ask_count: number };
  trades: { trades: TradeEntry[]; count: number };
}

interface OrderForm {
  side: 'BUY' | 'SELL';
  price: string;
  amount: string;
  address: string;
  public_key: string;
  private_key: string;
}

// ── Helpers ──────────────────────────────────────────────────────

function formatNumber(n: number, decimals = 4): string {
  return n.toLocaleString('en-US', { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

function formatTimestamp(ts: number): string {
  if (!ts) return '-';
  return new Date(ts * 1000).toLocaleString('en-US', {
    month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  });
}

const MONO = { fontFamily: "'IBM Plex Mono', monospace" } as const;

// ── Main component ───────────────────────────────────────────────

export function TradingClient() {
  const [data, setData] = useState<TradingData | null>(null);
  const [myOrders, setMyOrders] = useState<OrderEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' } | null>(null);
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const [form, setForm] = useState<OrderForm>({
    side: 'BUY',
    price: '',
    amount: '',
    address: '',
    public_key: '',
    private_key: '',
  });

  // ── Data fetching ──────────────────────────────────────────────

  const fetchData = useCallback(async () => {
    try {
      const res = await fetch('/api/vault/trading');
      if (!res.ok) throw new Error('Failed to fetch trading data');
      const json = await res.json();
      setData(json);
      setError('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Connection error');
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchMyOrders = useCallback(async () => {
    if (!form.address) return;
    try {
      const res = await fetch(`/api/vault/trading?view=orders&address=${encodeURIComponent(form.address)}`);
      if (res.ok) {
        const json = await res.json();
        setMyOrders(json.orders || []);
      }
    } catch {
      // Silent fail for my-orders polling
    }
  }, [form.address]);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 5000);
    return () => clearInterval(interval);
  }, [fetchData]);

  useEffect(() => {
    if (form.address) fetchMyOrders();
  }, [form.address, fetchMyOrders]);

  // ── Toast ──────────────────────────────────────────────────────

  const showToast = useCallback((message: string, type: 'success' | 'error') => {
    setToast({ message, type });
    if (toastTimer.current) clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(null), 4000);
  }, []);

  // ── Place order ────────────────────────────────────────────────

  const handlePlaceOrder = useCallback(async () => {
    if (!form.address || !form.public_key || !form.private_key) {
      showToast('Address, public key, and private key are required', 'error');
      return;
    }

    const price = parseFloat(form.price);
    const amount = parseFloat(form.amount);
    if (isNaN(price) || price <= 0) {
      showToast('Price must be a positive number', 'error');
      return;
    }
    if (isNaN(amount) || amount <= 0) {
      showToast('Amount must be a positive number', 'error');
      return;
    }

    setSubmitting(true);
    try {
      // Sign the order client-side using the crypto module via a fetch to a signing endpoint
      // For the PoC, we send the private key to the backend which signs and processes
      const orderData = {
        side: form.side,
        address: form.address,
        price,
        amount,
        public_key: form.public_key,
        private_key: form.private_key,
        // order_id, timestamp, and signature will be set by the backend
      };

      // First sign the order locally by calling the orders endpoint directly
      const res = await fetch('/api/vault/trading', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(orderData),
      });

      const body = await res.json();

      if (!res.ok) {
        throw new Error(body.error || 'Failed to place order');
      }

      const tradeCount = body.trades?.length || 0;
      const statusMsg = body.status === 'FILLED'
        ? `Order filled! ${tradeCount} trade(s) executed`
        : body.status === 'PARTIALLY_FILLED'
          ? `Order partially filled. ${tradeCount} trade(s), remainder in book`
          : 'Order placed in book';

      showToast(statusMsg, 'success');
      setForm(f => ({ ...f, price: '', amount: '' }));
      fetchData();
      fetchMyOrders();
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Failed to place order', 'error');
    } finally {
      setSubmitting(false);
    }
  }, [form, showToast, fetchData, fetchMyOrders]);

  // ── Cancel order ───────────────────────────────────────────────

  const handleCancel = useCallback(async (orderId: string) => {
    try {
      const res = await fetch('/api/vault/trading', {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ order_id: orderId, address: form.address }),
      });

      const body = await res.json();
      if (!res.ok) throw new Error(body.error || 'Failed to cancel');

      showToast('Order cancelled', 'success');
      fetchData();
      fetchMyOrders();
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Cancel failed', 'error');
    }
  }, [form.address, showToast, fetchData, fetchMyOrders]);

  // ── Derived ────────────────────────────────────────────────────

  const summary = data?.summary;
  const bids = data?.book?.bids || [];
  const asks = data?.book?.asks || [];
  const trades = data?.trades?.trades || [];

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

      <div className="flex-1 overflow-auto">
        {loading ? (
          <div className="flex items-center justify-center h-full">
            <div className="text-center">
              <div className="w-8 h-8 border-2 border-[#45c4b0] border-t-transparent rounded-full animate-spin mx-auto mb-3" />
              <span className="text-[12px] text-[#5b6577]" style={MONO}>Loading trading data...</span>
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

            {/* Header */}
            <div className="mb-6">
              <h1 className="text-[20px] font-bold text-[#e6edf7]" style={MONO}>AUT / USD Trading</h1>
              <p className="text-[12px] text-[#5b6577] mt-0.5">Limit order book for gold-backed AUT tokens</p>
            </div>

            {/* Market metrics bar */}
            <div className="grid grid-cols-5 gap-3 mb-6">
              <MetricCard
                label="Last Price"
                value={summary?.last_price != null ? `$${formatNumber(summary.last_price, 2)}` : '-'}
                accent="#e6edf7"
              />
              <MetricCard
                label="Best Bid"
                value={summary?.best_bid != null ? `$${formatNumber(summary.best_bid, 2)}` : '-'}
                accent="#22c55e"
              />
              <MetricCard
                label="Best Ask"
                value={summary?.best_ask != null ? `$${formatNumber(summary.best_ask, 2)}` : '-'}
                accent="#ef4444"
              />
              <MetricCard
                label="Spread"
                value={summary?.spread != null ? `$${formatNumber(summary.spread, 2)}` : '-'}
                accent="#d4a017"
              />
              <MetricCard
                label="24h Volume"
                value={`${formatNumber(summary?.volume_24h || 0)} AUT`}
                accent="#45c4b0"
              />
            </div>

            {/* Main grid: order book + form */}
            <div className="grid grid-cols-[1fr_380px] gap-6 mb-6">

              {/* Order book */}
              <div className="bg-[#0c1018] border border-[#1e2736] rounded-lg overflow-hidden">
                <div className="px-4 py-3 border-b border-[#1e2736]">
                  <h2 className="text-[13px] font-semibold text-[#e6edf7]" style={MONO}>Order Book</h2>
                </div>

                <div className="grid grid-cols-2 divide-x divide-[#1e2736]">
                  {/* Bids (buy side) */}
                  <div>
                    <div className="grid grid-cols-3 px-4 py-2 border-b border-[#1e2736]">
                      <span className="text-[10px] text-[#5b6577] font-medium" style={MONO}>Price (USD)</span>
                      <span className="text-[10px] text-[#5b6577] font-medium text-right" style={MONO}>Amount</span>
                      <span className="text-[10px] text-[#5b6577] font-medium text-right" style={MONO}>Total</span>
                    </div>
                    <div className="max-h-[300px] overflow-auto">
                      {bids.length === 0 ? (
                        <div className="px-4 py-8 text-center text-[11px] text-[#3d4654]" style={MONO}>No bids</div>
                      ) : (
                        bids.slice(0, 15).map((bid) => (
                          <div key={bid.order_id} className="grid grid-cols-3 px-4 py-1.5 hover:bg-[#111823] transition-colors">
                            <span className="text-[11px] text-[#22c55e]" style={MONO}>{formatNumber(bid.price, 2)}</span>
                            <span className="text-[11px] text-[#9fb0c6] text-right" style={MONO}>{formatNumber(bid.remaining_amount)}</span>
                            <span className="text-[11px] text-[#5b6577] text-right" style={MONO}>{formatNumber(bid.price * bid.remaining_amount, 2)}</span>
                          </div>
                        ))
                      )}
                    </div>
                  </div>

                  {/* Asks (sell side) */}
                  <div>
                    <div className="grid grid-cols-3 px-4 py-2 border-b border-[#1e2736]">
                      <span className="text-[10px] text-[#5b6577] font-medium" style={MONO}>Price (USD)</span>
                      <span className="text-[10px] text-[#5b6577] font-medium text-right" style={MONO}>Amount</span>
                      <span className="text-[10px] text-[#5b6577] font-medium text-right" style={MONO}>Total</span>
                    </div>
                    <div className="max-h-[300px] overflow-auto">
                      {asks.length === 0 ? (
                        <div className="px-4 py-8 text-center text-[11px] text-[#3d4654]" style={MONO}>No asks</div>
                      ) : (
                        asks.slice(0, 15).map((ask) => (
                          <div key={ask.order_id} className="grid grid-cols-3 px-4 py-1.5 hover:bg-[#111823] transition-colors">
                            <span className="text-[11px] text-[#ef4444]" style={MONO}>{formatNumber(ask.price, 2)}</span>
                            <span className="text-[11px] text-[#9fb0c6] text-right" style={MONO}>{formatNumber(ask.remaining_amount)}</span>
                            <span className="text-[11px] text-[#5b6577] text-right" style={MONO}>{formatNumber(ask.price * ask.remaining_amount, 2)}</span>
                          </div>
                        ))
                      )}
                    </div>
                  </div>
                </div>
              </div>

              {/* Order form */}
              <div className="bg-[#0c1018] border border-[#1e2736] rounded-lg overflow-hidden">
                <div className="px-4 py-3 border-b border-[#1e2736]">
                  <h2 className="text-[13px] font-semibold text-[#e6edf7]" style={MONO}>Place Order</h2>
                </div>

                <div className="p-4 space-y-3">
                  {/* Side toggle */}
                  <div className="grid grid-cols-2 gap-2">
                    <button
                      onClick={() => setForm(f => ({ ...f, side: 'BUY' }))}
                      className={`py-2 rounded-md text-[12px] font-semibold transition-colors ${
                        form.side === 'BUY'
                          ? 'bg-[#0d2818] border border-[#22c55e]/40 text-[#22c55e]'
                          : 'bg-[#111823] border border-[#232c3c] text-[#5b6577] hover:text-[#9fb0c6]'
                      }`}
                      style={MONO}
                    >
                      BUY
                    </button>
                    <button
                      onClick={() => setForm(f => ({ ...f, side: 'SELL' }))}
                      className={`py-2 rounded-md text-[12px] font-semibold transition-colors ${
                        form.side === 'SELL'
                          ? 'bg-[#2a1215] border border-[#ef4444]/40 text-[#ef4444]'
                          : 'bg-[#111823] border border-[#232c3c] text-[#5b6577] hover:text-[#9fb0c6]'
                      }`}
                      style={MONO}
                    >
                      SELL
                    </button>
                  </div>

                  {/* Price */}
                  <div>
                    <label className="block text-[11px] text-[#7a869a] mb-1" style={MONO}>
                      Price (USD per AUT)<span className="text-[#ef4444] ml-0.5">*</span>
                    </label>
                    <input
                      type="number"
                      value={form.price}
                      onChange={e => setForm(f => ({ ...f, price: e.target.value }))}
                      placeholder="0.00"
                      step="0.01"
                      min="0.01"
                      disabled={submitting}
                      className="w-full px-3 py-2.5 bg-[#111823] border border-[#232c3c] rounded-lg text-[13px] text-[#d4a017] placeholder-[#3d4654] focus:outline-none focus:border-[#45c4b0] disabled:opacity-50 transition-colors"
                      style={MONO}
                    />
                  </div>

                  {/* Amount */}
                  <div>
                    <label className="block text-[11px] text-[#7a869a] mb-1" style={MONO}>
                      Amount (AUT)<span className="text-[#ef4444] ml-0.5">*</span>
                    </label>
                    <input
                      type="number"
                      value={form.amount}
                      onChange={e => setForm(f => ({ ...f, amount: e.target.value }))}
                      placeholder="0.0000"
                      step="0.0001"
                      min="0.0001"
                      disabled={submitting}
                      className="w-full px-3 py-2.5 bg-[#111823] border border-[#232c3c] rounded-lg text-[13px] text-[#dbe4f0] placeholder-[#3d4654] focus:outline-none focus:border-[#45c4b0] disabled:opacity-50 transition-colors"
                      style={MONO}
                    />
                  </div>

                  {/* Order total preview */}
                  {form.price && form.amount && (
                    <div className="px-3 py-2.5 bg-[#111823] border border-[#1e2736] rounded-lg">
                      <div className="flex justify-between">
                        <span className="text-[11px] text-[#5b6577]" style={MONO}>Order total</span>
                        <span className="text-[12px] text-[#45c4b0] font-semibold" style={MONO}>
                          ${formatNumber(parseFloat(form.price || '0') * parseFloat(form.amount || '0'), 2)} USD
                        </span>
                      </div>
                    </div>
                  )}

                  {/* Address */}
                  <div>
                    <label className="block text-[11px] text-[#7a869a] mb-1" style={MONO}>
                      Your Address<span className="text-[#ef4444] ml-0.5">*</span>
                    </label>
                    <input
                      type="text"
                      value={form.address}
                      onChange={e => setForm(f => ({ ...f, address: e.target.value }))}
                      placeholder="0x..."
                      disabled={submitting}
                      className="w-full px-3 py-2 bg-[#111823] border border-[#232c3c] rounded-lg text-[12px] text-[#dbe4f0] placeholder-[#3d4654] focus:outline-none focus:border-[#45c4b0] disabled:opacity-50 transition-colors"
                      style={MONO}
                    />
                  </div>

                  {/* Public key */}
                  <div>
                    <label className="block text-[11px] text-[#7a869a] mb-1" style={MONO}>
                      Public Key<span className="text-[#ef4444] ml-0.5">*</span>
                    </label>
                    <input
                      type="text"
                      value={form.public_key}
                      onChange={e => setForm(f => ({ ...f, public_key: e.target.value }))}
                      placeholder="Hex public key"
                      disabled={submitting}
                      className="w-full px-3 py-2 bg-[#111823] border border-[#232c3c] rounded-lg text-[12px] text-[#dbe4f0] placeholder-[#3d4654] focus:outline-none focus:border-[#45c4b0] disabled:opacity-50 transition-colors"
                      style={MONO}
                    />
                  </div>

                  {/* Private key */}
                  <div>
                    <label className="block text-[11px] text-[#7a869a] mb-1" style={MONO}>
                      Private Key<span className="text-[#ef4444] ml-0.5">*</span>
                    </label>
                    <input
                      type="password"
                      value={form.private_key}
                      onChange={e => setForm(f => ({ ...f, private_key: e.target.value }))}
                      placeholder="Hex private key (for signing)"
                      disabled={submitting}
                      className="w-full px-3 py-2 bg-[#111823] border border-[#232c3c] rounded-lg text-[12px] text-[#dbe4f0] placeholder-[#3d4654] focus:outline-none focus:border-[#45c4b0] disabled:opacity-50 transition-colors"
                      style={MONO}
                    />
                    <p className="text-[9px] text-[#3d4654] mt-1" style={MONO}>
                      Used for order signing and trade settlement. Never stored.
                    </p>
                  </div>

                  {/* Submit */}
                  <button
                    onClick={handlePlaceOrder}
                    disabled={submitting || !form.price || !form.amount || !form.address || !form.public_key || !form.private_key}
                    className={`w-full py-2.5 rounded-lg font-semibold text-[13px] transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 ${
                      form.side === 'BUY'
                        ? 'bg-[#22c55e] hover:bg-[#16a34a] text-[#0a0e14]'
                        : 'bg-[#ef4444] hover:bg-[#dc2626] text-white'
                    }`}
                    style={MONO}
                  >
                    {submitting && (
                      <div className="w-3.5 h-3.5 border-2 border-current border-t-transparent rounded-full animate-spin" />
                    )}
                    {submitting ? 'Placing...' : `${form.side} AUT`}
                  </button>
                </div>
              </div>
            </div>

            {/* Bottom section: My orders + Trade history */}
            <div className="grid grid-cols-2 gap-6">

              {/* My open orders */}
              <div className="bg-[#0c1018] border border-[#1e2736] rounded-lg overflow-hidden">
                <div className="flex items-center justify-between px-4 py-3 border-b border-[#1e2736]">
                  <h2 className="text-[13px] font-semibold text-[#e6edf7]" style={MONO}>My Open Orders</h2>
                  <span className="text-[10px] text-[#5b6577] px-2 py-0.5 bg-[#111823] rounded-full" style={MONO}>
                    {myOrders.length}
                  </span>
                </div>
                <div className="max-h-[280px] overflow-auto">
                  {!form.address ? (
                    <div className="px-4 py-8 text-center text-[11px] text-[#3d4654]" style={MONO}>
                      Enter your address to view orders
                    </div>
                  ) : myOrders.length === 0 ? (
                    <div className="px-4 py-8 text-center text-[11px] text-[#3d4654]" style={MONO}>
                      No open orders
                    </div>
                  ) : (
                    <table className="w-full">
                      <thead>
                        <tr className="text-[10px] text-[#5b6577] border-b border-[#1e2736]" style={MONO}>
                          <th className="text-left px-4 py-2 font-medium">Side</th>
                          <th className="text-right px-4 py-2 font-medium">Price</th>
                          <th className="text-right px-4 py-2 font-medium">Remaining</th>
                          <th className="text-left px-4 py-2 font-medium">Status</th>
                          <th className="text-right px-4 py-2 font-medium">Action</th>
                        </tr>
                      </thead>
                      <tbody>
                        {myOrders.map((order) => (
                          <tr key={order.order_id} className="border-b border-[#111823] hover:bg-[#111823] transition-colors">
                            <td className="px-4 py-2">
                              <span
                                className={`text-[10px] px-1.5 py-0.5 rounded font-semibold ${
                                  order.side === 'BUY'
                                    ? 'bg-[#0d2818] text-[#4ade80]'
                                    : 'bg-[#2a1215] text-[#f87171]'
                                }`}
                                style={MONO}
                              >
                                {order.side}
                              </span>
                            </td>
                            <td className="px-4 py-2 text-[11px] text-[#d4a017] text-right" style={MONO}>
                              ${formatNumber(order.price, 2)}
                            </td>
                            <td className="px-4 py-2 text-[11px] text-[#9fb0c6] text-right" style={MONO}>
                              {formatNumber(order.remaining_amount)}
                            </td>
                            <td className="px-4 py-2 text-[10px] text-[#5b6577]" style={MONO}>
                              {order.status}
                            </td>
                            <td className="px-4 py-2 text-right">
                              <button
                                onClick={() => handleCancel(order.order_id)}
                                className="text-[10px] text-[#ef4444] hover:text-[#f87171] transition-colors"
                                style={MONO}
                              >
                                Cancel
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              </div>

              {/* Trade history */}
              <div className="bg-[#0c1018] border border-[#1e2736] rounded-lg overflow-hidden">
                <div className="flex items-center justify-between px-4 py-3 border-b border-[#1e2736]">
                  <h2 className="text-[13px] font-semibold text-[#e6edf7]" style={MONO}>Recent Trades</h2>
                  <span className="text-[10px] text-[#5b6577] px-2 py-0.5 bg-[#111823] rounded-full" style={MONO}>
                    {trades.length}
                  </span>
                </div>
                <div className="max-h-[280px] overflow-auto">
                  {trades.length === 0 ? (
                    <div className="px-4 py-8 text-center text-[11px] text-[#3d4654]" style={MONO}>
                      No trades yet
                    </div>
                  ) : (
                    <table className="w-full">
                      <thead>
                        <tr className="text-[10px] text-[#5b6577] border-b border-[#1e2736]" style={MONO}>
                          <th className="text-right px-4 py-2 font-medium">Price</th>
                          <th className="text-right px-4 py-2 font-medium">Amount</th>
                          <th className="text-left px-4 py-2 font-medium">Buyer</th>
                          <th className="text-left px-4 py-2 font-medium">Seller</th>
                          <th className="text-left px-4 py-2 font-medium">Time</th>
                        </tr>
                      </thead>
                      <tbody>
                        {trades.map((trade) => (
                          <tr key={trade.trade_id} className="border-b border-[#111823] hover:bg-[#111823] transition-colors">
                            <td className="px-4 py-2 text-[11px] text-[#d4a017] text-right" style={MONO}>
                              ${formatNumber(trade.price, 2)}
                            </td>
                            <td className="px-4 py-2 text-[11px] text-[#9fb0c6] text-right" style={MONO}>
                              {formatNumber(trade.amount)}
                            </td>
                            <td className="px-4 py-2 text-[10px] text-[#5b6577]" style={MONO} title={trade.buyer_address}>
                              {trade.buyer_address.slice(0, 14)}...
                            </td>
                            <td className="px-4 py-2 text-[10px] text-[#5b6577]" style={MONO} title={trade.seller_address}>
                              {trade.seller_address.slice(0, 14)}...
                            </td>
                            <td className="px-4 py-2 text-[10px] text-[#5b6577] whitespace-nowrap">{formatTimestamp(trade.timestamp)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}
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
