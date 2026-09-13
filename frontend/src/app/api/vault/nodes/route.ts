import { NextResponse } from 'next/server';

const BASE_PORT = parseInt(process.env.BLOCKCHAIN_BASE_PORT || '5100', 10);
const NUM_NODES = parseInt(process.env.BLOCKCHAIN_NUM_NODES || '3', 10);

export async function GET() {
  const nodes: Array<{
    url: string;
    status: string;
    chain_height: number;
    peers: number;
    mempool_size: number;
  }> = [];

  for (let i = 0; i < NUM_NODES; i++) {
    const url = `http://127.0.0.1:${BASE_PORT + i}`;
    try {
      const res = await fetch(`${url}/health`, { cache: 'no-store' });
      if (res.ok) {
        const data = await res.json();
        nodes.push({
          url,
          status: data.status,
          chain_height: data.chain_height,
          peers: data.peers,
          mempool_size: data.mempool_size,
        });
      } else {
        nodes.push({ url, status: 'error', chain_height: 0, peers: 0, mempool_size: 0 });
      }
    } catch {
      nodes.push({ url, status: 'offline', chain_height: 0, peers: 0, mempool_size: 0 });
    }
  }

  return NextResponse.json({ nodes });
}
