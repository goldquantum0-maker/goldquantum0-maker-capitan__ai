import React, { useState, useEffect, lazy, Suspense } from 'react';
import { Routes, Route } from 'react-router-dom';
import Sidebar from './components/Sidebar';
import TopBar from './components/TopBar';
import ChatView from './components/ChatView';
import { useAuth } from './context/AuthContext';
import { useWallet } from './context/WalletContext';
import { useChat } from './context/ChatContext';

const WalletPage = lazy(() => import('./pages/WalletPage'));
const PortfolioPage = lazy(() => import('./pages/PortfolioPage'));
const WorkspacePage = lazy(() => import('./pages/WorkspacePage'));
const LeaderboardPage = lazy(() => import('./pages/LeaderboardPage'));
const DeveloperPage = lazy(() => import('./pages/DeveloperPage'));
const FounderDashboard = lazy(() => import('./pages/FounderDashboard'));

import SignupModal from './components/modals/SignupModal';
import LoginModal from './components/modals/LoginModal';
import BuyCloseModal from './components/modals/BuyCloseModal';
import StakeModal from './components/modals/StakeModal';
import SwapModal from './components/modals/SwapModal';
import SendModal from './components/modals/SendModal';
import ReceiveModal from './components/modals/ReceiveModal';
import ProfileModal from './components/modals/ProfileModal';
import FounderLoginModal from './components/modals/FounderLoginModal';
import PasswordModal from './components/modals/PasswordModal';
import NotifPanel from './components/NotifPanel';
import Toast from './components/Toast';

export default function App() {
  const [splashDone, setSplashDone] = useState(true);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [notifOpen, setNotifOpen] = useState(false);
  const [activeModal, setActiveModal] = useState(null);
  const [toastMsg, setToastMsg] = useState('');

  const { loading: authLoading } = useAuth();
  const { refreshBalance, refreshPortfolio, refreshTxs } = useWallet();
  const { newChat } = useChat();

    useEffect(() => {
    if (!authLoading) {
      refreshBalance();
      refreshPortfolio();
      refreshTxs();
    }
  }, [authLoading, refreshBalance, refreshPortfolio, refreshTxs]);

  const toast = (msg) => {
    setToastMsg(msg);
    setTimeout(() => setToastMsg(''), 2500);
  };

  const openModal = (name) => setActiveModal(name);
  const closeModal = () => setActiveModal(null);


  return (
    <div className="app flex h-screen w-screen overflow-hidden bg-[var(--bg-primary)] text-[var(--text-primary)] font-sans transition-colors duration-200">
      <Sidebar
        open={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        onOpenModal={openModal}
        onNewChat={newChat}
      />

      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-black/60 backdrop-blur-sm z-35 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      <TopBar
        onToggleSidebar={() => setSidebarOpen(!sidebarOpen)}
        onNotifClick={() => setNotifOpen(!notifOpen)}
      />

      <main className="flex-1 flex flex-col overflow-hidden ml-0">
        <Suspense fallback={
          <div className="flex items-center justify-center h-full">
            <div className="w-5 h-5 border-2 border-[var(--glass-border)] border-t-[var(--accent)] rounded-full animate-spin" />
          </div>
        }>
          <Routes>
            <Route path="/" element={<ChatView onOpenModal={openModal} toast={toast} />} />
            <Route path="/wallet" element={<WalletPage toast={toast} onOpenModal={openModal} />} />
            <Route path="/portfolio" element={<PortfolioPage toast={toast} />} />
            <Route path="/workspaces" element={<WorkspacePage toast={toast} />} />
            <Route path="/leaderboard" element={<LeaderboardPage />} />
            <Route path="/developer" element={<DeveloperPage toast={toast} />} />
            <Route path="/dashboard" element={<FounderDashboard toast={toast} />} />
          </Routes>
        </Suspense>
      </main>

      {activeModal === 'signup' && <SignupModal onClose={closeModal} toast={toast} />}
      {activeModal === 'login' && <LoginModal onClose={closeModal} toast={toast} />}
      {activeModal === 'buy' && <BuyCloseModal onClose={closeModal} toast={toast} />}
      {activeModal === 'stake' && <StakeModal onClose={closeModal} toast={toast} />}
      {activeModal === 'swap' && <SwapModal onClose={closeModal} toast={toast} />}
      {activeModal === 'send' && <SendModal onClose={closeModal} toast={toast} />}
      {activeModal === 'receive' && <ReceiveModal onClose={closeModal} />}
      {activeModal === 'profile' && <ProfileModal onClose={closeModal} toast={toast} />}
      {activeModal === 'founder' && <FounderLoginModal onClose={closeModal} toast={toast} />}
      {activeModal === 'password' && <PasswordModal onClose={closeModal} toast={toast} />}

      <NotifPanel open={notifOpen} onClose={() => setNotifOpen(false)} />

      {toastMsg && <Toast message={toastMsg} />}
    </div>
  );
}