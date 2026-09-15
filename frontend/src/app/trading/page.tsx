import { TradingClient } from '@/components/TradingClient';

export const metadata = {
  title: 'AUT Trading | Gold Vault',
  description: 'Trade AUT gold-backed tokens with limit orders',
};

export default function TradingPage() {
  return <TradingClient />;
}
