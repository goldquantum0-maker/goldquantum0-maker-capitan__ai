import React, { useState } from 'react';
import ModalWrapper from './ModalWrapper';
import { useWallet } from '../../context/WalletContext';

export default function PasswordModal({ onClose, toast }) {
  const { setSessionPassword } = useWallet();
  const [pwd, setPwd] = useState('');

  const handleConfirm = () => {
    if (!pwd) { toast('Password required'); return; }
    setSessionPassword(pwd);
    onClose();
  };

  return (
    <ModalWrapper title="Wallet Password" onClose={onClose}>
      <p className="text-sm text-[var(--text-secondary)] mb-4">
        Enter your wallet password to sign the on‑chain action.
      </p>
      <input
        id="wallet-password"
        name="password"
        type="password"
        value={pwd}
        onChange={(e) => setPwd(e.target.value)}
        placeholder="Password"
        autoComplete="off"
        autoFocus
        onKeyDown={(e) => { if (e.key === 'Enter') handleConfirm(); }}
        className="w-full p-3 border border-[var(--glass-border)] rounded-2xl bg-[var(--bg-secondary)] text-[var(--text-primary)] mb-4 outline-none"
      />
      <div className="flex gap-3">
        <button onClick={handleConfirm} className="flex-1 py-3 bg-[var(--accent)] text-white rounded-3xl font-semibold hover:bg-[var(--accent-dark)] transition">
          Confirm
        </button>
        <button onClick={onClose} className="flex-1 py-3 border border-[var(--glass-border)] text-[var(--text-primary)] rounded-3xl font-semibold hover:bg-[var(--bg-tertiary)] transition">
          Cancel
        </button>
      </div>
    </ModalWrapper>
  );
}