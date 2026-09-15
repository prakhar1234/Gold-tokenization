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

export async function GET() {
  try {
    const [healthRes, tokenRes, reservesRes] = await Promise.all([
      fetch(`${BLOCKCHAIN_URL}/health`, { cache: 'no-store' }),
      fetch(`${BLOCKCHAIN_URL}/token/info`, { cache: 'no-store' }),
      fetch(`${BLOCKCHAIN_URL}/reserves`, { cache: 'no-store' }),
    ]);

    if (!healthRes.ok || !tokenRes.ok || !reservesRes.ok) {
      return NextResponse.json(
        { error: 'Failed to fetch blockchain data' },
        { status: 502 }
      );
    }

    const [healthText, tokenText, reservesText] = await Promise.all([
      healthRes.text(),
      tokenRes.text(),
      reservesRes.text(),
    ]);

    const health = safeJsonParse(healthText);
    const token = safeJsonParse(tokenText);
    const reserves = safeJsonParse(reservesText);

    return NextResponse.json({ health, token, reserves });
  } catch (err) {
    console.error('Gold vault proxy error:', err);
    return NextResponse.json(
      { error: 'Blockchain node unreachable' },
      { status: 502 }
    );
  }
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();

    if (!body.custodian || !body.amount_grams) {
      return NextResponse.json(
        { error: 'custodian and amount_grams are required' },
        { status: 400 }
      );
    }

    const response = await fetch(`${BLOCKCHAIN_URL}/reserves`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        custodian: body.custodian,
        amount_grams: parseFloat(body.amount_grams),
        purity: parseFloat(body.purity || '0.999'),
        certificate_ref: body.certificate_ref || '',
        depositor_address: body.depositor_address || '',
      }),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: 'Blockchain error' }));
      return NextResponse.json(error, { status: response.status });
    }

    const data = await response.json();
    return NextResponse.json(data, { status: 201 });
  } catch (err) {
    console.error('Gold reserve POST error:', err);
    return NextResponse.json(
      { error: 'Failed to register reserve' },
      { status: 500 }
    );
  }
}
