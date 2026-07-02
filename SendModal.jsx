import React, { useState } from 'react';
import ModalWrapper from './ModalWrapper';
import { useWallet } from '../../context/WalletContext';
import { apiCall } from '../../utils/api';

export default function SendModal({ onClose, toast }) {
  const { sendTx } = useWallet();
  const [chain, setChain] = useState('polygon');
  const [token, setToken] = useState('');
  const [to, setTo] = useState('');
  const [amount, setAmount] = useState('');
  const [password, setPassword] = useState('');

  const handleSend = async () => {
    if (!to || !amount || !password) { toast('Fill all fields'); return; }
    try {
      // In a real app you'd get the active wallet id from the backend
      const wallets = await apiCall('/api/wallets');
      const active = wallets.wallets.find(w => w.active) || wallets.wallets[0];
      if (!active) { toast('No wallet found'); return; }
      const res = await sendTx(active.id, to, amount, password, token);
      toast(`Sent! TX: ${res.tx_hash?.slice(0, 10)}...`);
      onClose();
    } catch (e) { toast('Send failed: ' + (e.message || 'Unknown error')); }
  };

  return (
    <ModalWrapper title="Send" onClose={onClose}>
      <select
        value={chain}
        onChange={(e) => setChain(e.target.value)}
        className="w-full p-3 border border-[var(--glass-border)] rounded-2xl bg-[var(--bg-secondary)] text-[var(--text-primary)] mb-3 outline-none"
      >
        <option value="polygon">Polygon</option>
        <option value="ethereum">Ethereum</option>
        <option value="bsc">BSC</option>
      </select>

      <input
        value={to}
        onChange={(e) => setTo(e.target.value)}
        placeholder="Recipient address"
        className="w-full p-3 border border-[var(--glass-border)] rounded-2xl bg-[var(--bg-secondary)] text-[var(--text-primary)] mb-3 outline-none font-mono text-xs"
      />

      <input
        value={token}
        onChange={(e) => setToken(e.target.value)}
        placeholder="Token symbol (e.g., USDT)"
        className="w-full p-3 border border-[var(--glass-border)] rounded-2xl bg-[var(--bg-secondary)] text-[var(--text-primary)] mb-3 outline-none"
      />

      <input
        type="number"
        value={amount}
        onChange={(e) => setAmount(e.target.value)}
        placeholder="Amount"
        className="w-full p-3 border border-[var(--glass-border)] rounded-2xl bg-[var(--bg-secondary)] text-[var(--text-primary)] mb-3 outline-none"
      />

      <input
        type="password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        placeholder="Wallet password"
        className="w-full p-3 border border-[var(--glass-border)] rounded-2xl bg-[var(--bg-secondary)] text-[var(--text-primary)] mb-4 outline-none"
      />

      <button
        onClick={handleSend}
        className="w-full py-3 bg-[var(--accent)] text-white rounded-3xl font-semibold hover:bg-[var(--accent-dark)] transition"
      >
        Send
      </button>
    </ModalWrapper>
  );
}