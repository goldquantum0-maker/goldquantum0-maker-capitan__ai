import React, { useState } from 'react';
import ModalWrapper from './ModalWrapper';
import { useWallet } from '../../context/WalletContext';

export default function StakeModal({ onClose, toast }) {
  const { stakeClose, unstakeClose, closeBalance, closeStaked } = useWallet();
  const [amount, setAmount] = useState('');
  const [password, setPassword] = useState('');
  const [mode, setMode] = useState('stake'); // 'stake' or 'unstake'

  const handleAction = async () => {
    if (!password) { toast('Password required'); return; }
    try {
      if (mode === 'stake') {
        if (!amount || parseInt(amount) <= 0) { toast('Enter a valid amount'); return; }
        await stakeClose(amount, password);
        toast(`Staked ${amount} CLOSE`);
      } else {
        if (closeStaked <= 0) { toast('Nothing to unstake'); return; }
        await unstakeClose(password);
        toast('Unstaked all CLOSE');
      }
      onClose();
    } catch (e) { toast(e.message || 'Action failed'); }
  };

  return (
    <ModalWrapper title={mode === 'stake' ? 'Stake CLOSE' : 'Unstake CLOSE'} onClose={onClose}>
      <div className="flex gap-2 mb-4">
        <button
          onClick={() => setMode('stake')}
          className={`flex-1 py-2 rounded-xl text-sm font-semibold transition ${
            mode === 'stake' ? 'bg-[var(--accent)] text-white' : 'bg-[var(--bg-tertiary)] text-[var(--text-secondary)]'
          }`}
        >
          Stake
        </button>
        <button
          onClick={() => setMode('unstake')}
          className={`flex-1 py-2 rounded-xl text-sm font-semibold transition ${
            mode === 'unstake' ? 'bg-[var(--accent)] text-white' : 'bg-[var(--bg-tertiary)] text-[var(--text-secondary)]'
          }`}
        >
          Unstake
        </button>
      </div>

      {mode === 'stake' && (
        <>
          <p className="text-xs text-[var(--text-secondary)] mb-3">
            Available: {closeBalance.toLocaleString()} CLOSE
          </p>
          <input
            id="stake-amount"
            name="stake_amount"
            type="number"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            placeholder="Amount to stake"
            className="w-full p-3 border border-[var(--glass-border)] rounded-2xl bg-[var(--bg-secondary)] text-[var(--text-primary)] mb-3 outline-none"
          />
        </>
      )}
      {mode === 'unstake' && (
        <p className="text-xs text-[var(--text-secondary)] mb-4">
          Staked: {closeStaked.toLocaleString()} CLOSE – this will unstake everything.
        </p>
      )}

      <input
        id="stake-password"
        name="password"
        type="password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        placeholder="Wallet password"
        className="w-full p-3 border border-[var(--glass-border)] rounded-2xl bg-[var(--bg-secondary)] text-[var(--text-primary)] mb-4 outline-none"
      />
      <button
        onClick={handleAction}
        className="w-full py-3 bg-[var(--accent)] text-white rounded-3xl font-semibold hover:bg-[var(--accent-dark)] transition"
      >
        {mode === 'stake' ? 'Stake' : 'Unstake'}
      </button>
    </ModalWrapper>
  );
}