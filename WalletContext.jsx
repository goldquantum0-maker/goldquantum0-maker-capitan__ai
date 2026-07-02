import React, { createContext, useContext, useState, useCallback } from 'react';
import { apiCall } from '../utils/api';
import { useAuth } from './AuthContext';

const WalletContext = createContext(null);

export const useWallet = () => useContext(WalletContext);

const CLOSE_PRICE = 0.00009776;

export const WalletProvider = ({ children }) => {
  const { user } = useAuth();
  const [closeBalance, setCloseBalance] = useState(0);
  const [closeStaked, setCloseStaked] = useState(0);
  const [stakeTier, setStakeTier] = useState('none');
  const [walletAddress, setWalletAddress] = useState('');
  const [sessionPassword, setSessionPassword] = useState(null);
  const [portfolio, setPortfolio] = useState({ total_usd: 0, tokens: [] });
  const [txs, setTxs] = useState([]);

  const refreshBalance = useCallback(async () => {
    if (!user) return;
    try {
      const bal = await apiCall('/api/wallet/balance');
      setCloseBalance(bal.close_balance || 0);
      setCloseStaked(bal.close_staked || 0);
      setStakeTier(bal.stake_tier || 'none');
      if (bal.wallet_address) setWalletAddress(bal.wallet_address);
      localStorage.setItem('close_balance', bal.close_balance);
      localStorage.setItem('close_staked', bal.close_staked);
      localStorage.setItem('stake_tier', bal.stake_tier);
    } catch {}
  }, [user]);

  const refreshPortfolio = useCallback(async () => {
    if (!user) return;
    try {
      const p = await apiCall('/api/wallet/portfolio');
      setPortfolio(p);
    } catch {}
  }, [user]);

  const refreshTxs = useCallback(async () => {
    if (!user) return;
    try {
      const t = await apiCall('/api/wallet/transactions');
      setTxs(t.transactions || []);
    } catch {}
  }, [user]);

  const activateWallet = async (password) => {
    const res = await apiCall('/api/wallet/activate', {
      method: 'POST',
      body: JSON.stringify({ password }),
    });
    setCloseBalance(res.close_credited);
    setWalletAddress(res.wallet_address);
    setSessionPassword(password);
    return res;
  };

  const createWallet = async (chain, label, password) => {
    const res = await apiCall('/api/wallet/create', {
      method: 'POST',
      body: JSON.stringify({ chain, label, password }),
    });
    setWalletAddress(res.address);
    setSessionPassword(password);
    return res;
  };

  const purchaseClose = async (usdAmount, txHash) => {
    const res = await apiCall('/api/wallet/purchase', {
      method: 'POST',
      body: JSON.stringify({ usd_amount: usdAmount, tx_hash: txHash }),
    });
    await refreshBalance();
    return res;
  };

  const stakeClose = async (amount, password) => {
    await apiCall('/api/wallet/stake', {
      method: 'POST',
      body: JSON.stringify({ amount: parseInt(amount), password }),
    });
    await refreshBalance();
  };

  const unstakeClose = async (password) => {
    await apiCall('/api/wallet/unstake', {
      method: 'POST',
      body: JSON.stringify({ password }),
    });
    await refreshBalance();
  };

  const sendTx = async (walletId, to, amount, password, tokenAddress) => {
    const res = await apiCall(`/api/wallet/${walletId}/send`, {
      method: 'POST',
      body: JSON.stringify({ to, amount, password, token_address: tokenAddress }),
    });
    await refreshBalance();
    return res;
  };

  const lockWallet = () => setSessionPassword(null);

  return (
    <WalletContext.Provider value={{
      closeBalance, setCloseBalance, closeStaked, stakeTier,
      walletAddress, sessionPassword, setSessionPassword,
      portfolio, txs, CLOSE_PRICE,
      refreshBalance, refreshPortfolio, refreshTxs,
      activateWallet, createWallet, purchaseClose,
      stakeClose, unstakeClose, sendTx, lockWallet,
    }}>
      {children}
    </WalletContext.Provider>
  );
};