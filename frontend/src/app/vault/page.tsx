import type { Metadata } from 'next';
import { GoldVaultClient } from '@/components/GoldVaultClient';

export const metadata: Metadata = {
  title: 'Gold Vault | AUT Tokenization Platform',
  description: 'Onboard physical gold reserves and mint AUT tokens on the Gold Tokenization blockchain',
};

export default function VaultPage() {
  return <GoldVaultClient />;
}
