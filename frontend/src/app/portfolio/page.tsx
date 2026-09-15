import type { Metadata } from 'next';
import { PortfolioClient } from '@/components/PortfolioClient';

export const metadata: Metadata = {
  title: 'Client Portfolio | AUT Tokenization Platform',
  description: 'View per-client gold reserves, AUT balance, and transaction history',
};

export default async function PortfolioPage({
  searchParams,
}: {
  searchParams: Promise<{ address?: string }>;
}) {
  const params = await searchParams;
  return <PortfolioClient initialAddress={params.address} />;
}
