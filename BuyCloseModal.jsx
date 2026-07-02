import React, { useState } from 'react';
import ModalWrapper from './ModalWrapper';
import { useWallet } from '../../context/WalletContext';

export default function BuyCloseModal({ onClose, toast }) {
  const { purchaseClose } = useWallet();
  const [usdAmount, setUsdAmount] = useState('1');
  const [txHash, setTxHash] = useState('');

  const handleBuy = async () => {
    if (!usdAmount || !txHash) { toast('Fill all fields'); return; }
    try {
      const res = await purchaseClose(parseFloat(usdAmount), txHash);
      if (res.verified) {
        toast('CLOSE purchased successfully!');
        onClose();
      } else {
        toast('Payment not verified yet. Please check the TX hash.');
      }
    } catch { toast('Purchase failed. Check TX hash and try again.'); }
  };

  return (
    <ModalWrapper title="Buy CLOSE" onClose={onClose}>
      <p className="text-sm text-[var(--text-secondary)] mb-4">
        Send your payment to the Hot Wallet address below, then paste the transaction hash.
      </p>
      <div className="bg-[var(--bg-secondary)] border border-[var(--glass-border)] rounded-xl p-3 mb-4 break-all text-xs font-mono text-[var(--text-primary)]">
        0x109464E84bDD6552d76bcBbaEf03bDe8069C0698
      </div>
      <input
        id="buy-usd"
        name="usd_amount"
        type="number"
        value={usdAmount}
        onChange={(e) => setUsdAmount(e.target.value)}
        placeholder="USD amount"
        min="1"
        className="w-full p-3 border border-[var(--glass-border)] rounded-2xl bg-[var(--bg-secondary)] text-[var(--text-primary)] mb-3 outline-none"
      />
      <input
        id="buy-txhash"
        name="tx_hash"
        value={txHash}
        onChange={(e) => setTxHash(e.target.value)}
        placeholder="Transaction hash"
        className="w-full p-3 border border-[var(--glass-border)] rounded-2xl bg-[var(--bg-secondary)] text-[var(--text-primary)] mb-4 outline-none font-mono text-xs"
      />
      <button
        onClick={handleBuy}
        className="w-full py-3 bg-gradient-to-r from-[#f0b90b] to-[#d4a30a] text-black rounded-3xl font-semibold hover:opacity-90 transition"
      >
        Verify & Buy
      </button>
    </ModalWrapper>
  );
}