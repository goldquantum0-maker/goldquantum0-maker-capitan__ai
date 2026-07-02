import React from 'react';
import { Menu, Bell } from 'lucide-react';

export default function TopBar({ onToggleSidebar, onNotifClick }) {
  return (
    <div className="fixed top-3 right-3 z-45 flex items-center gap-3">
      <button
        onClick={onNotifClick}
        className="relative w-[38px] h-[38px] rounded-[40px] bg-[var(--glass-bg)] border border-[var(--glass-border)] flex items-center justify-center text-[var(--text-secondary)] backdrop-blur-xl"
        aria-label="Notifications"
      >
        <Bell size={17} />
        <span
          className="absolute -top-0.5 -right-0.5 bg-red-500 text-white text-[10px] font-bold w-[18px] h-[18px] rounded-full items-center justify-center hidden"
          id="notifBadge"
        >
          0
        </span>
      </button>
      <button
        onClick={onToggleSidebar}
        className="w-[38px] h-[38px] rounded-[40px] bg-[var(--glass-bg)] border border-[var(--glass-border)] flex items-center justify-center text-[var(--text-secondary)] backdrop-blur-xl"
        aria-label="Toggle sidebar"
      >
        <Menu size={17} />
      </button>
    </div>
  );
}