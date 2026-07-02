import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { useWallet } from '../context/WalletContext';
import { apiCall } from '../utils/api';
import { fmtUsd, fmtNum } from '../utils/format';
import {
  Send, ArrowDownLeft, Repeat, Clock, Settings, Copy, ChevronRight,
  Flame, ArrowLeft, Check, QrCode, ChevronDown, Wallet, ShieldAlert,
  ExternalLink, TrendingUp, TrendingDown, Loader2
} from 'lucide-react';

// ---- Helper Components ----
function TabButton({ icon: Icon, label, active, onClick }) {
  return (
    <button onClick={onClick} className="flex flex-col items-center gap-1 px-2">
      <Icon size={20} strokeWidth={2} className={active ? "text-orange-400" : "text-zinc-600"} />
      <span className={`text-[10px] font-medium ${active ? "text-orange-400" : "text-zinc-600"}`}>{label}</span>
    </button>
  );
}

function ScreenHeader({ title, onBack, right }) {
  return (
    <div className="flex items-center justify-between px-5 pt-2 pb-4">
      {onBack ? (
        <button onClick={onBack} className="text-zinc-400 hover:text-zinc-200">
          <ArrowLeft size={20} />
        </button>
      ) : <div className="w-5" />}
      <span className="text-zinc-200 text-sm font-semibold tracking-wide">{title}</span>
      {right || <div className="w-5" />}
    </div>
  );
}

function Row({ label, value, mono }) {
  return (
    <div className="flex items-center justify-between px-4 py-3">
      <span className="text-zinc-500 text-xs">{label}</span>
      <span className={`text-zinc-200 text-xs ${mono ? "font-mono" : "font-medium"}`}>{value}</span>
    </div>
  );
}

function ActionButton({ icon: Icon, label, onClick }) {
  return (
    <button onClick={onClick} className="flex flex-col items-center gap-2 group">
      <div className="w-12 h-12 rounded-full bg-zinc-900 border border-zinc-800 flex items-center justify-center group-hover:border-orange-800 group-active:scale-95 transition">
        <Icon size={18} className="text-zinc-300" />
      </div>
      <span className="text-zinc-400 text-[11px] font-medium">{label}</span>
    </button>
  );
}

// ---- Screens ----
function HomeScreen({ showBalance, setShowBalance, setTab, walletData }) {
  const { closeBalance, closeStaked, stakeTier, CLOSE_PRICE, portfolio } = walletData;
  const tokens = portfolio?.tokens || [];
  const totalUsd = portfolio?.total_usd || 0;
  const totalBurned = closeStaked; // or fetch from a dedicated endpoint if different

  return (
    <div>
      <div className="flex items-center justify-between px-5 pt-2 pb-2">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-full bg-zinc-800 flex items-center justify-center">
            <Wallet size={14} className="text-orange-400" />
          </div>
          <div>
            <div className="text-zinc-100 text-xs font-semibold leading-none">OS Wallet</div>
            <div className="text-zinc-500 text-[10px] leading-none mt-1">
              {walletData.walletAddress ? `Polygon · ${walletData.walletAddress.slice(0,6)}…${walletData.walletAddress.slice(-4)}` : 'No wallet'}
            </div>
          </div>
        </div>
        <Settings size={18} className="text-zinc-500 cursor-pointer" />
      </div>

      <div className="px-5 pt-6 pb-2">
        <div className="flex items-center gap-2 text-zinc-500 text-xs mb-2">
          <span>Total balance</span>
          <button onClick={() => setShowBalance(!showBalance)} className="text-zinc-600 hover:text-zinc-400">
            {showBalance ? "hide" : "show"}
          </button>
        </div>
        <div className="font-mono text-4xl text-zinc-50 font-medium tracking-tight">
          {showBalance ? fmtUsd(totalUsd) : "••••••"}
        </div>
        <div className="flex items-center gap-1 mt-2 text-emerald-400 text-xs font-medium">
          <TrendingUp size={12} />
          <span>+{/* 24h change */}0.0% today</span>
        </div>
      </div>

      <div className="grid grid-cols-4 gap-3 px-5 py-6">
        <ActionButton icon={Send} label="Send" onClick={() => setTab("send")} />
        <ActionButton icon={ArrowDownLeft} label="Receive" onClick={() => setTab("receive")} />
        <ActionButton icon={Repeat} label="Swap" />
        <ActionButton icon={Wallet} label="Buy" />
      </div>

      {/* Burn ticker */}
      <div className="mx-5 mb-5 rounded-xl border border-orange-900/40 bg-gradient-to-r from-orange-950/40 to-zinc-900 px-4 py-3 flex items-center gap-3">
        <div className="relative">
          <Flame size={18} className="text-orange-400" />
          <div className="absolute inset-0 animate-ping opacity-40">
            <Flame size={18} className="text-orange-400" />
          </div>
        </div>
        <div className="flex-1">
          <div className="text-zinc-300 text-xs font-medium">CLOSE staked (tier)</div>
          <div className="text-orange-300 font-mono text-sm">
            {fmtNum(closeStaked)} CLOSE · {stakeTier?.toUpperCase() || 'NONE'}
          </div>
        </div>
        <ChevronRight size={14} className="text-zinc-600" />
      </div>

      {/* Token list */}
      <div className="px-5">
        <div className="text-zinc-500 text-xs font-medium mb-3">Assets</div>
        <div className="space-y-1">
          {tokens.length === 0 ? (
            <p className="text-zinc-600 text-sm text-center py-4">No tokens found</p>
          ) : (
            tokens.map((t) => (
              <div key={t.symbol} className="flex items-center justify-between py-2.5 border-b border-zinc-900">
                <div className="flex items-center gap-3">
                  <div className="w-9 h-9 rounded-full bg-zinc-800 flex items-center justify-center text-[11px] font-bold text-zinc-300">
                    {t.symbol.slice(0, 2)}
                  </div>
                  <div>
                    <div className="text-zinc-100 text-sm font-medium">{t.symbol}</div>
                    <div className="text-zinc-500 text-xs">{fmtNum(t.balance)} {t.symbol}</div>
                  </div>
                </div>
                <div className="text-right">
                  <div className="text-zinc-100 text-sm font-mono">{fmtUsd(t.usd_value)}</div>
                  {t.usd_change_24h != null && (
                    <div className={`text-xs flex items-center justify-end gap-0.5 ${t.usd_change_24h > 0 ? "text-emerald-400" : t.usd_change_24h < 0 ? "text-rose-400" : "text-zinc-600"}`}>
                      {t.usd_change_24h > 0 ? <TrendingUp size={10} /> : <TrendingDown size={10} />}
                      {t.usd_change_24h > 0 ? "+" : ""}{t.usd_change_24h?.toFixed(1)}%
                    </div>
                  )}
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

function SendScreen({ sendStep, setSendStep, setTab, toast }) {
  const [amount, setAmount] = useState("50");
  const [recipient, setRecipient] = useState("");

  if (sendStep === "success") {
    return (
      <div className="px-5 pt-10 flex flex-col items-center text-center">
        <div className="w-16 h-16 rounded-full bg-emerald-950 border border-emerald-800 flex items-center justify-center mb-5">
          <Check size={28} className="text-emerald-400" />
        </div>
        <div className="text-zinc-100 text-lg font-semibold mb-1">Transaction sent</div>
        <div className="text-zinc-500 text-sm mb-6">{amount} USDT to {recipient?.slice(0, 8)}…</div>
        <div className="w-full bg-zinc-900 border border-zinc-800 rounded-xl p-4 mb-6">
          <div className="flex justify-between text-xs mb-2">
            <span className="text-zinc-500">Status</span>
            <span className="text-amber-400 font-medium">Pending confirmation</span>
          </div>
          <div className="flex justify-between text-xs">
            <span className="text-zinc-500">Transaction</span>
            <span className="text-zinc-300 font-mono flex items-center gap-1">0x77…e2c <ExternalLink size={10} /></span>
          </div>
        </div>
        <button onClick={() => { setSendStep("form"); setTab("home"); }} className="w-full bg-zinc-100 text-zinc-950 font-semibold text-sm py-3 rounded-xl">
          Done
        </button>
      </div>
    );
  }

  if (sendStep === "review") {
    return (
      <div>
        <ScreenHeader title="Review send" onBack={() => setSendStep("form")} />
        <div className="px-5 pt-4">
          <div className="text-center mb-6">
            <div className="font-mono text-3xl text-zinc-50">{amount || "0"} USDT</div>
            <div className="text-zinc-500 text-sm mt-1">≈ {fmtUsd(Number(amount || 0))}</div>
          </div>
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl divide-y divide-zinc-800">
            <Row label="To" value={recipient || "0x9b1f...c02e"} mono />
            <Row label="Network" value="Polygon" />
            <Row label="Network fee" value="~0.004 POL ($0.002)" />
            <Row label="Total" value={`${amount || 0} USDT + fee`} />
          </div>
          <div className="mt-4 flex items-start gap-2 bg-zinc-900/60 border border-zinc-800 rounded-lg p-3">
            <ShieldAlert size={14} className="text-amber-400 mt-0.5 shrink-0" />
            <span className="text-zinc-500 text-xs">Double-check the recipient address. Transactions can't be reversed.</span>
          </div>
        </div>
        <div className="px-5 mt-6">
          <button onClick={() => setSendStep("success")} className="w-full bg-orange-500 hover:bg-orange-400 text-zinc-950 font-semibold text-sm py-3 rounded-xl transition">
            Confirm & send
          </button>
        </div>
      </div>
    );
  }

  return (
    <div>
      <ScreenHeader title="Send" onBack={() => setTab("home")} />
      <div className="px-5 pt-2">
        <label className="text-zinc-500 text-xs font-medium">Recipient</label>
        <div className="mt-2 flex items-center gap-2 bg-zinc-900 border border-zinc-800 rounded-xl px-4 py-3">
          <input value={recipient} onChange={(e) => setRecipient(e.target.value)} placeholder="Address or ENS" className="bg-transparent flex-1 text-zinc-100 text-sm outline-none placeholder:text-zinc-600" />
          <QrCode size={16} className="text-zinc-500" />
        </div>
        <label className="text-zinc-500 text-xs font-medium mt-5 block">Asset</label>
        <button className="mt-2 w-full flex items-center justify-between bg-zinc-900 border border-zinc-800 rounded-xl px-4 py-3">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded-full bg-zinc-800 flex items-center justify-center text-[9px] font-bold text-zinc-300">US</div>
            <span className="text-zinc-100 text-sm">USDT</span>
            <span className="text-zinc-600 text-xs">340.0 available</span>
          </div>
          <ChevronDown size={14} className="text-zinc-500" />
        </button>
        <label className="text-zinc-500 text-xs font-medium mt-5 block">Amount</label>
        <div className="mt-2 flex items-center gap-2 bg-zinc-900 border border-zinc-800 rounded-xl px-4 py-3">
          <input value={amount} onChange={(e) => setAmount(e.target.value)} className="bg-transparent flex-1 text-zinc-100 font-mono text-lg outline-none" />
          <button onClick={() => setAmount("340")} className="text-orange-400 text-xs font-semibold bg-orange-950/50 px-2 py-1 rounded-md">MAX</button>
        </div>
        <div className="text-zinc-600 text-xs mt-1.5">≈ {fmtUsd(Number(amount || 0))}</div>
        <div className="mt-6 flex items-center justify-between text-xs px-1">
          <span className="text-zinc-500">Estimated network fee</span>
          <span className="text-zinc-300">~0.004 POL</span>
        </div>
      </div>
      <div className="px-5 mt-8">
        <button onClick={() => setSendStep("review")} disabled={!amount} className="w-full bg-zinc-100 disabled:opacity-40 text-zinc-950 font-semibold text-sm py-3 rounded-xl">
          Review
        </button>
      </div>
    </div>
  );
}

function ReceiveScreen({ setTab }) {
  const { walletAddress } = useWallet();
  const address = walletAddress || "0x3c6833cFDdED80fE76474a3Cb2Cc050Daec91fe8";
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(address);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div>
      <ScreenHeader title="Receive" onBack={() => setTab("home")} />
      <div className="px-5 pt-4 flex flex-col items-center">
        <div className="w-48 h-48 bg-zinc-100 rounded-2xl flex items-center justify-center mb-6">
          <QrCode size={140} className="text-zinc-950" strokeWidth={1} />
        </div>
        <div className="text-zinc-500 text-xs mb-2">Your Polygon address</div>
        <div className="w-full bg-zinc-900 border border-zinc-800 rounded-xl px-4 py-3 flex items-center justify-between mb-3">
          <span className="text-zinc-200 font-mono text-xs truncate mr-2">{address}</span>
          <button onClick={handleCopy} className="text-zinc-400 shrink-0">
            {copied ? <Check size={16} className="text-emerald-400" /> : <Copy size={16} />}
          </button>
        </div>
        <div className="w-full flex items-start gap-2 bg-amber-950/20 border border-amber-900/40 rounded-lg p-3">
          <ShieldAlert size={14} className="text-amber-400 mt-0.5 shrink-0" />
          <span className="text-amber-200/80 text-xs">Only send Polygon network assets to this address.</span>
        </div>
      </div>
    </div>
  );
}

function ActivityScreen() {
  const { txs } = useWallet();
  const transactions = txs || [];

  const iconFor = (type) => {
    if (type === "burn") return <Flame size={14} className="text-orange-400" />;
    if (type === "receive") return <ArrowDownLeft size={14} className="text-emerald-400" />;
    if (type === "send") return <Send size={14} className="text-zinc-400" />;
    if (type === "stake") return <Repeat size={14} className="text-violet-400" />;
    return null;
  };
  const bgFor = (type) => {
    if (type === "burn") return "bg-orange-950/60";
    if (type === "receive") return "bg-emerald-950/60";
    if (type === "stake") return "bg-violet-950/60";
    return "bg-zinc-800";
  };

  return (
    <div>
      <ScreenHeader title="Activity" />
      <div className="px-5 pt-2 space-y-1">
        {transactions.length === 0 ? (
          <p className="text-zinc-600 text-sm text-center py-8">No transactions yet</p>
        ) : (
          transactions.map((tx, i) => (
            <div key={i} className="flex items-center justify-between py-3 border-b border-zinc-900">
              <div className="flex items-center gap-3">
                <div className={`w-8 h-8 rounded-full flex items-center justify-center ${bgFor(tx.type)}`}>
                  {iconFor(tx.type)}
                </div>
                <div>
                  <div className="text-zinc-100 text-sm font-medium capitalize">{tx.type}</div>
                  <div className="text-zinc-500 text-xs">{tx.counterparty || tx.description || ''}</div>
                </div>
              </div>
              <div className="text-right">
                <div className={`text-sm font-mono ${tx.type === "receive" ? "text-emerald-400" : "text-zinc-200"}`}>
                  {tx.type === "receive" ? "+" : "-"}{fmtNum(tx.amount)} {tx.token_symbol || 'CLOSE'}
                </div>
                <div className="text-xs text-zinc-600">
                  {tx.time || tx.created_at ? new Date(tx.created || tx.created_at).toLocaleDateString() : ''}
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

// ---- Main WalletPage Export ----
export default function WalletPage({ toast, onOpenModal }) {
  const { user } = useAuth();
  const {
    closeBalance, closeStaked, stakeTier, walletAddress,
    portfolio, refreshBalance, refreshPortfolio, refreshTxs,
  } = useWallet();
  const [tab, setTab] = useState("home");
  const [sendStep, setSendStep] = useState("form");
  const [showBalance, setShowBalance] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Fetch fresh wallet data when the component mounts
  useEffect(() => {
    if (!user) return;
    const fetchData = async () => {
      setLoading(true);
      setError(null);
      try {
        await Promise.all([refreshBalance(), refreshPortfolio(), refreshTxs()]);
      } catch (err) {
        setError(err.message || "Failed to load wallet data");
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [user, refreshBalance, refreshPortfolio, refreshTxs]);

  const walletData = {
    closeBalance,
    closeStaked,
    stakeTier,
    walletAddress,
    portfolio,
    CLOSE_PRICE: 0.00009776, // or from env
  };

  return (
    <div className="min-h-screen bg-zinc-950 flex items-center justify-center p-6 font-sans">
      <div className="w-full max-w-sm bg-zinc-950 border border-zinc-800 rounded-[2.5rem] overflow-hidden shadow-2xl">
        <div className="h-8 bg-zinc-950" />
        <div className="h-[680px] overflow-y-auto pb-24 relative">
          {loading ? (
            <div className="flex items-center justify-center h-full">
              <Loader2 size={24} className="animate-spin text-zinc-500" />
            </div>
          ) : error ? (
            <div className="flex flex-col items-center justify-center h-full px-5">
              <ShieldAlert size={32} className="text-rose-400 mb-3" />
              <p className="text-rose-400 text-sm text-center">{error}</p>
              <button
                onClick={() => {
                  setError(null);
                  Promise.all([refreshBalance(), refreshPortfolio(), refreshTxs()]);
                }}
                className="mt-4 text-orange-400 text-xs underline"
              >
                Retry
              </button>
            </div>
          ) : (
            <>
              {tab === "home" && (
                <HomeScreen
                  showBalance={showBalance}
                  setShowBalance={setShowBalance}
                  setTab={setTab}
                  walletData={walletData}
                />
              )}
              {tab === "send" && (
                <SendScreen
                  sendStep={sendStep}
                  setSendStep={setSendStep}
                  setTab={setTab}
                  toast={toast}
                />
              )}
              {tab === "receive" && (
                <ReceiveScreen setTab={setTab} />
              )}
              {tab === "activity" && <ActivityScreen />}
            </>
          )}
        </div>

        {/* Bottom tab bar */}
        {!loading && !error && (
          <div className="absolute bottom-0 left-0 right-0 max-w-sm mx-auto bg-zinc-950/95 backdrop-blur border-t border-zinc-800 px-6 py-3 flex justify-between">
            <TabButton icon={Wallet} label="Home" active={tab === "home"} onClick={() => setTab("home")} />
            <TabButton icon={Send} label="Send" active={tab === "send"} onClick={() => { setSendStep("form"); setTab("send"); }} />
            <TabButton icon={ArrowDownLeft} label="Receive" active={tab === "receive"} onClick={() => setTab("receive")} />
            <TabButton icon={Clock} label="Activity" active={tab === "activity"} onClick={() => setTab("activity")} />
          </div>
        )}
      </div>
    </div>
  );
}