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
  const address = request.nextUrl.searchParams.get('address');
  if (!address) {
    return NextResponse.json({ error: 'address query parameter required' }, { status: 400 });
  }

  try {
    const [portfolioRes, txRes] = await Promise.all([
      fetch(`${BLOCKCHAIN_URL}/portfolio/${encodeURIComponent(address)}`, { cache: 'no-store' }),
      fetch(`${BLOCKCHAIN_URL}/transactions/${encodeURIComponent(address)}`, { cache: 'no-store' }),
    ]);

    if (!portfolioRes.ok || !txRes.ok) {
      return NextResponse.json({ error: 'Failed to fetch portfolio data' }, { status: 502 });
    }

    const [portfolioText, txText] = await Promise.all([
      portfolioRes.text(),
      txRes.text(),
    ]);

    const portfolio = safeJsonParse(portfolioText) as Record<string, unknown>;
    const txData = safeJsonParse(txText) as Record<string, unknown>;

    return NextResponse.json({ ...portfolio, transactions: (txData as { transactions: unknown[] }).transactions });
  } catch (err) {
    console.error('Portfolio proxy error:', err);
    return NextResponse.json({ error: 'Blockchain node unreachable' }, { status: 502 });
  }
}
