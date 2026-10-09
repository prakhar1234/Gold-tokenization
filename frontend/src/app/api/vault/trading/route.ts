import { NextRequest, NextResponse } from 'next/server';

const BLOCKCHAIN_URL = process.env.BLOCKCHAIN_NODE_URL || 'http://127.0.0.1:5100';

/** Parse JSON that may contain Python-style Infinity/NaN values. */
function safeJsonParse(text: string): unknown {
  const sanitized = text
    .replace(/:\s*Infinity\b/g, ': 999999999')
    .replace(/:\s*-Infinity\b/g, ': -999999999')
    .replace(/:\s*NaN\b/g, ': 0');
  return JSON.parse(sanitized);
}

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const view = searchParams.get('view');

    if (view === 'book') {
      const res = await fetch(`${BLOCKCHAIN_URL}/orders/book`, { cache: 'no-store' });
      if (!res.ok) return NextResponse.json({ error: 'Failed to fetch order book' }, { status: 502 });
      const data = safeJsonParse(await res.text());
      return NextResponse.json(data);
    }

    if (view === 'trades') {
      const address = searchParams.get('address');
      const limit = searchParams.get('limit') || '50';
      const url = address
        ? `${BLOCKCHAIN_URL}/trades/${encodeURIComponent(address)}?limit=${limit}`
        : `${BLOCKCHAIN_URL}/trades?limit=${limit}`;
      const res = await fetch(url, { cache: 'no-store' });
      if (!res.ok) return NextResponse.json({ error: 'Failed to fetch trades' }, { status: 502 });
      const data = safeJsonParse(await res.text());
      return NextResponse.json(data);
    }

    if (view === 'orders') {
      const address = searchParams.get('address');
      const url = address
        ? `${BLOCKCHAIN_URL}/orders?address=${encodeURIComponent(address)}`
        : `${BLOCKCHAIN_URL}/orders`;
      const res = await fetch(url, { cache: 'no-store' });
      if (!res.ok) return NextResponse.json({ error: 'Failed to fetch orders' }, { status: 502 });
      const data = safeJsonParse(await res.text());
      return NextResponse.json(data);
    }

    // Default: market summary + order book + recent trades in parallel
    const [summaryRes, bookRes, tradesRes] = await Promise.all([
      fetch(`${BLOCKCHAIN_URL}/market/summary`, { cache: 'no-store' }),
      fetch(`${BLOCKCHAIN_URL}/orders/book`, { cache: 'no-store' }),
      fetch(`${BLOCKCHAIN_URL}/trades?limit=20`, { cache: 'no-store' }),
    ]);

    if (!summaryRes.ok || !bookRes.ok || !tradesRes.ok) {
      return NextResponse.json({ error: 'Failed to fetch trading data' }, { status: 502 });
    }

    const [summaryText, bookText, tradesText] = await Promise.all([
      summaryRes.text(),
      bookRes.text(),
      tradesRes.text(),
    ]);

    const summary = safeJsonParse(summaryText);
    const book = safeJsonParse(bookText);
    const trades = safeJsonParse(tradesText);

    return NextResponse.json({ summary, book, trades });
  } catch (err) {
    console.error('Trading proxy GET error:', err);
    return NextResponse.json({ error: 'Blockchain node unreachable' }, { status: 502 });
  }
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();

    const required = ['side', 'address', 'price', 'amount', 'public_key'];
    for (const field of required) {
      if (!body[field]) {
        return NextResponse.json({ error: `Missing field: ${field}` }, { status: 400 });
      }
    }

    // PoC: either a pre-signed signature or a private_key for server-side signing is required
    if (!body.signature && !body.private_key) {
      return NextResponse.json({ error: 'Missing field: signature or private_key' }, { status: 400 });
    }

    const response = await fetch(`${BLOCKCHAIN_URL}/orders`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });

    const text = await response.text();
    const data = safeJsonParse(text);

    if (!response.ok) {
      return NextResponse.json(data, { status: response.status });
    }

    return NextResponse.json(data, { status: 201 });
  } catch (err) {
    console.error('Trading proxy POST error:', err);
    return NextResponse.json({ error: 'Failed to place order' }, { status: 500 });
  }
}

export async function DELETE(request: NextRequest) {
  try {
    const body = await request.json();
    const { order_id, address } = body;

    if (!order_id || !address) {
      return NextResponse.json({ error: 'order_id and address are required' }, { status: 400 });
    }

    const response = await fetch(`${BLOCKCHAIN_URL}/orders/${encodeURIComponent(order_id)}`, {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ address }),
    });

    const text = await response.text();
    const data = safeJsonParse(text);

    if (!response.ok) {
      return NextResponse.json(data, { status: response.status });
    }

    return NextResponse.json(data);
  } catch (err) {
    console.error('Trading proxy DELETE error:', err);
    return NextResponse.json({ error: 'Failed to cancel order' }, { status: 500 });
  }
}
