import React, { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { useWallet } from '../context/WalletContext';
import { useTheme } from '../context/ThemeContext';
import {
  MessageSquarePlus, Wallet, Briefcase, Building2, Trophy,
  Code2, LayoutDashboard, ChevronDown, Sun, Moon, Monitor
} from 'lucide-react';

export default function Sidebar({ open, onClose, onOpenModal, onNewChat }) {
  const { user, isGuest } = useAuth();
  const { closeBalance, stakeTier } = useWallet();
  const { theme, setTheme } = useTheme();
  const [appearanceOpen, setAppearanceOpen] = useState(false);
  const [founderClicks, setFounderClicks] = useState(0);
  const location = useLocation();

  const handleFounderClick = () => {
    setFounderClicks(prev => {
      const next = prev + 1;
      if (next >= 13) {
        onOpenModal('founder');
        return 0;
      }
      setTimeout(() => setFounderClicks(0), 3000);
      return next;
    });
  };

  const navItems = [
    { to: '/wallet', icon: Wallet, label: 'OS Wallets', show: true },
    { to: '/portfolio', icon: Briefcase, label: 'Portfolio', show: !!user },
    { to: '/workspaces', icon: Building2, label: 'Work Areas', show: !!user },
    { to: '/leaderboard', icon: Trophy, label: 'Leaderboard', show: !!user },
    { to: '/developer', icon: Code2, label: 'Developer', show: !!user && ['pro', 'enterprise', 'founder'].includes(stakeTier) },
    { to: '/dashboard', icon: LayoutDashboard, label: 'Dashboard', show: !!user && stakeTier === 'founder' },
  ];

  return (
    <aside
      className={`
        fixed lg:relative z-40 w-[280px] h-full
        bg-[var(--sidebar-bg)] border-r border-[var(--border)]
        flex flex-col overflow-y-auto backdrop-blur-xl
        transition-transform duration-300 ease-in-out
        ${open ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}
      `}
    >
      {/* Brand */}
      <div className="p-5 flex items-center gap-3">
        <svg
          className="w-8 h-8 cursor-pointer"
          viewBox="0 0 40 40"
          onClick={handleFounderClick}
        >
          <circle cx="20" cy="20" r="18" fill="none" stroke="#00b4d8" strokeWidth="2" />
          <circle cx="20" cy="20" r="13" fill="none" stroke="#90e0ef" strokeWidth="1" strokeDasharray="6 4" />
          <text x="20" y="26" textAnchor="middle" fontFamily="Inter,sans-serif" fontSize="18" fill="#00b4d8" fontWeight="700">C</text>
        </svg>
        <span className="font-extrabold text-lg tracking-wider bg-gradient-to-r from-[#00b4d8] to-[#90e0ef] bg-clip-text text-transparent bg-[length:200%_200%] animate-logo-shift">
          CAPITAN AI
        </span>
      </div>

      {/* New Chat */}
      <button
        onClick={() => { onNewChat(); onClose(); }}
        className="mx-3 mt-2 flex items-center justify-center gap-2 px-4 py-2.5 bg-[var(--accent)] text-white rounded-xl font-semibold text-sm hover:bg-[var(--accent-dark)] transition"
      >
        <MessageSquarePlus size={14} />
        New chat
      </button>

      {/* Navigation */}
      <nav className="mt-4 flex-1">
        {navItems.filter(i => i.show).map(item => (
          <Link
            key={item.to}
            to={item.to}
            onClick={onClose}
            className={`
              flex items-center gap-3 px-4 py-2.5 mx-3 my-0.5 rounded-xl text-sm font-medium
              transition-all duration-200
              ${location.pathname === item.to
                ? 'bg-[var(--accent-glow)] text-[var(--accent)]'
                : 'text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--accent)] hover:translate-x-1'
              }
            `}
          >
            <item.icon size={16} />
            {item.label}
          </Link>
        ))}
      </nav>

      {/* Guest CTA */}
      {isGuest && (
        <div className="mx-3 my-2">
          <button
            onClick={() => { onOpenModal('signup'); onClose(); }}
            className="w-full py-2 px-3 border-2 border-[var(--accent)] text-[var(--accent)] rounded-2xl text-xs font-semibold hover:bg-[var(--accent-glow)] transition"
          >
            Sign up for 2,000 CLOSE
          </button>
        </div>
      )}

      {/* Appearance */}
      <div className="mx-3 border-t border-[var(--border)] pt-2">
        <button
          onClick={() => setAppearanceOpen(!appearanceOpen)}
          className="flex items-center justify-between w-full px-4 py-2.5 text-xs font-medium text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)] rounded-xl"
        >
          Appearance
          <ChevronDown size={12} className={`transition-transform ${appearanceOpen ? 'rotate-180' : ''}`} />
        </button>
        {appearanceOpen && (
          <div className="ml-6 space-y-1">
            {[
              { val: 'light', icon: Sun, label: 'Light' },
              { val: 'dark', icon: Moon, label: 'Dark' },
              { val: 'system', icon: Monitor, label: 'System' },
            ].map(({ val, icon: Icon, label }) => (
              <button
                key={val}
                onClick={() => setTheme(val)}
                className={`flex items-center gap-2 w-full px-4 py-2 text-xs rounded-lg ${
                  theme === val ? 'text-[var(--accent)] bg-[var(--accent-glow)]' : 'text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)]'
                }`}
              >
                <Icon size={14} /> {label}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Profile */}
      <div
        className="flex items-center justify-between p-4 border-t border-[var(--border)] cursor-pointer hover:bg-[var(--bg-tertiary)] transition"
        onClick={() => { onOpenModal('profile'); onClose(); }}
      >
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-full bg-[var(--accent-glow)] border-2 border-[var(--accent)] flex items-center justify-center">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="#90e0ef">
              <circle cx="12" cy="8" r="4" />
              <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
            </svg>
          </div>
          <div>
            <div className="font-semibold text-sm">{user?.name || user?.email?.split('@')[0] || 'Guest'}</div>
            <div className="text-xs text-[var(--text-tertiary)]">
              {user ? `${closeBalance.toLocaleString()} CLOSE` : 'Sign up for 2,000 CLOSE'}
            </div>
          </div>
        </div>
      </div>

      <div className="p-2.5 text-center text-[9px] text-[var(--text-tertiary)] border-t border-[var(--border)]">
        CLOSEAI Technologies
      </div>
    </aside>
  );
}