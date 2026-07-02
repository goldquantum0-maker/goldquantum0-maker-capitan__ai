import React from 'react';
import ModalWrapper from './ModalWrapper';
import { useAuth } from '../../context/AuthContext';
import { useWallet } from '../../context/WalletContext';

export default function ProfileModal({ onClose, toast }) {
  const { user, logout } = useAuth();
  const { closeBalance, closeStaked, stakeTier, CLOSE_PRICE, lockWallet } = useWallet();

  const handleLock = () => {
    lockWallet();
    toast('Wallet locked');
  };

  const handleLogout = () => {
    logout();
    toast('Signed out');
    onClose();
  };

  return (
    <ModalWrapper title="Account" onClose={onClose}>
      <div className="space-y-3 text-sm">
        <div className="flex justify-between">
          <span className="text-[var(--text-secondary)]">Email</span>
          <span className="text-[var(--text-primary)] font-medium">{user?.email || 'Guest'}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-[var(--text-secondary)]">CLOSE Balance</span>
          <span className="text-[var(--text-primary)] font-medium">
            {closeBalance.toLocaleString()} (${((closeBalance * CLOSE_PRICE)).toFixed(4)})
          </span>
        </div>
        <div className="flex justify-between">
          <span className="text-[var(--text-secondary)]">Staked</span>
          <span className="text-[var(--text-primary)] font-medium">{closeStaked.toLocaleString()}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-[var(--text-secondary)]">Tier</span>
          <span className="text-[var(--accent)] font-semibold uppercase">{stakeTier}</span>
        </div>
      </div>

      {user ? (
        <div className="mt-6 space-y-2">
          <button
            onClick={handleLock}
            className="w-full py-3 border border-[var(--glass-border)] text-[var(--text-primary)] rounded-3xl font-semibold hover:bg-[var(--bg-tertiary)] transition"
          >
            Lock Wallet
          </button>
          <button
            onClick={handleLogout}
            className="w-full py-3 bg-[var(--danger)] text-white rounded-3xl font-semibold hover:opacity-90 transition"
          >
            Sign Out
          </button>
        </div>
      ) : (
        <button
          onClick={onClose}
          className="w-full mt-6 py-3 bg-[var(--accent)] text-white rounded-3xl font-semibold"
        >
          Close
        </button>
      )}
    </ModalWrapper>
  );
}