import React from 'react';
import ModalWrapper from './ModalWrapper';
import { useWallet } from '../../context/WalletContext';

export default function ReceiveModal({ onClose }) {
  const { walletAddress } = useWallet();
  const address = walletAddress || '0x3c6833cFDdED80fE76474a3Cb2Cc050Daec91fe8';

  const handleCopy = () => {
    navigator.clipboard.writeText(address);
    // The parent can show a toast, but for now we just copy silently
  };

  return (
    <ModalWrapper title="Receive" onClose={onClose}>
      <div className="flex flex-col items-center">
        <div className="w-48 h-48 bg-zinc-100 rounded-2xl flex items-center justify-center mb-4">
          {/* Basic placeholder QR – a real app would generate a QR code */}
          <svg width="140" height="140" viewBox="0 0 100 100" className="text-zinc-950">
            <rect x="10" y="10" width="30" height="30" fill="currentColor" />
            <rect x="60" y="10" width="30" height="30" fill="currentColor" />
            <rect x="10" y="60" width="30" height="30" fill="currentColor" />
            <rect x="60" y="60" width="30" height="30" fill="none" stroke="currentColor" strokeWidth="4" />
            <circle cx="75" cy="75" r="8" fill="currentColor" />
          </svg>
        </div>
        <p className="text-xs text-[var(--text-secondary)] mb-2">Your Polygon address</p>
        <div className="w-full bg-[var(--bg-secondary)] border border-[var(--glass-border)] rounded-xl px-4 py-3 flex items-center justify-between">
          <span className="text-[var(--text-primary)] font-mono text-xs truncate mr-2">{address}</span>
          <button onClick={handleCopy} className="text-[var(--text-secondary)] hover:text-[var(--accent)] shrink-0">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor">
              <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
              <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
            </svg>
          </button>
        </div>
        <div className="w-full mt-3 flex items-start gap-2 bg-amber-950/20 border border-amber-900/40 rounded-lg p-3">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" className="text-amber-400 mt-0.5 shrink-0">
            <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
            <line x1="12" y1="9" x2="12" y2="13" />
            <line x1="12" y1="17" x2="12.01" y2="17" />
          </svg>
          <span className="text-amber-200/80 text-xs">
            Only send Polygon network assets to this address.
          </span>
        </div>
      </div>
    </ModalWrapper>
  );
}