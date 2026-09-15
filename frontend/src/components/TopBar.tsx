'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';

const MONO = { fontFamily: "'IBM Plex Mono', monospace" } as const;

const NAV_LINKS = [
  { href: '/vault', label: 'Reserve Dashboard' },
  { href: '/wallets', label: 'Wallets' },
  { href: '/portfolio', label: 'Client Portfolio' },
  { href: '/trading', label: 'Trading' },
] as const;

export function TopBar() {
  const pathname = usePathname();

  return (
    <div className="flex items-center justify-between h-12 px-4 bg-[#0c1018] border-b border-[#1e2736]">
      {/* Left: Logo + Product + Nav */}
      <div className="flex items-center gap-3">
        <span className="text-[14px] text-[#d4a017]" style={MONO}>
          &#x2B21;
        </span>
        <span className="text-[13px] font-semibold text-[#e6edf7]" style={MONO}>
          Gold Vault
        </span>
        <span className="text-[#2a3140]">|</span>
        <nav className="flex items-center gap-1">
          {NAV_LINKS.map(({ href, label }) => {
            const isActive = pathname === href;
            return (
              <Link
                key={href}
                href={href}
                className={`text-[11px] px-2.5 py-1 rounded-md transition-colors ${
                  isActive
                    ? 'bg-[#182233] text-[#45c4b0] border border-[#45c4b0]/20'
                    : 'text-[#5b6577] hover:text-[#9fb0c6] hover:bg-[#111823]'
                }`}
                style={MONO}
              >
                {label}
              </Link>
            );
          })}
        </nav>
      </div>

      {/* Right: Network badge */}
      <div className="flex items-center gap-3">
        <span
          className="text-[10.5px] px-2.5 py-1 rounded-md bg-[#111823] border border-[#232c3c] text-[#7a869a]"
          style={MONO}
        >
          gold-mainnet
        </span>
      </div>
    </div>
  );
}
