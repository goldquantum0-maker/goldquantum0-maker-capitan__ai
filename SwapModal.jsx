import React, { useState } from 'react';
import ModalWrapper from './ModalWrapper';
import { apiCall } from '../../utils/api';

const CHAINS = {
  polygon: { name: 'Polygon', tokens: { POL: '0x00...', USDT: '0xc213...', USDC: '0x2791...' } },
  ethereum: { name: 'Ethereum', tokens: { ETH: '0x00...', USDT: '0xdAC1...', USDC: '0xA0b8...' } },
  bsc: { name: 'BSC', tokens: { BNB: '0x00...', USDT: '0x55d3...', USDC: '0x8AC7...' } },
};

export default function SwapModal({ onClose, toast }) {
  const [chain, setChain] = useState('polygon');
  const [fromToken, setFromToken] = useState('');
  const [toToken, setToToken] = useState('');
  const [amount, setAmount] = useState('');
  const [quote, setQuote] = useState(null);

  const fetchQuote = async () => {
    if (!fromToken || !toToken || !amount) { toast('Fill all fields'); return; }
    try {
      const res = await apiCall(
        `/api/swap/quote?chain=${chain}&from_token=${fromToken}&to_token=${toToken}&amount=${amount}`
      );
      setQuote(res);
    } catch { toast('Failed to get quote'); }
  };

  const tokens = CHAINS[chain]?.tokens || {};

  return (
    <ModalWrapper title="Swap Tokens" onClose={onClose}>
      <select
        value={chain}
        onChange={(e) => { setChain(e.target.value); setFromToken(''); setToToken(''); setQuote(null); }}
        className="w-full p-3 border border-[var(--glass-border)] rounded-2xl bg-[var(--bg-secondary)] text-[var(--text-primary)] mb-3 outline-none"
      >
        {Object.entries(CHAINS).map(([key, val]) => (
          <option key={key} value={key}>{val.name}</option>
        ))}
      </select>

      <select
        value={fromToken}
        onChange={(e) => setFromToken(e.target.value)}
        className="w-full p-3 border border-[var(--glass-border)] rounded-2xl bg-[var(--bg-secondary)] text-[var(--text-primary)] mb-3 outline-none"
      >
        <option value="">From token</option>
        {Object.entries(tokens).map(([sym]) => (
          <option key={sym} value={sym}>{sym}</option>
        ))}
      </select>

      <select
        value={toToken}
        onChange={(e) => setToToken(e.target.value)}
        className="w-full p-3 border border-[var(--glass-border)] rounded-2xl bg-[var(--bg-secondary)] text-[var(--text-primary)] mb-3 outline-none"
      >
        <option value="">To token</option>
        {Object.entries(tokens).map(([sym]) => (
          <option key={sym} value={sym}>{sym}</option>
        ))}
      </select>

      <input
        type="number"
        value={amount}
        onChange={(e) => setAmount(e.target.value)}
        placeholder="Amount"
        className="w-full p-3 border border-[var(--glass-border)] rounded-2xl bg-[var(--bg-secondary)] text-[var(--text-primary)] mb-4 outline-none"
      />

      <button
        onClick={fetchQuote}
        className="w-full py-3 bg-[var(--accent)] text-white rounded-3xl font-semibold mb-3 hover:bg-[var(--accent-dark)] transition"
      >
        Get Quote
      </button>

      {quote && (
        <div className="bg-[var(--bg-secondary)] border border-[var(--glass-border)] rounded-xl p-3 text-sm text-[var(--text-primary)]">
          Estimated output: <strong>{quote.to_amount} {quote.to_token}</strong><br />
          <span className="text-xs text-[var(--text-tertiary)]">Gas: {quote.estimated_gas}</span>
        </div>
      )}
    </ModalWrapper>
  );
}