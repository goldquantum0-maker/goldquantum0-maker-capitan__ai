import React, { useState } from 'react';
import ModalWrapper from './ModalWrapper';
import { useAuth } from '../../context/AuthContext';

export default function FounderLoginModal({ onClose, toast }) {
  const { founderLogin } = useAuth();
  const [code, setCode] = useState('');

  const handleSubmit = async () => {
    if (!code) { toast('Enter founder key'); return; }
    try {
      await founderLogin(code);
      toast('Founder access granted.');
      onClose();
    } catch { toast('Invalid founder key'); }
  };

  return (
    <ModalWrapper title="Founder Access" onClose={onClose}>
      <p className="text-sm text-[var(--text-secondary)] mb-4">
        Enter your founder key to unlock admin controls.
      </p>
      <input
        type="password"
        value={code}
        onChange={(e) => setCode(e.target.value)}
        placeholder="Founder key"
        autoFocus
        className="w-full p-3 border border-[var(--glass-border)] rounded-2xl bg-[var(--bg-secondary)] text-[var(--text-primary)] mb-4 outline-none"
      />
      <button
        onClick={handleSubmit}
        className="w-full py-3 bg-gradient-to-r from-[#f0b90b] to-[#d4a30a] text-black rounded-3xl font-semibold hover:opacity-90 transition"
      >
        Verify
      </button>
    </ModalWrapper>
  );
}