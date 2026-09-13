import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'Gold Vault | AUT Tokenization Platform',
  description: 'Onboard physical gold reserves and manage AUT token supply on the Gold Tokenization blockchain',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-[#0a0e14] text-[#dbe4f0]">
        {children}
      </body>
    </html>
  );
}
