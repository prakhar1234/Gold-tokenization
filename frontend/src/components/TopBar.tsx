'use client';

export function TopBar() {
  return (
    <div className="flex items-center justify-between h-12 px-4 bg-[#0c1018] border-b border-[#1e2736]">
      {/* Left: Logo + Product */}
      <div className="flex items-center gap-3">
        <span
          className="text-[14px] text-[#d4a017]"
          style={{ fontFamily: "'IBM Plex Mono', monospace" }}
        >
          &#x2B21;
        </span>
        <span
          className="text-[13px] font-semibold text-[#e6edf7]"
          style={{ fontFamily: "'IBM Plex Mono', monospace" }}
        >
          Gold Vault
        </span>
        <span className="text-[#2a3140]">|</span>
        <span className="text-[11px] text-[#5b6577]">
          AUT Tokenization Platform
        </span>
      </div>

      {/* Right: Network badge */}
      <div className="flex items-center gap-3">
        <span
          className="text-[10.5px] px-2.5 py-1 rounded-md bg-[#111823] border border-[#232c3c] text-[#7a869a]"
          style={{ fontFamily: "'IBM Plex Mono', monospace" }}
        >
          gold-mainnet
        </span>
      </div>
    </div>
  );
}
